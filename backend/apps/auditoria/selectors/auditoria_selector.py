from django.db.models import Q
from django.utils import timezone

from apps.auditoria.models import Auditoria


def obtener_auditorias_filtradas(params):
    queryset = Auditoria.objects.select_related("usuario").order_by("-fecha_evento")

    q = (params.get("q") or "").strip()
    criticidad = (params.get("criticidad") or "").strip()
    tabla = (params.get("tabla") or "").strip()
    accion = (params.get("accion") or "").strip()
    fecha_desde = (params.get("fecha_desde") or "").strip()
    fecha_hasta = (params.get("fecha_hasta") or "").strip()

    if q:
        queryset = queryset.filter(
            Q(accion__icontains=q)
            | Q(tipo_evento__icontains=q)
            | Q(tabla_afectada__icontains=q)
            | Q(descripcion__icontains=q)
            | Q(usuario__primer_nombre__icontains=q)
            | Q(usuario__primer_apellido__icontains=q)
            | Q(usuario__correo__icontains=q)
        )

    if criticidad:
        queryset = queryset.filter(criticidad__iexact=criticidad)

    if tabla:
        queryset = queryset.filter(tabla_afectada__iexact=tabla)

    if accion:
        queryset = queryset.filter(accion__iexact=accion)

    if fecha_desde:
        queryset = queryset.filter(fecha_evento__date__gte=fecha_desde)

    if fecha_hasta:
        queryset = queryset.filter(fecha_evento__date__lte=fecha_hasta)

    return queryset


def obtener_resumen_auditoria(queryset=None):
    if queryset is None:
        queryset = Auditoria.objects.all()
    hoy = timezone.localdate()
    return {
        "total": queryset.count(),
        "criticos": queryset.filter(criticidad__in=["CRITICA", "ALTA"]).count(),
        "hoy": queryset.filter(fecha_evento__date=hoy).count(),
        "tablas": queryset.exclude(tabla_afectada__isnull=True)
        .exclude(tabla_afectada__exact="")
        .values("tabla_afectada")
        .distinct()
        .count(),
    }


def obtener_opciones_filtro():
    base = Auditoria.objects.all()
    return {
        "criticidades": [
            item
            for item in base.exclude(criticidad__isnull=True)
            .exclude(criticidad__exact="")
            .order_by("criticidad")
            .values_list("criticidad", flat=True)
            .distinct()
        ],
        "tablas": [
            item
            for item in base.exclude(tabla_afectada__isnull=True)
            .exclude(tabla_afectada__exact="")
            .order_by("tabla_afectada")
            .values_list("tabla_afectada", flat=True)
            .distinct()
        ],
        "acciones": [
            item
            for item in base.exclude(accion__isnull=True)
            .exclude(accion__exact="")
            .order_by("accion")
            .values_list("accion", flat=True)
            .distinct()
        ],
    }
