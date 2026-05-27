import logging
import re
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

from django.contrib import messages
from django.db import DatabaseError, IntegrityError, OperationalError, transaction
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import RedirectView, TemplateView

from apps.core.mixins import SigLoginRequiredMixin, SigRoleOrPermissionRequiredMixin
from apps.core.services.navigation_service import (
    AREA_ROLES,
    PERM_ACREDITACION_GESTIONAR,
    PERM_ACREDITACION_VER,
    PERM_CONSULTA_VER,
    PERM_EVALUACION_REVISAR,
    PERM_EVIDENCIAS_REGISTRAR,
    ROLE_ADMIN,
    ROLE_CONSULTA,
    ROLE_EVALUATOR,
    ROLE_QUALITY,
    ROLE_RECTOR,
    _has_matching_permission,
    _has_matching_role,
    _normalize_permissions,
    _normalize_roles,
)
from apps.acreditacion.forms import (
    CacesCatalogSyncForm,
    CicloEstadoAutorizacionForm,
    ESTADOS_FLUJO_CICLO,
    ESTADOS_RECTOR_DECISION,
    CicloAuthorizationRevisionForm,
    CicloEstadoUpdateForm,
    CicloEvaluacionForm,
    CriterioForm,
    ElementoFundamentalForm,
    get_elemento_orden_visual_defaults,
    IndicadorElementoForm,
    IndicadorForm,
    SubcriterioForm,
)
from apps.core.models import EstadoCiclo
from apps.acreditacion.selectors import (
    attach_cycle_indicator_scope,
    get_acreditacion_metrics,
    get_caces_model_catalog_preview,
    get_ciclo_detail,
    get_ciclos_queryset,
    get_criterios_queryset,
    get_elementos_queryset,
    get_indicator_detail,
    get_indicator_selection_tree,
    get_indicadores_queryset,
    get_matrix_rows,
    get_subcriterios_queryset,
)
from apps.acreditacion.services import (
    actualizar_estado_ciclo,
    crear_ciclo,
    crear_criterio,
    crear_elemento,
    crear_indicador,
    crear_subcriterio,
    sincronizar_catalogo_desde_modelo_caces,
    vincular_indicador_elemento,
)
from apps.acreditacion.models import CicloEvaluacion
from apps.documentos.services import (
    AuthorizationServiceError,
    ProtectedDocumentAccessError,
    StructuredDocumentUploadError,
    resolve_protected_document_stream,
    upload_cycle_authorization_revision,
)
from apps.documentos.selectors import attach_cycle_authorization_status
from apps.evaluacion.forms import MatrixEvidenceRegistrationForm
from apps.evaluacion.selectors import get_matrix_registration_dashboard
from apps.evaluacion.models import TareaEvidencia
from apps.evaluacion.services import (
    MatrixEvidenceRegistrationError,
    register_matrix_evidence,
)
from apps.integraciones.services.graph_service import GraphServiceError
from apps.usuarios.models import Usuario


logger = logging.getLogger(__name__)


RECTOR_ROLE_TOKENS = {"RECTOR", "RECTORADO"}
QUALITY_ROLE_TOKENS = {
    "CALIDAD ACADEMICA",
    "DIRECTOR DE CALIDAD",
    "DIRECCION DE CALIDAD",
    "CALIDAD",
}


def _is_rector_role(role: str) -> bool:
    return str(role).strip().upper() in RECTOR_ROLE_TOKENS


def _is_quality_role(role: str) -> bool:
    return str(role).strip().upper() in QUALITY_ROLE_TOKENS


def _is_admin_role(role: str) -> bool:
    return str(role).strip().upper() == ROLE_ADMIN


REVIEWER_COMMENTS_PREFIX = "COMENTARIOS REVISOR:"
QUALITY_RESPONSE_PREFIX = "RESPUESTA CALIDAD:"
DOCX_COMMENT_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _split_observation_blocks(raw_text: str | None) -> tuple[str | None, str | None]:
    text = (raw_text or "").strip()
    if not text:
        return None, None

    upper_text = text.upper()
    reviewer_idx = upper_text.find(REVIEWER_COMMENTS_PREFIX)
    quality_idx = upper_text.find(QUALITY_RESPONSE_PREFIX)

    if reviewer_idx != -1 and quality_idx != -1 and quality_idx > reviewer_idx:
        reviewer_part = text[
            reviewer_idx + len(REVIEWER_COMMENTS_PREFIX) : quality_idx
        ].strip()
        quality_part = text[quality_idx + len(QUALITY_RESPONSE_PREFIX) :].strip()
        return reviewer_part or None, quality_part or None

    if quality_idx != -1:
        quality_part = text[quality_idx + len(QUALITY_RESPONSE_PREFIX) :].strip()
        return None, quality_part or None

    return text, None


def _build_quality_observation_payload(*, previous_value: str | None, submitted_value: str | None) -> str | None:
    submitted = (submitted_value or "").strip()
    if not submitted:
        return None

    reviewer_comments, _existing_quality_response = _split_observation_blocks(previous_value)
    if reviewer_comments:
        return (
            f"{REVIEWER_COMMENTS_PREFIX}\n{reviewer_comments}\n\n"
            f"{QUALITY_RESPONSE_PREFIX}\n{submitted}"
        )
    return submitted


def _extract_comment_items(text: str | None) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    normalized = raw.replace("\r", "\n")
    chunks = re.split(r"[\n;]+", normalized)
    items = [" ".join(chunk.strip().split()) for chunk in chunks if chunk and chunk.strip()]
    return items[:12]


def _read_word_comment_text(comment_node) -> str:
    pieces = [node.text for node in comment_node.findall(".//w:t", DOCX_COMMENT_NS) if node.text]
    return "".join(pieces).strip()


def _extract_word_comments_from_document(documento) -> tuple[list[dict[str, str]], str | None]:
    if documento is None:
        return [], None

    file_name = (getattr(documento, "nombre_archivo", "") or "").strip()
    if not file_name.lower().endswith(".docx"):
        return [], "El analisis de comentarios automatico solo aplica para documentos .docx."

    try:
        stream, _headers = resolve_protected_document_stream(documento)
        stream.seek(0)
        with ZipFile(stream) as archive:
            if "word/comments.xml" not in archive.namelist():
                return [], "El documento Word no contiene comentarios insertados."

            root = ET.fromstring(archive.read("word/comments.xml"))
            comments: list[dict[str, str]] = []
            for comment in root.findall("w:comment", DOCX_COMMENT_NS):
                comment_id = comment.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id", "")
                comments.append(
                    {
                        "id": comment_id,
                        "author": comment.attrib.get(
                            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}author",
                            "",
                        ),
                        "date": comment.attrib.get(
                            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}date",
                            "",
                        ),
                        "text": _read_word_comment_text(comment),
                    }
                )
            return comments, None
    except ProtectedDocumentAccessError as exc:
        return [], str(exc)
    except (BadZipFile, ET.ParseError, KeyError, OSError, ValueError):
        return [], "No fue posible analizar los comentarios del documento Word seleccionado."

