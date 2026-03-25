import hashlib
import mimetypes
from pathlib import PurePosixPath

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import get_valid_filename

from application.services import build_document_drive_path
from apps.auditoria.services.auditoria_service import registrar_evento
from apps.documentos.models import Documento, DocumentoAccesoLog, VersionDocumento
from apps.documentos.selectors import cycle_allows_document_upload
from apps.integraciones.services import graph_service


class StructuredDocumentUploadError(Exception):
    pass


def _safe_file_name(filename: str) -> str:
    clean_name = get_valid_filename(PurePosixPath(filename or "documento").name)
    return clean_name or "documento"


def _default_description(*, ciclo, indicador, elemento) -> str:
    return (
        f"Documento {indicador.codigo_indicador} / {elemento.codigo_elemento} "
        f"del ciclo {ciclo.nombre}"
    )


def _next_version_number(documento: Documento) -> int:
    current = (
        VersionDocumento.objects.filter(documento=documento)
        .aggregate(max_version=Max("numero_version"))
        .get("max_version")
    )
    return int(current or 0) + 1


def _register_document_log(*, documento, actor, request, accion: str, detalle: str):
    return DocumentoAccesoLog.objects.create(
        documento=documento,
        usuario=actor,
        accion=accion,
        fecha_evento=timezone.now(),
        ip=request.META.get("REMOTE_ADDR") if request else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:300] if request else None,
        resultado="OK",
        detalle=detalle[:1000],
    )


def _build_payload(
    *,
    ciclo,
    indicador,
    elemento,
    clasificacion,
    descripcion_documento,
    uploaded_file,
    actor,
    storage_path: PurePosixPath,
    content: bytes,
    graph_item: dict | None,
):
    content_hash = hashlib.sha256(content).hexdigest()
    document_hash = hashlib.sha256(
        f"{content_hash}|{storage_path.as_posix()}".encode("utf-8")
    ).hexdigest()
    graph_parent_reference = (graph_item or {}).get("parentReference", {})
    graph_last_modified = parse_datetime((graph_item or {}).get("lastModifiedDateTime") or "")

    # El esquema legacy solo tiene `ruta_local`; aqui persistimos la ruta relativa en Graph.
    return {
        "descripcion_documento": descripcion_documento
        or _default_description(ciclo=ciclo, indicador=indicador, elemento=elemento),
        "nombre_archivo": _safe_file_name(uploaded_file.name),
        "mime_type": uploaded_file.content_type or mimetypes.guess_type(uploaded_file.name)[0],
        "extension_archivo": PurePosixPath(uploaded_file.name).suffix.lower()[:15] or None,
        "tamano_archivo": len(content),
        "ruta_local": storage_path.as_posix(),
        "hash_documento": document_hash,
        "checksum_archivo": content_hash,
        "clasificacion": clasificacion,
        "esta_cifrado": False,
        "algoritmo_cifrado": None,
        "referencia_clave_cifrado": None,
        "graph_site_id": graph_parent_reference.get("siteId"),
        "graph_drive_id": graph_parent_reference.get("driveId")
        or getattr(settings, "GRAPH_DRIVE_ID", "").strip()
        or None,
        "graph_item_id": (graph_item or {}).get("id"),
        "graph_web_url": (graph_item or {}).get("webUrl"),
        "graph_etag": (graph_item or {}).get("eTag"),
        "graph_ctag": (graph_item or {}).get("cTag"),
        "graph_last_modified": graph_last_modified,
        "graph_size": (graph_item or {}).get("size"),
        "fecha_subida": timezone.now(),
        "subido_por": actor,
        "activo": True,
    }


