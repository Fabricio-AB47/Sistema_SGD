import logging
import json
import shutil
from pathlib import Path

from django.contrib import messages
from django.db import IntegrityError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import RedirectView, TemplateView
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.acreditacion.models import ElementoFundamental
from apps.core.mixins import SigLoginRequiredMixin, SigRoleOrPermissionRequiredMixin
from apps.core.services.navigation_service import (
    PERM_CONSULTA_VER,
    ROLE_ADMIN,
    ROLE_CONSULTA,
    ROLE_QUALITY,
    ROLE_RECTOR,
)
from apps.core.views.admin_page import AdminPageView
from apps.documentos.forms import DocxLaboratoryForm, StructuredDocumentUploadForm
from apps.documentos.selectors import (
    get_documento_for_access,
    get_document_access_logs_queryset,
    get_document_classifications_queryset,
    get_document_filter_queryset,
    get_document_management_summary,
    get_document_versions_queryset,
    get_documento_admin_detail,
    get_documentos_admin_queryset,
    get_approved_cycles_queryset,
    get_recent_cycle_upload_statuses,
    get_structured_documents_queryset,
)
from apps.documentos.services import (
    ProtectedDocumentAccessError,
    StructuredDocumentUploadError,
    build_docx_lab_result,
    cleanup_docx_lab_result,
    registrar_acceso_documento,
    load_docx_lab_result,
    resolve_graph_document_url,
    resolve_protected_document_stream,
    supports_inline_preview,
    upload_structured_document,
)
from apps.integraciones.services.graph_service import GraphServiceError
from apps.usuarios.models import Usuario


logger = logging.getLogger(__name__)

MODULE_TITLE = "Documentos"
MODULE_DESCRIPTION = "Gestiona documentos, versionamiento, accesos y autorizaciones de ciclo."
MODULE_TAB_LAB_TITLE = "Laboratorio DOCX"
DEFAULT_BINARY_CONTENT_TYPE = "application/octet-stream"
ERROR_DOCUMENT_NOT_FOUND = "El documento no existe."
MODULE_TABS = [
    {"label": "Clasificaciones documentales", "url_name": "documentos-clasificaciones-lista", "active_names": ["documentos-clasificaciones-lista"]},
    {"label": "Documentos", "url_name": "documentos-lista", "active_names": ["documentos-lista"]},
    {"label": "Detalle de documento", "url_name": "documentos-detalle", "active_names": ["documentos-detalle"]},
    {"label": "Historial de versiones", "url_name": "documentos-versiones", "active_names": ["documentos-versiones"]},
    {"label": "Historial de accesos", "url_name": "documentos-accesos", "active_names": ["documentos-accesos"]},
    {"label": MODULE_TAB_LAB_TITLE, "url_name": "documentos-docx-lab", "active_names": ["documentos-docx-lab"]},
]


def module_page(**kwargs):
    return AdminPageView.as_view(
        module_title=MODULE_TITLE,
        module_description=MODULE_DESCRIPTION,
        module_tabs=MODULE_TABS,
        **kwargs,
    )


def _report_document_error(*, request, exc: Exception, form=None, user_message: str):
    logger.exception("Operacion documental fallida", exc_info=exc)
    messages.error(request, user_message)
    if form is not None:
        form.add_error(None, user_message)


class DocumentosBaseView(SigRoleOrPermissionRequiredMixin, TemplateView):
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA)
    allowed_permissions = ("documentos.ver", PERM_CONSULTA_VER)
    access_denied_message = "No tienes acceso a gestion documental."
    template_name = ""
    page_title = ""
    page_description = ""
    page_status = "Operacion real"
    page_actions = []

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
                "module_tabs": MODULE_TABS,
                "page_title": self.page_title,
                "page_description": self.page_description,
                "page_status": self.page_status,
                "page_actions": self.page_actions,
                "current_url_name": self.request.resolver_match.url_name if self.request.resolver_match else "",
                "documentos_summary": get_document_management_summary(),
            }
        )
        context.update(kwargs)
        return context


class DocumentClassificationListView(DocumentosBaseView):
    template_name = "documentos/clasificacion_documento_list.html"
    page_title = "Clasificaciones documentales"
    page_description = "Consulta la configuracion real de clasificaciones documentales y su uso en el repositorio."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["classifications"] = get_document_classifications_queryset()
        return context


