import logging

from django.contrib import messages
from django.db import IntegrityError
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import RedirectView, TemplateView
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.acreditacion.models import IndicadorElementoFundamental
from apps.core.mixins import SigLoginRequiredMixin
from apps.core.views.admin_page import AdminPageView
from apps.documentos.forms import StructuredDocumentUploadForm
from apps.documentos.selectors import (
    get_documento_for_access,
    get_approved_cycles_queryset,
    get_recent_cycle_upload_statuses,
    get_structured_documents_queryset,
)
from apps.documentos.services import (
    ProtectedDocumentAccessError,
    StructuredDocumentUploadError,
    registrar_acceso_documento,
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
MODULE_TABS = [
    {"label": "Clasificaciones documentales", "url_name": "documentos-clasificaciones-lista", "active_names": ["documentos-clasificaciones-lista"]},
    {"label": "Documentos", "url_name": "documentos-lista", "active_names": ["documentos-lista"]},
    {"label": "Subir documento", "url_name": "documentos-subir", "active_names": ["documentos-subir"]},
    {"label": "Detalle de documento", "url_name": "documentos-detalle", "active_names": ["documentos-detalle"]},
    {"label": "Historial de versiones", "url_name": "documentos-versiones", "active_names": ["documentos-versiones"]},
    {"label": "Historial de accesos", "url_name": "documentos-accesos", "active_names": ["documentos-accesos"]},
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


class DocumentosBaseView(SigLoginRequiredMixin, TemplateView):
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
            }
        )
        context.update(kwargs)
        return context


class AuthorizationCycleView(SigLoginRequiredMixin, RedirectView):
    pattern_name = "acreditacion-ciclos-lista"
    permanent = False


class DocumentUploadView(DocumentosBaseView):
    template_name = "documentos/documento_upload.html"
    page_title = "Subir documento"
    page_description = (
        "Carga documentacion estructurada por indicador y elemento. "
        "Solo se habilita cuando el ciclo esta APROBADO y ya tiene documento de autorizacion."
    )
    page_actions = [
        {"label": "Ciclos de evaluacion", "url_name": "acreditacion-ciclos-lista", "variant": "secondary"},
    ]

    def _get_cycle_initial(self):
        ciclo_id = self.request.GET.get("ciclo")
        if not ciclo_id:
            return None
        return get_approved_cycles_queryset().filter(pk=ciclo_id).first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        approved_cycles = get_approved_cycles_queryset()
        has_structure = IndicadorElementoFundamental.objects.exists()
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


class ProtectedDocumentAccessView(SigLoginRequiredMixin, View):
    def _actor(self):
        user_id = self.request.session.get("sig_user_id")
        if not user_id:
            return None
        return Usuario.objects.filter(pk=user_id).only("id_user", "primer_nombre", "primer_apellido").first()

    def get(self, request, documento_id, *args, **kwargs):
        documento = get_documento_for_access(documento_id)
        if documento is None:
            raise Http404("El documento no existe.")

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
            actor=self._actor(),
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
                or "application/octet-stream"
            ),
        )


@method_decorator(xframe_options_sameorigin, name="dispatch")
class ProtectedDocumentPreviewView(ProtectedDocumentAccessView):
    def get(self, request, documento_id, *args, **kwargs):
        documento = get_documento_for_access(documento_id)
        if documento is None:
            raise Http404("El documento no existe.")

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
            actor=self._actor(),
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
                or "application/octet-stream"
            ),
        )


class ProtectedDocumentDownloadView(ProtectedDocumentAccessView):
    def get(self, request, documento_id, *args, **kwargs):
        documento = get_documento_for_access(documento_id)
        if documento is None:
            raise Http404("El documento no existe.")

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
            actor=self._actor(),
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
                or "application/octet-stream"
            ),
        )


class ProtectedDocumentGraphRedirectView(SigLoginRequiredMixin, View):
    def _actor(self):
        user_id = self.request.session.get("sig_user_id")
        if not user_id:
            return None
        return Usuario.objects.filter(pk=user_id).only("id_user", "primer_nombre", "primer_apellido").first()

    def get(self, request, documento_id, *args, **kwargs):
        documento = get_documento_for_access(documento_id)
        if documento is None:
            raise Http404("El documento no existe.")

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
            actor=self._actor(),
            request=request,
            accion="OPEN_DOCUMENTO_GRAPH",
            detalle=f"Se abrio en Graph el documento protegido {documento.nombre_archivo}.",
        )
        return redirect(graph_url)
