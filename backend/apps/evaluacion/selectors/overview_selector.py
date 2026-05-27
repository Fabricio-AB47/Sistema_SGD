from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal

from django.db.models import Prefetch
from django.db.models import Q

from apps.acreditacion.models import CicloEvaluacion, ElementoFundamental, Indicador
from apps.core.models import EstadoEvaluacion
from apps.evaluacion.models import Evaluacion, ObservacionEvaluacion, TareaEvidencia
from apps.evaluacion.selectors.registro_selector import get_current_enabled_cycle
from apps.evidencias.models import RegistroEvidencia


INBOX_STATE_PENDING_ASSIGNMENT = "PENDIENTE_ASIGNACION"
INBOX_FILTER_OPTIONS = (
    "TODOS",
    "ENVIADO",
    "REVISADO",
    "APROBADO",
    "RECHAZADO",
    INBOX_STATE_PENDING_ASSIGNMENT,
)
INBOX_FILTER_LABELS = {
    "TODOS": "Todos",
    "ENVIADO": "Enviados",
    "REVISADO": "Revisados",
    "APROBADO": "Aprobados",
    "RECHAZADO": "Rechazados",
    INBOX_STATE_PENDING_ASSIGNMENT: "Pendiente de asignacion",
}


def _normalize_inbox_filter(value: str | None) -> str:
    normalized = (value or "TODOS").strip().upper()
    return normalized if normalized in INBOX_FILTER_OPTIONS else "TODOS"


def _resolve_inbox_state(latest_evaluacion) -> str:
    if latest_evaluacion is None:
        return "ENVIADO"
    estado_desc = (getattr(getattr(latest_evaluacion, "estado", None), "descripcion", "") or "").strip().upper()
    if estado_desc in {"APROBADA", "APROBADO"}:
        return "APROBADO"
    if estado_desc in {"RECHAZADA", "RECHAZADO"}:
        return "RECHAZADO"
    if estado_desc in {"EN_ANALISIS", "OBSERVADA", "REVISADA", "REVISADO"}:
        return "REVISADO"
    return "REVISADO"


def _normalize_indicator_type_from_indicator(indicador) -> str:
    return (
        getattr(
            getattr(indicador, "tipo_indicador", None),
            "descripcion",
            "",
        )
        or ""
    ).strip().upper()


def _normalize_indicator_type(registro) -> str:
    return _normalize_indicator_type_from_indicator(getattr(registro, "indicador", None))


def _resolve_result_display(*, indicador, latest_evaluacion, porcentaje):
    indicator_type = _normalize_indicator_type_from_indicator(indicador)
    if indicator_type == "CUALITATIVO":
        if latest_evaluacion is None:
            return {
                "resultado": "--",
                "resultado_class": "acreditacion-status--muted",
                "resultado_kind": "qualitative",
            }
        estado_desc = (
            getattr(getattr(latest_evaluacion, "estado", None), "descripcion", "") or ""
        ).strip().upper()
        if latest_evaluacion.aprobado:
            return {
                "resultado": "Cumple",
                "resultado_class": "acreditacion-status--success",
                "resultado_kind": "qualitative",
            }
        if estado_desc not in {"RECHAZADA", "RECHAZADO", "OBSERVADA"}:
            return {
                "resultado": "--",
                "resultado_class": "acreditacion-status--muted",
                "resultado_kind": "qualitative",
            }
        return {
            "resultado": "No cumple",
            "resultado_class": "acreditacion-status--danger",
            "resultado_kind": "qualitative",
        }

    return {
        "resultado": f"{porcentaje:.2f}%" if porcentaje is not None else "--",
        "resultado_class": "acreditacion-status--info" if porcentaje is not None else "acreditacion-status--muted",
        "resultado_kind": "quantitative",
    }


def _hierarchy_row_key(row):
    indicador = row["indicador"]
    subcriterio = row["subcriterio"]
    criterio = row["criterio"]
    elemento = row.get("elemento")
    return (
        criterio.orden_visual or 0,
        criterio.codigo_criterio,
        subcriterio.orden_visual or 0,
        subcriterio.codigo_subcriterio,
        indicador.orden_visual or 0,
        indicador.codigo_indicador,
        getattr(elemento, "orden_visual", None) or 0,
        getattr(elemento, "codigo_elemento", "") or "",
        row.get("registro_id") or 0,
    )


