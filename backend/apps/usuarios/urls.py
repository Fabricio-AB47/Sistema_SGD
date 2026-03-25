from django.urls import path

from apps.usuarios.views.web import (
    UsuarioListView,
    UsuarioCreateView,
    UsuarioUpdateView,
    UsuarioDetailView,
    UsuarioAsignarRolesView,
    RolListView,
    RolCreateView,
)

urlpatterns = [
    path("usuarios/", UsuarioListView.as_view(), name="usuarios-lista"),
    path("usuarios/nuevo/", UsuarioCreateView.as_view(), name="usuarios-crear"),
    path("usuarios/<int:pk>/", UsuarioDetailView.as_view(), name="usuarios-detalle"),
    path("usuarios/<int:pk>/editar/", UsuarioUpdateView.as_view(), name="usuarios-editar"),
    path("usuarios/<int:pk>/roles/", UsuarioAsignarRolesView.as_view(), name="usuarios-asignar-roles"),
    path("roles/", RolListView.as_view(), name="roles-lista"),
    path("roles/nuevo/", RolCreateView.as_view(), name="roles-crear"),
]
