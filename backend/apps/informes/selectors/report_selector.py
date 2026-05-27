from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal

from apps.acreditacion.models import CicloEvaluacion
from apps.core.models import EstadoInforme
from apps.evaluacion.models import Evaluacion
from apps.evidencias.models import RegistroEvidencia
from apps.informes.models import InformeAutoevaluacion


def get_informe_metrics():
    return {
        "total": InformeAutoevaluacion.objects.count(),
        "borradores": InformeAutoevaluacion.objects.filter(estado__descripcion__iexact="BORRADOR").count(),
        "revision": InformeAutoevaluacion.objects.filter(estado__descripcion__iexact="EN_REVISION").count(),
        "aprobados": InformeAutoevaluacion.objects.filter(estado__descripcion__iexact="APROBADO").count(),
    }


def get_informes_queryset(*, ciclo_id=None, estado: str = ""):
    queryset = (
        InformeAutoevaluacion.objects.select_related(
            "ciclo",
            "documento",
            "elaborado_por",
            "aprobado_por",
            "estado",
        )
        .order_by("-fecha_generacion", "-id_informe")
    )
    if ciclo_id:
        queryset = queryset.filter(ciclo_id=ciclo_id)
    if estado:
        queryset = queryset.filter(estado__descripcion__iexact=estado)
    return queryset


def get_informe_detail(informe_id):
    if not informe_id:
        return None
    return get_informes_queryset().filter(pk=informe_id).first()


def get_informe_state_options():
    return EstadoInforme.objects.filter(activo=True).order_by("id_estado_informe")


def get_informe_cycle_options():
    return CicloEvaluacion.objects.select_related("estado").order_by("-fecha_inicio", "-id_ciclo")


def _format_percent(value: float) -> str:
    return f"{value:.2f}"


def _normalize_eval_state(evaluacion) -> str:
    if evaluacion is None:
        return "PENDIENTE"
    estado = (getattr(getattr(evaluacion, "estado", None), "descripcion", "") or "").strip().upper()
    if estado in {"APROBADA", "APROBADO"} or getattr(evaluacion, "aprobado", False):
        return "APROBADO"
    if estado in {"RECHAZADA", "RECHAZADO", "OBSERVADA"}:
        return "RECHAZADO"
    return "REVISADO"


def _evaluation_score(evaluacion) -> float:
    if evaluacion is None:
        return 0.0
    if getattr(evaluacion, "calificacion", None) is not None:
        value = Decimal(evaluacion.calificacion)
    elif getattr(evaluacion, "aprobado", False):
        value = Decimal("100")
    else:
        state = _normalize_eval_state(evaluacion)
        value = Decimal("0") if state == "RECHAZADO" else Decimal("65")
    value = min(max(value, Decimal("0")), Decimal("100"))
    return float(value)


def _base_registros_queryset(*, ciclo_id=None, indicador_id=None):
    queryset = RegistroEvidencia.objects.select_related(
        "ciclo",
        "estado",
        "indicador__tipo_indicador",
        "indicador__subcriterio__criterio",
        "elemento_fundamental",
        "documento",
        "registrado_por",
    ).order_by(
        "ciclo__fecha_inicio",
        "indicador__subcriterio__criterio__orden_visual",
        "indicador__subcriterio__criterio__codigo_criterio",
        "indicador__subcriterio__orden_visual",
        "indicador__subcriterio__codigo_subcriterio",
        "indicador__orden_visual",
        "indicador__codigo_indicador",
        "elemento_fundamental__orden_visual",
        "elemento_fundamental__codigo_elemento",
    )
    if ciclo_id:
        queryset = queryset.filter(ciclo_id=ciclo_id)
    if indicador_id:
        queryset = queryset.filter(indicador_id=indicador_id)
    return queryset


def _latest_evaluaciones_by_registro(registro_ids):
    latest = {}
    evaluaciones = (
        Evaluacion.objects.select_related("estado", "usuario_evaluador")
        .filter(registro_id__in=registro_ids)
        .order_by("registro_id", "-fecha_evaluacion", "-id_evaluacion")
    )
    for evaluacion in evaluaciones:
        latest.setdefault(evaluacion.registro_id, evaluacion)
    return latest


