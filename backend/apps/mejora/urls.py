from django.urls import path

from apps.mejora.views.web import (
    ProcesoAsignacionResponsablesView,
    ProcesoCargaInformacionView,
    ProcesoCicloAprobacionView,
    ProcesoDashboardView,
    ProcesoEnvioFormalView,
    ProcesoRecepcionEvaluadorView,
    ProcesoRevisionJefaturaView,
    ProcesoSeguimientoView,
)

urlpatterns = [
    path("", ProcesoDashboardView.as_view(), name="mejora-lista"),
    path("crear/", ProcesoCicloAprobacionView.as_view(), name="mejora-crear"),
    path("detalle/", ProcesoRevisionJefaturaView.as_view(), name="mejora-detalle"),
    path("seguimiento/", ProcesoSeguimientoView.as_view(), name="mejora-seguimiento"),
    path("ciclo-aprobacion/", ProcesoCicloAprobacionView.as_view(), name="mejora-ciclo-aprobacion"),
    path("asignacion-responsables/", ProcesoAsignacionResponsablesView.as_view(), name="mejora-asignacion-responsables"),
    path("carga-informacion/", ProcesoCargaInformacionView.as_view(), name="mejora-carga-informacion"),
    path("revision-jefatura/", ProcesoRevisionJefaturaView.as_view(), name="mejora-revision-jefatura"),
    path("envio-formal/", ProcesoEnvioFormalView.as_view(), name="mejora-envio-formal"),
    path("recepcion-evaluador/", ProcesoRecepcionEvaluadorView.as_view(), name="mejora-recepcion-evaluador"),
]