def _compute_percentage_and_semaforo(latest_evaluacion, inbox_state: str):
    if latest_evaluacion is None:
        return {
            "porcentaje": None,
            "semaforo": "PENDIENTE",
            "semaforo_class": "acreditacion-status--muted",
        }

    raw_score = getattr(latest_evaluacion, "calificacion", None)
    if raw_score is None:
        if inbox_state == "APROBADO":
            score = Decimal("100")
        elif inbox_state == "RECHAZADO":
            score = Decimal("0")
        else:
            score = Decimal("65")
    else:
        score = Decimal(raw_score)

    if score < 0:
        score = Decimal("0")
    if score > 100:
        score = Decimal("100")

    if score < 50:
        semaforo = "ROJO"
        semaforo_class = "acreditacion-status--danger"
    elif score < 80:
        semaforo = "AMARILLO"
        semaforo_class = "acreditacion-status--warning"
    else:
        semaforo = "VERDE"
        semaforo_class = "acreditacion-status--success"

    return {
        "porcentaje": float(score),
        "semaforo": semaforo,
        "semaforo_class": semaforo_class,
    }


def _row_compliance_score(row) -> float:
    porcentaje = row.get("porcentaje")
    return float(porcentaje) if porcentaje is not None else 0.0


def _format_percent(value: float) -> str:
    return f"{value:.2f}"


def _build_empty_inbox_summary():
    return {
        "total": 0,
        "criteria_total": 0,
        "subcriteria_total": 0,
        "indicators_total": 0,
        "elements_total": 0,
        "evaluated_total": 0,
        "pending_total": 0,
        "total_compliance": 0.0,
        "total_compliance_label": "0.00",
        "total_compliance_width": "0.00",
    }


def _build_inbox_summary(rows):
    if not rows:
        return _build_empty_inbox_summary()

    criteria = set()
    subcriteria = set()
    indicators = set()
    elements = set()
    score_total = 0.0
    evaluated_total = 0

    for row in rows:
        indicador = row["indicador"]
        subcriterio = row["subcriterio"]
        criterio = row["criterio"]
        elemento = row.get("elemento")
        criteria.add(criterio.pk)
        subcriteria.add(subcriterio.pk)
        indicators.add(indicador.pk)
        if elemento is not None:
            elements.add(elemento.pk)
        score_total += _row_compliance_score(row)
        if row.get("latest_evaluacion") is not None:
            evaluated_total += 1

    compliance = score_total / len(rows)
    return {
        "total": len(rows),
        "criteria_total": len(criteria),
        "subcriteria_total": len(subcriteria),
        "indicators_total": len(indicators),
        "elements_total": len(elements),
        "evaluated_total": evaluated_total,
        "pending_total": len(rows) - evaluated_total,
        "total_compliance": compliance,
        "total_compliance_label": _format_percent(compliance),
        "total_compliance_width": _format_percent(compliance),
    }


def _build_criterion_summaries(rows):
    criteria_map = OrderedDict()
    for row in rows:
        indicador = row["indicador"]
        subcriterio = row["subcriterio"]
        criterio = row["criterio"]
        elemento = row.get("elemento")
        node = criteria_map.setdefault(
            criterio.pk,
            {
                "codigo": criterio.codigo_criterio,
                "nombre": criterio.nombre_criterio,
                "scores": [],
                "evaluated": 0,
                "subcriteria": set(),
                "indicators": set(),
                "elements": set(),
            },
        )
        node["scores"].append(_row_compliance_score(row))
        node["evaluated"] += 1 if row.get("latest_evaluacion") is not None else 0
        node["subcriteria"].add(subcriterio.pk)
        node["indicators"].add(indicador.pk)
        if elemento is not None:
            node["elements"].add(elemento.pk)

    summaries = []
    for node in criteria_map.values():
        compliance = sum(node["scores"]) / len(node["scores"]) if node["scores"] else 0.0
        summaries.append(
            {
                "codigo": node["codigo"],
                "nombre": node["nombre"],
                "compliance": compliance,
                "compliance_label": _format_percent(compliance),
                "compliance_width": _format_percent(compliance),
                "evaluated": node["evaluated"],
                "total": len(node["scores"]),
                "subcriteria_total": len(node["subcriteria"]),
                "indicators_total": len(node["indicators"]),
                "elements_total": len(node["elements"]),
            }
        )
    return summaries