class DocumentListView(DocumentosBaseView):
    template_name = "documentos/documento_list.html"
    page_title = "Documentos"
    page_description = "Consulta el inventario documental real, su clasificacion, versionamiento y uso operativo."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["documents"] = get_documentos_admin_queryset()[:100]
        return context


class DocumentDetailView(DocumentosBaseView):
    template_name = "documentos/documento_detail.html"
    page_title = "Detalle de documento"
    page_description = "Visualiza metadata documental, estado de proteccion, versionamiento y accesos recientes."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        documento_id = self.request.GET.get("documento")
        selected_document = get_documento_admin_detail(documento_id)
        context["document_options"] = get_document_filter_queryset()
        context["selected_document"] = selected_document
        context["recent_versions"] = (
            get_document_versions_queryset(documento_id=selected_document.pk)[:10]
            if selected_document
            else []
        )
        context["recent_access_logs"] = (
            get_document_access_logs_queryset(documento_id=selected_document.pk)[:10]
            if selected_document
            else []
        )
        return context


class DocumentVersionListView(DocumentosBaseView):
    template_name = "documentos/version_documento_list.html"
    page_title = "Historial de versiones"
    page_description = "Consulta el versionamiento real de los documentos almacenados en el sistema."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        documento_id = self.request.GET.get("documento")
        context["document_options"] = get_document_filter_queryset()
        context["selected_document"] = get_documento_admin_detail(documento_id) if documento_id else None
        context["versions"] = get_document_versions_queryset(documento_id=documento_id)[:100]
        return context


class DocumentAccessLogListView(DocumentosBaseView):
    template_name = "documentos/documento_acceso_log.html"
    page_title = "Historial de accesos"
    page_description = "Revisa la trazabilidad real de accesos sobre documentos protegidos."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        documento_id = self.request.GET.get("documento")
        context["document_options"] = get_document_filter_queryset()
        context["selected_document"] = get_documento_admin_detail(documento_id) if documento_id else None
        context["access_logs"] = get_document_access_logs_queryset(documento_id=documento_id)[:100]
        return context


class AuthorizationCycleView(SigLoginRequiredMixin, RedirectView):
    pattern_name = "acreditacion-ciclos-lista"
    permanent = False


class DocumentUploadView(DocumentosBaseView):
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY)
    allowed_permissions = ("documentos.subir", "documentos.versionar")
    access_denied_message = "No tienes acceso para subir documentos."
    template_name = "documentos/documento_upload.html"
    page_title = "Subir documento"
    page_description = (
        "Carga documentacion estructurada por indicador y elemento. "
        "Solo se habilita cuando el ciclo esta APROBADO y ya tiene documento de autorizacion."
    )
    page_actions = [
        {"label": "Ciclos de evaluacion", "url_name": "acreditacion-ciclos-lista", "variant": "secondary"},
        {"label": MODULE_TAB_LAB_TITLE, "url_name": "documentos-docx-lab", "variant": "ghost"},
    ]

    def _get_cycle_initial(self):
        ciclo_id = self.request.GET.get("ciclo")
        if not ciclo_id:
            return None
        return get_approved_cycles_queryset().filter(pk=ciclo_id).first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        approved_cycles = get_approved_cycles_queryset()
        has_structure = ElementoFundamental.objects.exclude(indicador_id__isnull=True).exists()
        context["upload_form"] = kwargs.get("upload_form") or StructuredDocumentUploadForm(
            ciclo_initial=self._get_cycle_initial()
        )
        context["approved_cycles_count"] = approved_cycles.count()
        context["has_upload_structure"] = has_structure
        context["can_upload_documents"] = context["approved_cycles_count"] > 0 and has_structure
        context["cycle_statuses"] = get_recent_cycle_upload_statuses()
        context["documents"] = get_structured_documents_queryset()[:20]
        return context

    def post(self, request, *args, **kwargs):
        form = StructuredDocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                upload_structured_document(
                    ciclo=form.cleaned_data["ciclo"],
                    indicador=form.cleaned_data["indicador"],
                    elemento_fundamental=form.cleaned_data["elemento_fundamental"],
                    clasificacion=form.cleaned_data["clasificacion"],
                    uploaded_file=form.cleaned_data["archivo"],
                    descripcion_documento=form.cleaned_data.get("descripcion_documento"),
                    actor=self._actor(),
                    request=request,
                )
            except (StructuredDocumentUploadError, GraphServiceError, OSError, ValueError, IntegrityError) as exc:
                _report_document_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible cargar el documento. Verifica el archivo, la estructura y la conexion a Microsoft Graph.",
                )
            else:
                messages.success(request, "Documento cargado y versionado correctamente.")
                return redirect("documentos-subir")
        return self.render_to_response(self.get_context_data(upload_form=form))


