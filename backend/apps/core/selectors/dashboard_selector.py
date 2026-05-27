from __future__ import annotations

from decimal import Decimal

from apps.core.services.navigation_service import build_navigation_groups
from apps.evaluacion.models import Evaluacion, TareaEvidencia
from apps.evidencias.models import RegistroEvidencia
from apps.informes.models import InformeAutoevaluacion
from apps.mejora.models import PlanMejora

REVIEW_FILTER_OPTIONS = (
    ("RECHAZADAS", "Rechazadas"),
    ("APROBADAS", "Aprobadas"),
    ("REVISADAS", "Revisadas"),
)


def _normalize_status(value: str | None) -> str:
    return " ".join((value or "").strip().upper().split())


def _normalize_review_filter(value: str | None) -> str:
    normalized = _normalize_status(value)
    allowed = {code for code, _label in REVIEW_FILTER_OPTIONS}
    return normalized if normalized in allowed else "RECHAZADAS"


def _review_bucket_from_evaluation(evaluacion) -> str | None:
    if evaluacion is None:
        return None

    estado = _normalize_status(getattr(getattr(evaluacion, "estado", None), "descripcion", ""))
    if bool(getattr(evaluacion, "aprobado", False)) or estado in {"APROBADA", "APROBADO"}:
        return "APROBADAS"
    if estado in {"RECHAZADA", "RECHAZADO", "OBSERVADA"}:
        return "RECHAZADAS"
    if estado in {"REVISADA", "REVISADO", "EN_ANALISIS"}:
        return "REVISADAS"
    return "REVISADAS"


def _review_bucket_from_task(tarea) -> str | None:
    estado = _normalize_status(getattr(getattr(tarea, "estado", None), "descripcion", ""))
    if estado in {"APROBADA", "APROBADO"}:
        return "APROBADAS"
    if estado in {"RECHAZADA", "RECHAZADO"}:
        return "RECHAZADAS"
    if estado in {"REVISADA", "REVISADO", "CERRADA", "COMPLETADA", "FINALIZADA"}:
        return "REVISADAS"

    observacion = _normalize_status(getattr(tarea, "observacion", ""))
    if "CORRECCION_DIRECTOR" in observacion or "CORRECCIONES SOLICITADAS" in observacion:
        return "RECHAZADAS"
    if "VISTO_BUENO_DIRECTOR" in observacion or "VISTO BUENO DEL DIRECTOR" in observacion:
        return "APROBADAS"
    return None


def _compliance_from_evaluation(evaluacion, bucket: str | None):
    if evaluacion is None:
        return Decimal("100") if bucket == "APROBADAS" else Decimal("0") if bucket == "RECHAZADAS" else None

    calificacion = getattr(evaluacion, "calificacion", None)
    if calificacion is None:
        return Decimal("100") if bucket == "APROBADAS" else Decimal("0") if bucket == "RECHAZADAS" else None

    score = Decimal(str(calificacion))
    if score < 0:
        return Decimal("0")
    if score > 100:
        return Decimal("100")
    return score.quantize(Decimal("0.01"))


def _format_percent(value) -> str:
    if value is None:
        return "--"
    return f"{Decimal(value).quantize(Decimal('0.01'))}%"


def _latest_records_for_tasks(tasks):
    if not tasks:
        return {}

    filters = set(
        (task.ciclo_id, task.indicador_id, task.elemento_fundamental_id)
        for task in tasks
        if task.ciclo_id and task.indicador_id and task.elemento_fundamental_id
    )
    if not filters:
        return {}

    cycle_ids = {item[0] for item in filters}
    indicator_ids = {item[1] for item in filters}
    element_ids = {item[2] for item in filters}
    queryset = (
        RegistroEvidencia.objects.select_related("documento", "estado", "registrado_por")
        .filter(
            ciclo_id__in=cycle_ids,
            indicador_id__in=indicator_ids,
            elemento_fundamental_id__in=element_ids,
        )
        .order_by(
            "ciclo_id",
            "indicador_id",
            "elemento_fundamental_id",
            "-fecha_registro",
            "-id_registro",
        )
    )

    latest = {}
    for registro in queryset:
        key = (registro.ciclo_id, registro.indicador_id, registro.elemento_fundamental_id)
        if key in filters:
            latest.setdefault(key, registro)
    return latest


def _latest_evaluations_for_records(registros):
    registro_ids = [registro.pk for registro in registros if registro is not None]
    if not registro_ids:
        return {}

    latest = {}
    evaluaciones = (
        Evaluacion.objects.select_related("estado", "usuario_evaluador")
        .filter(registro_id__in=registro_ids)
        .order_by("registro_id", "-fecha_evaluacion", "-id_evaluacion")
    )
    for evaluacion in evaluaciones:
        latest.setdefault(evaluacion.registro_id, evaluacion)
    return latest


