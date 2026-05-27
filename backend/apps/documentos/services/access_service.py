import mimetypes
from io import BytesIO

from django.utils import timezone

from application.services import get_existing_local_mirror_file
from apps.auditoria.services.auditoria_service import registrar_evento
from apps.documentos.models import DocumentoAccesoLog
from apps.integraciones.services import graph_service


class ProtectedDocumentAccessError(Exception):
    pass


INLINE_PREVIEW_MIME_PREFIXES = (
    "application/pdf",
    "image/",
    "text/",
)
INLINE_PREVIEW_EXTENSIONS = {
    ".csv",
    ".json",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".txt",
    ".xml",
}


def resolve_protected_document_stream(documento):
    graph_item_id = getattr(documento, "graph_item_id", None)
    local_file_path = get_existing_local_mirror_file(getattr(documento, "ruta_local", None))
    if not graph_item_id and local_file_path is None:
        raise ProtectedDocumentAccessError(
            "El documento no tiene un item de Microsoft Graph asociado."
        )

    if graph_item_id:
        try:
            content, headers = graph_service.download_file_by_item_id(graph_item_id)
            return BytesIO(content), headers
        except graph_service.GraphServiceError as exc:
            if local_file_path is None:
                raise ProtectedDocumentAccessError(str(exc)) from exc

    content_type = (
        getattr(documento, "mime_type", None)
        or mimetypes.guess_type(getattr(documento, "nombre_archivo", "") or "")[0]
        or "application/octet-stream"
    )
    return local_file_path.open("rb"), {"Content-Type": content_type}


def supports_inline_preview(documento) -> bool:
    mime_type = (getattr(documento, "mime_type", "") or "").strip().lower()
    extension = (getattr(documento, "extension_archivo", "") or "").strip().lower()

    if any(mime_type.startswith(prefix) for prefix in INLINE_PREVIEW_MIME_PREFIXES):
        return True
    return extension in INLINE_PREVIEW_EXTENSIONS


def resolve_graph_document_url(documento) -> str:
    graph_web_url = (getattr(documento, "graph_web_url", "") or "").strip()
    if not graph_web_url:
        raise ProtectedDocumentAccessError(
            "El documento no tiene una URL de Microsoft Graph disponible para edicion."
        )
    return graph_web_url


def registrar_acceso_documento(*, documento, actor=None, request=None, accion="VIEW_DOCUMENTO", resultado="OK", detalle=""):
    DocumentoAccesoLog.objects.create(
        documento=documento,
        usuario=actor,
        accion=accion,
        fecha_evento=timezone.now(),
        ip=request.META.get("REMOTE_ADDR") if request else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:300] if request else None,
        resultado=resultado,
        detalle=(detalle or "")[:1000],
    )
    registrar_evento(
        accion=accion,
        descripcion=detalle or f"Se accedio al documento {documento.nombre_archivo}.",
        usuario=actor,
        tipo_evento="DOCUMENTOS",
        tabla_afectada="documento",
        id_registro=documento.pk,
        valores_nuevos={
            "documento_id": documento.pk,
            "nombre_archivo": documento.nombre_archivo,
            "graph_item_id": documento.graph_item_id,
        },
        criticidad="MEDIA",
        request=request,
    )
