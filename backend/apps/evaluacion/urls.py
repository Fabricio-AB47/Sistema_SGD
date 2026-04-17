from django.urls import path

from apps.evaluacion.views.web import (
    EvaluacionFormView,
    EvaluacionInboxView,
    EvidenciaDetailView,
    EvidenciaListView,
    EvidenciaRegistroRedirectView,
    ObservacionFormView,
)

urlpatterns = [
    path(
        "evidencias/registrar/",
        EvidenciaRegistroRedirectView.as_view(),
        name="evaluacion-evidencia-registrar",
    ),
    path("evidencias/", EvidenciaListView.as_view(), name="evaluacion-evidencias-lista"),
    path(
        "evidencias/detalle/",
        EvidenciaDetailView.as_view(),
        name="evaluacion-evidencia-detalle",
    ),
    path("bandeja/", EvaluacionInboxView.as_view(), name="evaluacion-bandeja"),
    path("evaluar/", EvaluacionFormView.as_view(), name="evaluacion-evaluar"),
    path("observaciones/", ObservacionFormView.as_view(), name="evaluacion-observaciones"),
]