@transaction.atomic
def upload_structured_document(
    *,
    ciclo,
    indicador,
    elemento_fundamental,
    clasificacion,
    uploaded_file,
    descripcion_documento: str | None = None,
    actor=None,
    request=None,
):
    if not cycle_allows_document_upload(ciclo):
        raise StructuredDocumentUploadError(
            "La carga documental solo se habilita cuando el ciclo esta APROBADO y su documento de autorizacion ya existe."
        )
    if uploaded_file is None:
        raise StructuredDocumentUploadError("Debes seleccionar un archivo.")
    if clasificacion is None:
        raise StructuredDocumentUploadError("La clasificacion documental es obligatoria.")
    graph_service.require_graph_configuration()

    content = uploaded_file.read()
    if not content:
        raise StructuredDocumentUploadError("El archivo enviado esta vacio.")
    graph_payload, graph_access_token = graph_service.get_graph_session()

    drive_folder = build_document_drive_path(indicador, elemento_fundamental, ciclo)
    file_name = _safe_file_name(uploaded_file.name)
    storage_path = drive_folder / file_name

    graph_item = graph_service.upload_file(
        relative_folder_path=drive_folder,
        file_name=file_name,
        content=content,
        content_type=uploaded_file.content_type,
        payload=graph_payload,
        access_token=graph_access_token,
    )

    payload = _build_payload(
        ciclo=ciclo,
        indicador=indicador,
        elemento=elemento_fundamental,
        clasificacion=clasificacion,
        descripcion_documento=descripcion_documento,
        uploaded_file=uploaded_file,
        actor=actor,
        storage_path=storage_path,
        content=content,
        graph_item=graph_item,
    )

    documento = Documento.objects.filter(
        ruta_local=storage_path.as_posix(),
        activo=True,
    ).first()
    created = documento is None
    if created:
        documento = Documento.objects.create(**payload)
    else:
        for field, value in payload.items():
            setattr(documento, field, value)
        documento.save(
            update_fields=[
                "descripcion_documento",
                "nombre_archivo",
                "mime_type",
                "extension_archivo",
                "tamano_archivo",
                "ruta_local",
                "hash_documento",
                "checksum_archivo",
                "clasificacion",
                "esta_cifrado",
                "algoritmo_cifrado",
                "referencia_clave_cifrado",
                "graph_site_id",
                "graph_drive_id",
                "graph_item_id",
                "graph_web_url",
                "graph_etag",
                "graph_ctag",
                "graph_last_modified",
                "graph_size",
                "fecha_subida",
                "subido_por",
                "activo",
            ],
        )

    version = VersionDocumento.objects.create(
        documento=documento,
        numero_version=_next_version_number(documento),
        descripcion_cambio=descripcion_documento or "Carga documental estructurada",
        fecha_version=timezone.now(),
        subido_por=actor,
        graph_item_id=(graph_item or {}).get("id"),
        ruta_local=storage_path.as_posix(),
        hash_documento=payload["checksum_archivo"],
        checksum_archivo=payload["checksum_archivo"],
        esta_cifrado=False,
        algoritmo_cifrado=None,
        referencia_clave_cifrado=None,
    )

    _register_document_log(
        documento=documento,
        actor=actor,
        request=request,
        accion="UPLOAD_DOCUMENTO_ESTRUCTURADO",
        detalle=(
            f"Se registro {file_name} en {indicador.codigo_indicador} / "
            f"{elemento_fundamental.codigo_elemento} para el ciclo {ciclo.nombre}."
        ),
    )
    registrar_evento(
        accion="CARGAR_DOCUMENTO_ESTRUCTURADO",
        descripcion=(
            f"Se registro el documento {file_name} para el ciclo {ciclo.nombre} "
            f"en el elemento {elemento_fundamental.codigo_elemento}."
        ),
        usuario=actor,
        tipo_evento="DOCUMENTOS",
        tabla_afectada="documento",
        id_registro=documento.pk,
        valores_nuevos={
            "documento_id": documento.pk,
            "version_id": version.pk,
            "ciclo_id": ciclo.pk,
            "indicador_id": indicador.pk,
            "elemento_id": elemento_fundamental.pk,
            "ruta_drive": (drive_folder / file_name).as_posix(),
            "graph_item_id": (graph_item or {}).get("id"),
        },
        criticidad="ALTA",
        request=request,
    )
    return {
        "documento": documento,
        "version": version,
        "drive_path": storage_path,
        "graph_item": graph_item,
        "created": created,
    }