MODULE_TITLE = "Acreditacion"
MODULE_DESCRIPTION = "Gestiona la estructura CACES real del sistema y su relacion con ciclos y evidencia."
MODULE_TABS = [
    {"label": "Criterios", "url_name": "acreditacion-criterios-lista", "active_names": ["acreditacion-criterios-lista"]},
    {"label": "Subcriterios", "url_name": "acreditacion-subcriterios-lista", "active_names": ["acreditacion-subcriterios-lista"]},
    {"label": "Indicadores", "url_name": "acreditacion-indicadores-lista", "active_names": ["acreditacion-indicadores-lista", "acreditacion-indicadores-detalle"]},
    {"label": "Elementos fundamentales", "url_name": "acreditacion-elementos-lista", "active_names": ["acreditacion-elementos-lista"]},
    {"label": "Importar CACES", "url_name": "acreditacion-caces-importar", "active_names": ["acreditacion-caces-importar"]},
    {
        "label": "Matriz de registro",
        "url_name": "acreditacion-matriz-registro",
        "active_names": [
            "acreditacion-matriz-registro",
            "acreditacion-matriz-registro-subir",
            "acreditacion-matriz-evidencias",
        ],
    },
    {"label": "Matriz de acreditacion", "url_name": "acreditacion-matriz", "active_names": ["acreditacion-matriz"]},
    {"label": "Ciclos y autorizacion", "url_name": "acreditacion-ciclos-lista", "active_names": ["acreditacion-ciclos-lista", "acreditacion-ciclos-crear", "acreditacion-ciclos-detalle"]},
]
QUICK_CACES_IMPORT_ACTION = {
    "label": "Importar matriz CACES",
    "url_name": "acreditacion-caces-importar",
    "variant": "secondary",
}
STRUCTURE_TAB_NAMES = {
    "acreditacion-criterios-lista",
    "acreditacion-subcriterios-lista",
    "acreditacion-indicadores-lista",
    "acreditacion-elementos-lista",
    "acreditacion-caces-importar",
}
CYCLE_TAB_NAMES = {"acreditacion-ciclos-lista"}
MATRIX_TAB_NAMES = {"acreditacion-matriz-registro", "acreditacion-matriz"}


def _effective_role_names(request):
    session_roles = tuple(request.session.get("sig_roles", []) or [])
    operational_roles = tuple(request.session.get("sig_operational_roles", []) or [])
    return tuple(dict.fromkeys([*session_roles, *operational_roles]))


def _has_session_access(request, *, roles=(), permissions=()) -> bool:
    normalized_roles = _normalize_roles(_effective_role_names(request))
    normalized_permissions = _normalize_permissions(
        tuple(request.session.get("sig_permissions", []) or [])
    )
    if ROLE_ADMIN in normalized_roles:
        return True
    role_ok = bool(roles) and _has_matching_role(normalized_roles, tuple(roles))
    permission_ok = bool(permissions) and _has_matching_permission(
        normalized_permissions,
        tuple(permissions),
    )
    return role_ok or permission_ok


def _get_acreditacion_tabs(request):
    visible_tabs = []
    for tab in MODULE_TABS:
        url_name = tab["url_name"]
        if url_name in STRUCTURE_TAB_NAMES:
            allowed = _has_session_access(
                request,
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_ACREDITACION_GESTIONAR,),
            )
        elif url_name in CYCLE_TAB_NAMES:
            allowed = _has_session_access(
                request,
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR),
                permissions=("ciclos.gestionar",),
            )
        elif url_name in MATRIX_TAB_NAMES:
            allowed = _has_session_access(
                request,
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA, *AREA_ROLES),
                permissions=(PERM_ACREDITACION_VER, PERM_EVIDENCIAS_REGISTRAR, PERM_CONSULTA_VER),
            )
        else:
            allowed = True
        if allowed:
            visible_tabs.append(tab)
    return visible_tabs


def _can_access_cycles(request) -> bool:
    return _has_session_access(
        request,
        roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR),
        permissions=("ciclos.gestionar",),
    )


def _can_register_matrix_evidence(request) -> bool:
    return _has_session_access(
        request,
        roles=(ROLE_ADMIN, ROLE_QUALITY, *AREA_ROLES),
        permissions=(PERM_EVIDENCIAS_REGISTRAR,),
    )


def _can_access_evidence_detail(request) -> bool:
    return _has_session_access(
        request,
        roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_EVALUATOR, ROLE_CONSULTA),
        permissions=(PERM_EVALUACION_REVISAR, PERM_CONSULTA_VER),
    )


def _filter_matrix_registration_rows(rows, query: str | None):
    query = " ".join((query or "").strip().lower().split())
    if not query:
        return list(rows)

    filtered_rows = []
    for row in rows:
        criterio = row["criterio"]
        subcriterio = row["subcriterio"]
        indicador = row["indicador"]
        elemento = row["elemento"]
        haystack = " ".join(
            str(value or "").lower()
            for value in (
                criterio.codigo_criterio,
                getattr(criterio, "nombre_criterio", ""),
                subcriterio.codigo_subcriterio,
                getattr(subcriterio, "nombre_subcriterio", ""),
                indicador.codigo_indicador,
                indicador.nombre_indicador,
                elemento.codigo_elemento,
                elemento.nombre_elemento,
            )
        )
        if query in haystack:
            filtered_rows.append(row)
    return filtered_rows[:50]


def _find_matrix_target(rows, *, indicador_id=None, elemento_id=None):
    try:
        indicador_pk = int(indicador_id)
        elemento_pk = int(elemento_id)
    except (TypeError, ValueError):
        return None

    for row in rows:
        if row["indicador"].pk == indicador_pk and row["elemento"].pk == elemento_pk:
            return row
    return None


def _completion_bucket(completion_percent: int) -> str:
    if completion_percent >= 100:
        return "100"
    if completion_percent >= 75:
        return "75"
    if completion_percent >= 50:
        return "50"
    if completion_percent >= 25:
        return "25"
    if completion_percent > 0:
        return "10"
    return "0"


def _selected_indicator_ids_from_cycle_form(form):
    field = form.fields["indicadores_evaluar"]
    if form.is_bound:
        if form.data.get(form.add_prefix("seleccionar_todos_indicadores")):
            return list(field.queryset.values_list("pk", flat=True))
        return form.data.getlist(form.add_prefix("indicadores_evaluar"))
    return field.initial or []


