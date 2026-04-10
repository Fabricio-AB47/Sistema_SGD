from django.db.models import Count, Prefetch
from django.core.cache import cache

from apps.acreditacion.models import (
    CicloEvaluacion,
    Criterio,
    ElementoFundamental,
    Indicador,
    Subcriterio,
)
from apps.core.models import EstadoCiclo


def get_acreditacion_metrics():
    cache_key = "sig:acreditacion:metrics"
    cached_metrics = cache.get(cache_key)
    if cached_metrics is not None:
        return cached_metrics

    metrics = {
        "criterios": Criterio.objects.count(),
        "subcriterios": Subcriterio.objects.count(),
        "indicadores": Indicador.objects.count(),
        "elementos": ElementoFundamental.objects.count(),
        "ciclos": CicloEvaluacion.objects.count(),
    }
    cache.set(cache_key, metrics, 60)
    return metrics


def get_criterios_queryset():
    return (
        Criterio.objects.annotate(
            subcriterios_count=Count("subcriterios", distinct=True),
            indicadores_count=Count("subcriterios__indicadores", distinct=True),
        )
        .order_by("orden_visual", "codigo_criterio")
    )


def get_subcriterios_queryset():
    return (
        Subcriterio.objects.select_related("criterio")
        .annotate(indicadores_count=Count("indicadores", distinct=True))
        .order_by("criterio__codigo_criterio", "orden_visual", "codigo_subcriterio")
    )


def get_indicadores_queryset():
    return (
        Indicador.objects.select_related("subcriterio__criterio", "tipo_indicador")
        .annotate(elementos_count=Count("elementos", distinct=True))
        .order_by(
            "subcriterio__criterio__codigo_criterio",
            "subcriterio__codigo_subcriterio",
            "orden_visual",
            "codigo_indicador",
        )
    )


def get_indicator_detail(indicador_id=None):
    queryset = Indicador.objects.select_related("subcriterio__criterio", "tipo_indicador").prefetch_related(
        Prefetch(
            "elementos",
            queryset=ElementoFundamental.objects.select_related("clasificacion").order_by(
                "orden_visual",
                "codigo_elemento",
            ),
            to_attr="elementos_detalle",
        )
    )
    if indicador_id:
        indicator = queryset.filter(pk=indicador_id).first()
    else:
        indicator = queryset.order_by("codigo_indicador").first()

    if indicator is None:
        return None

    return indicator


def get_elementos_queryset():
    return (
        ElementoFundamental.objects.select_related(
            "indicador__subcriterio__criterio",
            "clasificacion",
        )
        .order_by(
            "indicador__subcriterio__criterio__codigo_criterio",
            "indicador__subcriterio__codigo_subcriterio",
            "indicador__codigo_indicador",
            "orden_visual",
            "codigo_elemento",
        )
    )


def get_matrix_rows():
    rows = []
    indicadores = (
        Indicador.objects.select_related("subcriterio__criterio", "tipo_indicador")
        .prefetch_related(
            Prefetch(
                "elementos",
                queryset=ElementoFundamental.objects.select_related("clasificacion").order_by(
                    "orden_visual",
                    "codigo_elemento",
                ),
                to_attr="matrix_elements",
            )
        )
        .order_by(
            "subcriterio__criterio__codigo_criterio",
            "subcriterio__codigo_subcriterio",
            "codigo_indicador",
        )
    )

    for indicador in indicadores:
        relaciones = getattr(indicador, "matrix_elements", [])
        if not relaciones:
            rows.append(
                {
                    "criterio": indicador.subcriterio.criterio,
                    "subcriterio": indicador.subcriterio,
                    "indicador": indicador,
                    "elemento": None,
                }
            )
            continue

        for relacion in relaciones:
            rows.append(
                {
                    "criterio": indicador.subcriterio.criterio,
                    "subcriterio": indicador.subcriterio,
                    "indicador": indicador,
                    "elemento": relacion,
                }
            )
    return rows


def get_ciclos_queryset():
    return (
        CicloEvaluacion.objects.select_related(
            "estado",
            "documento_autorizacion",
            "aprobado_por",
        )
        .only(
            "id_ciclo",
            "nombre",
            "descripcion",
            "anio",
            "fecha_inicio",
            "fecha_fin",
            "estado",
            "estado__descripcion",
            "documento_autorizacion",
            "aprobado_por",
            "aprobado_por__primer_nombre",
            "aprobado_por__primer_apellido",
            "fecha_aprobacion",
            "observacion_aprobacion",
        )
        .order_by("-fecha_inicio", "-id_ciclo")
    )


def get_ciclo_detail(ciclo_id):
    ciclo = (
        CicloEvaluacion.objects.select_related(
            "estado",
            "documento_autorizacion",
            "aprobado_por",
        )
        .only(
            "id_ciclo",
            "nombre",
            "descripcion",
            "anio",
            "fecha_inicio",
            "fecha_fin",
            "estado",
            "estado__descripcion",
            "documento_autorizacion",
            "aprobado_por",
            "aprobado_por__primer_nombre",
            "aprobado_por__primer_apellido",
            "fecha_aprobacion",
            "observacion_aprobacion",
        )
        .filter(pk=ciclo_id)
        .first()
    )
    if ciclo is None:
        return None

    from apps.documentos.selectors.authorization_selector import attach_cycle_authorization_status

    return attach_cycle_authorization_status([ciclo])[0]


def get_estados_ciclo_queryset():
    return EstadoCiclo.objects.filter(activo=True).order_by("id_estado_ciclo")
