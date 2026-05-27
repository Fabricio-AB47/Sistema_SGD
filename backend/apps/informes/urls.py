from django.urls import path

from apps.informes.views.web import (
    InformeApproveView,
    InformeDetailView,
    InformeGenerateView,
    InformeListView,
    ReporteEstadoView,
    ReporteIndicadorView,
    ReportePeriodoView,
)

urlpatterns = [
    path("", InformeListView.as_view(), name="informes-lista"),
    path("generar/", InformeGenerateView.as_view(), name="informes-generar"),
    path("detalle/", InformeDetailView.as_view(), name="informes-detalle"),
    path("aprobar/", InformeApproveView.as_view(), name="informes-aprobar"),
    path("reportes/indicador/", ReporteIndicadorView.as_view(), name="informes-reporte-indicador"),
    path("reportes/estado/", ReporteEstadoView.as_view(), name="informes-reporte-estado"),
    path("reportes/periodo/", ReportePeriodoView.as_view(), name="informes-reporte-periodo"),
]
