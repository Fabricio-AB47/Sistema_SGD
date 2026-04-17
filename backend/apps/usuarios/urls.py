from django.urls import path

from apps.usuarios.views.web import (
    AreaInstitucionalListView,
    CargoAreaListView,
    UsuarioListView,
    UsuarioCreateView,
    UsuarioUpdateView,
    UsuarioDetailView,
    UsuarioAsignarRolesView,
    UsuarioEstructuraView,
    OrganigramaInstitucionalView,
    CambiarContextoOperativoView,
    RolListView,
    RolCreateView,
)

urlpatterns = [
    path("usuarios/", UsuarioListView.as_view(), name="usuarios-lista"),
    path("usuarios/nuevo/", UsuarioCreateView.as_view(), name="usuarios-crear"),
    path("usuarios/<int:pk>/", UsuarioDetailView.as_view(), name="usuarios-detalle"),
    path("usuarios/<int:pk>/editar/", UsuarioUpdateView.as_view(), name="usuarios-editar"),
    path("usuarios/<int:pk>/roles/", UsuarioAsignarRolesView.as_view(), name="usuarios-asignar-roles"),
    path("usuarios/<int:pk>/estructura/", UsuarioEstructuraView.as_view(), name="usuarios-estructura"),
    path("usuarios/contexto/cambiar/", CambiarContextoOperativoView.as_view(), name="usuarios-cambiar-contexto"),
    path("usuarios/organigrama/", OrganigramaInstitucionalView.as_view(), name="usuarios-organigrama"),
    path("roles/", RolListView.as_view(), name="roles-lista"),
    path("roles/nuevo/", RolCreateView.as_view(), name="roles-crear"),
    path("usuarios/estructura/areas/", AreaInstitucionalListView.as_view(), name="usuarios-areas"),
    path("usuarios/estructura/cargos/", CargoAreaListView.as_view(), name="usuarios-cargos"),
]
