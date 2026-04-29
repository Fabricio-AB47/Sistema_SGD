from django.urls import path
from .views.web import (
    DashboardView,
    InicioView,
    NotificacionMarcarLeidaView,
    NotificacionesMarcarTodasLeidasView,
)

urlpatterns = [
    path("", InicioView.as_view(), name="core-inicio"),
    path("dashboard/", DashboardView.as_view(), name="core-dashboard"),
    path(
        "notificaciones/<int:notificacion_id>/leer/",
        NotificacionMarcarLeidaView.as_view(),
        name="core-notificacion-leer",
    ),
    path(
        "notificaciones/leer-todas/",
        NotificacionesMarcarTodasLeidasView.as_view(),
        name="core-notificaciones-leer-todas",
    ),
]
