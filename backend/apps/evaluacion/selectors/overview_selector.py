from __future__ import annotations

from decimal import Decimal

from django.db.models import Q

from apps.core.models import EstadoEvaluacion
from apps.evaluacion.models import Evaluacion, ObservacionEvaluacion
from apps.evidencias.models import RegistroEvidencia


INBOX_FILTER_OPTIONS = ("TODOS", "ENVIADO", "REVISADO", "APROBADO", "RECHAZADO")


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


def get_evaluation_inbox_data(*, estado: str = "TODOS", only_released: bool = False):
    selected_estado = _normalize_inbox_filter(estado)
    registros = list(get_registros_queryset(only_released=only_released)[:200])
    if not registros:
        return {
            "rows": [],
            "counts": {"TODOS": 0, "ENVIADO": 0, "REVISADO": 0, "APROBADO": 0, "RECHAZADO": 0},
            "selected_estado": selected_estado,
            "filter_options": INBOX_FILTER_OPTIONS,
            "evaluaciones_recientes": list(get_evaluaciones_queryset()[:20]),
        }

    registro_ids = [registro.pk for registro in registros]
    latest_by_registro = {}
    latest_evaluaciones = (
        Evaluacion.objects.select_related("estado", "usuario_evaluador")
        .filter(registro_id__in=registro_ids)
        .order_by("registro_id", "-fecha_evaluacion", "-id_evaluacion")
    )
    for evaluacion in latest_evaluaciones:
        latest_by_registro.setdefault(evaluacion.registro_id, evaluacion)

    rows = []
    for registro in registros:
        latest = latest_by_registro.get(registro.pk)
        inbox_state = _resolve_inbox_state(latest)
        semaforo_data = _compute_percentage_and_semaforo(latest, inbox_state)
        rows.append(
            {
                "registro": registro,
                "latest_evaluacion": latest,
                "inbox_state": inbox_state,
                **semaforo_data,
            }
        )

    counts = {
        "TODOS": len(rows),
        "ENVIADO": sum(1 for row in rows if row["inbox_state"] == "ENVIADO"),
        "REVISADO": sum(1 for row in rows if row["inbox_state"] == "REVISADO"),
        "APROBADO": sum(1 for row in rows if row["inbox_state"] == "APROBADO"),
        "RECHAZADO": sum(1 for row in rows if row["inbox_state"] == "RECHAZADO"),
    }

    if selected_estado != "TODOS":
        rows = [row for row in rows if row["inbox_state"] == selected_estado]

    return {
        "rows": rows,
        "counts": counts,
        "selected_estado": selected_estado,
        "filter_options": INBOX_FILTER_OPTIONS,
        "evaluaciones_recientes": list(get_evaluaciones_queryset()[:20]),
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
            "indicador",
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
            "registro__indicador",
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
            "registro__indicador",
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
