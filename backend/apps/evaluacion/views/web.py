import logging
import unicodedata
from collections import OrderedDict

from django.contrib import messages
from django.db import DatabaseError, IntegrityError, OperationalError
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import RedirectView, TemplateView

from apps.acreditacion.models import ElementoFundamental, Indicador
from apps.core.mixins import SigLoginRequiredMixin
from apps.evaluacion.forms import (
    CerrarTareaEvidenciaForm,
    EvaluacionGestionForm,
    ObservacionGestionForm,
    TareaEvidenciaBulkForm,
    TareaEvidenciaForm,
)
from apps.evaluacion.selectors import (
    get_estado_tarea_options,
    get_evaluation_inbox_data,
    get_evaluacion_detail,
    get_evaluaciones_queryset,
    get_evidencia_dashboard_metrics,
    get_observaciones_queryset,
    get_registro_detail,
    get_registros_queryset,
    get_tarea_evidencia_detail,
    get_tarea_evidencia_metrics,
    get_tareas_evidencia_queryset,
)
from apps.evaluacion.services import (
    EvaluacionWorkflowError,
    TareaEvidenciaWorkflowError,
    cerrar_tarea_evidencia,
    habilitar_salida_evaluador,
    registrar_evaluacion,
    registrar_observacion,
    registrar_tarea_evidencia,
    registrar_tareas_evidencia_lote,
    resolver_observacion,
)
from apps.evaluacion.models import ObservacionEvaluacion
from apps.usuarios.models import AreaInstitucional, Usuario, UsuarioAreaCargo
from apps.usuarios.selectors import get_usuario_area_cargo_for_context


logger = logging.getLogger(__name__)


def _normalize_token(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", (value or "").strip())
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.upper().split())


QUALITY_ROLE_TOKENS = {
    "CALIDAD ACADEMICA",
    "DIRECTOR DE CALIDAD",
    "DIRECCION DE CALIDAD",
    "CALIDAD",
}
ADMIN_ROLE_TOKEN = "ADMINISTRADOR"

MODULE_TITLE = "Evaluacion"
MODULE_DESCRIPTION = "Gestiona evidencias registradas, evaluaciones y observaciones del flujo operativo."
MODULE_TABS = [
    {
        "label": "Registro de evidencia",
        "url_name": "evaluacion-evidencia-registrar",
        "active_names": ("evaluacion-evidencia-registrar",),
    },
    {
        "label": "Lista de evidencias",
        "url_name": "evaluacion-evidencias-lista",
        "active_names": ("evaluacion-evidencias-lista", "evaluacion-evidencia-detalle"),
    },
    {
        "label": "Tareas de evidencia",
        "url_name": "evaluacion-tareas",
        "active_names": ("evaluacion-tareas",),
    },
    {
        "label": "Bandeja de evaluacion",
        "url_name": "evaluacion-bandeja",
        "active_names": ("evaluacion-bandeja",),
    },
    {
        "label": "Evaluar evidencia",
        "url_name": "evaluacion-evaluar",
        "active_names": ("evaluacion-evaluar",),
    },
    {
        "label": "Observaciones",
        "url_name": "evaluacion-observaciones",
        "active_names": ("evaluacion-observaciones",),
    },
]


def _report_operation_error(*, request, exc: Exception, user_message: str, form=None):
    logger.exception("Operacion de evaluacion fallida", exc_info=exc)
    messages.error(request, user_message)
    if form is not None:
        form.add_error(None, user_message)


