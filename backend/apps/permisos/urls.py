from django.urls import path

from apps.permisos.views.web import (
    RoleDetailView,
    RoleIndicatorAccessView,
    RoleIndicatorElementAccessView,
    RoleListView,
    RolePermissionView,
    UserRoleAssignmentView,
)

urlpatterns = [
    path("roles/", RoleListView.as_view(), name="permisos-roles-lista"),
    path("roles/detalle/", RoleDetailView.as_view(), name="permisos-roles-detalle"),
    path("roles/permisos/", RolePermissionView.as_view(), name="permisos-roles-permisos"),
    path("usuario-rol/", UserRoleAssignmentView.as_view(), name="permisos-usuario-rol"),
    path("acceso-indicador/", RoleIndicatorAccessView.as_view(), name="permisos-acceso-indicador"),
    path("acceso-elemento/", RoleIndicatorElementAccessView.as_view(), name="permisos-acceso-elemento"),
]