def _empty_summary():
    return {
        "total": 0,
        "evaluadas": 0,
        "pendientes": 0,
        "aprobadas": 0,
        "rechazadas": 0,
        "cumplimiento": 0.0,
        "cumplimiento_label": "0.00",
    }


def _summary_from_rows(rows):
    if not rows:
        return _empty_summary()
    total = len(rows)
    evaluadas = sum(1 for row in rows if row["estado_evaluacion"] != "PENDIENTE")
    aprobadas = sum(1 for row in rows if row["estado_evaluacion"] == "APROBADO")
    rechazadas = sum(1 for row in rows if row["estado_evaluacion"] == "RECHAZADO")
    score = sum(row["cumplimiento"] for row in rows) / total
    return {
        "total": total,
        "evaluadas": evaluadas,
        "pendientes": total - evaluadas,
        "aprobadas": aprobadas,
        "rechazadas": rechazadas,
        "cumplimiento": score,
        "cumplimiento_label": _format_percent(score),
    }


def _report_rows(*, ciclo_id=None, indicador_id=None):
    registros = list(_base_registros_queryset(ciclo_id=ciclo_id, indicador_id=indicador_id))
    latest_by_registro = _latest_evaluaciones_by_registro([registro.pk for registro in registros])
    rows = []
    for registro in registros:
        evaluacion = latest_by_registro.get(registro.pk)
        estado_evaluacion = _normalize_eval_state(evaluacion)
        rows.append(
            {
                "registro": registro,
                "evaluacion": evaluacion,
                "estado_evaluacion": estado_evaluacion,
                "estado_evidencia": getattr(getattr(registro, "estado", None), "descripcion", "-"),
                "cumplimiento": _evaluation_score(evaluacion),
            }
        )
    return rows


def get_reporte_por_indicador(*, ciclo_id=None, indicador_id=None):
    rows = _report_rows(ciclo_id=ciclo_id, indicador_id=indicador_id)
    grouped = OrderedDict()
    for row in rows:
        indicador = row["registro"].indicador
        subcriterio = indicador.subcriterio
        criterio = subcriterio.criterio
        node = grouped.setdefault(
            indicador.pk,
            {
                "criterio": criterio,
                "subcriterio": subcriterio,
                "indicador": indicador,
                "rows": [],
            },
        )
        node["rows"].append(row)

    results = []
    for node in grouped.values():
        summary = _summary_from_rows(node["rows"])
        results.append(
            {
                "criterio": node["criterio"],
                "subcriterio": node["subcriterio"],
                "indicador": node["indicador"],
                **summary,
            }
        )
    return {"summary": _summary_from_rows(rows), "rows": results}


def get_reporte_por_estado(*, ciclo_id=None, indicador_id=None):
    rows = _report_rows(ciclo_id=ciclo_id, indicador_id=indicador_id)
    grouped = OrderedDict(
        (
            ("PENDIENTE", {"label": "Pendientes", "rows": []}),
            ("REVISADO", {"label": "Revisadas", "rows": []}),
            ("APROBADO", {"label": "Aprobadas", "rows": []}),
            ("RECHAZADO", {"label": "Rechazadas / observadas", "rows": []}),
        )
    )
    for row in rows:
        grouped[row["estado_evaluacion"]]["rows"].append(row)

    results = []
    total = len(rows)
    for key, node in grouped.items():
        summary = _summary_from_rows(node["rows"])
        proportion = (summary["total"] / total) * 100 if total else 0.0
        results.append(
            {
                "estado": key,
                "label": node["label"],
                "porcentaje_total": proportion,
                "porcentaje_total_label": _format_percent(proportion),
                **summary,
            }
        )
    return {"summary": _summary_from_rows(rows), "rows": results}


def get_reporte_por_periodo(*, ciclo_id=None, indicador_id=None):
    rows = _report_rows(ciclo_id=ciclo_id, indicador_id=indicador_id)
    grouped = OrderedDict()
    for row in rows:
        ciclo = row["registro"].ciclo
        node = grouped.setdefault(ciclo.pk, {"ciclo": ciclo, "rows": []})
        node["rows"].append(row)

    results = []
    for node in grouped.values():
        summary = _summary_from_rows(node["rows"])
        results.append({"ciclo": node["ciclo"], **summary})
    return {"summary": _summary_from_rows(rows), "rows": results}