def _summarize_matrix_rows(rows):
    total = len(rows)
    uploaded_rows = sum(1 for row in rows if row["has_evidence"])
    pending_review_rows = sum(1 for row in rows if row["has_pending_review"])
    pending_rows = max(total - uploaded_rows, 0)
    return {
        "total": total,
        "uploaded": uploaded_rows,
        "pending": pending_rows,
        "pending_review": pending_review_rows,
        "records": sum(row["record_count"] for row in rows),
        "completion_percent": int((uploaded_rows / total) * 100) if total else 0,
    }


def _reassigned_element_ids_for_request(request, *, ciclo):
    if ciclo is None:
        return None
    if _has_session_access(request, roles=(ROLE_ADMIN, ROLE_QUALITY)):
        return None

    user_id = request.session.get("sig_user_id")
    if not user_id:
        return None

    element_ids = set(
        TareaEvidencia.objects.filter(
            ciclo=ciclo,
            usuario_responsable_id=user_id,
            activo=True,
        )
        .exclude(asignado_por_id__isnull=True)
        .exclude(asignado_por_id=user_id)
        .values_list("elemento_fundamental_id", flat=True)
    )
    return element_ids or None


def _limit_dashboard_to_reassigned_scope(dashboard, request):
    selected_cycle = dashboard.get("selected_cycle")
    reassigned_element_ids = _reassigned_element_ids_for_request(
        request,
        ciclo=selected_cycle,
    )
    if reassigned_element_ids is None:
        dashboard["limited_to_reassigned_tasks"] = False
        return dashboard

    rows = [
        row
        for row in dashboard.get("matrix_registration_rows", [])
        if row["elemento"].pk in reassigned_element_ids
    ]
    dashboard["matrix_registration_rows"] = rows
    dashboard["missing_matrix_rows"] = [row for row in rows if not row["has_evidence"]]
    dashboard["matrix_registration_summary"] = _summarize_matrix_rows(rows)
    dashboard["recent_registered_evidences"] = [
        registro
        for registro in dashboard.get("recent_registered_evidences", [])
        if registro.elemento_fundamental_id in reassigned_element_ids
    ]
    dashboard["limited_to_reassigned_tasks"] = True
    dashboard["reassigned_element_ids"] = reassigned_element_ids
    return dashboard


class AcreditacionManageRequiredMixin(SigRoleOrPermissionRequiredMixin):
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY)
    allowed_permissions = (PERM_ACREDITACION_GESTIONAR,)
    access_denied_message = "No tienes acceso a la estructura de acreditacion."


class AcreditacionCycleRequiredMixin(SigRoleOrPermissionRequiredMixin):
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR)
    allowed_permissions = ("ciclos.gestionar",)
    access_denied_message = "No tienes acceso a la gestion de ciclos."


class AcreditacionMatrixRequiredMixin(SigRoleOrPermissionRequiredMixin):
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA, *AREA_ROLES)
    allowed_permissions = (PERM_ACREDITACION_VER, PERM_EVIDENCIAS_REGISTRAR, PERM_CONSULTA_VER)
    access_denied_message = "No tienes acceso a las matrices de acreditacion."


class AcreditacionMatrizRegistroRequiredMixin(SigRoleOrPermissionRequiredMixin):
    """Mixin para restringir acceso a matriz de registro a todos excepto evaluador y consulta."""
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, *AREA_ROLES)
    allowed_permissions = (PERM_ACREDITACION_VER, PERM_EVIDENCIAS_REGISTRAR)
    access_denied_message = "No tienes acceso a la matriz de registro. Este modulo no esta disponible para tu rol."


def _report_operation_error(*, request, exc: Exception, form=None, user_message: str):
    logger.exception("Operacion de acreditacion fallida", exc_info=exc)
    messages.error(request, user_message)
    if form is not None:
        form.add_error(None, user_message)


class AcreditacionBaseView(SigLoginRequiredMixin, TemplateView):
    template_name = ""
    page_title = ""
    page_description = ""
    page_status = "Operacion real"
    page_actions = []
    show_acreditacion_overview = True

    def get_page_actions(self):
        return self.page_actions

    def _actor(self):
        user_id = self.request.session.get("sig_user_id")
        if not user_id:
            return None
        return Usuario.objects.filter(pk=user_id).only("id_user", "primer_nombre", "primer_apellido").first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "module_title": MODULE_TITLE,
                "module_description": MODULE_DESCRIPTION,
                "module_tabs": _get_acreditacion_tabs(self.request),
                "page_title": self.page_title,
                "page_description": self.page_description,
                "page_status": self.page_status,
                "page_actions": self.get_page_actions(),
                "show_acreditacion_overview": self.show_acreditacion_overview,
                "current_url_name": self.request.resolver_match.url_name if self.request.resolver_match else "",
                "acreditacion_metrics": get_acreditacion_metrics(),
            }
        )
        context.update(kwargs)
        return context


class CriterioListView(AcreditacionManageRequiredMixin, AcreditacionBaseView):
    template_name = "acreditacion/criterio_list.html"
    page_title = "Criterios"
    page_description = "Carga y administra la estructura principal de criterios de acreditacion."
    page_actions = [QUICK_CACES_IMPORT_ACTION]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or CriterioForm()
        context["criterios"] = get_criterios_queryset()
        return context

    def post(self, request, *args, **kwargs):
        form = CriterioForm(request.POST)
        if form.is_valid():
            try:
                crear_criterio(form=form, actor=self._actor(), request=request)
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible registrar el criterio. Revisa la informacion y vuelve a intentar.",
                )
            else:
                messages.success(request, "Criterio registrado correctamente.")
                return redirect("acreditacion-criterios-lista")
        return self.render_to_response(self.get_context_data(form=form))


class SubcriterioListView(AcreditacionManageRequiredMixin, AcreditacionBaseView):
    template_name = "acreditacion/subcriterio_list.html"
    page_title = "Subcriterios"
    page_description = "Carga subcriterios asociados a cada criterio real del sistema."
    page_actions = [QUICK_CACES_IMPORT_ACTION]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or SubcriterioForm()
        context["subcriterios"] = get_subcriterios_queryset()
        context["criterios"] = get_criterios_queryset()
        return context

    def post(self, request, *args, **kwargs):
        form = SubcriterioForm(request.POST)
        if form.is_valid():
            try:
                crear_subcriterio(form=form, actor=self._actor(), request=request)
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible registrar el subcriterio. Revisa la informacion y vuelve a intentar.",
                )
            else:
                messages.success(request, "Subcriterio registrado correctamente.")
                return redirect("acreditacion-subcriterios-lista")
        return self.render_to_response(self.get_context_data(form=form))


