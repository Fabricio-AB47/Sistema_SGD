import logging
import unicodedata

from django.contrib import messages
from django.db import DatabaseError, IntegrityError, OperationalError
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import RedirectView, TemplateView

from apps.core.mixins import SigLoginRequiredMixin
from apps.evaluacion.forms import EvaluacionGestionForm, ObservacionGestionForm
from apps.evaluacion.selectors import (
    get_evaluation_inbox_data,
    get_evaluacion_detail,
    get_evaluaciones_queryset,
    get_evidencia_dashboard_metrics,
    get_observaciones_queryset,
    get_registro_detail,
    get_registros_queryset,
)
from apps.evaluacion.services import (
    EvaluacionWorkflowError,
    habilitar_salida_evaluador,
    registrar_evaluacion,
    registrar_observacion,
)
from apps.usuarios.models import Usuario
from apps.usuarios.selectors import get_usuario_area_cargo_for_context


logger = logging.getLogger(__name__)


def _normalize_token(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", (value or "").strip())
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.upper().split())

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

        return {
            "is_level_one_approver": is_level_one_approver,
            "is_tech_director": is_tech_director,
            "is_evaluator": is_evaluator,
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
        context["observaciones"] = (
            get_observaciones_queryset(evaluacion_id=selected_evaluation.pk)[:30]
            if selected_evaluation
            else []
        )
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

    def post(self, request, *args, **kwargs):
        registro = get_registro_detail(request.POST.get("registro"))
        if registro is None:
            raise Http404("La evidencia solicitada no existe.")

        scope_flags = self._actor_scope_flags()
        if not scope_flags["can_manage_release"]:
            messages.error(request, "No tienes permisos para habilitar la salida al evaluador.")
            return redirect(f"{reverse('evaluacion-evidencia-detalle')}?registro={registro.pk}")

        if request.POST.get("habilitar_salida") != "1":
            messages.warning(request, "Debes marcar la casilla para habilitar la salida al evaluador.")
            return redirect(f"{reverse('evaluacion-evidencia-detalle')}?registro={registro.pk}")

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

        return redirect(f"{reverse('evaluacion-evidencia-detalle')}?registro={registro.pk}")


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
