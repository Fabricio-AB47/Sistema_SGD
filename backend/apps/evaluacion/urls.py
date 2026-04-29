from django.urls import path

from apps.evaluacion.views.web import (
    EvaluacionFormView,
    EvaluacionInboxView,
    EvidenciaDetailView,
    EvidenciaListView,
    EvidenciaRegistroRedirectView,
    ObservacionFormView,
    TareaEvidenciaListView,
    TareaReasignacionView,
)

urlpatterns = [
    path(
        "evidencias/registrar/",
        EvidenciaRegistroRedirectView.as_view(),
        name="evaluacion-evidencia-registrar",
    ),
    path("evidencias/", EvidenciaListView.as_view(), name="evaluacion-evidencias-lista"),
    path("tareas/", TareaEvidenciaListView.as_view(), name="evaluacion-tareas"),
    path(
        "tareas/reasignacion/",
        TareaReasignacionView.as_view(),
        name="evaluacion-tareas-reasignacion",
    ),
    path(
        "evidencias/detalle/",
        EvidenciaDetailView.as_view(),
        name="evaluacion-evidencia-detalle",
    ),
    path("bandeja/", EvaluacionInboxView.as_view(), name="evaluacion-bandeja"),
    path("evaluar/", EvaluacionFormView.as_view(), name="evaluacion-evaluar"),
    path("observaciones/", ObservacionFormView.as_view(), name="evaluacion-observaciones"),
]