def _build_bulk_structure_groups():
    indicators = (
        Indicador.objects.filter(activo=True)
        .select_related("subcriterio__criterio")
        .prefetch_related(
            Prefetch(
                "elementos",
                queryset=ElementoFundamental.objects.filter(activo=True).order_by(
                    "orden_visual",
                    "codigo_elemento",
                ),
                to_attr="bulk_elementos",
            )
        )
        .order_by(
            "subcriterio__criterio__codigo_criterio",
            "subcriterio__codigo_subcriterio",
            "codigo_indicador",
        )
    )

    criteria_map = OrderedDict()
    indicators_total = 0
    elements_total = 0

    for indicador in indicators:
        elementos = list(getattr(indicador, "bulk_elementos", []))
        criterio = indicador.subcriterio.criterio
        subcriterio = indicador.subcriterio
        criterion_node = criteria_map.setdefault(
            criterio.pk,
            {
                "criterio": criterio,
                "indicators_total": 0,
                "elements_total": 0,
                "_subcriterios": OrderedDict(),
            },
        )
        subcriterion_node = criterion_node["_subcriterios"].setdefault(
            subcriterio.pk,
            {
                "subcriterio": subcriterio,
                "indicators_total": 0,
                "elements_total": 0,
                "indicator_groups": [],
            },
        )

        criterion_node["indicators_total"] += 1
        criterion_node["elements_total"] += len(elementos)
        subcriterion_node["indicators_total"] += 1
        subcriterion_node["elements_total"] += len(elementos)
        subcriterion_node["indicator_groups"].append(
            {
                "indicador": indicador,
                "elementos": elementos,
            }
        )
        indicators_total += 1
        elements_total += len(elementos)

    criteria_groups = []
    for criterion_node in criteria_map.values():
        criterion_node["subcriterios"] = list(criterion_node["_subcriterios"].values())
        del criterion_node["_subcriterios"]
        criteria_groups.append(criterion_node)

    return {
        "criteria_groups": criteria_groups,
        "summary": {
            "indicators_total": indicators_total,
            "elements_total": elements_total,
        },
    }


class EvaluacionBaseView(SigLoginRequiredMixin, TemplateView):
    template_name = ""
    page_title = ""
    page_description = ""
    page_status = "Operacion real"
    page_actions = []

    def _actor(self):
        user_id = self.request.session.get("sig_user_id")
        if not user_id:
            return None
        return Usuario.objects.filter(pk=user_id).only(
            "id_user",
            "primer_nombre",
            "primer_apellido",
            "correo",
        ).first()

    def _actor_assignment(self):
        user_id = self.request.session.get("sig_user_id")
        if not user_id:
            return None
        return get_usuario_area_cargo_for_context(
            usuario=user_id,
            assignment_id=self.request.session.get("sig_active_assignment_id"),
        )

    def _actor_scope_flags(self):
        assignment = self._actor_assignment()
        role_tokens = tuple(
            _normalize_token(role)
            for role in (self.request.session.get("sig_roles", []) or [])
        )
        cargo_name = _normalize_token(getattr(getattr(assignment, "cargo", None), "nombre_cargo", ""))
        cargo_level = getattr(getattr(assignment, "cargo", None), "nivel_jerarquico", None)
        cargo_approves = bool(getattr(getattr(assignment, "cargo", None), "aprueba_interno", False))

        is_level_one_approver = bool(cargo_approves and cargo_level == 1)
        is_tech_director = cargo_name == "DIRECTOR DE TECNOLOGIA"
        is_evaluator = any("EVALUADOR" in token for token in role_tokens)
        is_admin = any(token == ADMIN_ROLE_TOKEN for token in role_tokens)
        is_quality = any(token in QUALITY_ROLE_TOKENS for token in role_tokens)

        return {
            "is_admin": is_admin,
            "is_level_one_approver": is_level_one_approver,
            "is_tech_director": is_tech_director,
            "is_evaluator": is_evaluator,
            "is_quality": is_quality,
            "can_assign_tasks": is_admin or is_quality,
            "can_manage_release": is_level_one_approver or is_tech_director,
        }

    def _registro_released(self, registro) -> bool:
        return bool(getattr(registro, "fecha_envio_revision", None))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "module_title": MODULE_TITLE,
                "module_description": MODULE_DESCRIPTION,
                "module_tabs": MODULE_TABS,
                "page_title": self.page_title,
                "page_description": self.page_description,
                "page_status": self.page_status,
                "page_actions": self.page_actions,
                "current_url_name": self.request.resolver_match.url_name if self.request.resolver_match else "",
                "evaluation_metrics": get_evidencia_dashboard_metrics(),
            }
        )
        context.update(kwargs)
        return context


