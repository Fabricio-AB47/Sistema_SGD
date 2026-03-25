from django.urls import path

from apps.integraciones.views import (
    ConsumoLogView,
    CredencialCreateView,
    CredencialListView,
    ServicioCreateView,
    ServicioListView,
    ServicioUpdateView,
    TokenListView,
    generar_token_view,
)


urlpatterns = [
    path("integraciones/servicios/", ServicioListView.as_view(), name="integraciones-servicios-lista"),
    path("integraciones/servicios/nuevo/", ServicioCreateView.as_view(), name="integraciones-servicios-crear"),
    path("integraciones/servicios/<int:pk>/editar/", ServicioUpdateView.as_view(), name="integraciones-servicios-editar"),
    path("integraciones/credenciales/", CredencialListView.as_view(), name="integraciones-credenciales-lista"),
    path("integraciones/credenciales/nueva/", CredencialCreateView.as_view(), name="integraciones-credenciales-crear"),
    path("integraciones/tokens/", TokenListView.as_view(), name="integraciones-tokens-lista"),
    path("integraciones/credenciales/<int:credencial_id>/generar-token/", generar_token_view, name="integraciones-generar-token"),
    path("integraciones/consumos/", ConsumoLogView.as_view(), name="integraciones-consumos-lista"),
]
