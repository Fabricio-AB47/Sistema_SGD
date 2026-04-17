from django.urls import path

from apps.informes.views.web import (
    InformeApproveView,
    InformeDetailView,
    InformeGenerateView,
    InformeListView,
)

urlpatterns = [
    path("", InformeListView.as_view(), name="informes-lista"),
    path("generar/", InformeGenerateView.as_view(), name="informes-generar"),
    path("detalle/", InformeDetailView.as_view(), name="informes-detalle"),
    path("aprobar/", InformeApproveView.as_view(), name="informes-aprobar"),
]
