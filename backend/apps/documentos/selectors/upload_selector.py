from django.db.models import Count

from application.services import get_ciclo_auth_drive_root
from apps.acreditacion.models import CicloEvaluacion
from apps.documentos.models import Documento
from apps.documentos.selectors.authorization_selector import (
    attach_cycle_authorization_status,
    authorization_document_exists,
)


def get_approved_cycles_queryset():
    return (
        CicloEvaluacion.objects.select_related("estado")
        .filter(estado__descripcion__iexact="APROBADO")
        .order_by("-fecha_inicio", "-id_ciclo")
    )


def cycle_allows_document_upload(ciclo) -> bool:
    if ciclo is None:
        return False
    if (getattr(ciclo.estado, "descripcion", "") or "").strip().upper() != "APROBADO":
        return False
    return authorization_document_exists(ciclo.nombre, ciclo.anio)


def get_recent_cycle_upload_statuses(limit: int = 8):
    ciclos = (
        CicloEvaluacion.objects.select_related("estado")
        .order_by("-fecha_inicio", "-id_ciclo")[:limit]
    )
    return attach_cycle_authorization_status(ciclos)


def get_structured_documents_queryset():
    auth_root = get_ciclo_auth_drive_root().as_posix()
    return (
        Documento.objects.select_related("clasificacion", "subido_por")
        .filter(activo=True)
        .exclude(ruta_local__startswith=auth_root)
        .annotate(versiones_count=Count("versiones", distinct=True))
        .order_by("-fecha_subida", "-id_documento")
    )
