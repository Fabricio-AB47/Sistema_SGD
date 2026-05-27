from collections import OrderedDict

from django.db.models import Count, Prefetch
from django.core.cache import cache

from apps.acreditacion.models import (
    CicloEvaluacion,
    Criterio,
    ElementoFundamental,
    Indicador,
    RolIndicador,
    Subcriterio,
)
from apps.core.models import EstadoCiclo
from apps.evidencias.models import RegistroEvidencia


UPLOADED_EVIDENCE_STATES = {
    "APROBADA",
    "CARGADA",
    "EN_REVISION_EVALUADOR",
    "ENVIADA_EVALUADOR",
    "REGISTRADA",
    "VALIDADA",
}


def _normalize_state(value):
    return " ".join((value or "").strip().upper().split())


def _coerce_pk(value):
    try:
        pk = int(value)
    except (TypeError, ValueError):
        return None
    return pk if pk > 0 else None


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
            queryset=ElementoFundamental.objects.order_by(
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
        )
        .order_by(
            "indicador__subcriterio__criterio__codigo_criterio",
            "indicador__subcriterio__codigo_subcriterio",
            "indicador__codigo_indicador",
            "orden_visual",
            "codigo_elemento",
        )
    )


def get_cycle_indicator_scope_ids(ciclo_id):
    ciclo_pk = _coerce_pk(ciclo_id)
    if not ciclo_pk:
        return set()
    return set(
        RolIndicador.objects.filter(ciclo_id=ciclo_pk, activo=True)
        .values_list("indicador_id", flat=True)
        .distinct()
    )


def attach_cycle_indicator_scope(ciclos):
    ciclos = list(ciclos)
    cycle_ids = [ciclo.pk for ciclo in ciclos]
    total_active = Indicador.objects.filter(activo=True).count()
    scope_counts = {
        item["ciclo_id"]: item["total"]
        for item in RolIndicador.objects.filter(ciclo_id__in=cycle_ids, activo=True)
        .values("ciclo_id")
        .annotate(total=Count("indicador_id", distinct=True))
    }
    for ciclo in ciclos:
        selected_count = scope_counts.get(ciclo.pk)
        ciclo.selected_indicators_count = selected_count
        ciclo.indicator_scope_label = (
            "Todos"
            if selected_count is None
            else f"{selected_count} de {total_active}"
        )
    return ciclos


def get_indicator_selection_tree(*, selected_indicator_ids=None):
    selected_ids = {
        int(item)
        for item in (selected_indicator_ids or [])
        if str(item).strip().isdigit()
    }
    indicadores = (
        Indicador.objects.select_related("subcriterio__criterio", "tipo_indicador")
        .filter(
            activo=True,
            subcriterio__activo=True,
            subcriterio__criterio__activo=True,
        )
        .order_by(
            "subcriterio__criterio__orden_visual",
            "subcriterio__criterio__codigo_criterio",
            "subcriterio__orden_visual",
            "subcriterio__codigo_subcriterio",
            "orden_visual",
            "codigo_indicador",
        )
    )
    criteria = OrderedDict()
    total_indicators = 0
    total_selected = 0
    for indicador in indicadores:
        criterio = indicador.subcriterio.criterio
        subcriterio = indicador.subcriterio
        is_selected = indicador.pk in selected_ids
        total_indicators += 1
        total_selected += 1 if is_selected else 0
        criterion_node = criteria.setdefault(
            criterio.pk,
            {
                "criterio": criterio,
                "subcriteria": OrderedDict(),
                "indicators_total": 0,
                "selected_total": 0,
            },
        )
        subcriterion_node = criterion_node["subcriteria"].setdefault(
            subcriterio.pk,
            {
                "subcriterio": subcriterio,
                "indicators": [],
                "indicators_total": 0,
                "selected_total": 0,
            },
        )
        indicator_node = {
            "indicador": indicador,
            "selected": is_selected,
        }
        subcriterion_node["indicators"].append(indicator_node)
        subcriterion_node["indicators_total"] += 1
        subcriterion_node["selected_total"] += 1 if is_selected else 0
        criterion_node["indicators_total"] += 1
        criterion_node["selected_total"] += 1 if is_selected else 0

    groups = []
    for criterion_node in criteria.values():
        criterion_node["subcriteria"] = list(criterion_node["subcriteria"].values())
        groups.append(criterion_node)
    return {
        "groups": groups,
        "total_indicators": total_indicators,
        "selected_total": total_selected,
    }


