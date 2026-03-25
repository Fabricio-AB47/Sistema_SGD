from collections import OrderedDict

from django.db.models import Count, Prefetch, Q

from apps.acreditacion.models import RolIndicador, RolIndicadorElemento
from apps.permisos.models import Permiso, Rol, RolPermiso, UsuarioRol


def get_permission_metrics():
    return {
        "roles": Rol.objects.count(),
        "permisos": Permiso.objects.count(),
        "usuarios_roles": UsuarioRol.objects.filter(activo=True).count(),
        "accesos_indicador": RolIndicador.objects.filter(activo=True).count(),
        "accesos_elemento": RolIndicadorElemento.objects.count(),
    }


def get_roles_queryset():
    return (
        Rol.objects.annotate(
            permisos_count=Count("permisos_asignados__permiso", distinct=True),
            usuarios_count=Count(
                "usuarios__usuario",
                filter=Q(usuarios__activo=True),
                distinct=True,
            ),
            indicadores_count=Count(
                "indicadores_asignados__indicador",
                filter=Q(indicadores_asignados__activo=True),
                distinct=True,
            ),
        )
        .order_by("nombre_rol")
    )


def get_role_detail(role_id):
    if not role_id:
        return None

    return (
        Rol.objects.prefetch_related(
            Prefetch(
                "permisos_asignados",
                queryset=RolPermiso_related_queryset(),
                to_attr="permisos_detalle",
            ),
            Prefetch(
                "usuarios",
                queryset=UsuarioRol_related_queryset(),
                to_attr="usuarios_detalle",
            ),
            Prefetch(
                "indicadores_asignados",
                queryset=RolIndicador_related_queryset(),
                to_attr="indicadores_detalle",
            ),
        )
        .filter(pk=role_id)
        .first()
    )


def RolPermiso_related_queryset():
    return RolPermiso.objects.select_related("permiso").order_by(
        "permiso__modulo", "permiso__codigo_permiso"
    )


def UsuarioRol_related_queryset():
    return (
        UsuarioRol.objects.select_related("usuario", "asignado_por")
        .order_by("-activo", "usuario__primer_apellido", "usuario__primer_nombre")
    )


def RolIndicador_related_queryset():
    return (
        RolIndicador.objects.select_related(
            "indicador__subcriterio__criterio",
            "ciclo",
            "asignado_por",
        ).order_by("-activo", "ciclo__fecha_inicio", "indicador__codigo_indicador")
    )


def get_permissions_grouped():
    grouped = OrderedDict()
    for permiso in Permiso.objects.filter(activo=True).order_by("modulo", "codigo_permiso"):
        grouped.setdefault(permiso.modulo, []).append(permiso)
    return grouped


def get_role_permissions(role_id=None):
    queryset = Rol.objects.order_by("nombre_rol")
    selected_role = queryset.filter(pk=role_id).first() if role_id else queryset.first()
    assigned_ids = set()
    if selected_role:
        assigned_ids = set(
            selected_role.permisos_asignados.values_list("permiso_id", flat=True)
        )
    return {
        "roles": queryset,
        "selected_role": selected_role,
        "permissions_grouped": get_permissions_grouped(),
        "assigned_ids": assigned_ids,
    }


def get_user_role_assignments():
    return (
        UsuarioRol.objects.select_related("usuario", "rol", "asignado_por")
        .order_by("-activo", "-fecha_asignacion")
    )


def get_role_indicator_assignments():
    return (
        RolIndicador.objects.select_related(
            "rol",
            "indicador__subcriterio__criterio",
            "ciclo",
            "asignado_por",
        )
        .order_by("-activo", "rol__nombre_rol", "indicador__codigo_indicador")
    )


def get_role_indicator_element_assignments():
    return (
        RolIndicadorElemento.objects.select_related(
            "rol_indicador__rol",
            "rol_indicador__indicador",
            "rol_indicador__ciclo",
            "elemento_fundamental",
            "asignado_por",
        )
        .order_by(
            "rol_indicador__rol__nombre_rol",
            "rol_indicador__indicador__codigo_indicador",
            "elemento_fundamental__codigo_elemento",
        )
    )
