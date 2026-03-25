from django.urls import path

from apps.auditoria.views.web import AuditoriaDetailView, AuditoriaListView


urlpatterns = [
    path("auditoria/", AuditoriaListView.as_view(), name="auditoria-lista"),
    path("auditoria/<int:pk>/", AuditoriaDetailView.as_view(), name="auditoria-detalle"),
]