class DocxLaboratoryView(DocumentosBaseView):
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY)
    allowed_permissions = ("documentos.subir", "documentos.versionar")
    access_denied_message = "No tienes acceso al laboratorio documental."
    template_name = "documentos/docx_lab.html"
    page_title = MODULE_TAB_LAB_TITLE
    page_description = "Carga un DOCX de prueba, extrae comentarios y genera una reconstruccion editable para validar el flujo."
    page_actions = [
        {"label": "Subir documento", "url_name": "documentos-subir", "variant": "secondary"},
    ]

    session_token_key = "docx_lab_result_token"

    def _result_token(self):
        return self.request.session.get(self.session_token_key)

    def _cleanup_current_result(self):
        cleanup_docx_lab_result(self._result_token())
        if self.session_token_key in self.request.session:
            del self.request.session[self.session_token_key]
            self.request.session.modified = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lab_form"] = kwargs.get("lab_form") or DocxLaboratoryForm()
        context["lab_result"] = load_docx_lab_result(self._result_token())
        if context["lab_result"] is not None:
            context["lab_result_json"] = json.dumps(context["lab_result"], ensure_ascii=False, indent=2)
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get("clear") == "1":
            self._cleanup_current_result()
            messages.success(request, "El resultado temporal del laboratorio fue eliminado.")
            return redirect("documentos-docx-lab")

        if request.GET.get("download") == "1":
            result = load_docx_lab_result(self._result_token())
            if not result:
                messages.error(request, "No existe una reconstruccion DOCX disponible para descargar.")
                return redirect("documentos-docx-lab")

            reconstructed_path = Path(result["reconstructed_path"])
            if not reconstructed_path.exists():
                messages.error(request, "La reconstruccion DOCX ya no esta disponible en disco.")
                self._cleanup_current_result()
                return redirect("documentos-docx-lab")

            return FileResponse(
                reconstructed_path.open("rb"),
                as_attachment=True,
                filename=reconstructed_path.name,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        form = DocxLaboratoryForm(request.POST, request.FILES)
        if form.is_valid():
            previous_token = self._result_token()
            try:
                result = build_docx_lab_result(uploaded_file=form.cleaned_data["archivo"])
            except Exception as exc:
                _report_document_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible procesar el DOCX de prueba.",
                )
            else:
                request.session[self.session_token_key] = result["result_token"]
                request.session.modified = True
                if previous_token and previous_token != result["result_token"]:
                    cleanup_docx_lab_result(previous_token)
                messages.success(request, "El DOCX se analizo y se genero una reconstruccion de prueba.")
                return redirect("documentos-docx-lab")

        return self.render_to_response(self.get_context_data(lab_form=form))


class ProtectedDocumentAccessView(SigLoginRequiredMixin, View):
    def _actor(self):
        user_id = self.request.session.get("sig_user_id")
        if not user_id:
            return None
        return Usuario.objects.filter(pk=user_id).only("id_user", "primer_nombre", "primer_apellido").first()

    def get(self, request, documento_id, *args, **kwargs):
        actor = self._actor()
        documento = get_documento_for_access(documento_id, actor=actor)
        if documento is None:
            raise Http404(ERROR_DOCUMENT_NOT_FOUND)

        try:
            content_stream, headers = resolve_protected_document_stream(documento)
        except ProtectedDocumentAccessError as exc:
            _report_document_error(
                request=request,
                exc=exc,
                user_message="No fue posible abrir el documento protegido.",
            )
            return redirect("acreditacion-ciclos-lista")

        registrar_acceso_documento(
            documento=documento,
            actor=actor,
            request=request,
            accion="VIEW_DOCUMENTO_PROTEGIDO",
            detalle=f"Se accedio al documento protegido {documento.nombre_archivo}.",
        )
        return FileResponse(
            content_stream,
            as_attachment=False,
            filename=documento.nombre_archivo,
            content_type=(
                documento.mime_type
                or headers.get("Content-Type")
                or DEFAULT_BINARY_CONTENT_TYPE
            ),
        )


