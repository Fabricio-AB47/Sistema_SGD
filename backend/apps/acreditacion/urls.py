from django.urls import path
from django.views.generic import RedirectView

from apps.acreditacion.views.web import (
    CicloCreateView,
    CicloDetailView,
    CicloEstadoUpdateView,
    CicloListView,
    CriterioListView,
    ElementoListView,
    IndicadorDetailView,
    IndicadorListView,
    MatrizRegistroUploadView,
    MatrizRegistroView,
    MatrizView,
    SubcriterioListView,
)

urlpatterns = [
    path("criterios/", CriterioListView.as_view(), name="acreditacion-criterios-lista"),
    path("subcriterios/", SubcriterioListView.as_view(), name="acreditacion-subcriterios-lista"),
    path("indicadores/", IndicadorListView.as_view(), name="acreditacion-indicadores-lista"),
    path("indicadores/detalle/", IndicadorDetailView.as_view(), name="acreditacion-indicadores-detalle"),
    path("elementos/", ElementoListView.as_view(), name="acreditacion-elementos-lista"),
    path("matriz-registro/", MatrizRegistroView.as_view(), name="acreditacion-matriz-registro"),
    path(
        "matriz-registro/subir/",
        MatrizRegistroUploadView.as_view(),
        name="acreditacion-matriz-registro-subir",
    ),
    path(
        "matriz-evidencias/",
        RedirectView.as_view(
            pattern_name="acreditacion-matriz",
            permanent=False,
            query_string=True,
        ),
        name="acreditacion-matriz-evidencias",
    ),
    path("matriz/", MatrizView.as_view(), name="acreditacion-matriz"),
    path("ciclos/", CicloListView.as_view(), name="acreditacion-ciclos-lista"),
    path("ciclos/crear/", CicloCreateView.as_view(), name="acreditacion-ciclos-crear"),
    path("ciclos/<int:ciclo_id>/", CicloDetailView.as_view(), name="acreditacion-ciclos-detalle"),
    path("ciclos/<int:ciclo_id>/estado/", CicloEstadoUpdateView.as_view(), name="acreditacion-ciclos-estado"),
    path(
        "asignaciones/indicador/",
        RedirectView.as_view(pattern_name="permisos-acceso-evaluacion", permanent=False),
        name="acreditacion-asignacion-indicador",
    ),
    path(
        "asignaciones/elemento/",
        RedirectView.as_view(pattern_name="permisos-acceso-evaluacion", permanent=False),
        name="acreditacion-asignacion-elemento",
    ),
]
