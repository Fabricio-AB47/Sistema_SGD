from django.urls import path
from .views.web import DashboardView, InicioView

urlpatterns = [
    path("", InicioView.as_view(), name="core-inicio"),
    path("dashboard/", DashboardView.as_view(), name="core-dashboard"),
]