class EvidenciaRegistroRedirectView(RedirectView):
    pattern_name = "acreditacion-matriz-registro"
    permanent = False


class EvidenciaListView(EvaluacionBaseView):
    template_name = "evaluacion/evidencia_list.html"
    page_title = "Lista de evidencias"
    page_description = "Consulta registros documentales, su estado de evidencia y la trazabilidad de evaluacion."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_flags = self._actor_scope_flags()
        q = self.request.GET.get("q", "")
        estado = self.request.GET.get("estado", "")
        ciclo = self.request.GET.get("ciclo")
        registros = get_registros_queryset(
            q=q,
            estado=estado,
            ciclo_id=ciclo,
            only_released=scope_flags["is_evaluator"],
        )[:100]
        context["registros"] = registros
        context["scope_flags"] = scope_flags
        context["selected_filters"] = {
            "q": q,
            "estado": estado,
            "ciclo": ciclo or "",
        }
        return context


class TareaEvidenciaListView(EvaluacionBaseView):
    template_name = "evaluacion/tarea_evidencia_list.html"
    page_title = "Tareas de evidencia"
    page_description = "Delega y cierra responsables de carga por ciclo, indicador y elemento."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_flags = self._actor_scope_flags()
        q = self.request.GET.get("q", "")
        estado = self.request.GET.get("estado", "")
        ciclo = self.request.GET.get("ciclo", "")
        area = self.request.GET.get("area", "")
        responsable = self.request.GET.get("responsable", "")
        actor = self._actor()
        can_assign_tasks = scope_flags["can_assign_tasks"]
        effective_responsable = responsable if can_assign_tasks else getattr(actor, "pk", -1)
        if can_assign_tasks:
            context["form"] = kwargs.get("form") or TareaEvidenciaForm()
            context["bulk_form"] = kwargs.get("bulk_form") or TareaEvidenciaBulkForm()
            bulk_structure = _build_bulk_structure_groups()
            context["bulk_criteria_groups"] = bulk_structure["criteria_groups"]
            context["bulk_structure_summary"] = bulk_structure["summary"]
            context["bulk_selected_element_ids"] = self._get_bulk_selected_element_ids(context["bulk_form"])
            context["task_responsable_choices"] = self._serialize_responsable_choices(context["form"])
            context["bulk_responsable_choices"] = self._serialize_responsable_choices(context["bulk_form"])
        else:
            context["form"] = None
            context["bulk_form"] = None
            context["bulk_criteria_groups"] = []
            context["bulk_structure_summary"] = {"indicators_total": 0, "elements_total": 0}
            context["bulk_selected_element_ids"] = set()
            context["task_responsable_choices"] = []
            context["bulk_responsable_choices"] = []
        context["close_form"] = kwargs.get("close_form") or CerrarTareaEvidenciaForm()
        context["tareas"] = get_tareas_evidencia_queryset(
            q=q,
            estado_id=estado,
            ciclo_id=ciclo,
            responsable_id=effective_responsable,
            area_id=area,
        )[:100]
        context["scope_flags"] = scope_flags
        context["current_actor_id"] = getattr(actor, "pk", None)
        context["area_options"] = AreaInstitucional.objects.filter(activo=True).order_by("nombre_area")
        context["tarea_metrics"] = get_tarea_evidencia_metrics(
            responsable_id=None if can_assign_tasks else getattr(actor, "pk", -1)
        )
        context["estado_tarea_options"] = get_estado_tarea_options()
        context["selected_filters"] = {
            "q": q,
            "estado": estado,
            "ciclo": ciclo,
            "area": area,
            "responsable": responsable,
        }
        return context

    @staticmethod
    def _selected_form_value(form, field_name: str):
        if not form:
            return None
        if form.is_bound:
            return (form.data.get(form.add_prefix(field_name)) or "").strip()
        initial_value = form.initial.get(field_name)
        return str(getattr(initial_value, "pk", initial_value or "")).strip()

    def _serialize_responsable_choices(self, form):
        if not form:
            return []

        field = form.fields.get("usuario_responsable")
        if field is None:
            return []

        responsibles = list(field.queryset)
        if not responsibles:
            return []

        user_ids = [usuario.pk for usuario in responsibles]
        assignments = (
            UsuarioAreaCargo.objects.select_related("area", "cargo")
            .filter(
                usuario_id__in=user_ids,
                activo=True,
                area__activo=True,
                cargo__activo=True,
            )
            .order_by("area__nombre_area", "cargo__nivel_jerarquico", "cargo__nombre_cargo")
        )
        area_map = {}
        for assignment in assignments:
            bucket = area_map.setdefault(assignment.usuario_id, [])
            area_id = str(assignment.area_id)
            if area_id not in bucket:
                bucket.append(area_id)

        selected_value = self._selected_form_value(form, "usuario_responsable")
        return [
            {
                "value": str(usuario.pk),
                "label": field.label_from_instance(usuario),
                "area_ids": area_map.get(usuario.pk, []),
                "selected": str(usuario.pk) == selected_value,
            }
            for usuario in responsibles
        ]

    @staticmethod
    def _get_bulk_selected_element_ids(form):
        if not getattr(form, "is_bound", False):
            return set()

        selected = set()
        for value in form.data.getlist("elementos_fundamentales"):
            try:
                selected.add(int(value))
            except (TypeError, ValueError):
                continue
        return selected

    def _handle_close(self, request):
        form = CerrarTareaEvidenciaForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(close_form=form))

        tarea = get_tarea_evidencia_detail(form.cleaned_data["tarea_id"])
        if tarea is None:
            messages.error(request, "La tarea seleccionada no existe.")
            return redirect("evaluacion-tareas")

        actor = self._actor()
        scope_flags = self._actor_scope_flags()
        if (
            not scope_flags.get("can_assign_tasks")
            and tarea.usuario_responsable_id != getattr(actor, "pk", None)
        ):
            messages.error(request, "Solo puedes cerrar tareas asignadas a tu usuario.")
            return redirect("evaluacion-tareas")

        try:
            cerrar_tarea_evidencia(
                tarea=tarea,
                resultado_tarea=form.cleaned_data["resultado_tarea"],
                actor=actor,
                request=request,
            )
        except (TareaEvidenciaWorkflowError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
            _report_operation_error(
                request=request,
                exc=exc,
                user_message="No fue posible cerrar la tarea de evidencia.",
            )
        else:
            messages.success(request, "Tarea de evidencia cerrada correctamente.")
        return redirect("evaluacion-tareas")

    def _handle_bulk_assign(self, request):
        scope_flags = self._actor_scope_flags()
        if not scope_flags.get("can_assign_tasks"):
            messages.error(
                request,
                "Solo Calidad puede realizar asignaciones parciales de indicadores y elementos.",
            )
            return redirect("evaluacion-tareas")

        form = TareaEvidenciaBulkForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(bulk_form=form))

        try:
            result = registrar_tareas_evidencia_lote(
                ciclo=form.cleaned_data["ciclo"],
                elementos_fundamentales=form.cleaned_data["elementos_fundamentales"],
                usuario_responsable=form.cleaned_data["usuario_responsable"],
                estado=form.cleaned_data["estado"],
                fecha_limite=form.cleaned_data.get("fecha_limite"),
                prioridad=form.cleaned_data.get("prioridad"),
                observacion=form.cleaned_data.get("observacion"),
                actor=self._actor(),
                request=request,
            )
        except (
            TareaEvidenciaWorkflowError,
            ValueError,
            IntegrityError,
            OperationalError,
            DatabaseError,
        ) as exc:
            _report_operation_error(
                request=request,
                exc=exc,
                form=form,
                user_message="No fue posible registrar la asignacion parcial de tareas.",
            )
            return self.render_to_response(self.get_context_data(bulk_form=form))

        messages.success(
            request,
            (
                "Asignacion parcial procesada correctamente: "
                f"{result['total']} elementos ({result['created']} nuevas, {result['updated']} actualizadas)."
            ),
        )
        return redirect("evaluacion-tareas")

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        if action == "close":
            return self._handle_close(request)
        if action == "bulk_assign":
            return self._handle_bulk_assign(request)

        scope_flags = self._actor_scope_flags()
        if not scope_flags.get("can_assign_tasks"):
            messages.error(request, "Solo Calidad puede asignar tareas de evidencia.")
            return redirect("evaluacion-tareas")

        form = TareaEvidenciaForm(request.POST)
        if form.is_valid():
            try:
                result = registrar_tarea_evidencia(
                    ciclo=form.cleaned_data["ciclo"],
                    indicador=form.cleaned_data["indicador"],
                    elemento_fundamental=form.cleaned_data["elemento_fundamental"],
                    usuario_responsable=form.cleaned_data["usuario_responsable"],
                    estado=form.cleaned_data["estado"],
                    fecha_limite=form.cleaned_data.get("fecha_limite"),
                    prioridad=form.cleaned_data.get("prioridad"),
                    observacion=form.cleaned_data.get("observacion"),
                    actor=self._actor(),
                    request=request,
                )
            except (
                TareaEvidenciaWorkflowError,
                ValueError,
                IntegrityError,
                OperationalError,
                DatabaseError,
            ) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible registrar la tarea de evidencia.",
                )
            else:
                messages.success(
                    request,
                    "Tarea de evidencia creada correctamente."
                    if result["created"]
                    else "Tarea de evidencia actualizada correctamente.",
                )
                return redirect("evaluacion-tareas")
        return self.render_to_response(self.get_context_data(form=form))


