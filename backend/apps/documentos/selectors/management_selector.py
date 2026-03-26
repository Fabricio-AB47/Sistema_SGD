from django.db.models import Count, Q

from apps.documentos.models import (
    ClasificacionDocumento,
    Documento,
    DocumentoAccesoLog,
    VersionDocumento,
)


def _coerce_documento_id(documento_id):
    try:
        return int(documento_id)
    except (TypeError, ValueError):
        return None


def get_document_management_summary():
    return {
        "clasificaciones": ClasificacionDocumento.objects.count(),
        "documentos": Documento.objects.count(),
        "documentos_activos": Documento.objects.filter(activo=True).count(),
        "versiones": VersionDocumento.objects.count(),
        "accesos": DocumentoAccesoLog.objects.count(),
    }


def get_document_classifications_queryset():
    return (
        ClasificacionDocumento.objects.annotate(
            documentos_count=Count("documentos", distinct=True),
            documentos_activos_count=Count(
                "documentos",
                filter=Q(documentos__activo=True),
                distinct=True,
            ),
        )
        .order_by("codigo")
    )


def get_documentos_admin_queryset():
    return (
        Documento.objects.select_related("clasificacion", "subido_por")
        .annotate(
            versiones_count=Count("versiones", distinct=True),
            accesos_count=Count("logs_acceso", distinct=True),
            evidencias_count=Count("registros_evidencia", distinct=True),
        )
        .order_by("-fecha_subida", "-id_documento")
    )


def get_document_filter_queryset():
    return Documento.objects.only("id_documento", "nombre_archivo").order_by("nombre_archivo")


def get_documento_admin_detail(documento_id=None):
    normalized_id = _coerce_documento_id(documento_id)
    queryset = get_documentos_admin_queryset()
    if normalized_id is not None:
        return queryset.filter(pk=normalized_id).first()
    return queryset.first()


def get_document_versions_queryset(documento_id=None):
    normalized_id = _coerce_documento_id(documento_id)
    queryset = (
        VersionDocumento.objects.select_related("documento__clasificacion", "subido_por")
        .order_by("-fecha_version", "-id_version")
    )
    if normalized_id is not None:
        queryset = queryset.filter(documento_id=normalized_id)
    return queryset


def get_document_access_logs_queryset(documento_id=None):
    normalized_id = _coerce_documento_id(documento_id)
    queryset = (
        DocumentoAccesoLog.objects.select_related("documento", "usuario")
        .order_by("-fecha_evento", "-id_documento_acceso_log")
    )
    if normalized_id is not None:
        queryset = queryset.filter(documento_id=normalized_id)
    return queryset
