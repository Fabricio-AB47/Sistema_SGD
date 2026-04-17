from __future__ import annotations

from apps.acreditacion.models import CicloEvaluacion
from apps.core.models import EstadoInforme
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
