from django.urls import path

from apps.evaluacion.views.caces import (
    CacesCalculateQuantitativeApiView,
    CacesCategoriesApiView,
    CacesCoverageApiView,
    CacesCycleDashboardView,
    CacesCycleResultApiView,
    CacesCyclesApiView,
    CacesDashboardView,
    CacesFinalReportView,
    CacesIndicatorDetailView,
    CacesIndicatorResultApiView,
    CacesIndicatorsApiView,
    CacesPendingIndicatorsApiView,
    CacesSaveManualQuantitativeApiView,
    CacesSaveQualitativeApiView,
    CacesSaveVariablesApiView,
    CacesVariablesApiView,
)
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
    path("caces/", CacesDashboardView.as_view(), name="evaluacion-caces"),
    path("caces/ciclo/", CacesCycleDashboardView.as_view(), name="evaluacion-caces-ciclo"),
    path(
        "caces/indicador/",
        CacesIndicatorDetailView.as_view(),
        name="evaluacion-caces-indicador",
    ),
    path(
        "caces/reporte/",
        CacesFinalReportView.as_view(),
        name="evaluacion-caces-reporte",
    ),
    path("caces/api/ciclos/", CacesCyclesApiView.as_view(), name="evaluacion-caces-api-ciclos"),
    path(
        "caces/api/indicadores/",
        CacesIndicatorsApiView.as_view(),
        name="evaluacion-caces-api-indicadores",
    ),
    path(
        "caces/api/pendientes/",
        CacesPendingIndicatorsApiView.as_view(),
        name="evaluacion-caces-api-pendientes",
    ),
    path(
        "caces/api/categorias/",
        CacesCategoriesApiView.as_view(),
        name="evaluacion-caces-api-categorias",
    ),
    path(
        "caces/api/variables/",
        CacesVariablesApiView.as_view(),
        name="evaluacion-caces-api-variables",
    ),
    path(
        "caces/api/evaluacion/cualitativa/",
        CacesSaveQualitativeApiView.as_view(),
        name="evaluacion-caces-api-cualitativa",
    ),
    path(
        "caces/api/evaluacion/variables/",
        CacesSaveVariablesApiView.as_view(),
        name="evaluacion-caces-api-guardar-variables",
    ),
    path(
        "caces/api/evaluacion/calcular/",
        CacesCalculateQuantitativeApiView.as_view(),
        name="evaluacion-caces-api-calcular",
    ),
    path(
        "caces/api/evaluacion/manual/",
        CacesSaveManualQuantitativeApiView.as_view(),
        name="evaluacion-caces-api-manual",
    ),
    path(
        "caces/api/resultado-indicador/",
        CacesIndicatorResultApiView.as_view(),
        name="evaluacion-caces-api-resultado-indicador",
    ),
    path(
        "caces/api/resultado-ciclo/",
        CacesCycleResultApiView.as_view(),
        name="evaluacion-caces-api-resultado-ciclo",
    ),
    path(
        "caces/api/cobertura/",
        CacesCoverageApiView.as_view(),
        name="evaluacion-caces-api-cobertura",
    ),
]