class IndicadorListView(AcreditacionManageRequiredMixin, AcreditacionBaseView):
    template_name = "acreditacion/indicador_list.html"
    page_title = "Indicadores"
    page_description = "Carga indicadores y vincula su tipo, subcriterio y peso de evaluacion."
    page_actions = [QUICK_CACES_IMPORT_ACTION]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or IndicadorForm()
        context["indicadores"] = get_indicadores_queryset()
        return context

    def post(self, request, *args, **kwargs):
        form = IndicadorForm(request.POST)
        if form.is_valid():
            try:
                indicador = crear_indicador(form=form, actor=self._actor(), request=request)
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible registrar el indicador. Revisa la informacion y vuelve a intentar.",
                )
            else:
                messages.success(request, "Indicador registrado correctamente.")
                return redirect(f"{reverse('acreditacion-indicadores-detalle')}?indicador={indicador.pk}")
        return self.render_to_response(self.get_context_data(form=form))


class IndicadorDetailView(AcreditacionManageRequiredMixin, AcreditacionBaseView):
    template_name = "acreditacion/indicador_detail.html"
    page_title = "Detalle de indicador"
    page_description = "Gestiona la ficha operativa del indicador y su relacion con elementos fundamentales."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_indicator = kwargs.get("selected_indicator") or get_indicator_detail(
            self.request.GET.get("indicador")
        )
        context["selected_indicator"] = selected_indicator
        context["indicadores"] = get_indicadores_queryset()
        context["relation_form"] = kwargs.get("relation_form") or IndicadorElementoForm(
            initial={"indicador": selected_indicator} if selected_indicator else None,
            fixed_indicador=selected_indicator,
        )
        return context

    def post(self, request, *args, **kwargs):
        form = IndicadorElementoForm(request.POST)
        selected_indicator = get_indicator_detail(request.POST.get("indicador"))
        if selected_indicator is not None:
            form = IndicadorElementoForm(
                request.POST,
                fixed_indicador=selected_indicator,
            )
        if form.is_valid():
            try:
                vincular_indicador_elemento(
                    indicador=form.cleaned_data["indicador"],
                    elemento_fundamental=form.cleaned_data["elemento_fundamental"],
                    actor=self._actor(),
                    request=request,
                )
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible vincular el elemento al indicador.",
                )
            else:
                messages.success(request, "Elemento vinculado al indicador.")
                return redirect(f"{reverse('acreditacion-indicadores-detalle')}?indicador={form.cleaned_data['indicador'].pk}")
        return self.render_to_response(
            self.get_context_data(relation_form=form, selected_indicator=selected_indicator)
        )


class ElementoListView(AcreditacionManageRequiredMixin, AcreditacionBaseView):
    template_name = "acreditacion/elemento_list.html"
    page_title = "Elementos fundamentales"
    page_description = "Carga los elementos fundamentales que alimentan la evidencia documental."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or ElementoFundamentalForm()
        context["elementos"] = get_elementos_queryset()
        context["element_order_map"] = get_elemento_orden_visual_defaults()
        return context

    def post(self, request, *args, **kwargs):
        form = ElementoFundamentalForm(request.POST)
        if form.is_valid():
            try:
                crear_elemento(form=form, actor=self._actor(), request=request)
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible registrar el elemento fundamental.",
                )
            else:
                messages.success(request, "Elemento fundamental registrado correctamente.")
                return redirect("acreditacion-elementos-lista")
        return self.render_to_response(self.get_context_data(form=form))


class CacesCatalogSyncView(AcreditacionManageRequiredMixin, AcreditacionBaseView):
    template_name = "acreditacion/caces_catalog_sync.html"
    page_title = "Importar matriz CACES"
    page_description = "Crea criterios, subcriterios, indicadores y carpetas Graph desde la matriz CACES activa."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or CacesCatalogSyncForm()
        context["preview"] = get_caces_model_catalog_preview()
        context["sync_result"] = kwargs.get("sync_result")
        return context

    def post(self, request, *args, **kwargs):
        form = CacesCatalogSyncForm(request.POST)
        sync_result = None
        if form.is_valid():
            try:
                sync_result = sincronizar_catalogo_desde_modelo_caces(
                    actor=self._actor(),
                    request=request,
                    ensure_existing_storage=form.cleaned_data.get("asegurar_carpetas_existentes"),
                )
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message=(
                        "No fue posible sincronizar la matriz CACES. "
                        "Verifica la conexion a SQL Server y Microsoft Graph."
                    ),
                )
            else:
                messages.success(request, "Matriz CACES sincronizada correctamente.")
                form = CacesCatalogSyncForm()
        return self.render_to_response(
            self.get_context_data(form=form, sync_result=sync_result)
        )


class MatrizView(AcreditacionMatrixRequiredMixin, AcreditacionBaseView):
    template_name = "acreditacion/matriz.html"
    page_title = "Matriz de acreditacion"
    page_description = "Lectura real de la jerarquia criterio > subcriterio > indicador > elemento."
    show_acreditacion_overview = False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_cycle_id = self.request.GET.get("ciclo")
        selected_cycle = (
            CicloEvaluacion.objects.filter(pk=selected_cycle_id).first()
            if selected_cycle_id
            else None
        )
        context["matrix_rows"] = get_matrix_rows(ciclo_id=selected_cycle_id)
        context["selected_cycle"] = selected_cycle
        context["can_access_evidence_detail"] = _can_access_evidence_detail(self.request)
        return context