class EvidenciaDetailView(EvaluacionBaseView):
    template_name = "evaluacion/evidencia_detail.html"
    page_title = "Detalle de evidencia"
    page_description = "Consulta el documento, el estado del registro y el historial de evaluaciones relacionadas."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_flags = self._actor_scope_flags()
        registro = kwargs.get("registro") or get_registro_detail(self.request.GET.get("registro"))
        context["registro"] = registro
        context["release_controls"] = {
            "can_manage": scope_flags["can_manage_release"],
            "can_reassign": scope_flags["is_tech_director"],
            "is_released": self._registro_released(registro) if registro else False,
        }
        context["evaluaciones"] = (
            get_evaluaciones_queryset(registro_id=registro.pk)[:30] if registro else []
        )
        selected_evaluation = context["evaluaciones"][0] if context["evaluaciones"] else None
        selected_state = _normalize_token(getattr(getattr(selected_evaluation, "estado", None), "descripcion", ""))
        rejected_context = selected_state in {"RECHAZADA", "RECHAZADO", "OBSERVADA"}
        context["observaciones"] = (
            get_observaciones_queryset(evaluacion_id=selected_evaluation.pk)[:30]
            if selected_evaluation
            else []
        )
        context["selected_evaluation"] = selected_evaluation
        context["is_rejected_context"] = rejected_context
        context["can_manage_corrections"] = bool(scope_flags.get("is_quality") and rejected_context)
        return context

    def get(self, request, *args, **kwargs):
        registro = get_registro_detail(request.GET.get("registro"))
        if registro is None:
            raise Http404("La evidencia solicitada no existe.")
        scope_flags = self._actor_scope_flags()
        if scope_flags["is_evaluator"] and not self._registro_released(registro):
            messages.warning(
                request,
                "La evidencia todavia no ha sido habilitada para evaluacion por un cargo de nivel 1.",
            )
            return redirect("evaluacion-evidencias-lista")
        return self.render_to_response(self.get_context_data(registro=registro))

    @staticmethod
    def _detail_redirect(registro):
        return redirect(f"{reverse('evaluacion-evidencia-detalle')}?registro={registro.pk}")

    def _resolve_observacion_from_request(self, *, request, registro):
        observacion_id = request.POST.get("observacion_id")
        return (
            ObservacionEvaluacion.objects.select_related("evaluacion__estado", "evaluacion__registro")
            .filter(pk=observacion_id, evaluacion__registro_id=registro.pk)
            .first()
        )

    def _handle_resolver_observacion(self, *, request, registro, scope_flags):
        observacion = self._resolve_observacion_from_request(request=request, registro=registro)
        if observacion is None:
            messages.error(request, "La recomendacion seleccionada no existe para este registro.")
            return self._detail_redirect(registro)

        if not scope_flags.get("is_quality"):
            messages.error(request, "Solo Calidad puede gestionar correcciones en esta pantalla.")
            return self._detail_redirect(registro)

        estado_actual = _normalize_token(
            getattr(getattr(observacion.evaluacion, "estado", None), "descripcion", "")
        )
        if estado_actual not in {"RECHAZADA", "RECHAZADO", "OBSERVADA"}:
            messages.warning(request, "Solo se pueden resolver recomendaciones de evaluaciones rechazadas u observadas.")
            return self._detail_redirect(registro)

        try:
            resolver_observacion(
                observacion=observacion,
                solucion=request.POST.get("solucion"),
                marcar_atendida=bool(request.POST.get("marcar_atendida")),
                actor=self._actor(),
                request=request,
            )
        except (EvaluacionWorkflowError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
            _report_operation_error(
                request=request,
                exc=exc,
                user_message="No fue posible actualizar la correccion de la recomendacion.",
            )
        else:
            messages.success(request, "Correccion actualizada correctamente.")
        return self._detail_redirect(registro)

    def _handle_release(self, *, request, registro, scope_flags):
        if not scope_flags["can_manage_release"]:
            messages.error(request, "No tienes permisos para habilitar la salida al evaluador.")
            return self._detail_redirect(registro)

        if request.POST.get("habilitar_salida") != "1":
            messages.warning(request, "Debes marcar la casilla para habilitar la salida al evaluador.")
            return self._detail_redirect(registro)

        try:
            result = habilitar_salida_evaluador(
                registro=registro,
                actor=self._actor(),
                allow_reassign=scope_flags["is_tech_director"],
                request=request,
            )
        except (EvaluacionWorkflowError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
            _report_operation_error(
                request=request,
                exc=exc,
                user_message="No fue posible actualizar la salida hacia evaluacion.",
            )
        else:
            if result["status"] == "released":
                messages.success(request, "Salida al evaluador habilitada correctamente.")
            elif result["status"] == "reassigned":
                messages.success(request, "Salida al evaluador reasignada por Director de Tecnologia.")
            else:
                messages.info(request, "La evidencia ya se encontraba habilitada para evaluacion.")
        return self._detail_redirect(registro)

    def post(self, request, *args, **kwargs):
        registro = get_registro_detail(request.POST.get("registro"))
        if registro is None:
            raise Http404("La evidencia solicitada no existe.")

        scope_flags = self._actor_scope_flags()
        post_action = (request.POST.get("action") or "").strip().lower()

        if post_action == "resolver_observacion":
            return self._handle_resolver_observacion(
                request=request,
                registro=registro,
                scope_flags=scope_flags,
            )

        return self._handle_release(
            request=request,
            registro=registro,
            scope_flags=scope_flags,
        )


class EvaluacionInboxView(EvaluacionBaseView):
    template_name = "evaluacion/bandeja_evaluacion.html"
    page_title = "Bandeja de evaluacion"
    page_description = "Prioriza evidencias pendientes, observadas o en análisis para seguimiento operativo."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_flags = self._actor_scope_flags()
        selected_estado = self.request.GET.get("estado", "TODOS")
        inbox_data = get_evaluation_inbox_data(
            estado=selected_estado,
            only_released=scope_flags["is_evaluator"],
        )
        context["registros_pendientes"] = inbox_data["rows"]
        context["inbox_counts"] = inbox_data["counts"]
        context["selected_estado"] = inbox_data["selected_estado"]
        context["inbox_filter_options"] = inbox_data["filter_options"]
        context["evaluaciones_recientes"] = inbox_data["evaluaciones_recientes"]
        context["scope_flags"] = scope_flags
        return context


class EvaluacionFormView(EvaluacionBaseView):
    template_name = "evaluacion/evaluacion_form.html"
    page_title = "Evaluar evidencia"
    page_description = "Registra el resultado de la evaluacion formal y sincroniza el estado operativo de la evidencia."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_flags = self._actor_scope_flags()
        registro = kwargs.get("registro") or get_registro_detail(
            self.request.GET.get("registro") or self.request.POST.get("registro")
        )
        if scope_flags["is_evaluator"] and registro is not None and not self._registro_released(registro):
            registro = None
            messages.warning(
                self.request,
                "La evidencia no esta habilitada para evaluacion. Debe ser liberada por un cargo de nivel 1.",
            )
        context["registro"] = registro
        context["scope_flags"] = scope_flags
        context["form"] = kwargs.get("form") or EvaluacionGestionForm(
            registro_initial=registro
        )
        context["evaluaciones_recientes"] = (
            get_evaluaciones_queryset(registro_id=registro.pk)[:10] if registro else get_evaluaciones_queryset()[:10]
        )
        return context

    def post(self, request, *args, **kwargs):
        form = EvaluacionGestionForm(request.POST)
        scope_flags = self._actor_scope_flags()
        if form.is_valid():
            registro = form.cleaned_data["registro"]
            if scope_flags["is_evaluator"] and not self._registro_released(registro):
                form.add_error("registro", "La evidencia no esta habilitada para evaluacion.")
                return self.render_to_response(
                    self.get_context_data(
                        form=form,
                        registro=get_registro_detail(request.POST.get("registro")),
                    )
                )
            try:
                result = registrar_evaluacion(
                    registro=registro,
                    estado=form.cleaned_data["estado"],
                    calificacion=form.cleaned_data.get("calificacion"),
                    comentario=form.cleaned_data.get("comentario"),
                    actor=self._actor(),
                    request=request,
                )
            except (
                EvaluacionWorkflowError,
                ValueError,
                IntegrityError,
                OperationalError,
                DatabaseError,
            ) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible registrar la evaluacion de la evidencia.",
                )
            else:
                messages.success(
                    request,
                    "Evaluacion registrada correctamente."
                    if result["created"]
                    else "Evaluacion actualizada correctamente.",
                )
                return redirect(
                    f"{reverse('evaluacion-evidencia-detalle')}?registro={form.cleaned_data['registro'].pk}"
                )
        return self.render_to_response(
            self.get_context_data(
                form=form,
                registro=get_registro_detail(request.POST.get("registro")),
            )
        )


class ObservacionFormView(EvaluacionBaseView):
    template_name = "evaluacion/observacion_form.html"
    page_title = "Observaciones"
    page_description = "Registra observaciones asociadas a una evaluacion y deja trazabilidad para correcciones."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        evaluacion = kwargs.get("evaluacion") or get_evaluacion_detail(
            self.request.GET.get("evaluacion") or self.request.POST.get("evaluacion")
        )
        context["evaluacion"] = evaluacion
        context["form"] = kwargs.get("form") or ObservacionGestionForm(
            evaluacion_initial=evaluacion
        )
        context["observaciones"] = (
            get_observaciones_queryset(evaluacion_id=evaluacion.pk)[:20]
            if evaluacion
            else get_observaciones_queryset()[:20]
        )
        return context

    def post(self, request, *args, **kwargs):
        form = ObservacionGestionForm(request.POST)
        if form.is_valid():
            try:
                registrar_observacion(
                    evaluacion=form.cleaned_data["evaluacion"],
                    observacion=form.cleaned_data["observacion"],
                    actor=self._actor(),
                    request=request,
                )
            except (
                EvaluacionWorkflowError,
                ValueError,
                IntegrityError,
                OperationalError,
                DatabaseError,
            ) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible registrar la observacion.",
                )
            else:
                messages.success(request, "Observacion registrada correctamente.")
                return redirect(
                    f"{reverse('evaluacion-observaciones')}?evaluacion={form.cleaned_data['evaluacion'].pk}"
                )
        return self.render_to_response(
            self.get_context_data(
                form=form,
                evaluacion=get_evaluacion_detail(self.request.POST.get("evaluacion")),
            )
        )
