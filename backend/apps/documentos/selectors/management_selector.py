from django.db.models import Count, Q

from apps.core.models import ClasificacionDocumento
from apps.evidencias.models import Documento, DocumentoAccesoLog, RegistroEvidencia, VersionDocumento


def _coerce_pk(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def get_document_management_summary():
    return {
        "clasificaciones": ClasificacionDocumento.objects.count(),
        "clasificaciones_activas": ClasificacionDocumento.objects.filter(activo=True).count(),
        "documentos": Documento.objects.count(),
        "documentos_activos": Documento.objects.filter(activo=True).count(),
        "versiones": VersionDocumento.objects.count(),
        "evidencias": RegistroEvidencia.objects.count(),
        "accesos": DocumentoAccesoLog.objects.count(),
    }


def get_document_classifications_queryset():
    return (
        ClasificacionDocumento.objects.annotate(
            documentos_total=Count("documentos", distinct=True),
            documentos_activos=Count(
                "documentos",
                filter=Q(documentos__activo=True),
                distinct=True,
            ),
        )
        .order_by("codigo")
    )


def get_documentos_admin_queryset(*, clasificacion_id=None):
    queryset = (
        Documento.objects.select_related("clasificacion", "subido_por")
        .annotate(
            versiones_count=Count("versiones", distinct=True),
            evidencias_count=Count("registros_evidencia", distinct=True),
            accesos_count=Count("logs_acceso", distinct=True),
        )
        .order_by("-fecha_subida", "-id_documento")
    )
    clasificacion_pk = _coerce_pk(clasificacion_id)
    if clasificacion_pk:
        queryset = queryset.filter(clasificacion_id=clasificacion_pk)
    return queryset


def get_document_filter_queryset():
    return (
        Documento.objects.select_related("clasificacion")
        .only(
            "id_documento",
            "nombre_archivo",
            "descripcion_documento",
            "clasificacion__codigo",
        )
        .order_by("nombre_archivo", "id_documento")
    )


def get_documento_admin_detail(documento_id):
    documento_pk = _coerce_pk(documento_id)
    if not documento_pk:
        return None
    return (
        Documento.objects.select_related("clasificacion", "subido_por")
        .annotate(
            versiones_count=Count("versiones", distinct=True),
            evidencias_count=Count("registros_evidencia", distinct=True),
            accesos_count=Count("logs_acceso", distinct=True),
        )
        .filter(pk=documento_pk)
        .first()
    )


def get_document_versions_queryset(*, documento_id=None, limit=None):
    queryset = VersionDocumento.objects.select_related("documento", "subido_por").order_by(
        "-fecha_version", "-id_version"
    )
    documento_pk = _coerce_pk(documento_id)
    if documento_pk:
        queryset = queryset.filter(documento_id=documento_pk)
    if limit is not None:
        return queryset[:limit]
    return queryset


def get_document_access_logs_queryset(*, documento_id=None, limit=None):
    queryset = DocumentoAccesoLog.objects.select_related("documento", "usuario").order_by(
        "-fecha_evento", "-id_documento_acceso_log"
    )
    documento_pk = _coerce_pk(documento_id)
    if documento_pk:
        queryset = queryset.filter(documento_id=documento_pk)
    if limit is not None:
        return queryset[:limit]
    return queryset


def get_document_evidence_records_queryset(*, documento_id=None, limit=None):
    queryset = RegistroEvidencia.objects.select_related(
        "documento",
        "ciclo",
        "indicador",
        "elemento_fundamental",
        "estado",
        "registrado_por",
    ).order_by("-fecha_registro", "-id_registro")
    documento_pk = _coerce_pk(documento_id)
    if documento_pk:
        queryset = queryset.filter(documento_id=documento_pk)
    if limit is not None:
        return queryset[:limit]
    return queryset
