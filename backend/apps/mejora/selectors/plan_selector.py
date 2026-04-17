from __future__ import annotations

from apps.mejora.models import AccionMejora, PlanMejora, SeguimientoAccionMejora


def get_mejora_metrics():
    return {
        "planes": PlanMejora.objects.count(),
        "activos": PlanMejora.objects.filter(
            estado__descripcion__in=["BORRADOR", "ENVIADO", "EN_EJECUCION", "PAUSADO", "APROBADO"]
        ).count(),
        "acciones": AccionMejora.objects.count(),
        "seguimientos": SeguimientoAccionMejora.objects.count(),
    }


def get_planes_queryset(*, estado: str = ""):
    queryset = (
        PlanMejora.objects.select_related(
            "evaluacion__registro__ciclo",
            "evaluacion__registro__indicador",
            "responsable",
            "estado",
        )
        .order_by("-fecha_inicio", "-id_plan_mejora")
    )
    if estado:
        queryset = queryset.filter(estado__descripcion__iexact=estado)
    return queryset


def get_plan_detail(plan_id):
    if not plan_id:
        return None
    return get_planes_queryset().filter(pk=plan_id).first()


def get_acciones_queryset(*, plan_id=None):
    queryset = (
        AccionMejora.objects.select_related("plan", "responsable")
        .order_by("plan_id", "id_accion")
    )
    if plan_id:
        queryset = queryset.filter(plan_id=plan_id)
    return queryset


def get_seguimientos_queryset(*, accion_id=None, plan_id=None):
    queryset = (
        SeguimientoAccionMejora.objects.select_related(
            "accion__plan",
            "documento",
            "registrado_por",
        )
        .order_by("-fecha_seguimiento", "-id_seguimiento_accion")
    )
    if accion_id:
        queryset = queryset.filter(accion_id=accion_id)
    if plan_id:
        queryset = queryset.filter(accion__plan_id=plan_id)
    return queryset