def _coerce_pk(value):
    try:
        pk = int(value)
    except (TypeError, ValueError):
        return None
    return pk if pk > 0 else None


def _get_available_evaluation_cycles():
    return list(
        CicloEvaluacion.objects.select_related("estado").order_by(
            "-fecha_inicio",
            "-id_ciclo",
        )
    )


def _resolve_evaluation_cycle(ciclo_id=None):
    available_cycles = _get_available_evaluation_cycles()
    selected_pk = _coerce_pk(ciclo_id)
    if selected_pk:
        for ciclo in available_cycles:
            if ciclo.pk == selected_pk:
                return ciclo, available_cycles

    current_cycle = get_current_enabled_cycle()
    if current_cycle is not None:
        for ciclo in available_cycles:
            if ciclo.pk == current_cycle.pk:
                return ciclo, available_cycles
        return current_cycle, available_cycles

    return (available_cycles[0] if available_cycles else None), available_cycles


def _get_inbox_structure_indicators():
    return list(
        Indicador.objects.filter(
            activo=True,
            subcriterio__activo=True,
            subcriterio__criterio__activo=True,
        )
        .select_related("tipo_indicador", "subcriterio__criterio")
        .prefetch_related(
            Prefetch(
                "elementos",
                queryset=ElementoFundamental.objects.filter(activo=True).order_by(
                    "orden_visual",
                    "codigo_elemento",
                ),
                to_attr="inbox_elementos",
            )
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


def _get_latest_records_by_element(*, ciclo, only_released: bool):
    if ciclo is None:
        return {}

    queryset = get_registros_queryset(ciclo_id=ciclo.pk, only_released=only_released)
    latest_by_element = {}
    for registro in queryset:
        latest_by_element.setdefault(registro.elemento_fundamental_id, registro)
    return latest_by_element


def _get_assigned_element_ids(*, ciclo):
    if ciclo is None:
        return set()
    return set(
        TareaEvidencia.objects.filter(ciclo=ciclo, activo=True).values_list(
            "elemento_fundamental_id",
            flat=True,
        )
    )


def _build_pending_assignment_row(*, indicador, elemento, selected_cycle):
    subcriterio = indicador.subcriterio
    criterio = subcriterio.criterio
    semaforo_data = _compute_percentage_and_semaforo(None, INBOX_STATE_PENDING_ASSIGNMENT)
    result_data = _resolve_result_display(
        indicador=indicador,
        latest_evaluacion=None,
        porcentaje=semaforo_data["porcentaje"],
    )
    return {
        "registro": None,
        "registro_id": None,
        "criterio": criterio,
        "subcriterio": subcriterio,
        "indicador": indicador,
        "elemento": elemento,
        "selected_cycle": selected_cycle,
        "latest_evaluacion": None,
        "inbox_state": INBOX_STATE_PENDING_ASSIGNMENT,
        "state_label": "PENDIENTE DE ASIGNACION",
        "state_class": "acreditacion-status--warning",
        "can_evaluate": False,
        "has_assignment": False,
        "has_record": False,
        **semaforo_data,
        **result_data,
    }


def _build_record_row(*, registro, latest_evaluacion):
    inbox_state = _resolve_inbox_state(latest_evaluacion)
    semaforo_data = _compute_percentage_and_semaforo(latest_evaluacion, inbox_state)
    result_data = _resolve_result_display(
        indicador=registro.indicador,
        latest_evaluacion=latest_evaluacion,
        porcentaje=semaforo_data["porcentaje"],
    )
    return {
        "registro": registro,
        "registro_id": registro.pk,
        "criterio": registro.indicador.subcriterio.criterio,
        "subcriterio": registro.indicador.subcriterio,
        "indicador": registro.indicador,
        "elemento": registro.elemento_fundamental,
        "selected_cycle": registro.ciclo,
        "latest_evaluacion": latest_evaluacion,
        "inbox_state": inbox_state,
        "state_label": inbox_state,
        "state_class": "",
        "can_evaluate": True,
        "has_assignment": True,
        "has_record": True,
        **semaforo_data,
        **result_data,
    }


def _build_inbox_rows(*, selected_cycle, only_released: bool):
    indicators = _get_inbox_structure_indicators()
    latest_by_element = _get_latest_records_by_element(
        ciclo=selected_cycle,
        only_released=only_released,
    )

    registro_ids = [registro.pk for registro in latest_by_element.values()]
    latest_by_registro = {}
    if registro_ids:
        latest_evaluaciones = (
            Evaluacion.objects.select_related("estado", "usuario_evaluador")
            .filter(registro_id__in=registro_ids)
            .order_by("registro_id", "-fecha_evaluacion", "-id_evaluacion")
        )
        for evaluacion in latest_evaluaciones:
            latest_by_registro.setdefault(evaluacion.registro_id, evaluacion)

    assigned_element_ids = _get_assigned_element_ids(ciclo=selected_cycle)
    rows = []
    for indicador in indicators:
        elementos = list(getattr(indicador, "inbox_elementos", []))
        if not elementos:
            rows.append(
                _build_pending_assignment_row(
                    indicador=indicador,
                    elemento=None,
                    selected_cycle=selected_cycle,
                )
            )
            continue

        for elemento in elementos:
            registro = latest_by_element.get(elemento.pk)
            if registro is not None:
                rows.append(
                    _build_record_row(
                        registro=registro,
                        latest_evaluacion=latest_by_registro.get(registro.pk),
                    )
                )
                continue

            rows.append(
                _build_pending_assignment_row(
                    indicador=indicador,
                    elemento=elemento,
                    selected_cycle=selected_cycle,
                )
            )
            rows[-1]["has_assignment"] = elemento.pk in assigned_element_ids

    rows.sort(key=_hierarchy_row_key)
    return rows


def _get_filter_options():
    return [
        {"value": value, "label": INBOX_FILTER_LABELS.get(value, value)}
        for value in INBOX_FILTER_OPTIONS
    ]


def get_evaluation_inbox_data(*, estado: str = "TODOS", only_released: bool = False, ciclo_id=None):
    selected_estado = _normalize_inbox_filter(estado)
    selected_cycle, available_cycles = _resolve_evaluation_cycle(ciclo_id)
    rows = _build_inbox_rows(
        selected_cycle=selected_cycle,
        only_released=only_released,
    )
    if not rows:
        return {
            "rows": [],
            "counts": {
                "TODOS": 0,
                "ENVIADO": 0,
                "REVISADO": 0,
                "APROBADO": 0,
                "RECHAZADO": 0,
                INBOX_STATE_PENDING_ASSIGNMENT: 0,
            },
            "summary": _build_empty_inbox_summary(),
            "criterion_summaries": [],
            "selected_estado": selected_estado,
            "filter_options": _get_filter_options(),
            "evaluaciones_recientes": list(get_evaluaciones_queryset()[:20]),
            "selected_cycle": selected_cycle,
            "available_cycles": available_cycles,
        }

    counts = {
        "TODOS": len(rows),
        "ENVIADO": sum(1 for row in rows if row["inbox_state"] == "ENVIADO"),
        "REVISADO": sum(1 for row in rows if row["inbox_state"] == "REVISADO"),
        "APROBADO": sum(1 for row in rows if row["inbox_state"] == "APROBADO"),
        "RECHAZADO": sum(1 for row in rows if row["inbox_state"] == "RECHAZADO"),
        INBOX_STATE_PENDING_ASSIGNMENT: sum(
            1 for row in rows if row["inbox_state"] == INBOX_STATE_PENDING_ASSIGNMENT
        ),
    }
    summary = _build_inbox_summary(rows)
    criterion_summaries = _build_criterion_summaries(rows)

    if selected_estado != "TODOS":
        rows = [row for row in rows if row["inbox_state"] == selected_estado]

    return {
        "rows": rows,
        "counts": counts,
        "summary": summary,
        "criterion_summaries": criterion_summaries,
        "selected_estado": selected_estado,
        "filter_options": _get_filter_options(),
        "evaluaciones_recientes": list(get_evaluaciones_queryset()[:20]),
        "selected_cycle": selected_cycle,
        "available_cycles": available_cycles,
    }


def get_evidencia_dashboard_metrics():
    return {
        "total_registros": RegistroEvidencia.objects.count(),
        "pendientes_revision": RegistroEvidencia.objects.filter(
            estado__descripcion__in=["CARGADA", "VALIDADA", "EN_REVISION_INTERNA", "ENVIADA_EVALUADOR", "EN_REVISION_EVALUADOR", "REENVIADA"]
        ).count(),
        "evaluaciones": Evaluacion.objects.count(),
        "observaciones": ObservacionEvaluacion.objects.count(),
    }


def get_registros_queryset(*, q: str = "", estado: str = "", ciclo_id=None, only_released: bool = False):
    queryset = (
        RegistroEvidencia.objects.select_related(
            "documento",
            "estado",
            "ciclo",
            "indicador__subcriterio__criterio",
            "indicador__tipo_indicador",
            "elemento_fundamental",
            "registrado_por",
            "enviado_revision_por",
        )
        .order_by("-fecha_registro", "-id_registro")
    )

    q = (q or "").strip()
    if q:
        queryset = queryset.filter(
            Q(documento__nombre_archivo__icontains=q)
            | Q(ciclo__nombre__icontains=q)
            | Q(indicador__codigo_indicador__icontains=q)
            | Q(indicador__nombre_indicador__icontains=q)
            | Q(elemento_fundamental__codigo_elemento__icontains=q)
            | Q(elemento_fundamental__nombre_elemento__icontains=q)
        )
    if estado:
        queryset = queryset.filter(estado__descripcion__iexact=estado)
    if ciclo_id:
        queryset = queryset.filter(ciclo_id=ciclo_id)
    if only_released:
        queryset = queryset.filter(fecha_envio_revision__isnull=False)
    return queryset


def get_registro_detail(registro_id):
    if not registro_id:
        return None
    return (
        RegistroEvidencia.objects.select_related(
            "documento",
            "estado",
            "ciclo",
            "indicador__subcriterio__criterio",
            "indicador__tipo_indicador",
            "elemento_fundamental",
            "registrado_por",
            "enviado_revision_por",
        )
        .filter(pk=registro_id)
        .first()
    )


def get_evaluaciones_queryset(*, registro_id=None, estado: str = ""):
    queryset = (
        Evaluacion.objects.select_related(
            "registro__documento",
            "registro__ciclo",
            "registro__indicador__tipo_indicador",
            "registro__elemento_fundamental",
            "usuario_evaluador",
            "estado",
        )
        .order_by("-fecha_evaluacion", "-id_evaluacion")
    )
    if registro_id:
        queryset = queryset.filter(registro_id=registro_id)
    if estado:
        queryset = queryset.filter(estado__descripcion__iexact=estado)
    return queryset


def get_evaluacion_detail(evaluacion_id):
    if not evaluacion_id:
        return None
    return (
        Evaluacion.objects.select_related(
            "registro__documento",
            "registro__ciclo",
            "registro__indicador__tipo_indicador",
            "registro__elemento_fundamental",
            "usuario_evaluador",
            "estado",
        )
        .filter(pk=evaluacion_id)
        .first()
    )


def get_observaciones_queryset(*, evaluacion_id=None):
    queryset = (
        ObservacionEvaluacion.objects.select_related(
            "evaluacion__registro__documento",
            "evaluacion__registro__ciclo",
            "evaluacion__registro__indicador",
            "evaluacion__registro__elemento_fundamental",
            "usuario_emisor",
        )
        .order_by("-fecha_observacion", "-id_observacion")
    )
    if evaluacion_id:
        queryset = queryset.filter(evaluacion_id=evaluacion_id)
    return queryset


def get_evaluation_state_options():
    return EstadoEvaluacion.objects.filter(activo=True).order_by("descripcion")