class ProtectedDocumentAvailabilityView(ProtectedDocumentAccessView):
    def get(self, request, documento_id, *args, **kwargs):
        actor = self._actor()
        documento = get_documento_for_access(documento_id, actor=actor)
        if documento is None:
            return JsonResponse(
                {
                    "available": False,
                    "message": "Archivo no encontrado.",
                }
            )

        try:
            content_stream, _headers = resolve_protected_document_stream(documento)
        except ProtectedDocumentAccessError as exc:
            logger.warning(
                "No fue posible validar disponibilidad del documento protegido %s: %s",
                documento_id,
                exc,
            )
            return JsonResponse(
                {
                    "available": False,
                    "message": "Archivo no encontrado o no disponible.",
                }
            )

        content_stream.close()
        return JsonResponse(
            {
                "available": True,
                "message": "Archivo disponible.",
            }
        )


@method_decorator(xframe_options_sameorigin, name="dispatch")
class ProtectedDocumentPreviewView(ProtectedDocumentAccessView):
    def get(self, request, documento_id, *args, **kwargs):
        actor = self._actor()
        documento = get_documento_for_access(documento_id, actor=actor)
        if documento is None:
            raise Http404(ERROR_DOCUMENT_NOT_FOUND)

        if not supports_inline_preview(documento):
            messages.error(
                request,
                "El formato del documento no soporta previsualizacion inline. Usa la opcion de abrir en Graph.",
            )
            return redirect("acreditacion-ciclos-lista")

        try:
            content_stream, headers = resolve_protected_document_stream(documento)
        except ProtectedDocumentAccessError as exc:
            _report_document_error(
                request=request,
                exc=exc,
                user_message="No fue posible previsualizar el documento protegido.",
            )
            return redirect("acreditacion-ciclos-lista")

        registrar_acceso_documento(
            documento=documento,
            actor=actor,
            request=request,
            accion="PREVIEW_DOCUMENTO_PROTEGIDO",
            detalle=f"Se previsualizo el documento protegido {documento.nombre_archivo}.",
        )
        return FileResponse(
            content_stream,
            as_attachment=False,
            filename=documento.nombre_archivo,
            content_type=(
                documento.mime_type
                or headers.get("Content-Type")
                or DEFAULT_BINARY_CONTENT_TYPE
            ),
        )


class ProtectedDocumentDownloadView(ProtectedDocumentAccessView):
    def get(self, request, documento_id, *args, **kwargs):
        actor = self._actor()
        documento = get_documento_for_access(documento_id, actor=actor)
        if documento is None:
            raise Http404(ERROR_DOCUMENT_NOT_FOUND)

        try:
            content_stream, headers = resolve_protected_document_stream(documento)
        except ProtectedDocumentAccessError as exc:
            _report_document_error(
                request=request,
                exc=exc,
                user_message="No fue posible descargar el documento protegido.",
            )
            return redirect("acreditacion-ciclos-lista")

        registrar_acceso_documento(
            documento=documento,
            actor=actor,
            request=request,
            accion="DOWNLOAD_DOCUMENTO_PROTEGIDO",
            detalle=f"Se descargo el documento protegido {documento.nombre_archivo}.",
        )
        return FileResponse(
            content_stream,
            as_attachment=True,
            filename=documento.nombre_archivo,
            content_type=(
                documento.mime_type
                or headers.get("Content-Type")
                or DEFAULT_BINARY_CONTENT_TYPE
            ),
        )


class ProtectedDocumentGraphRedirectView(SigLoginRequiredMixin, View):
    def _actor(self):
        user_id = self.request.session.get("sig_user_id")
        if not user_id:
            return None
        return Usuario.objects.filter(pk=user_id).only("id_user", "primer_nombre", "primer_apellido").first()

    def get(self, request, documento_id, *args, **kwargs):
        actor = self._actor()
        documento = get_documento_for_access(documento_id, actor=actor)
        if documento is None:
            raise Http404(ERROR_DOCUMENT_NOT_FOUND)

        try:
            graph_url = resolve_graph_document_url(documento)
        except ProtectedDocumentAccessError as exc:
            _report_document_error(
                request=request,
                exc=exc,
                user_message="No fue posible abrir la revision del documento en Graph.",
            )
            return redirect("acreditacion-ciclos-lista")

        registrar_acceso_documento(
            documento=documento,
            actor=actor,
            request=request,
            accion="OPEN_DOCUMENTO_GRAPH",
            detalle=f"Se abrio en Graph el documento protegido {documento.nombre_archivo}.",
        )
        return redirect(graph_url)
