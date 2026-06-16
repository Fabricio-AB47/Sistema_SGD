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
    UPLOADED_EVIDENCE_STATES,
    get_current_enabled_cycle,
    get_caces_cycle,
    get_caces_cycle_result,
    get_caces_cycles,
    get_caces_indicator_matrix,
    get_default_caces_cycle,
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
    aprobar_tarea_visto_bueno_director,
    cerrar_tarea_evidencia,
    habilitar_salida_evaluador,
    materializar_tareas_principales_desde_acceso,
    obtener_aprobacion_principal_registro,
    redireccionar_tarea_subordinado,
    rechazar_tarea_revision_director,
    registrar_evaluacion,
    registrar_observacion,
    registrar_tarea_evidencia,
    registrar_tareas_evidencia_lote,
    resolver_observacion,
    tarea_tiene_visto_bueno_director,
)
from apps.evaluacion.models import ObservacionEvaluacion
from apps.evidencias.models import RegistroEvidencia
from apps.usuarios.models import AreaInstitucional, Usuario, UsuarioAreaCargo, UsuarioRol
from apps.usuarios.selectors import get_usuario_area_cargo_for_context


logger = logging.getLogger(__name__)
TASK_NOT_FOUND_MESSAGE = "La tarea seleccionada no existe."


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
EVALUATOR_ROLE_TOKEN = "EVALUADOR"
DIRECTOR_REDIRECT_BLOCKED_ROLE_TOKENS = {
    EVALUATOR_ROLE_TOKEN,
    "CONSULTA",
}
EVALUACION_ENTRY_ROLE_TOKENS = {
    ADMIN_ROLE_TOKEN,
    EVALUATOR_ROLE_TOKEN,
    *QUALITY_ROLE_TOKENS,
}
EVALUACION_ENTRY_ACCESS_DENIED_MESSAGE = (
    "Solo los roles ADMINISTRADOR, CALIDAD o EVALUADOR pueden ingresar a evaluacion."
)
EVALUATOR_ALLOWED_URL_NAMES = {
    "evaluacion-bandeja",
    "evaluacion-evaluar",
    "evaluacion-caces",
    "evaluacion-caces-ciclo",
    "evaluacion-caces-indicador",
    "evaluacion-caces-api-ciclos",
    "evaluacion-caces-api-indicadores",
    "evaluacion-caces-api-pendientes",
    "evaluacion-caces-api-categorias",
    "evaluacion-caces-api-variables",
    "evaluacion-caces-api-cualitativa",
    "evaluacion-caces-api-guardar-variables",
    "evaluacion-caces-api-calcular",
    "evaluacion-caces-api-manual",
    "evaluacion-caces-api-resultado-indicador",
    "evaluacion-caces-api-resultado-ciclo",
    "evaluacion-caces-api-cobertura",
}

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
        "label": "Reasignacion de tareas",
        "url_name": "evaluacion-tareas-reasignacion",
        "active_names": ("evaluacion-tareas-reasignacion",),
    },
    {
        "label": "Bandeja de evaluacion",
        "url_name": "evaluacion-bandeja",
        "active_names": (
            "evaluacion-bandeja",
            "evaluacion-caces",
            "evaluacion-caces-ciclo",
            "evaluacion-caces-indicador",
            "evaluacion-caces-reporte",
        ),
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


def _request_role_tokens(request):
    return tuple(
        dict.fromkeys(
            _normalize_token(role)
            for role in [
                *(request.session.get("sig_roles", []) or []),
                *(request.session.get("sig_operational_roles", []) or []),
            ]
            if _normalize_token(role)
        )
    )


def _has_evaluation_entry_access(request) -> bool:
    role_tokens = set(_request_role_tokens(request))
    return bool(role_tokens.intersection(EVALUACION_ENTRY_ROLE_TOKENS))


def _is_evaluator_only_request(request) -> bool:
    role_tokens = set(_request_role_tokens(request))
    return (
        EVALUATOR_ROLE_TOKEN in role_tokens
        and ADMIN_ROLE_TOKEN not in role_tokens
        and not role_tokens.intersection(QUALITY_ROLE_TOKENS)
    )


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


class EvaluacionEntryRoleRequiredMixin:
    access_denied_message = EVALUACION_ENTRY_ACCESS_DENIED_MESSAGE

    def dispatch(self, request, *args, **kwargs):
        if request.session.get("sig_user_id") and not _has_evaluation_entry_access(request):
            messages.error(request, self.access_denied_message)
            return redirect("core-dashboard")
        return super().dispatch(request, *args, **kwargs)


class EvaluacionBaseView(SigLoginRequiredMixin, TemplateView):
    template_name = ""
    page_title = ""
    page_description = ""
    page_status = "Operacion real"
    page_actions = []

    def dispatch(self, request, *args, **kwargs):
        current_url_name = request.resolver_match.url_name if request.resolver_match else ""
        if (
            request.session.get("sig_user_id")
            and _is_evaluator_only_request(request)
            and current_url_name not in EVALUATOR_ALLOWED_URL_NAMES
        ):
            messages.error(request, "El rol Evaluador solo puede acceder a la bandeja CACES de evaluacion.")
            return redirect("evaluacion-bandeja")
        return super().dispatch(request, *args, **kwargs)

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
        role_tokens = _request_role_tokens(self.request)
        cargo_name = _normalize_token(getattr(getattr(assignment, "cargo", None), "nombre_cargo", ""))
        cargo_level = getattr(getattr(assignment, "cargo", None), "nivel_jerarquico", None)
        cargo_approves = bool(getattr(getattr(assignment, "cargo", None), "aprueba_interno", False))

        is_level_one_approver = bool(cargo_approves and cargo_level == 1)
        is_tech_director = cargo_name == "DIRECTOR DE TECNOLOGIA"
        is_area_director = "DIRECTOR" in cargo_name if cargo_name else False
        is_evaluator = EVALUATOR_ROLE_TOKEN in role_tokens
        is_consulta = "CONSULTA" in role_tokens
        is_admin = ADMIN_ROLE_TOKEN in role_tokens
        is_quality = any(token in QUALITY_ROLE_TOKENS for token in role_tokens)
        is_evaluator_only = is_evaluator and not is_admin and not is_quality

        return {
            "is_admin": is_admin,
            "is_level_one_approver": is_level_one_approver,
            "is_tech_director": is_tech_director,
            "is_area_director": is_area_director,
            "is_evaluator": is_evaluator,
            "is_evaluator_only": is_evaluator_only,
            "is_consulta": is_consulta,
            "is_quality": is_quality,
            "can_enter_evaluation": is_admin or is_evaluator,
            "can_assign_tasks": is_admin or is_quality,
            "can_manage_release": is_admin or is_level_one_approver or is_tech_director,
            "can_manage_corrections": is_admin or is_quality,
            "can_redirect_subordinates": (
                is_admin
                or (
                    is_level_one_approver
                    and not is_evaluator
                    and not is_consulta
                )
            ),
        }

    def _registro_released(self, registro) -> bool:
        return bool(getattr(registro, "fecha_envio_revision", None))

    def _module_tabs(self):
        scope_flags = self._actor_scope_flags()
        if scope_flags.get("is_evaluator_only"):
            return [
                tab
                for tab in MODULE_TABS
                if tab["url_name"] == "evaluacion-bandeja"
            ]
        tabs = []
        for tab in MODULE_TABS:
            if (
                tab["url_name"] == "evaluacion-tareas-reasignacion"
                and not scope_flags.get("can_redirect_subordinates")
            ):
                continue
            tabs.append(tab)
        return tabs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "module_title": MODULE_TITLE,
                "module_description": MODULE_DESCRIPTION,
                "module_tabs": self._module_tabs(),
                "page_title": self.page_title,
                "page_description": self.page_description,
                "page_status": self.page_status,
                "page_actions": self.page_actions,
                "current_url_name": self.request.resolver_match.url_name if self.request.resolver_match else "",
                "evaluation_metrics": get_evidencia_dashboard_metrics(),
                "scope_flags": self._actor_scope_flags(),
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
            only_released=scope_flags["is_evaluator"] and not scope_flags["is_admin"],
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

    @staticmethod
    def _active_operational_roles_for_user(user_id, *, include_blocked=False):
        if not user_id:
            return set(), []

        role_ids = set()
        role_names = []
        for role_id, role_name in (
            UsuarioRol.objects.filter(
                usuario_id=user_id,
                activo=True,
                rol__activo=True,
            )
            .order_by("rol__nombre_rol")
            .values_list("rol_id", "rol__nombre_rol")
        ):
            if (
                not include_blocked
                and _normalize_token(role_name) in DIRECTOR_REDIRECT_BLOCKED_ROLE_TOKENS
            ):
                continue
            role_ids.add(role_id)
            role_names.append(role_name)
        return role_ids, role_names

    @staticmethod
    def _role_names_by_user(user_ids, role_ids=None, *, include_blocked=False):
        if not user_ids:
            return {}

        queryset = UsuarioRol.objects.filter(
            usuario_id__in=user_ids,
            activo=True,
            rol__activo=True,
        ).order_by("rol__nombre_rol")
        if role_ids is not None:
            queryset = queryset.filter(rol_id__in=role_ids)

        role_names = {}
        for user_id, role_name in queryset.values_list("usuario_id", "rol__nombre_rol"):
            if (
                not include_blocked
                and _normalize_token(role_name) in DIRECTOR_REDIRECT_BLOCKED_ROLE_TOKENS
            ):
                continue
            role_names.setdefault(user_id, []).append(role_name)
        return role_names

    @staticmethod
    def _blocked_only_user_ids(role_names_by_user):
        blocked_user_ids = set()
        for user_id, role_names in role_names_by_user.items():
            normalized_roles = {
                _normalize_token(role_name)
                for role_name in role_names
                if _normalize_token(role_name)
            }
            if normalized_roles and normalized_roles.issubset(DIRECTOR_REDIRECT_BLOCKED_ROLE_TOKENS):
                blocked_user_ids.add(user_id)
        return blocked_user_ids

    def _director_subordinate_options(self, *, actor):
        if actor is None:
            return []

        actor_id = getattr(actor, "pk", None)
        if not actor_id:
            return []

        scope_flags = self._actor_scope_flags()
        candidate_users = Usuario.objects.filter(activo=True).exclude(pk=actor_id).order_by(
            "primer_apellido",
            "primer_nombre",
            "correo",
        )
        candidate_user_ids = set(candidate_users.values_list("pk", flat=True))
        if not candidate_user_ids:
            return []

        if not scope_flags.get("is_admin"):
            actor_role_ids, _actor_role_names = self._active_operational_roles_for_user(actor_id)
            if not actor_role_ids:
                return []
            candidate_user_ids = set(
                UsuarioRol.objects.filter(
                    usuario_id__in=candidate_user_ids,
                    rol_id__in=actor_role_ids,
                    activo=True,
                    rol__activo=True,
                ).values_list("usuario_id", flat=True)
            )
            if not candidate_user_ids:
                return []

        role_names_by_user = self._role_names_by_user(candidate_user_ids, include_blocked=True)
        blocked_user_ids = self._blocked_only_user_ids(role_names_by_user)
        candidate_user_ids = candidate_user_ids - blocked_user_ids
        if not candidate_user_ids:
            return []

        assignments = (
            UsuarioAreaCargo.objects.select_related("usuario", "area", "cargo")
            .filter(
                activo=True,
                area__activo=True,
                cargo__activo=True,
                usuario__activo=True,
                usuario_id__in=candidate_user_ids,
            )
            .order_by(
                "usuario__primer_apellido",
                "usuario__primer_nombre",
                "area__nombre_area",
                "cargo__nivel_jerarquico",
                "cargo__nombre_cargo",
            )
        )
        assignment_by_user = {}
        for assignment in assignments:
            assignment_by_user.setdefault(assignment.usuario_id, assignment)

        options = []
        for usuario in candidate_users.filter(pk__in=candidate_user_ids):
            assignment = assignment_by_user.get(usuario.pk)
            role_suffix = ", ".join(
                role_name
                for role_name in role_names_by_user.get(usuario.pk, [])
                if _normalize_token(role_name) not in DIRECTOR_REDIRECT_BLOCKED_ROLE_TOKENS
            )
            label = usuario.nombre_completo or usuario.correo
            if assignment is not None:
                label = f"{label} ({assignment.area.nombre_area} / {assignment.cargo.nombre_cargo})"
            else:
                label = f"{label} (Usuario registrado)"
            if role_suffix:
                label = f"{label} | Rol: {role_suffix}"
            options.append(
                {
                    "value": str(usuario.pk),
                    "label": label,
                }
            )
        return options

    @staticmethod
    def _can_redirect_task(*, tarea, actor_id, actor_area_id, can_redirect_subordinates, is_admin=False):
        if not can_redirect_subordinates or not actor_id or tarea.fecha_cierre:
            return False
        if is_admin:
            return True
        if not actor_area_id:
            return False
        if tarea.usuario_responsable_id != actor_id and tarea.asignado_por_id != actor_id:
            return False
        task_assignments = getattr(tarea.usuario_responsable, "task_area_assignments", [])
        if not task_assignments:
            return False
        return any(assignment.area_id == actor_area_id for assignment in task_assignments)

    @staticmethod
    def _can_signoff_task(*, tarea, actor_id, can_redirect_subordinates, is_admin=False):
        if not can_redirect_subordinates or not actor_id:
            return False
        if not tarea.fecha_cierre:
            return False
        if tarea_tiene_visto_bueno_director(tarea):
            return False
        if is_admin:
            return True
        if tarea.usuario_responsable_id == actor_id:
            return False
        return tarea.asignado_por_id == actor_id

    @staticmethod
    def _latest_registro_for_tarea(tarea):
        return (
            RegistroEvidencia.objects.select_related("documento", "estado")
            .filter(
                ciclo=tarea.ciclo,
                indicador=tarea.indicador,
                elemento_fundamental=tarea.elemento_fundamental,
            )
            .order_by("-fecha_registro", "-id_registro")
            .first()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_flags = self._actor_scope_flags()
        q = self.request.GET.get("q", "")
        estado = self.request.GET.get("estado", "")
        ciclo = self.request.GET.get("ciclo", "")
        area = self.request.GET.get("area", "")
        responsable = self.request.GET.get("responsable", "")
        actor = self._actor()
        actor_assignment = self._actor_assignment()
        actor_area_id = getattr(actor_assignment, "area_id", None)
        actor_id = getattr(actor, "pk", None)
        can_assign_tasks = scope_flags["can_assign_tasks"]
        can_redirect_subordinates = scope_flags.get("can_redirect_subordinates", False)
        is_admin = scope_flags.get("is_admin", False)
        effective_responsable = responsable if can_assign_tasks else getattr(actor, "pk", -1)
        if can_assign_tasks:
            assigned_by_filter = None
        elif can_redirect_subordinates:
            assigned_by_filter = actor_id
        else:
            assigned_by_filter = None
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
            assigned_by_id=assigned_by_filter,
        )[:100]
        context["scope_flags"] = scope_flags
        context["current_actor_id"] = actor_id
        context["subordinate_options"] = self._director_subordinate_options(actor=actor)
        for tarea in context["tareas"]:
            tarea.director_can_redirect = self._can_redirect_task(
                tarea=tarea,
                actor_id=actor_id,
                actor_area_id=actor_area_id,
                can_redirect_subordinates=can_redirect_subordinates,
                is_admin=is_admin,
            )
            tarea.director_can_signoff = self._can_signoff_task(
                tarea=tarea,
                actor_id=actor_id,
                can_redirect_subordinates=can_redirect_subordinates,
                is_admin=is_admin,
            )
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
            messages.error(request, TASK_NOT_FOUND_MESSAGE)
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
                "Solo Administrador o Calidad puede realizar asignaciones parciales de indicadores y elementos.",
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

    def _handle_director_redirect(self, request, *, redirect_url_name="evaluacion-tareas"):
        actor = self._actor()
        actor_id = getattr(actor, "pk", None)
        scope_flags = self._actor_scope_flags()
        actor_assignment = self._actor_assignment()
        actor_area_id = getattr(actor_assignment, "area_id", None)
        can_redirect_subordinates = scope_flags.get("can_redirect_subordinates", False)
        is_admin = scope_flags.get("is_admin", False)

        tarea = get_tarea_evidencia_detail(request.POST.get("tarea_id"))
        if tarea is None:
            messages.error(request, TASK_NOT_FOUND_MESSAGE)
            return redirect(redirect_url_name)

        if not self._can_redirect_task(
            tarea=tarea,
            actor_id=actor_id,
            actor_area_id=actor_area_id,
            can_redirect_subordinates=can_redirect_subordinates,
            is_admin=is_admin,
        ):
            messages.error(
                request,
                (
                    "Solo se pueden desglosar tareas abiertas hacia usuarios activos."
                    if is_admin
                    else "Solo puedes desglosar tareas propias hacia usuarios de tu rol asignado."
                ),
            )
            return redirect(redirect_url_name)

        subordinate_options = {item["value"] for item in self._director_subordinate_options(actor=actor)}
        subordinate_id = str(request.POST.get("subordinado_id") or "").strip()
        if subordinate_id not in subordinate_options:
            messages.error(
                request,
                (
                    "Selecciona un usuario activo disponible en el sistema."
                    if is_admin
                    else "Selecciona un usuario valido de tu rol asignado."
                ),
            )
            return redirect(redirect_url_name)

        subordinado = Usuario.objects.filter(pk=subordinate_id, activo=True).first()
        if subordinado is None:
            messages.error(request, "No fue posible identificar al usuario seleccionado.")
            return redirect(redirect_url_name)

        try:
            redireccionar_tarea_subordinado(
                tarea=tarea,
                nuevo_responsable=subordinado,
                actor=actor,
                comentario=request.POST.get("comentario_redireccion"),
                request=request,
            )
        except (TareaEvidenciaWorkflowError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
            _report_operation_error(
                request=request,
                exc=exc,
                user_message="No fue posible desglosar la carga de trabajo.",
            )
        else:
            messages.success(request, "Carga desglosada y reasignada correctamente.")

        return redirect(redirect_url_name)

    def _handle_director_signoff(self, request, *, redirect_url_name="evaluacion-tareas"):
        actor = self._actor()
        actor_id = getattr(actor, "pk", None)
        scope_flags = self._actor_scope_flags()
        can_redirect_subordinates = scope_flags.get("can_redirect_subordinates", False)
        is_admin = scope_flags.get("is_admin", False)

        tarea = get_tarea_evidencia_detail(request.POST.get("tarea_id"))
        if tarea is None:
            messages.error(request, TASK_NOT_FOUND_MESSAGE)
            return redirect(redirect_url_name)

        if not self._can_signoff_task(
            tarea=tarea,
            actor_id=actor_id,
            can_redirect_subordinates=can_redirect_subordinates,
            is_admin=is_admin,
        ):
            messages.error(
                request,
                (
                    "El administrador puede registrar el visto bueno de cualquier tarea cerrada."
                    if is_admin
                    else "Solo el director que desgloso la tarea puede registrar el visto bueno."
                ),
            )
            return redirect(redirect_url_name)

        try:
            aprobar_tarea_visto_bueno_director(
                tarea=tarea,
                actor=actor,
                comentario=(
                    request.POST.get("comentario_revision")
                    or request.POST.get("comentario_visto_bueno")
                ),
                request=request,
            )
        except (TareaEvidenciaWorkflowError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
            _report_operation_error(
                request=request,
                exc=exc,
                user_message="No fue posible registrar el visto bueno del director.",
            )
        else:
            try:
                registro = self._latest_registro_for_tarea(tarea)
                if registro is None:
                    raise EvaluacionWorkflowError("No fue posible identificar la evidencia aprobada.")
                release_result = habilitar_salida_evaluador(
                    registro=registro,
                    actor=actor,
                    allow_reassign=scope_flags["can_manage_release"],
                    require_actor_approver=not scope_flags.get("is_admin"),
                    request=request,
                )
            except (EvaluacionWorkflowError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    user_message=(
                        "El visto bueno fue registrado, pero no fue posible enviar la evidencia "
                        "automaticamente al evaluador."
                    ),
                )
            else:
                if release_result["status"] == "already_released":
                    messages.info(
                        request,
                        "Documento aprobado. La evidencia ya estaba habilitada para evaluacion.",
                    )
                else:
                    messages.success(
                        request,
                        "Documento aprobado y enviado automaticamente al evaluador.",
                    )

        return redirect(redirect_url_name)

    def _handle_director_reject(self, request, *, redirect_url_name="evaluacion-tareas"):
        actor = self._actor()
        actor_id = getattr(actor, "pk", None)
        scope_flags = self._actor_scope_flags()
        can_redirect_subordinates = scope_flags.get("can_redirect_subordinates", False)
        is_admin = scope_flags.get("is_admin", False)

        tarea = get_tarea_evidencia_detail(request.POST.get("tarea_id"))
        if tarea is None:
            messages.error(request, TASK_NOT_FOUND_MESSAGE)
            return redirect(redirect_url_name)

        if not self._can_signoff_task(
            tarea=tarea,
            actor_id=actor_id,
            can_redirect_subordinates=can_redirect_subordinates,
            is_admin=is_admin,
        ):
            messages.error(
                request,
                (
                    "El administrador puede solicitar correcciones sobre cualquier tarea cerrada."
                    if is_admin
                    else "Solo el director que desgloso la tarea puede solicitar correcciones."
                ),
            )
            return redirect(redirect_url_name)

        try:
            rechazar_tarea_revision_director(
                tarea=tarea,
                actor=actor,
                comentario=(
                    request.POST.get("comentario_revision")
                    or request.POST.get("comentario_visto_bueno")
                ),
                request=request,
            )
        except (TareaEvidenciaWorkflowError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
            _report_operation_error(
                request=request,
                exc=exc,
                user_message="No fue posible solicitar correcciones sobre la evidencia.",
            )
        else:
            messages.warning(
                request,
                "Correcciones solicitadas. Se envio la alerta por correo y la tarea quedo habilitada para nueva carga.",
            )

        return redirect(redirect_url_name)

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        if action == "close":
            return self._handle_close(request)
        if action == "bulk_assign":
            return self._handle_bulk_assign(request)
        if action == "director_redirect":
            return self._handle_director_redirect(request)
        if action == "director_signoff":
            return self._handle_director_signoff(request)
        if action == "director_reject":
            return self._handle_director_reject(request)

        scope_flags = self._actor_scope_flags()
        if not scope_flags.get("can_assign_tasks"):
            messages.error(request, "Solo Administrador o Calidad puede asignar tareas de evidencia.")
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


class TareaReasignacionView(TareaEvidenciaListView):
    template_name = "evaluacion/tarea_reasignacion.html"
    page_title = "Reasignacion de tareas"
    page_description = "Permite desglosar tareas segun el alcance del rol asignado."

    @staticmethod
    def _uploaded_element_ids_for_cycle(*, ciclo, tareas):
        element_ids = {
            tarea.elemento_fundamental_id
            for tarea in tareas
            if getattr(tarea, "elemento_fundamental_id", None)
        }
        if ciclo is None or not element_ids:
            return set()

        registros = (
            RegistroEvidencia.objects.select_related("estado")
            .filter(ciclo=ciclo, elemento_fundamental_id__in=element_ids)
            .order_by("elemento_fundamental_id", "-fecha_registro", "-id_registro")
        )
        latest_status_by_element = {}
        for registro in registros:
            latest_status_by_element.setdefault(
                registro.elemento_fundamental_id,
                _normalize_token(getattr(getattr(registro, "estado", None), "descripcion", "")),
            )
        return {
            element_id
            for element_id, status in latest_status_by_element.items()
            if status in UPLOADED_EVIDENCE_STATES
        }

    @staticmethod
    def _latest_records_by_task(tareas):
        task_keys = {
            (
                getattr(tarea, "ciclo_id", None),
                getattr(tarea, "indicador_id", None),
                getattr(tarea, "elemento_fundamental_id", None),
            )
            for tarea in tareas
        }
        task_keys.discard((None, None, None))
        if not task_keys:
            return {}

        ciclo_ids = {key[0] for key in task_keys}
        indicador_ids = {key[1] for key in task_keys}
        elemento_ids = {key[2] for key in task_keys}
        registros = (
            RegistroEvidencia.objects.select_related(
                "documento",
                "estado",
                "registrado_por",
            )
            .filter(
                ciclo_id__in=ciclo_ids,
                indicador_id__in=indicador_ids,
                elemento_fundamental_id__in=elemento_ids,
            )
            .order_by(
                "ciclo_id",
                "indicador_id",
                "elemento_fundamental_id",
                "-fecha_registro",
                "-id_registro",
            )
        )
        latest_by_key = {}
        for registro in registros:
            key = (
                registro.ciclo_id,
                registro.indicador_id,
                registro.elemento_fundamental_id,
            )
            if key in task_keys:
                latest_by_key.setdefault(key, registro)
        return latest_by_key

    @staticmethod
    def _build_reassignment_structure(tareas):
        criteria_map = OrderedDict()
        for tarea in tareas:
            indicador = tarea.indicador
            subcriterio = indicador.subcriterio
            criterio = subcriterio.criterio

            criterion_node = criteria_map.setdefault(
                criterio.pk,
                {
                    "criterio": criterio,
                    "total": 0,
                    "reasignables": 0,
                    "revision": 0,
                    "_subcriterios": OrderedDict(),
                },
            )
            subcriterion_node = criterion_node["_subcriterios"].setdefault(
                subcriterio.pk,
                {
                    "subcriterio": subcriterio,
                    "total": 0,
                    "reasignables": 0,
                    "revision": 0,
                    "_indicadores": OrderedDict(),
                },
            )
            indicator_node = subcriterion_node["_indicadores"].setdefault(
                indicador.pk,
                {
                    "indicador": indicador,
                    "total": 0,
                    "reasignables": 0,
                    "revision": 0,
                    "tareas": [],
                },
            )

            indicator_node["tareas"].append(tarea)
            for node in (criterion_node, subcriterion_node, indicator_node):
                node["total"] += 1
                if getattr(tarea, "director_can_redirect", False):
                    node["reasignables"] += 1
                if getattr(tarea, "director_can_signoff", False):
                    node["revision"] += 1

        criteria_groups = []
        for criterion_node in criteria_map.values():
            subcriteria = []
            for subcriterion_node in criterion_node["_subcriterios"].values():
                subcriterion_node["indicadores"] = list(subcriterion_node["_indicadores"].values())
                del subcriterion_node["_indicadores"]
                subcriteria.append(subcriterion_node)
            criterion_node["subcriterios"] = subcriteria
            del criterion_node["_subcriterios"]
            criteria_groups.append(criterion_node)
        return criteria_groups

    def get_context_data(self, **kwargs):
        context = EvaluacionBaseView.get_context_data(self, **kwargs)
        scope_flags = self._actor_scope_flags()
        actor = self._actor()
        actor_assignment = self._actor_assignment()
        actor_id = getattr(actor, "pk", None)
        actor_area_id = getattr(actor_assignment, "area_id", None)
        can_redirect_subordinates = scope_flags.get("can_redirect_subordinates", False)
        is_admin = scope_flags.get("is_admin", False)
        q = self.request.GET.get("q", "")
        selected_cycle = get_current_enabled_cycle()

        if can_redirect_subordinates and selected_cycle:
            try:
                materializar_tareas_principales_desde_acceso(
                    ciclo=selected_cycle,
                    actor=actor,
                    include_all=is_admin,
                    request=self.request,
                )
            except (TareaEvidenciaWorkflowError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                _report_operation_error(
                    request=self.request,
                    exc=exc,
                    user_message="No fue posible preparar las tareas del ciclo aprobado.",
                )
            task_filters = {
                "q": q,
                "ciclo_id": selected_cycle.pk,
                "order_by_hierarchy": True,
            }
            if not is_admin:
                task_filters.update(
                    {
                        "responsable_id": actor_id,
                        "assigned_by_id": actor_id,
                    }
                )
            tareas = list(
                get_tareas_evidencia_queryset(**task_filters)[:100]
            )
            uploaded_element_ids = self._uploaded_element_ids_for_cycle(
                ciclo=selected_cycle,
                tareas=tareas,
            )
            if uploaded_element_ids:
                tareas = [
                    tarea
                    for tarea in tareas
                    if tarea.elemento_fundamental_id not in uploaded_element_ids
                ]
            subordinate_options = self._director_subordinate_options(actor=actor)
        else:
            tareas = []
            subordinate_options = []

        latest_records_by_task = self._latest_records_by_task(tareas)
        pending_reassignment_count = 0
        pending_signoff_count = 0
        for tarea in tareas:
            task_key = (
                getattr(tarea, "ciclo_id", None),
                getattr(tarea, "indicador_id", None),
                getattr(tarea, "elemento_fundamental_id", None),
            )
            review_record = latest_records_by_task.get(task_key)
            tarea.review_record = review_record
            tarea.review_document = getattr(review_record, "documento", None) if review_record else None
            tarea.review_state_label = (
                getattr(getattr(review_record, "estado", None), "descripcion", "")
                if review_record
                else ""
            )
            tarea.director_can_redirect = self._can_redirect_task(
                tarea=tarea,
                actor_id=actor_id,
                actor_area_id=actor_area_id,
                can_redirect_subordinates=can_redirect_subordinates,
                is_admin=is_admin,
            )
            tarea.director_pending_signoff = self._can_signoff_task(
                tarea=tarea,
                actor_id=actor_id,
                can_redirect_subordinates=can_redirect_subordinates,
                is_admin=is_admin,
            )
            tarea.director_can_signoff = bool(
                tarea.director_pending_signoff
                and getattr(tarea.review_document, "pk", None)
            )
            tarea.reassignment_options = [
                option
                for option in subordinate_options
                if option["value"] != str(tarea.usuario_responsable_id)
            ]
            if tarea.director_can_redirect:
                pending_reassignment_count += 1
            if tarea.director_can_signoff:
                pending_signoff_count += 1
        reassignment_structure = self._build_reassignment_structure(tareas)

        context.update(
            {
                "module_tabs": [
                    tab
                    for tab in context.get("module_tabs", [])
                    if tab["url_name"] == "evaluacion-tareas-reasignacion"
                ],
                "scope_flags": scope_flags,
                "current_actor_id": actor_id,
                "actor_assignment": actor_assignment,
                "selected_cycle": selected_cycle,
                "tareas": tareas,
                "reassignment_structure": reassignment_structure,
                "subordinate_options": subordinate_options,
                "selected_filters": {
                    "q": q,
                },
                "reassignment_metrics": {
                    "total": len(tareas),
                    "reasignables": pending_reassignment_count,
                    "revision": pending_signoff_count,
                    "usuarios": len(subordinate_options),
                },
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        if action == "director_redirect":
            return self._handle_director_redirect(
                request,
                redirect_url_name="evaluacion-tareas-reasignacion",
            )
        if action == "director_signoff":
            return self._handle_director_signoff(
                request,
                redirect_url_name="evaluacion-tareas-reasignacion",
            )
        if action == "director_reject":
            return self._handle_director_reject(
                request,
                redirect_url_name="evaluacion-tareas-reasignacion",
            )

        messages.error(request, "Selecciona una accion valida para la reasignacion.")
        return redirect("evaluacion-tareas-reasignacion")


class EvidenciaDetailView(EvaluacionBaseView):
    template_name = "evaluacion/evidencia_detail.html"
    page_title = "Detalle de evidencia"
    page_description = "Consulta el documento, el estado del registro y el historial de evaluaciones relacionadas."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_flags = self._actor_scope_flags()
        actor_id = getattr(self._actor(), "pk", None)
        registro = kwargs.get("registro") or get_registro_detail(self.request.GET.get("registro"))
        approval_status = obtener_aprobacion_principal_registro(registro) if registro else None
        approval_task = approval_status.get("task") if approval_status else None
        context["registro"] = registro
        context["scope_flags"] = scope_flags
        context["release_controls"] = {
            "can_manage": scope_flags["can_manage_release"],
            "is_released": self._registro_released(registro) if registro else False,
            "approval": approval_status,
            "can_release": bool(
                scope_flags["can_manage_release"]
                and registro
                and approval_status["approved"]
                and (
                    scope_flags.get("is_admin")
                    or getattr(approval_task, "asignado_por_id", None) == actor_id
                )
            ),
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
        context["can_manage_corrections"] = bool(
            scope_flags.get("can_manage_corrections") and rejected_context
        )
        return context

    def get(self, request, *args, **kwargs):
        registro = get_registro_detail(request.GET.get("registro"))
        if registro is None:
            raise Http404("La evidencia solicitada no existe.")
        scope_flags = self._actor_scope_flags()
        if (
            scope_flags["is_evaluator"]
            and not scope_flags["is_admin"]
            and not self._registro_released(registro)
        ):
            messages.warning(
                request,
                "La evidencia todavia no ha sido habilitada para evaluacion por un cargo de nivel 1.",
            )
            return redirect("evaluacion-evidencias-lista")
        if self._auto_release_approved_registro(
            request=request,
            registro=registro,
            scope_flags=scope_flags,
        ):
            return self._detail_redirect(registro)
        return self.render_to_response(self.get_context_data(registro=registro))

    @staticmethod
    def _detail_redirect(registro):
        return redirect(f"{reverse('evaluacion-evidencia-detalle')}?registro={registro.pk}")

    def _auto_release_approved_registro(self, *, request, registro, scope_flags) -> bool:
        if self._registro_released(registro) or not scope_flags["can_manage_release"]:
            return False

        approval_status = obtener_aprobacion_principal_registro(registro)
        approval_task = approval_status.get("task") if approval_status else None
        actor = self._actor()
        actor_id = getattr(actor, "pk", None)
        can_release = bool(
            approval_status
            and approval_status["approved"]
            and (
                scope_flags.get("is_admin")
                or getattr(approval_task, "asignado_por_id", None) == actor_id
            )
        )
        if not can_release:
            return False

        try:
            result = habilitar_salida_evaluador(
                registro=registro,
                actor=actor,
                allow_reassign=scope_flags["can_manage_release"],
                require_actor_approver=not scope_flags.get("is_admin"),
                request=request,
            )
        except (EvaluacionWorkflowError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
            _report_operation_error(
                request=request,
                exc=exc,
                user_message="No fue posible enviar automaticamente la evidencia al evaluador.",
            )
            return False

        if result["status"] == "already_released":
            return False
        messages.success(request, "Evidencia aprobada y enviada automaticamente al evaluador.")
        return True

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

        if not scope_flags.get("can_manage_corrections"):
            messages.error(request, "Solo Administrador o Calidad puede gestionar correcciones en esta pantalla.")
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

        messages.info(
            request,
            "La salida al evaluador se habilita automaticamente cuando el director registra el visto bueno.",
        )
        return self._detail_redirect(registro)


class EvaluacionInboxView(EvaluacionEntryRoleRequiredMixin, EvaluacionBaseView):
    template_name = "evaluacion/bandeja_evaluacion.html"
    page_title = "Bandeja de evaluacion"
    page_description = "Centraliza la evaluacion documental y la evaluacion CACES por tipo de indicador."

    PANEL_EVIDENCIAS = "evidencias"
    PANEL_CACES = "caces"
    CACES_TYPE_OPTIONS = (
        ("TODOS", "Todos"),
        ("CUALITATIVO", "Cualitativos"),
        ("CUANTITATIVO", "Cuantitativos"),
    )

    def _selected_estado(self):
        return self.request.POST.get("estado_filtro") or self.request.GET.get("estado", "TODOS")

    def _selected_evidence_cycle_id(self):
        return self.request.POST.get("ciclo") or self.request.GET.get("ciclo")

    def _selected_panel(self):
        if self._actor_scope_flags().get("is_evaluator_only"):
            return self.PANEL_CACES
        panel = (self.request.GET.get("panel") or self.PANEL_EVIDENCIAS).strip().lower()
        return panel if panel in {self.PANEL_EVIDENCIAS, self.PANEL_CACES} else self.PANEL_EVIDENCIAS

    def _selected_caces_type(self):
        selected_type = (self.request.GET.get("tipo") or "TODOS").strip().upper()
        valid_types = {value for value, _label in self.CACES_TYPE_OPTIONS}
        return selected_type if selected_type in valid_types else "TODOS"

    def _selected_caces_cycle(self):
        cycle_id = self.request.GET.get("ciclo") or self.request.POST.get("ciclo")
        return get_caces_cycle(cycle_id) or get_default_caces_cycle()

    def _bandeja_url(self, *, registro_id=None, modal=False):
        url = f"{reverse('evaluacion-bandeja')}?panel={self.PANEL_EVIDENCIAS}&estado={self._selected_estado()}"
        cycle_id = self._selected_evidence_cycle_id()
        if cycle_id:
            url = f"{url}&ciclo={cycle_id}"
        if registro_id:
            url = f"{url}&registro={registro_id}"
        if modal:
            url = f"{url}&modal=evaluar"
        return url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_flags = self._actor_scope_flags()
        selected_estado = self._selected_estado()
        inbox_data = get_evaluation_inbox_data(
            estado=selected_estado,
            only_released=scope_flags["is_evaluator"] and not scope_flags["is_admin"],
            ciclo_id=self._selected_evidence_cycle_id(),
        )
        selected_registro = kwargs.get("registro") or get_registro_detail(
            self.request.GET.get("registro") or self.request.POST.get("registro")
        )
        if (
            scope_flags["is_evaluator"]
            and not scope_flags["is_admin"]
            and selected_registro is not None
            and not self._registro_released(selected_registro)
        ):
            selected_registro = None
            messages.warning(
                self.request,
                "La evidencia no esta habilitada para evaluacion. Debe ser liberada por un cargo de nivel 1.",
            )
        evaluation_form = kwargs.get("evaluation_form") or EvaluacionGestionForm(
            registro_initial=selected_registro
        )
        context["registros_pendientes"] = inbox_data["rows"]
        context["inbox_counts"] = inbox_data["counts"]
        context["inbox_summary"] = inbox_data["summary"]
        context["criterion_summaries"] = inbox_data["criterion_summaries"]
        context["selected_estado"] = inbox_data["selected_estado"]
        context["inbox_filter_options"] = inbox_data["filter_options"]
        context["evaluaciones_recientes"] = inbox_data["evaluaciones_recientes"]
        context["selected_evidence_cycle"] = inbox_data["selected_cycle"]
        context["evidence_cycles"] = inbox_data["available_cycles"]
        context["scope_flags"] = scope_flags
        context["selected_evaluation_record"] = selected_registro
        context["evaluation_form"] = evaluation_form
        context["evaluation_mode"] = getattr(evaluation_form, "evaluation_mode", "quantitative")
        context["indicator_type"] = getattr(
            getattr(getattr(selected_registro, "indicador", None), "tipo_indicador", None),
            "descripcion",
            "",
        )
        context["show_evaluation_modal"] = bool(
            selected_registro
            and (
                self.request.GET.get("modal") == "evaluar"
                or kwargs.get("evaluation_form") is not None
            )
        )
        context["close_evaluation_url"] = self._bandeja_url()

        selected_panel = self._selected_panel()
        selected_caces_cycle = (
            self._selected_caces_cycle()
            if selected_panel == self.PANEL_CACES
            else None
        )
        caces_matrix = (
            get_caces_indicator_matrix(selected_caces_cycle.pk)
            if selected_caces_cycle
            else None
        )
        context["selected_evaluation_panel"] = selected_panel
        evaluation_panel_options = [
            {
                "key": self.PANEL_EVIDENCIAS,
                "label": "Evidencias",
                "description": "Revisa documentos enviados y registra la evaluacion operativa.",
                "url": (
                    f"{reverse('evaluacion-bandeja')}?panel={self.PANEL_EVIDENCIAS}&estado={selected_estado}"
                    + (
                        f"&ciclo={inbox_data['selected_cycle'].pk}"
                        if inbox_data.get("selected_cycle")
                        else ""
                    )
                ),
            },
            {
                "key": self.PANEL_CACES,
                "label": "CACES",
                "description": "Evalua indicadores cualitativos y cuantitativos por ponderacion.",
                "url": f"{reverse('evaluacion-bandeja')}?panel={self.PANEL_CACES}",
            },
        ]
        if scope_flags.get("is_evaluator_only"):
            evaluation_panel_options = [
                option
                for option in evaluation_panel_options
                if option["key"] == self.PANEL_CACES
            ]
        context["evaluation_panel_options"] = tuple(evaluation_panel_options)
        context["caces_cycles"] = get_caces_cycles() if selected_panel == self.PANEL_CACES else []
        context["selected_caces_cycle"] = selected_caces_cycle
        context["selected_caces_type"] = self._selected_caces_type()
        context["caces_type_options"] = self.CACES_TYPE_OPTIONS
        context["caces_matrix"] = caces_matrix
        context["caces_cycle_result"] = (
            get_caces_cycle_result(selected_caces_cycle.pk)
            if selected_caces_cycle
            else None
        )
        return context

    def post(self, request, *args, **kwargs):
        form = EvaluacionGestionForm(request.POST)
        scope_flags = self._actor_scope_flags()
        if scope_flags.get("is_evaluator_only"):
            messages.error(request, "El rol Evaluador debe registrar la calificacion desde la matriz CACES.")
            return redirect(f"{reverse('evaluacion-bandeja')}?panel={self.PANEL_CACES}")
        selected_registro = get_registro_detail(request.POST.get("registro"))
        if form.is_valid():
            registro = form.cleaned_data["registro"]
            if (
                scope_flags["is_evaluator"]
                and not scope_flags["is_admin"]
                and not self._registro_released(registro)
            ):
                form.add_error("registro", "La evidencia no esta habilitada para evaluacion.")
                return self.render_to_response(
                    self.get_context_data(
                        evaluation_form=form,
                        registro=selected_registro,
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
                return redirect(self._bandeja_url())
        return self.render_to_response(
            self.get_context_data(
                evaluation_form=form,
                registro=selected_registro,
            )
        )


class EvaluacionFormView(EvaluacionEntryRoleRequiredMixin, EvaluacionBaseView):
    template_name = "evaluacion/evaluacion_form.html"
    page_title = "Evaluar evidencia"
    page_description = "Registra el resultado de la evaluacion formal y sincroniza el estado operativo de la evidencia."

    def get(self, request, *args, **kwargs):
        url = reverse("evaluacion-bandeja")
        registro_id = request.GET.get("registro")
        if registro_id:
            url = f"{url}?registro={registro_id}&modal=evaluar"
        return redirect(url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_flags = self._actor_scope_flags()
        registro = kwargs.get("registro") or get_registro_detail(
            self.request.GET.get("registro") or self.request.POST.get("registro")
        )
        if (
            scope_flags["is_evaluator"]
            and not scope_flags["is_admin"]
            and registro is not None
            and not self._registro_released(registro)
        ):
            registro = None
            messages.warning(
                self.request,
                "La evidencia no esta habilitada para evaluacion. Debe ser liberada por un cargo de nivel 1.",
            )
        context["registro"] = registro
        context["scope_flags"] = scope_flags
        form = kwargs.get("form") or EvaluacionGestionForm(registro_initial=registro)
        context["form"] = form
        context["evaluation_mode"] = getattr(form, "evaluation_mode", "quantitative")
        context["indicator_type"] = getattr(
            getattr(getattr(registro, "indicador", None), "tipo_indicador", None),
            "descripcion",
            "",
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
            if (
                scope_flags["is_evaluator"]
                and not scope_flags["is_admin"]
                and not self._registro_released(registro)
            ):
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


class ObservacionFormView(EvaluacionEntryRoleRequiredMixin, EvaluacionBaseView):
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
