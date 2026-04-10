from django.urls import path

from apps.permisos.views.web import (
    RoleDetailView,
    RoleIndicatorAccessRedirectView,
    RoleIndicatorElementAccessRedirectView,
    RoleListView,
    RolePermissionView,
    RoleStructureAccessView,
    RoleStructureAccessRedirectView,
    UserRoleAssignmentView,
)

urlpatterns = [
    path("roles/", RoleListView.as_view(), name="permisos-roles-lista"),
    path("roles/detalle/", RoleDetailView.as_view(), name="permisos-roles-detalle"),
    path("roles/permisos/", RolePermissionView.as_view(), name="permisos-roles-permisos"),
    path("usuario-rol/", UserRoleAssignmentView.as_view(), name="permisos-usuario-rol"),
    path("acceso-evaluacion/", RoleStructureAccessView.as_view(), name="permisos-acceso-evaluacion"),
    path("acceso-estructural/", RoleStructureAccessRedirectView.as_view(), name="permisos-acceso-estructural"),
    path("acceso-indicador/", RoleIndicatorAccessRedirectView.as_view(), name="permisos-acceso-indicador"),
    path("acceso-elemento/", RoleIndicatorElementAccessRedirectView.as_view(), name="permisos-acceso-elemento"),
]