class MatrizRegistroView(AcreditacionMatrizRegistroRequiredMixin, AcreditacionBaseView):
    template_name = "acreditacion/matriz_registro.html"
    page_title = "Matriz de registro"
    page_description = (
        "Unifica la carga documental con el registro de evidencia sobre la misma matriz "
        "operativa de criterio, subcriterio, indicador y elemento."
    )
    page_actions = [
        {"label": "Ver matriz", "url_name": "acreditacion-matriz", "variant": "secondary"},
        {"label": "Asignar criterios", "url_name": "permisos-acceso-evaluacion", "variant": "secondary"},
        {"label": "Gestion documental", "url_name": "documentos-lista", "variant": "secondary"},
    ]
    show_acreditacion_overview = False

    def get_page_actions(self):
        actions = [{"label": "Ver matriz", "url_name": "acreditacion-matriz", "variant": "secondary"}]
        if _has_session_access(
            self.request,
            roles=(ROLE_ADMIN, ROLE_QUALITY),
        ):
            actions.append(
                {"label": "Asignar criterios", "url_name": "permisos-acceso-evaluacion", "variant": "secondary"}
            )
        if _has_session_access(
            self.request,
            roles=(ROLE_ADMIN, ROLE_QUALITY),
            permissions=("documentos.ver",),
        ):
            actions.append(
                {"label": "Gestion documental", "url_name": "documentos-lista", "variant": "secondary"}
            )
        return actions

    def _dashboard(self, **kwargs):
        ciclo_id = kwargs.get("selected_cycle_id")
        if ciclo_id is None:
            ciclo_id = self.request.GET.get("ciclo") or self.request.POST.get("ciclo")
        dashboard = get_matrix_registration_dashboard(ciclo_id=ciclo_id)
        return _limit_dashboard_to_reassigned_scope(dashboard, self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dashboard = self._dashboard(selected_cycle_id=kwargs.get("selected_cycle_id"))
        selected_cycle = dashboard.get("selected_cycle")
        summary = dashboard.get("matrix_registration_summary", {})
        completion_percent = int(summary.get("completion_percent", 0) or 0)
        summary["completion_bucket"] = _completion_bucket(completion_percent)
        context.update(dashboard)

        rows = dashboard.get("matrix_registration_rows", [])
        query = kwargs.get("search_query")
        if query is None:
            query = self.request.GET.get("q", "")
        filtered_rows = _filter_matrix_registration_rows(rows, query)

        selected_indicator_id = (
            kwargs.get("selected_indicator_id")
            or self.request.GET.get("indicador")
            or self.request.POST.get("indicador")
        )
        selected_element_id = (
            kwargs.get("selected_element_id")
            or self.request.GET.get("elemento")
            or self.request.POST.get("elemento_fundamental")
        )
        selected_target = _find_matrix_target(
            rows,
            indicador_id=selected_indicator_id,
            elemento_id=selected_element_id,
        )

        initial = {}
        if selected_target:
            initial["indicador"] = selected_target["indicador"]
            initial["elemento_fundamental"] = selected_target["elemento"]

        allowed_cycle_ids = [ciclo.pk for ciclo in dashboard.get("available_cycles", [])]
        form = kwargs.get("registration_form")
        if form is None:
            form = MatrixEvidenceRegistrationForm(
                initial=initial,
                ciclo_initial=selected_cycle,
                allowed_cycle_ids=allowed_cycle_ids,
            )

        can_access_cycles = _can_access_cycles(self.request)
        if not can_access_cycles:
            context["cycle_statuses"] = list(dashboard.get("available_cycles", []))
        context["can_access_cycles"] = can_access_cycles
        context["can_access_evidence_detail"] = _can_access_evidence_detail(self.request)
        context["can_register_matrix_evidence"] = _can_register_matrix_evidence(self.request)
        context["filtered_matrix_rows"] = filtered_rows
        context["search_query"] = query
        context["selected_target"] = selected_target
        context["registration_form"] = form
        context["show_upload_modal"] = bool(
            selected_target
            and _can_register_matrix_evidence(self.request)
            and (
                self.request.GET.get("modal") == "upload"
                or kwargs.get("registration_form") is not None
            )
        )
        context["missing_preview_rows"] = list(dashboard.get("missing_matrix_rows", []))[:8]
        context["page_highlights"] = [
            {
                "label": "Ciclo activo",
                "value": getattr(selected_cycle, "nombre", "Sin ciclo habilitado"),
            },
            {"label": "Subidas", "value": summary.get("uploaded", 0)},
            {"label": "Faltantes", "value": summary.get("pending", 0)},
            {"label": "Cobertura", "value": f"{summary.get('completion_percent', 0)}%"},
        ]
        return context

    def post(self, request, *args, **kwargs):
        if not _can_register_matrix_evidence(request):
            messages.error(request, "No tienes permisos para registrar evidencia en la matriz.")
            return redirect("acreditacion-matriz-registro")

        dashboard = self._dashboard(
            selected_cycle_id=request.GET.get("ciclo") or request.POST.get("ciclo")
        )
        selected_target = _find_matrix_target(
            dashboard.get("matrix_registration_rows", []),
            indicador_id=request.GET.get("indicador") or request.POST.get("indicador"),
            elemento_id=request.GET.get("elemento") or request.POST.get("elemento_fundamental"),
        )
        initial = {}
        if selected_target:
            initial["indicador"] = selected_target["indicador"]
            initial["elemento_fundamental"] = selected_target["elemento"]

        allowed_cycle_ids = [ciclo.pk for ciclo in dashboard.get("available_cycles", [])]
        form = MatrixEvidenceRegistrationForm(
            request.POST,
            request.FILES,
            initial=initial,
            ciclo_initial=dashboard.get("selected_cycle"),
            allowed_cycle_ids=allowed_cycle_ids,
        )
        if form.is_valid():
            allowed_element_ids = {
                row["elemento"].pk
                for row in dashboard.get("matrix_registration_rows", [])
            }
            if (
                dashboard.get("limited_to_reassigned_tasks")
                and form.cleaned_data["elemento_fundamental"].pk not in allowed_element_ids
            ):
                form.add_error(
                    "elemento_fundamental",
                    "Solo puedes registrar evidencia en las tareas reasignadas a tu usuario.",
                )
                return self.render_to_response(
                    self.get_context_data(
                        registration_form=form,
                        selected_cycle_id=request.GET.get("ciclo")
                        or request.POST.get("ciclo")
                        or getattr(dashboard.get("selected_cycle"), "pk", None),
                        selected_indicator_id=request.POST.get("indicador"),
                        selected_element_id=request.POST.get("elemento_fundamental"),
                        search_query=request.POST.get("q", ""),
                    )
                )
            try:
                registration_result = register_matrix_evidence(
                    ciclo=form.cleaned_data["ciclo"],
                    indicador=form.cleaned_data["indicador"],
                    elemento_fundamental=form.cleaned_data["elemento_fundamental"],
                    clasificacion=form.cleaned_data["clasificacion"],
                    uploaded_file=form.cleaned_data["archivo"],
                    descripcion_documento=form.cleaned_data.get("descripcion_documento"),
                    comentario=form.cleaned_data.get("comentario"),
                    actor=self._actor(),
                    request=request,
                )
            except (
                MatrixEvidenceRegistrationError,
                StructuredDocumentUploadError,
                GraphServiceError,
                AuthorizationServiceError,
                OSError,
                ValueError,
                IntegrityError,
                OperationalError,
                DatabaseError,
            ) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message=(
                        "No fue posible registrar la evidencia. "
                        "Verifica el ciclo, el archivo y la conexion con Microsoft Graph."
                    ),
                )
            else:
                messages.success(
                    request,
                    (
                        "Documento y evidencia registrados, aprobados internamente y enviados al evaluador."
                        if registration_result.get("auto_sent_to_evaluator")
                        else "Documento y evidencia registrados correctamente."
                    ),
                )
                return redirect(
                    (
                        f"{reverse('acreditacion-matriz-registro')}"
                        f"?ciclo={form.cleaned_data['ciclo'].pk}"
                        f"&indicador={form.cleaned_data['indicador'].pk}"
                        f"&elemento={form.cleaned_data['elemento_fundamental'].pk}"
                    )
                )

        return self.render_to_response(
            self.get_context_data(
                registration_form=form,
                selected_cycle_id=request.GET.get("ciclo")
                or request.POST.get("ciclo")
                or getattr(dashboard.get("selected_cycle"), "pk", None),
                selected_indicator_id=request.POST.get("indicador"),
                selected_element_id=request.POST.get("elemento_fundamental"),
                search_query=request.POST.get("q", ""),
            )
        )


