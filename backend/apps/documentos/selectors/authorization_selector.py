from pathlib import PurePosixPath

from django.db.models import Count

from application.services import (
    build_ciclo_auth_drive_path_for_values,
    get_ciclo_auth_drive_root,
)
from apps.acreditacion.models import CicloEvaluacion
from apps.documentos.models import Documento
from apps.integraciones.services import graph_service
from apps.integraciones.services.graph_service import get_connection_summary


def _document_exists_in_graph(documento, *, payload=None, access_token=None) -> bool:
    ruta_local = (getattr(documento, "ruta_local", "") or "").strip()
    if not ruta_local:
        return False
    graph_item = graph_service.get_item_by_relative_path(
        ruta_local,
        payload=payload,
        access_token=access_token,
        refresh=True,
    )
    return graph_item is not None


def _get_cycle_auth_folder(nombre_ciclo: str, anio: int | None = None) -> str:
    return build_ciclo_auth_drive_path_for_values(nombre_ciclo, anio).as_posix()


def get_authorization_root_context():
    return {
        "drive_root": get_ciclo_auth_drive_root().as_posix(),
    }


def get_cycle_authorization_status(nombre_ciclo: str, anio: int | None = None):
    drive_folder = build_ciclo_auth_drive_path_for_values(nombre_ciclo, anio)
    documents = get_authorization_documents_queryset().filter(
        ruta_local__startswith=drive_folder.as_posix()
    )
    return {
        "drive_folder": drive_folder.as_posix(),
        "document_count": documents.count(),
        "has_document": documents.exists(),
    }


def attach_cycle_authorization_status(ciclos):
    ciclos = list(ciclos)
    if not ciclos:
        return ciclos

    drive_root = get_ciclo_auth_drive_root().as_posix()
    drive_root_parts = PurePosixPath(drive_root).parts
    folder_depth = len(drive_root_parts) + 1
    folder_map = {_get_cycle_auth_folder(ciclo.nombre, ciclo.anio): ciclo for ciclo in ciclos}
    authorization_document_ids = {
        ciclo.documento_autorizacion_id
        for ciclo in ciclos
        if getattr(ciclo, "documento_autorizacion_id", None)
    }

    explicit_documents = {
        documento.pk: documento
        for documento in Documento.objects.filter(
            pk__in=authorization_document_ids,
            activo=True,
        )
        .only(
            "id_documento",
            "nombre_archivo",
            "fecha_subida",
            "ruta_local",
            "subido_por",
            "clasificacion",
            "graph_item_id",
        )
        .select_related("subido_por", "clasificacion")
    }

    auth_documents = list(
        Documento.objects.filter(
            ruta_local__startswith=drive_root,
            activo=True,
        )
        .only(
            "id_documento",
            "nombre_archivo",
            "fecha_subida",
            "ruta_local",
            "subido_por",
            "clasificacion",
            "graph_item_id",
        )
        .select_related("subido_por", "clasificacion")
        .order_by("-fecha_subida", "-id_documento")
    )
    try:
        graph_payload, graph_access_token = graph_service.get_graph_session()
    except graph_service.GraphServiceError:
        graph_payload = None
        graph_access_token = None

    graph_availability: dict[int, bool] = {}
    folder_stats: dict[str, dict[str, object]] = {
        folder: {"count": 0, "document": None}
        for folder in folder_map
    }

    documents_to_validate = list(explicit_documents.values()) + auth_documents
    validated_documents: dict[int, Documento] = {}
    for documento in documents_to_validate:
        if documento.pk in graph_availability:
            is_available = graph_availability[documento.pk]
        elif graph_payload is None or graph_access_token is None:
            is_available = False
        else:
            is_available = _document_exists_in_graph(
                documento,
                payload=graph_payload,
                access_token=graph_access_token,
            )
        graph_availability[documento.pk] = is_available
        if is_available:
            validated_documents[documento.pk] = documento

    for documento in auth_documents:
        ruta_local = str(documento.ruta_local or "")
        try:
            folder = str(PurePosixPath(*PurePosixPath(ruta_local).parts[:folder_depth]).as_posix())
        except Exception:
            continue
        stats = folder_stats.get(folder)
        if not stats:
            continue
        stats["count"] = int(stats["count"]) + 1
        if stats["document"] is None and graph_availability.get(documento.pk, False):
            stats["document"] = documento

    for ciclo in ciclos:
        folder = _get_cycle_auth_folder(ciclo.nombre, ciclo.anio)
        stats = folder_stats.get(folder, {"count": 0, "document": None})
        explicit_document = validated_documents.get(getattr(ciclo, "documento_autorizacion_id", None))
        resolved_document = explicit_document or stats["document"]
        document_count = int(stats["count"])
        if resolved_document is not None and document_count == 0:
            document_count = 1
        ciclo.authorization_document_count = document_count
        ciclo.has_authorization_document = resolved_document is not None
        ciclo.authorization_document = resolved_document
        ciclo.document_upload_enabled = (
            ciclo.has_authorization_document
            and (getattr(ciclo.estado, "descripcion", "") or "").strip().upper() == "APROBADO"
        )
    return ciclos


def authorization_document_exists(nombre_ciclo: str, anio: int | None = None) -> bool:
    folder = build_ciclo_auth_drive_path_for_values(nombre_ciclo, anio)
    documentos = Documento.objects.filter(
        ruta_local__startswith=folder.as_posix(),
        activo=True,
    ).only("ruta_local", "graph_item_id")
    try:
        graph_payload, graph_access_token = graph_service.get_graph_session()
    except graph_service.GraphServiceError:
        return False
    for documento in documentos:
        if _document_exists_in_graph(
            documento,
            payload=graph_payload,
            access_token=graph_access_token,
        ):
            return True
    return False


def authorization_document_exists_for_cycle(ciclo) -> bool:
    if ciclo is None:
        return False

    documento = getattr(ciclo, "documento_autorizacion", None)
    if documento is None and getattr(ciclo, "documento_autorizacion_id", None):
        documento = (
            Documento.objects.filter(
                pk=ciclo.documento_autorizacion_id,
                activo=True,
            )
            .only("ruta_local", "graph_item_id")
            .first()
        )
    try:
        graph_payload, graph_access_token = graph_service.get_graph_session()
    except graph_service.GraphServiceError:
        return False

    if documento is not None:
        return _document_exists_in_graph(
            documento,
            payload=graph_payload,
            access_token=graph_access_token,
        )
    return authorization_document_exists(ciclo.nombre, ciclo.anio)


def get_authorization_documents_queryset():
    drive_root = get_ciclo_auth_drive_root().as_posix()
    return (
        Documento.objects.select_related("clasificacion", "subido_por")
        .filter(ruta_local__startswith=drive_root)
        .only(
            "id_documento",
            "nombre_archivo",
            "fecha_subida",
            "ruta_local",
            "clasificacion",
            "subido_por",
        )
        .annotate(versiones_count=Count("versiones", distinct=True))
        .order_by("-fecha_subida", "-id_documento")
    )


def get_recent_cycle_authorization_documents(limit: int = 15):
    return get_authorization_documents_queryset()[:limit]


def get_recent_ciclos(limit: int = 8):
    return (
        CicloEvaluacion.objects.select_related("estado", "documento_autorizacion", "aprobado_por")
        .order_by("-fecha_inicio", "-id_ciclo")[:limit]
    )


def get_graph_connection_summary(*, validate: bool = False):
    return get_connection_summary(validate=validate)
