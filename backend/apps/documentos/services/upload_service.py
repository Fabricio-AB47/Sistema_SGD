import hashlib
import mimetypes
import re
import unicodedata
from pathlib import PurePosixPath

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import get_valid_filename

from application.services import build_document_drive_path, write_local_mirror_file
from apps.auditoria.services.auditoria_service import registrar_evento
from apps.documentos.models import Documento, DocumentoAccesoLog, VersionDocumento
from apps.documentos.selectors import cycle_allows_document_upload
from apps.integraciones.services import graph_service


class StructuredDocumentUploadError(Exception):
    pass


def _safe_file_name(filename: str) -> str:
    clean_name = get_valid_filename(PurePosixPath(filename or "documento").name)
    return clean_name or "documento"


def _file_token(value: str | None, *, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    raw_value = ascii_value.strip().upper().replace(" ", "_")
    clean_value = re.sub(r"[^A-Z0-9_-]+", "_", raw_value).strip("_")
    return clean_value or fallback


def _indicator_initials(indicador) -> str:
    initials = _initials_from_text(getattr(indicador, "nombre_indicador", None))
    if initials:
        return initials[:12]
    return _file_token(getattr(indicador, "codigo_indicador", None), fallback="IND")


def _initials_from_text(value: str | None, *, ignore_numbers: bool = False) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").upper()
    words = re.findall(r"[A-Z0-9]+", ascii_name)
    stopwords = {
        "A",
        "AL",
        "CICLO",
        "CON",
        "DE",
        "DEL",
        "E",
        "EL",
        "EN",
        "LA",
        "LAS",
        "LOS",
        "O",
        "PARA",
        "POR",
        "U",
        "Y",
    }
    return "".join(
        word[0]
        for word in words
        if word not in stopwords and not (ignore_numbers and word.isdigit())
    )


def _cycle_initials(ciclo) -> str:
    initials = _initials_from_text(getattr(ciclo, "nombre", None), ignore_numbers=True)
    return initials[:8] or "CE"


def _element_relation_number(elemento) -> str:
    codigo = str(getattr(elemento, "codigo_elemento", "") or "").strip()
    match = re.search(r"(\d+)$", codigo)
    if match:
        return match.group(1)

    orden_visual = getattr(elemento, "orden_visual", None)
    if orden_visual not in (None, ""):
        try:
            return f"{int(orden_visual):02d}"
        except (TypeError, ValueError):
            pass

    elemento_id = getattr(elemento, "pk", None)
    return str(elemento_id or "00")


def _cycle_year(ciclo) -> str:
    anio = getattr(ciclo, "anio", None)
    if anio:
        return str(anio)

    fecha_inicio = getattr(ciclo, "fecha_inicio", None)
    if fecha_inicio:
        return str(fecha_inicio.year)

    return str(timezone.localdate().year)


def _structured_evidence_file_name(*, ciclo, indicador, elemento, original_name: str) -> str:
    indicador_siglas = _indicator_initials(indicador)
    ciclo_siglas = _cycle_initials(ciclo)
    elemento_codigo = f"EL{_element_relation_number(elemento)}"
    extension = PurePosixPath(original_name or "").suffix.lower()
    return _safe_file_name(
        f"{indicador_siglas}_{ciclo_siglas}_{elemento_codigo}_{_cycle_year(ciclo)}{extension}"
    )


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
    file_name: str,
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
        "nombre_archivo": file_name,
        "mime_type": uploaded_file.content_type
        or mimetypes.guess_type(file_name)[0]
        or mimetypes.guess_type(uploaded_file.name)[0],
        "extension_archivo": PurePosixPath(file_name).suffix.lower()[:15] or None,
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
    graph_service.ensure_drive_folder(
        drive_folder,
        payload=graph_payload,
        access_token=graph_access_token,
        refresh=True,
    )
    validated_folder = graph_service.get_item_by_relative_path(
        drive_folder,
        payload=graph_payload,
        access_token=graph_access_token,
        refresh=True,
    )
    if validated_folder is None:
        raise StructuredDocumentUploadError(
            f"No fue posible validar la carpeta Graph para {drive_folder.as_posix()}."
        )
    file_name = _structured_evidence_file_name(
        ciclo=ciclo,
        indicador=indicador,
        elemento=elemento_fundamental,
        original_name=uploaded_file.name,
    )
    storage_path = drive_folder / file_name

    graph_item = graph_service.upload_file(
        relative_folder_path=drive_folder,
        file_name=file_name,
        content=content,
        content_type=uploaded_file.content_type,
        ensure_folder=False,
        payload=graph_payload,
        access_token=graph_access_token,
    )
    local_mirror_path = write_local_mirror_file(storage_path, content)

    payload = _build_payload(
        ciclo=ciclo,
        indicador=indicador,
        elemento=elemento_fundamental,
        clasificacion=clasificacion,
        descripcion_documento=descripcion_documento,
        uploaded_file=uploaded_file,
        actor=actor,
        storage_path=storage_path,
        file_name=file_name,
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
            "ruta_espejo_local": str(local_mirror_path) if local_mirror_path else None,
            "graph_item_id": (graph_item or {}).get("id"),
        },
        criticidad="ALTA",
        request=request,
    )
    return {
        "documento": documento,
        "version": version,
        "drive_path": storage_path,
        "local_mirror_path": local_mirror_path,
        "graph_item": graph_item,
        "created": created,
    }