class MatrizRegistroUploadView(AcreditacionMatrizRegistroRequiredMixin, AcreditacionBaseView):
    template_name = "acreditacion/matriz_registro_upload.html"
    page_title = "Subir informacion"
    page_description = "Registra el documento de evidencia del elemento seleccionado."
    page_actions = [
        {"label": "Volver a matriz", "url_name": "acreditacion-matriz-registro", "variant": "secondary"},
    ]
    show_acreditacion_overview = False

    def _dashboard(self, **kwargs):
        ciclo_id = kwargs.get("selected_cycle_id")
        if ciclo_id is None:
            ciclo_id = self.request.GET.get("ciclo") or self.request.POST.get("ciclo")
        dashboard = get_matrix_registration_dashboard(ciclo_id=ciclo_id)
        return _limit_dashboard_to_reassigned_scope(dashboard, self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dashboard = self._dashboard(selected_cycle_id=kwargs.get("selected_cycle_id"))
        selected_cycle = dashboard.get("selected_cycle")
        allowed_cycle_ids = [ciclo.pk for ciclo in dashboard.get("available_cycles", [])]
        rows = dashboard.get("matrix_registration_rows", [])
        query = kwargs.get("search_query")
        if query is None:
            query = self.request.GET.get("q", "")
        filtered_rows = _filter_matrix_registration_rows(rows, query)

        selected_indicator_id = (
            kwargs.get("selected_indicator_id")
            or self.request.GET.get("indicador")
            or self.request.POST.get("indicador")
        )
        selected_element_id = (
            kwargs.get("selected_element_id")
            or self.request.GET.get("elemento")
            or self.request.POST.get("elemento_fundamental")
        )
        selected_target = _find_matrix_target(
            rows,
            indicador_id=selected_indicator_id,
            elemento_id=selected_element_id,
        )

        initial = {}
        if selected_target:
            initial["indicador"] = selected_target["indicador"]
            initial["elemento_fundamental"] = selected_target["elemento"]

        form = kwargs.get("registration_form")
        if form is None:
            form = MatrixEvidenceRegistrationForm(
                initial=initial,
                ciclo_initial=selected_cycle,
                allowed_cycle_ids=allowed_cycle_ids,
            )

        context.update(dashboard)
        context.update(
            {
                "can_access_cycles": _can_access_cycles(self.request),
                "can_register_matrix_evidence": _can_register_matrix_evidence(self.request),
                "filtered_matrix_rows": filtered_rows,
                "search_query": query,
                "selected_target": selected_target,
                "registration_form": form,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        if not _can_register_matrix_evidence(request):
            messages.error(request, "No tienes permisos para registrar evidencia en la matriz.")
            return redirect("acreditacion-matriz-registro")

        dashboard = self._dashboard(
            selected_cycle_id=request.GET.get("ciclo") or request.POST.get("ciclo")
        )
        allowed_cycle_ids = [ciclo.pk for ciclo in dashboard.get("available_cycles", [])]
        form = MatrixEvidenceRegistrationForm(
            request.POST,
            request.FILES,
            ciclo_initial=dashboard.get("selected_cycle"),
            allowed_cycle_ids=allowed_cycle_ids,
        )
        if form.is_valid():
            allowed_element_ids = {
                row["elemento"].pk
                for row in dashboard.get("matrix_registration_rows", [])
            }
            if (
                dashboard.get("limited_to_reassigned_tasks")
                and form.cleaned_data["elemento_fundamental"].pk not in allowed_element_ids
            ):
                form.add_error(
                    "elemento_fundamental",
                    "Solo puedes registrar evidencia en las tareas reasignadas a tu usuario.",
                )
                return self.render_to_response(
                    self.get_context_data(
                        registration_form=form,
                        selected_cycle_id=request.GET.get("ciclo")
                        or request.POST.get("ciclo")
                        or getattr(dashboard.get("selected_cycle"), "pk", None),
                        selected_indicator_id=request.POST.get("indicador"),
                        selected_element_id=request.POST.get("elemento_fundamental"),
                        search_query=request.POST.get("q", ""),
                    )
                )
            try:
                registration_result = register_matrix_evidence(
                    ciclo=form.cleaned_data["ciclo"],
                    indicador=form.cleaned_data["indicador"],
                    elemento_fundamental=form.cleaned_data["elemento_fundamental"],
                    clasificacion=form.cleaned_data["clasificacion"],
                    uploaded_file=form.cleaned_data["archivo"],
                    descripcion_documento=form.cleaned_data.get("descripcion_documento"),
                    comentario=form.cleaned_data.get("comentario"),
                    actor=self._actor(),
                    request=request,
                )
            except (
                MatrixEvidenceRegistrationError,
                StructuredDocumentUploadError,
                GraphServiceError,
                AuthorizationServiceError,
                OSError,
                ValueError,
                IntegrityError,
                OperationalError,
                DatabaseError,
            ) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message=(
                        "No fue posible registrar la evidencia. "
                        "Verifica el ciclo, el archivo y la conexion con Microsoft Graph."
                    ),
                )
            else:
                messages.success(
                    request,
                    (
                        "Documento y evidencia registrados, aprobados internamente y enviados al evaluador."
                        if registration_result.get("auto_sent_to_evaluator")
                        else "Documento y evidencia registrados correctamente en la matriz de registro."
                    ),
                )
                return redirect(
                    (
                        f"{reverse('acreditacion-matriz-registro')}"
                        f"?ciclo={form.cleaned_data['ciclo'].pk}"
                        f"&indicador={form.cleaned_data['indicador'].pk}"
                        f"&elemento={form.cleaned_data['elemento_fundamental'].pk}"
                    )
                )

        return self.render_to_response(
            self.get_context_data(
                registration_form=form,
                selected_cycle_id=request.GET.get("ciclo")
                or request.POST.get("ciclo")
                or getattr(dashboard.get("selected_cycle"), "pk", None),
                selected_indicator_id=request.POST.get("indicador"),
                selected_element_id=request.POST.get("elemento_fundamental"),
                search_query=request.POST.get("q", ""),
            )
        )


class CicloListView(AcreditacionCycleRequiredMixin, AcreditacionBaseView):
    template_name = "acreditacion/ciclo_list.html"
    page_title = "Ciclos y documento de autorizacion"
    page_description = "En una sola pantalla registras el ciclo, cargas su autorizacion y consultas el documento asociado."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session_roles = tuple(self.request.session.get("sig_roles", []) or [])
        operational_roles = tuple(self.request.session.get("sig_operational_roles", []) or [])
        effective_roles = tuple(dict.fromkeys([*session_roles, *operational_roles]))
        has_admin_role = any(_is_admin_role(role) for role in effective_roles)
        has_quality_role = any(_is_quality_role(role) for role in effective_roles)
        has_rector_role = any(_is_rector_role(role) for role in effective_roles)
        # Quality operations have priority over rector-only restrictions on this screen.
        context["can_create_cycles"] = has_admin_role or has_quality_role or not has_rector_role
        context["is_quality_actor"] = has_admin_role or has_quality_role
        form = kwargs.get("form") or CicloEvaluacionForm(
            usuario_id=self.request.session.get("sig_user_id"),
            assignment_id=self.request.session.get("sig_active_assignment_id"),
        )
        context["form"] = form
        context["indicator_selection_tree"] = get_indicator_selection_tree(
            selected_indicator_ids=_selected_indicator_ids_from_cycle_form(form)
        )
        context["select_all_indicators"] = bool(
            form.data.get(form.add_prefix("seleccionar_todos_indicadores"))
            if form.is_bound
            else form.fields["seleccionar_todos_indicadores"].initial
        )
        ciclos = attach_cycle_indicator_scope(
            attach_cycle_authorization_status(get_ciclos_queryset())
        )
        context["ciclos"] = ciclos
        context["ciclos_summary"] = {
            "total": len(ciclos),
            "con_autorizacion": sum(1 for ciclo in ciclos if getattr(ciclo, "has_authorization_document", False)),
            "aprobados": sum(
                1
                for ciclo in ciclos
                if (getattr(getattr(ciclo, "estado", None), "descripcion", "") or "").strip().upper() == "APROBADO"
            ),
            "habilitados": sum(1 for ciclo in ciclos if getattr(ciclo, "document_upload_enabled", False)),
        }
        return context

    def post(self, request, *args, **kwargs):
        session_roles = tuple(request.session.get("sig_roles", []) or [])
        operational_roles = tuple(request.session.get("sig_operational_roles", []) or [])
        effective_roles = tuple(dict.fromkeys([*session_roles, *operational_roles]))
        has_admin_role = any(_is_admin_role(role) for role in effective_roles)
        has_quality_role = any(_is_quality_role(role) for role in effective_roles)
        has_rector_role = any(_is_rector_role(role) for role in effective_roles)
        if has_rector_role and not (has_admin_role or has_quality_role):
            messages.warning(request, "El rol RECTOR solo puede revisar, aprobar o rechazar ciclos.")
            return redirect("acreditacion-ciclos-lista")

        form = CicloEvaluacionForm(
            request.POST,
            request.FILES,
            usuario_id=request.session.get("sig_user_id"),
            assignment_id=request.session.get("sig_active_assignment_id"),
        )
        if form.is_valid():
            try:
                crear_ciclo(form=form, actor=self._actor(), request=request)
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                user_message = str(exc).strip() or (
                    "No fue posible registrar el ciclo y su documento. Verifica los datos, la conexion a SQL Server y Microsoft Graph."
                )
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message=user_message,
                )
            else:
                messages.success(request, "Ciclo y documento de autorizacion registrados correctamente.")
                return redirect("acreditacion-ciclos-lista")
        else:
            messages.error(
                request,
                "No fue posible registrar el ciclo. Revisa los campos obligatorios y vuelve a adjuntar el documento de autorizacion.",
            )
        return self.render_to_response(self.get_context_data(form=form))


class CicloCreateView(RedirectView):
    pattern_name = "acreditacion-ciclos-lista"
    permanent = False


class CicloDetailView(AcreditacionCycleRequiredMixin, AcreditacionBaseView):
    template_name = "acreditacion/ciclo_detail.html"
    page_title = "Informacion del ciclo"
    page_description = "Consulta el estado del ciclo y el documento de autorizacion asociado en una subpantalla dedicada."
    page_actions = [
        {"label": "Volver a ciclos", "url_name": "acreditacion-ciclos-lista", "variant": "secondary"},
    ]
    show_acreditacion_overview = False

    def _effective_roles(self, request):
        session_roles = tuple(request.session.get("sig_roles", []) or [])
        operational_roles = tuple(request.session.get("sig_operational_roles", []) or [])
        return tuple(dict.fromkeys([*session_roles, *operational_roles]))

    def _is_quality(self, request) -> bool:
        return any(_is_admin_role(role) or _is_quality_role(role) for role in self._effective_roles(request))

    def _is_rector(self, request) -> bool:
        return any(_is_rector_role(role) for role in self._effective_roles(request))

    def _allowed_states_for_actor(self, request) -> tuple[str, ...]:
        if self._is_quality(request):
            return ESTADOS_FLUJO_CICLO
        if self._is_rector(request):
            return ESTADOS_RECTOR_DECISION
        return ESTADOS_FLUJO_CICLO

    def _get_estado_by_normalized_name(self, normalized_name: str):
        for estado in EstadoCiclo.objects.filter(activo=True).only("id_estado_ciclo", "descripcion"):
            current_name = (getattr(estado, "descripcion", "") or "").strip().upper().replace(" ", "_")
            if current_name == normalized_name:
                return estado
        return None

    def _ensure_rector_review_state(self, request, ciclo):
        if self._is_quality(request):
            return ciclo
        if not self._is_rector(request):
            return ciclo

        estado_actual = (getattr(getattr(ciclo, "estado", None), "descripcion", "") or "").strip().upper().replace(" ", "_")
        if estado_actual != "ENVIADO":
            return ciclo

        estado_en_ejecucion = self._get_estado_by_normalized_name("EN_EJECUCION")
        if estado_en_ejecucion is None:
            return ciclo

        try:
            actualizar_estado_ciclo(
                ciclo=ciclo,
                estado=estado_en_ejecucion,
                observacion_aprobacion=None,
                actor=self._actor(),
                request=request,
            )
            messages.info(request, "El ciclo cambio a EN_EJECUCION para revision del Rector.")
        except (ValueError, IntegrityError, OperationalError, DatabaseError):
            return ciclo

        return get_ciclo_detail(ciclo.pk) or ciclo

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ciclo = kwargs.get("ciclo")
        allowed_states = self._allowed_states_for_actor(self.request)
        reviewer_comments, quality_response = _split_observation_blocks(
            getattr(ciclo, "observacion_aprobacion", None)
        )
        word_comments, word_comments_error = _extract_word_comments_from_document(
            getattr(ciclo, "authorization_document", None)
        )
        context["ciclo"] = ciclo
        context["is_rector_actor"] = self._is_rector(self.request)
        context["is_quality_actor"] = self._is_quality(self.request)
        context["reviewer_comments"] = reviewer_comments
        context["reviewer_comment_items"] = _extract_comment_items(reviewer_comments)
        context["word_document_comments"] = word_comments
        context["word_document_comments_error"] = word_comments_error
        context["has_word_document_comments"] = bool(word_comments)
        context["quality_response"] = quality_response
        context["ciclo_form"] = kwargs.get("ciclo_form") or CicloEstadoAutorizacionForm(
            initial={
                "ciclo_id": ciclo.pk,
                "estado": ciclo.estado,
                "observacion_aprobacion": quality_response or ciclo.observacion_aprobacion,
                "descripcion_documento": "",
            },
            allowed_states=allowed_states,
        )
        return context

    def get(self, request, ciclo_id, *args, **kwargs):
        ciclo = get_ciclo_detail(ciclo_id)
        if ciclo is None:
            raise Http404("El ciclo no existe.")
        ciclo = self._ensure_rector_review_state(request, ciclo)
        return self.render_to_response(self.get_context_data(ciclo=ciclo))

    def post(self, request, ciclo_id, *args, **kwargs):
        ciclo = get_ciclo_detail(ciclo_id)
        if ciclo is None:
            raise Http404("El ciclo no existe.")

        form = CicloEstadoAutorizacionForm(
            request.POST,
            request.FILES,
            allowed_states=self._allowed_states_for_actor(request),
        )
        if form.is_valid():
            if form.cleaned_data["ciclo_id"] != ciclo.pk:
                form.add_error(None, "El ciclo enviado no coincide con la solicitud.")
                return self.render_to_response(self.get_context_data(ciclo=ciclo, ciclo_form=form))

            try:
                with transaction.atomic():
                    observacion_payload = form.cleaned_data.get("observacion_aprobacion")
                    if self._is_quality(request):
                        observacion_payload = _build_quality_observation_payload(
                            previous_value=getattr(ciclo, "observacion_aprobacion", None),
                            submitted_value=observacion_payload,
                        )

                    actualizar_estado_ciclo(
                        ciclo=ciclo,
                        estado=form.cleaned_data["estado"],
                        observacion_aprobacion=observacion_payload,
                        actor=self._actor(),
                        request=request,
                    )

                    uploaded_file = form.cleaned_data.get("archivo")
                    if uploaded_file:
                        revision_result = upload_cycle_authorization_revision(
                            ciclo=ciclo,
                            descripcion_documento=form.cleaned_data.get("descripcion_documento"),
                            uploaded_file=uploaded_file,
                            actor=self._actor(),
                            request=request,
                        )
                        if revision_result["documento"].pk != ciclo.documento_autorizacion_id:
                            ciclo.documento_autorizacion = revision_result["documento"]
                            ciclo.save(update_fields=["documento_autorizacion"])
                        messages.success(request, "Estado del ciclo y nueva version del documento registrados correctamente.")
                    else:
                        messages.success(request, f"Estado actualizado a {form.cleaned_data['estado'].descripcion}.")
                return redirect("acreditacion-ciclos-lista")
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                user_message = str(exc).strip() or "No fue posible guardar el estado y la version del documento."
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message=user_message,
                )

        ciclo = get_ciclo_detail(ciclo_id)
        return self.render_to_response(
            self.get_context_data(
                ciclo=ciclo,
                ciclo_form=form,
            )
        )