def _build_designation_summary(rows):
    grouped = {}
    for row in rows:
        responsable = row["responsable"]
        key = getattr(responsable, "pk", None) or 0
        node = grouped.setdefault(
            key,
            {
                "responsable": responsable,
                "responsable_nombre": (
                    getattr(responsable, "nombre_completo", None)
                    or getattr(responsable, "correo", None)
                    or "Sin responsable"
                ),
                "total": 0,
                "aprobadas": 0,
                "rechazadas": 0,
                "revisadas": 0,
                "scores": [],
            },
        )
        node["total"] += 1
        if row["bucket"] == "APROBADAS":
            node["aprobadas"] += 1
        elif row["bucket"] == "RECHAZADAS":
            node["rechazadas"] += 1
        elif row["bucket"] == "REVISADAS":
            node["revisadas"] += 1
        if row["cumplimiento"] is not None:
            node["scores"].append(row["cumplimiento"])

    summary = []
    for node in grouped.values():
        avg_score = None
        if node["scores"]:
            avg_score = (sum(node["scores"], Decimal("0")) / len(node["scores"])).quantize(Decimal("0.01"))
        node["cumplimiento_promedio"] = avg_score
        node["cumplimiento_label"] = _format_percent(avg_score)
        del node["scores"]
        summary.append(node)
    return sorted(summary, key=lambda item: (-item["total"], item["responsable_nombre"]))


def get_dashboard_metrics():
    return {
        "evidencias": RegistroEvidencia.objects.count(),
        "evaluaciones_pendientes": Evaluacion.objects.filter(
            estado__descripcion__in=["PENDIENTE", "EN_ANALISIS"]
        ).count(),
        "informes_revision": InformeAutoevaluacion.objects.filter(
            estado__descripcion__in=["BORRADOR", "EN_REVISION"]
        ).count(),
        "planes_activos": PlanMejora.objects.filter(
            estado__descripcion__in=["BORRADOR", "ENVIADO", "EN_EJECUCION", "PAUSADO", "APROBADO"]
        ).count(),
    }


def get_dashboard_review_grid(*, estado: str | None = None, limit: int = 80):
    selected_estado = _normalize_review_filter(estado)
    tasks = list(
        TareaEvidencia.objects.select_related(
            "ciclo",
            "indicador__subcriterio__criterio",
            "elemento_fundamental",
            "usuario_responsable",
            "estado",
            "asignado_por",
        )
        .filter(activo=True)
        .order_by("-fecha_asignacion", "-id_tarea_evidencia")[:300]
    )
    records_by_task = _latest_records_for_tasks(tasks)
    latest_records = list(records_by_task.values())
    evaluations_by_record = _latest_evaluations_for_records(latest_records)

    rows = []
    for task in tasks:
        registro = records_by_task.get(
            (task.ciclo_id, task.indicador_id, task.elemento_fundamental_id)
        )
        evaluacion = evaluations_by_record.get(getattr(registro, "pk", None))
        bucket = _review_bucket_from_evaluation(evaluacion) or _review_bucket_from_task(task)
        if bucket not in {"REVISADAS", "APROBADAS", "RECHAZADAS"}:
            continue

        cumplimiento = _compliance_from_evaluation(evaluacion, bucket)
        rows.append(
            {
                "tarea": task,
                "registro": registro,
                "evaluacion": evaluacion,
                "bucket": bucket,
                "bucket_label": dict(REVIEW_FILTER_OPTIONS).get(bucket, bucket.title()),
                "cumplimiento": cumplimiento,
                "cumplimiento_label": _format_percent(cumplimiento),
                "responsable": task.usuario_responsable,
                "estado_tarea": getattr(getattr(task, "estado", None), "descripcion", ""),
                "estado_evaluacion": getattr(getattr(evaluacion, "estado", None), "descripcion", ""),
                "observacion_revision": (
                    getattr(task, "observacion", None)
                    or getattr(evaluacion, "comentario", None)
                    or ""
                ),
            }
        )

    counts = {
        code: sum(1 for row in rows if row["bucket"] == code)
        for code, _label in REVIEW_FILTER_OPTIONS
    }
    filtered_rows = [row for row in rows if row["bucket"] == selected_estado][:limit]

    return {
        "selected_estado": selected_estado,
        "filter_options": [
            {"code": code, "label": label, "count": counts[code]}
            for code, label in REVIEW_FILTER_OPTIONS
        ],
        "counts": counts,
        "rows": filtered_rows,
        "designation_summary": _build_designation_summary(filtered_rows),
    }


def get_dashboard_quick_links(*, role_names=(), permission_codes=(), limit: int = 8):
    groups = build_navigation_groups(role_names=role_names, permission_codes=permission_codes)
    quick_links = []
    for group in groups:
        for item in group["items"]:
            if item.url_name == "core-dashboard":
                continue
            quick_links.append(
                {
                    "group": group["label"],
                    "label": item.label,
                    "url_name": item.url_name,
                    "icon": getattr(item, "icon", "compass"),
                }
            )
            if len(quick_links) >= limit:
                return quick_links
    return quick_links
