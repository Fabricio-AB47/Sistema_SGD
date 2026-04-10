import hashlib
import mimetypes
from pathlib import PurePosixPath

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import get_valid_filename

from application.services import build_ciclo_auth_drive_path_for_values
from apps.core.services.dependency_health import (
    DependencyValidationError,
    ensure_database_connection,
)
from apps.core.models import ClasificacionDocumento
from apps.auditoria.services.auditoria_service import registrar_evento
from apps.documentos.models import Documento, DocumentoAccesoLog, VersionDocumento
from apps.documentos.selectors.authorization_selector import authorization_document_exists
from apps.integraciones.services import graph_service


class AuthorizationServiceError(Exception):
    pass


class AuthorizationDocumentRequiredError(AuthorizationServiceError):
    pass


def validate_cycle_authorization_dependencies(
    *,
    nombre_ciclo: str,
    anio: int | None = None,
) -> tuple[dict, str]:
    ensure_database_connection()
    drive_path = build_ciclo_auth_drive_path_for_values(nombre_ciclo, anio)
    graph_service.clear_graph_cache(drive_path)
    return graph_service.get_graph_session()


def _safe_file_name(filename: str) -> str:
    clean_name = get_valid_filename(PurePosixPath(filename or "documento").name)
    return clean_name or "documento"


def _default_description(nombre_ciclo: str, anio: int | None) -> str:
    suffix = f" ({anio})" if anio else ""
    return f"Documento de autorizacion del ciclo {nombre_ciclo}{suffix}"


def _build_document_payload(
    *,
    nombre_ciclo: str,
    anio: int | None,
    clasificacion,
    descripcion_documento: str | None,
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
        or _default_description(nombre_ciclo, anio),
        "nombre_archivo": _safe_file_name(uploaded_file.name),
        "mime_type": uploaded_file.content_type or mimetypes.guess_type(uploaded_file.name)[0],
        "extension_archivo": PurePosixPath(uploaded_file.name).suffix.lower()[:20] or None,
        "tamano_archivo": len(content),
        "ruta_local": storage_path.as_posix(),
        "hash_documento": document_hash,
        "checksum_archivo": content_hash,
        "clasificacion": clasificacion,
        "esta_cifrado": False,
        "algoritmo_cifrado": None,
        "referencia_clave_cifrado": None,
        "graph_site_id": graph_parent_reference.get("siteId"),
        "graph_drive_id": (graph_item or {}).get("parentReference", {}).get("driveId")
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


def _registrar_log_documento(*, documento, actor, request, accion: str, resultado: str, detalle: str):
    return DocumentoAccesoLog.objects.create(
        documento=documento,
        usuario=actor,
        accion=accion,
        fecha_evento=timezone.now(),
        ip=request.META.get("REMOTE_ADDR") if request else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:300] if request else None,
        resultado=resultado,
        detalle=detalle[:1000],
    )


def _next_version_number(documento: Documento) -> int:
    current = (
        VersionDocumento.objects.filter(documento=documento)
        .aggregate(max_version=Max("numero_version"))
        .get("max_version")
    )
    return int(current or 0) + 1


def _get_existing_authorization_document(nombre_ciclo: str, anio: int | None = None):
    drive_folder = build_ciclo_auth_drive_path_for_values(nombre_ciclo, anio).as_posix()
    return (
        Documento.objects.filter(
            ruta_local__startswith=drive_folder,
            activo=True,
        )
        .select_related("clasificacion")
        .order_by("-fecha_subida", "-id_documento")
        .first()
    )


def require_authorization_document_for_cycle_values(nombre_ciclo: str, anio: int | None = None):
    if authorization_document_exists(nombre_ciclo, anio):
        return
    raise AuthorizationDocumentRequiredError(
        "No existe documento de autorizacion para ese ciclo. Debes cargarlo desde el formulario unificado de creacion de ciclo."
    )


def prepare_cycle_authorization_storage(
    *,
    nombre_ciclo: str,
    anio: int | None = None,
    actor=None,
    request=None,
    payload=None,
    access_token=None,
):
    drive_path = build_ciclo_auth_drive_path_for_values(nombre_ciclo, anio)
    graph_item = graph_service.ensure_drive_folder(
        drive_path,
        payload=payload,
        access_token=access_token,
    )

    registrar_evento(
        accion="PREPARAR_CARPETA_AUTORIZACION_CICLO",
        descripcion=f"Se preparo la carpeta Graph del ciclo {nombre_ciclo}.",
        usuario=actor,
        tipo_evento="ALMACENAMIENTO",
        tabla_afectada="documento",
        valores_nuevos={
            "ciclo": nombre_ciclo,
            "anio": anio,
            "ruta_drive": drive_path.as_posix(),
            "graph_web_url": (graph_item or {}).get("webUrl"),
        },
        criticidad="MEDIA",
        request=request,
    )
    return {
        "drive_path": drive_path,
        "graph_item": graph_item,
    }