class CicloEstadoUpdateView(AcreditacionCycleRequiredMixin, View):
    def _actor(self):
        user_id = self.request.session.get("sig_user_id")
        if not user_id:
            return None
        return Usuario.objects.filter(pk=user_id).only("id_user", "primer_nombre", "primer_apellido").first()

    def _is_quality(self, request) -> bool:
        session_roles = tuple(request.session.get("sig_roles", []) or [])
        operational_roles = tuple(request.session.get("sig_operational_roles", []) or [])
        effective_roles = tuple(dict.fromkeys([*session_roles, *operational_roles]))
        return any(_is_admin_role(role) or _is_quality_role(role) for role in effective_roles)

    def _is_rector(self, request) -> bool:
        session_roles = tuple(request.session.get("sig_roles", []) or [])
        operational_roles = tuple(request.session.get("sig_operational_roles", []) or [])
        effective_roles = tuple(dict.fromkeys([*session_roles, *operational_roles]))
        return any(_is_rector_role(role) for role in effective_roles)

    def post(self, request, ciclo_id, *args, **kwargs):
        ciclo = CicloEvaluacion.objects.select_related("estado").filter(pk=ciclo_id).first()
        if ciclo is None:
            raise Http404("El ciclo no existe.")

        if self._is_quality(request):
            allowed_states = ESTADOS_FLUJO_CICLO
        elif self._is_rector(request):
            allowed_states = ESTADOS_RECTOR_DECISION
        else:
            allowed_states = ESTADOS_FLUJO_CICLO

        form = CicloEstadoUpdateForm(
            request.POST,
            allowed_states=allowed_states,
        )
        if form.is_valid():
            if form.cleaned_data["ciclo_id"] != ciclo.pk:
                form.add_error(None, "El ciclo enviado no coincide con la solicitud.")
            else:
                try:
                    actualizar_estado_ciclo(
                        ciclo=ciclo,
                        estado=form.cleaned_data["estado"],
                        observacion_aprobacion=form.cleaned_data.get("observacion_aprobacion"),
                        actor=self._actor(),
                        request=request,
                    )
                except (ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                    _report_operation_error(
                        request=request,
                        exc=exc,
                        user_message="No fue posible actualizar el estado del ciclo.",
                    )
                else:
                    messages.success(request, f"Estado actualizado a {form.cleaned_data['estado'].descripcion}.")
                return redirect("acreditacion-ciclos-lista")

        messages.error(request, "No fue posible actualizar el estado del ciclo.")
        return redirect("acreditacion-ciclos-lista")
