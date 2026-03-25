from pathlib import PurePosixPath

from django.db.models import Count

from application.services import (
    build_ciclo_auth_drive_path_for_values,
    get_ciclo_auth_drive_root,
)
from apps.acreditacion.models import CicloEvaluacion
from apps.documentos.models import Documento
from apps.integraciones.services.graph_service import get_connection_summary


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
    folder_map = {
        build_ciclo_auth_drive_path_for_values(ciclo.nombre, ciclo.anio).as_posix(): ciclo
        for ciclo in ciclos
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
        )
        .select_related("subido_por")
        .order_by("-fecha_subida", "-id_documento")
    )

    folder_stats: dict[str, dict[str, object]] = {
        folder: {"count": 0, "document": None}
        for folder in folder_map
    }

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
        if stats["document"] is None:
            stats["document"] = documento

    for ciclo in ciclos:
        folder = build_ciclo_auth_drive_path_for_values(ciclo.nombre, ciclo.anio).as_posix()
        stats = folder_stats.get(folder, {"count": 0, "document": None})
        document_count = int(stats["count"])
        ciclo.authorization_document_count = document_count
        ciclo.has_authorization_document = document_count > 0
        ciclo.authorization_document = stats["document"]
        ciclo.document_upload_enabled = (
            ciclo.has_authorization_document
            and (getattr(ciclo.estado, "descripcion", "") or "").strip().upper() == "APROBADO"
        )
    return ciclos


def authorization_document_exists(nombre_ciclo: str, anio: int | None = None) -> bool:
    folder = build_ciclo_auth_drive_path_for_values(nombre_ciclo, anio)
    return Documento.objects.filter(
        ruta_local__startswith=folder.as_posix(),
        activo=True,
    ).exists()


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
        CicloEvaluacion.objects.select_related("estado")
        .order_by("-fecha_inicio", "-id_ciclo")[:limit]
    )


def get_graph_connection_summary(*, validate: bool = False):
    return get_connection_summary(validate=validate)