@transaction.atomic
def upload_cycle_authorization_document(
    *,
    nombre_ciclo: str,
    anio: int | None = None,
    clasificacion=None,
    descripcion_documento: str | None = None,
    uploaded_file=None,
    actor=None,
    request=None,
):
    if uploaded_file is None:
        raise AuthorizationServiceError("El archivo de autorizacion es obligatorio.")
    if clasificacion is None:
        raise AuthorizationServiceError("La clasificacion documental es obligatoria.")

    file_name = _safe_file_name(uploaded_file.name)
    file_content = uploaded_file.read()
    if not file_content:
        raise AuthorizationServiceError("El archivo enviado esta vacio.")
    try:
        graph_payload, graph_access_token = validate_cycle_authorization_dependencies(
            nombre_ciclo=nombre_ciclo,
            anio=anio,
        )
    except DependencyValidationError as exc:
        raise AuthorizationServiceError(str(exc)) from exc
    except graph_service.GraphServiceError as exc:
        raise AuthorizationServiceError(
            "No fue posible validar la conexion con OneDrive / Microsoft Graph."
        ) from exc

    storage = prepare_cycle_authorization_storage(
        nombre_ciclo=nombre_ciclo,
        anio=anio,
        actor=actor,
        request=request,
        payload=graph_payload,
        access_token=graph_access_token,
    )
    drive_folder = storage["drive_path"]
    storage_path = drive_folder / file_name

    graph_item = graph_service.upload_file(
        relative_folder_path=drive_folder,
        file_name=file_name,
        content=file_content,
        content_type=uploaded_file.content_type,
        ensure_folder=False,
        payload=graph_payload,
        access_token=graph_access_token,
        refresh=True,
    )

    payload = _build_document_payload(
        nombre_ciclo=nombre_ciclo,
        anio=anio,
        clasificacion=clasificacion,
        descripcion_documento=descripcion_documento,
        uploaded_file=uploaded_file,
        actor=actor,
        storage_path=storage_path,
        content=file_content,
        graph_item=graph_item,
    )
    documento = _get_existing_authorization_document(nombre_ciclo, anio)
    if documento is None:
        documento = (
            Documento.objects.filter(
                ruta_local=storage_path.as_posix(),
                activo=True,
            )
            .select_related("clasificacion")
            .first()
        )
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
        descripcion_cambio=descripcion_documento or "Carga de autorizacion de ciclo",
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

    _registrar_log_documento(
        documento=documento,
        actor=actor,
        request=request,
        accion="UPLOAD_AUTORIZACION_CICLO",
        resultado="OK",
        detalle=f"Se registro el documento {file_name} para el ciclo {nombre_ciclo}.",
    )
    registrar_evento(
        accion="CARGAR_DOCUMENTO_AUTORIZACION_CICLO",
        descripcion=f"Se registro el documento de autorizacion del ciclo {nombre_ciclo}.",
        usuario=actor,
        tipo_evento="DOCUMENTOS",
        tabla_afectada="documento",
        id_registro=documento.pk,
        valores_nuevos={
            "documento_id": documento.pk,
            "version_id": version.pk,
            "ruta_drive": storage_path.as_posix(),
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


@transaction.atomic
def upload_cycle_authorization_document_from_form(*, form, actor=None, request=None):
    return upload_cycle_authorization_document(
        nombre_ciclo=form.cleaned_data["nombre_ciclo"],
        anio=form.cleaned_data.get("anio"),
        clasificacion=form.cleaned_data["clasificacion"],
        descripcion_documento=form.cleaned_data.get("descripcion_documento"),
        uploaded_file=form.cleaned_data["archivo"],
        actor=actor,
        request=request,
    )


@transaction.atomic
def upload_cycle_authorization_revision(
    *,
    ciclo,
    descripcion_documento: str | None = None,
    uploaded_file=None,
    actor=None,
    request=None,
):
    documento_actual = getattr(ciclo, "documento_autorizacion", None)
    if documento_actual is None and getattr(ciclo, "documento_autorizacion_id", None):
        documento_actual = (
            Documento.objects.filter(
                pk=ciclo.documento_autorizacion_id,
                activo=True,
            )
            .select_related("clasificacion")
            .first()
        )
    if documento_actual is None:
        documento_actual = _get_existing_authorization_document(ciclo.nombre, ciclo.anio)
    clasificacion = None
    if documento_actual is not None:
        clasificacion = documento_actual.clasificacion
    if clasificacion is None:
        clasificacion = ClasificacionDocumento.objects.filter(
            codigo="AUT_CICLO",
            activo=True,
        ).first()
    if clasificacion is None:
        clasificacion = ClasificacionDocumento.objects.filter(codigo="ACTA", activo=True).first()
    if clasificacion is None:
        raise AuthorizationServiceError(
            "No existe una clasificacion AUT_CICLO o ACTA activa para registrar la nueva version del documento."
        )

    return upload_cycle_authorization_document(
        nombre_ciclo=ciclo.nombre,
        anio=ciclo.anio,
        clasificacion=clasificacion,
        descripcion_documento=descripcion_documento or "Nueva version del documento de autorizacion",
        uploaded_file=uploaded_file,
        actor=actor,
        request=request,
    )