def get_caces_model_catalog_preview():
    from apps.evaluacion.models import ModeloIndicadorCaces

    modelos = list(
        ModeloIndicadorCaces.objects.filter(activo=True).order_by("numero_modelo")
    )
    existing_codes = {
        code.upper()
        for code in Indicador.objects.filter(
            codigo_indicador__in=[modelo.codigo_modelo for modelo in modelos]
        ).values_list("codigo_indicador", flat=True)
    }
    criteria = OrderedDict()
    for modelo in modelos:
        criterio_nombre = (modelo.criterio or "Sin criterio").strip()
        subcriterio_nombre = (modelo.subcriterio or "General").strip()
        criterion_node = criteria.setdefault(
            criterio_nombre,
            {
                "nombre": criterio_nombre,
                "subcriteria": OrderedDict(),
                "indicators_total": 0,
            },
        )
        subcriterion_node = criterion_node["subcriteria"].setdefault(
            subcriterio_nombre,
            {
                "nombre": subcriterio_nombre,
                "indicators": [],
                "indicators_total": 0,
            },
        )
        exists = (modelo.codigo_modelo or "").upper() in existing_codes
        indicator_node = {
            "codigo": modelo.codigo_modelo,
            "nombre": modelo.nombre_indicador,
            "tipo": modelo.tipo_evaluacion,
            "ponderacion": modelo.ponderacion_a,
            "exists": exists,
        }
        subcriterion_node["indicators"].append(indicator_node)
        subcriterion_node["indicators_total"] += 1
        criterion_node["indicators_total"] += 1

    groups = []
    for criterion_node in criteria.values():
        criterion_node["subcriteria"] = list(criterion_node["subcriteria"].values())
        groups.append(criterion_node)

    return {
        "groups": groups,
        "summary": {
            "modelos": len(modelos),
            "criterios": len(groups),
            "subcriterios": sum(len(group["subcriteria"]) for group in groups),
            "indicadores_existentes": sum(
                1
                for group in groups
                for subcriterion in group["subcriteria"]
                for indicator in subcriterion["indicators"]
                if indicator["exists"]
            ),
            "indicadores_faltantes": sum(
                1
                for group in groups
                for subcriterion in group["subcriteria"]
                for indicator in subcriterion["indicators"]
                if not indicator["exists"]
            ),
        },
    }


def get_matrix_rows(*, ciclo_id=None):
    rows = []
    selected_cycle_pk = _coerce_pk(ciclo_id)
    scope_ids = get_cycle_indicator_scope_ids(selected_cycle_pk)
    indicadores = (
        Indicador.objects.select_related("subcriterio__criterio", "tipo_indicador")
        .prefetch_related(
            Prefetch(
                "elementos",
                queryset=ElementoFundamental.objects.order_by(
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
    if scope_ids:
        indicadores = indicadores.filter(pk__in=scope_ids)

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

    element_ids = [row["elemento"].pk for row in rows if row["elemento"] is not None]
    if not element_ids:
        return rows

    registros = (
        RegistroEvidencia.objects.select_related("documento", "estado", "ciclo")
        .filter(elemento_fundamental_id__in=element_ids)
        .order_by("elemento_fundamental_id", "-fecha_registro", "-id_registro")
    )
    if selected_cycle_pk:
        registros = registros.filter(ciclo_id=selected_cycle_pk)

    latest_by_element = {}
    for registro in registros:
        latest_by_element.setdefault(registro.elemento_fundamental_id, registro)

    for row in rows:
        elemento = row["elemento"]
        latest_record = latest_by_element.get(elemento.pk) if elemento is not None else None
        latest_state = _normalize_state(
            getattr(getattr(latest_record, "estado", None), "descripcion", None)
        )
        row["latest_record"] = latest_record
        row["latest_document"] = latest_record.documento if latest_record else None
        row["has_evidence"] = bool(
            latest_record is not None and latest_state in UPLOADED_EVIDENCE_STATES
        )
        row["has_pending_review"] = bool(latest_record is not None and not row["has_evidence"])
        row["evidence_status"] = latest_state
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
