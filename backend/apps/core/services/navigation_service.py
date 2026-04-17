from __future__ import annotations

from dataclasses import dataclass

from apps.usuarios.models import Usuario, UsuarioAreaCargo


ROLE_ADMIN = "ADMINISTRADOR"
ROLE_QUALITY = "CALIDAD ACADEMICA"
ROLE_RECTOR = "RECTOR"
ROLE_EVALUATOR = "EVALUADOR"
ROLE_CONSULTA = "CONSULTA"
PERM_USUARIOS_VER = "usuarios.ver"
PERM_USUARIOS_CREAR = "usuarios.crear"
PERM_USUARIOS_EDITAR = "usuarios.editar"
PERM_ROLES_GESTIONAR = "roles.gestionar"
PERM_ACREDITACION_GESTIONAR = "acreditacion.gestionar"
PERM_ACREDITACION_VER = "acreditacion.ver"
PERM_EVIDENCIAS_REGISTRAR = "evidencias.registrar"
PERM_CONSULTA_VER = "consulta.ver"
PERM_EVALUACION_REVISAR = "evaluacion.revisar"
PERM_MEJORA_GESTIONAR = "mejora.gestionar"
AREA_ROLES = {
    "TECNOLOGIA",
    "FINANCIERO",
    "ADMISIONES",
    "ACADEMICO",
    "BIENESTAR",
}


@dataclass(frozen=True)
class NavigationItem:
    label: str
    url_name: str
    active_names: tuple[str, ...]
    roles: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    icon: str = "compass"


NAVIGATION_GROUPS = (
    {
        "label": "Inicio",
        "items": (
            NavigationItem(
                label="Dashboard",
                url_name="core-dashboard",
                active_names=("core-dashboard",),
            ),
        ),
    },
    {
        "label": "Seguridad y administracion",
        "items": (
            NavigationItem(
                label="Usuarios",
                url_name="usuarios-lista",
                active_names=(
                    "usuarios-lista",
                    "usuarios-crear",
                    "usuarios-detalle",
                    "usuarios-editar",
                    "usuarios-asignar-roles",
                    "usuarios-estructura",
                ),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_USUARIOS_VER, PERM_USUARIOS_CREAR, PERM_USUARIOS_EDITAR),
                icon="users",
            ),
            NavigationItem(
                label="Roles",
                url_name="roles-lista",
                active_names=("roles-lista", "roles-crear"),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_ROLES_GESTIONAR,),
                icon="shield",
            ),
            NavigationItem(
                label="Areas institucionales",
                url_name="usuarios-areas",
                active_names=("usuarios-areas",),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_USUARIOS_EDITAR,),
                icon="map",
            ),
            NavigationItem(
                label="Cargos por area",
                url_name="usuarios-cargos",
                active_names=("usuarios-cargos",),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_USUARIOS_EDITAR,),
                icon="briefcase",
            ),
            NavigationItem(
                label="Organigrama institucional",
                url_name="usuarios-organigrama",
                active_names=("usuarios-organigrama",),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_USUARIOS_VER, PERM_USUARIOS_EDITAR),
                icon="orgchart",
            ),
            NavigationItem(
                label="Sesiones",
                url_name="seguridad-sesiones",
                active_names=("seguridad-sesiones",),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_EVALUATOR, ROLE_CONSULTA),
                icon="clock",
            ),
            NavigationItem(
                label="Permisos por rol",
                url_name="permisos-roles-permisos",
                active_names=("permisos-roles-permisos", "permisos-roles-detalle"),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_ROLES_GESTIONAR,),
                icon="key",
            ),
            NavigationItem(
                label="Asignacion usuario-rol",
                url_name="permisos-usuario-rol",
                active_names=("permisos-usuario-rol",),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_ROLES_GESTIONAR,),
                icon="swap",
            ),
            NavigationItem(
                label="Acceso a evaluacion",
                url_name="permisos-acceso-evaluacion",
                active_names=(
                    "permisos-acceso-evaluacion",
                    "permisos-acceso-estructural",
                    "permisos-acceso-indicador",
                    "permisos-acceso-elemento",
                ),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_ROLES_GESTIONAR,),
            ),
            NavigationItem(
                label="Servicios API",
                url_name="integraciones-servicios-lista",
                active_names=(
                    "integraciones-servicios-lista",
                    "integraciones-servicios-crear",
                    "integraciones-servicios-editar",
                ),
                roles=(ROLE_ADMIN,),
            ),
            NavigationItem(
                label="Credenciales API",
                url_name="integraciones-credenciales-lista",
                active_names=(
                    "integraciones-credenciales-lista",
                    "integraciones-credenciales-crear",
                    "integraciones-credenciales-editar",
                ),
                roles=(ROLE_ADMIN,),
            ),
            NavigationItem(
                label="Tokens API",
                url_name="integraciones-tokens-lista",
                active_names=("integraciones-tokens-lista",),
                roles=(ROLE_ADMIN,),
            ),
            NavigationItem(
                label="Consumos API",
                url_name="integraciones-consumos-lista",
                active_names=("integraciones-consumos-lista",),
                roles=(ROLE_ADMIN,),
            ),
        ),
    },
    {
        "label": "Acreditacion y estructura",
        "items": (
            NavigationItem(
                label="Ciclos y autorizacion",
                url_name="acreditacion-ciclos-lista",
                active_names=(
                    "acreditacion-ciclos-lista",
                    "acreditacion-ciclos-crear",
                    "acreditacion-ciclos-detalle",
                    "acreditacion-ciclos-estado",
                ),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR),
                permissions=("ciclos.gestionar",),
            ),
            NavigationItem(
                label="Criterios",
                url_name="acreditacion-criterios-lista",
                active_names=("acreditacion-criterios-lista",),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_ACREDITACION_GESTIONAR,),
            ),
            NavigationItem(
                label="Subcriterios",
                url_name="acreditacion-subcriterios-lista",
                active_names=("acreditacion-subcriterios-lista",),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_ACREDITACION_GESTIONAR,),
            ),
            NavigationItem(
                label="Indicadores",
                url_name="acreditacion-indicadores-lista",
                active_names=("acreditacion-indicadores-lista", "acreditacion-indicadores-detalle"),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_ACREDITACION_GESTIONAR,),
            ),
            NavigationItem(
                label="Elementos fundamentales",
                url_name="acreditacion-elementos-lista",
                active_names=("acreditacion-elementos-lista",),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_ACREDITACION_GESTIONAR,),
            ),
            NavigationItem(
                label="Matriz de registro",
                url_name="acreditacion-matriz-registro",
                active_names=(
                    "acreditacion-matriz-registro",
                    "acreditacion-matriz-evidencias",
                    "acreditacion-matriz",
                ),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA, *AREA_ROLES),
                permissions=(PERM_ACREDITACION_VER, PERM_EVIDENCIAS_REGISTRAR, PERM_CONSULTA_VER),
            ),
        ),
    },
    {
        "label": "Operacion documental",
        "items": (
            NavigationItem(
                label="Gestion documental",
                url_name="documentos-lista",
                active_names=(
                    "documentos-clasificaciones-lista",
                    "documentos-lista",
                    "documentos-detalle",
                    "documentos-versiones",
                    "documentos-accesos",
                ),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_EVALUATOR, ROLE_CONSULTA, *AREA_ROLES),
                permissions=("documentos.ver", PERM_CONSULTA_VER),
            ),
            NavigationItem(
                label="Subir documento",
                url_name="documentos-subir",
                active_names=("documentos-subir",),
                roles=(ROLE_ADMIN, ROLE_QUALITY, *AREA_ROLES),
                permissions=("documentos.subir", "documentos.versionar", PERM_EVIDENCIAS_REGISTRAR),
            ),
            NavigationItem(
                label="Evidencias",
                url_name="evaluacion-evidencias-lista",
                active_names=(
                    "evaluacion-evidencias-lista",
                    "evaluacion-evidencia-registrar",
                    "evaluacion-evidencia-detalle",
                ),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_EVALUATOR, ROLE_CONSULTA, *AREA_ROLES),
                permissions=(PERM_EVIDENCIAS_REGISTRAR, PERM_EVALUACION_REVISAR, PERM_CONSULTA_VER),
            ),
            NavigationItem(
                label="Bandeja de evaluacion",
                url_name="evaluacion-bandeja",
                active_names=("evaluacion-bandeja",),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_EVALUATOR),
                permissions=(PERM_EVALUACION_REVISAR,),
            ),
            NavigationItem(
                label="Evaluar evidencia",
                url_name="evaluacion-evaluar",
                active_names=("evaluacion-evaluar",),
                roles=(ROLE_ADMIN, ROLE_EVALUATOR),
                permissions=(PERM_EVALUACION_REVISAR,),
            ),
            NavigationItem(
                label="Observaciones",
                url_name="evaluacion-observaciones",
                active_names=("evaluacion-observaciones",),
                roles=(ROLE_ADMIN, ROLE_EVALUATOR),
                permissions=(PERM_EVALUACION_REVISAR,),
            ),
        ),
    },
    {
        "label": "Informes y mejora",
        "items": (
            NavigationItem(
                label="Informes",
                url_name="informes-lista",
                active_names=("informes-lista", "informes-detalle"),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA),
                permissions=("informes.generar", "informes.aprobar", PERM_CONSULTA_VER),
            ),
            NavigationItem(
                label="Generar informe",
                url_name="informes-generar",
                active_names=("informes-generar",),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=("informes.generar",),
            ),
            NavigationItem(
                label="Aprobar informe",
                url_name="informes-aprobar",
                active_names=("informes-aprobar",),
                roles=(ROLE_ADMIN, ROLE_RECTOR),
                permissions=("informes.aprobar",),
            ),
            NavigationItem(
                label="Planes de mejora",
                url_name="mejora-lista",
                active_names=("mejora-lista", "mejora-detalle"),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA),
                permissions=(PERM_MEJORA_GESTIONAR, PERM_CONSULTA_VER),
            ),
            NavigationItem(
                label="Crear plan",
                url_name="mejora-crear",
                active_names=("mejora-crear",),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_MEJORA_GESTIONAR,),
            ),
            NavigationItem(
                label="Seguimiento",
                url_name="mejora-seguimiento",
                active_names=("mejora-seguimiento",),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR),
                permissions=(PERM_MEJORA_GESTIONAR,),
            ),
        ),
    },
    {
        "label": "Control y consulta",
        "items": (
            NavigationItem(
                label="Auditoria",
                url_name="auditoria-lista",
                active_names=("auditoria-lista", "auditoria-detalle"),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=("auditoria.ver",),
            ),
        ),
    },
)


ROLE_PRIORITY = (
    ROLE_ADMIN,
    ROLE_QUALITY,
    ROLE_RECTOR,
    ROLE_EVALUATOR,
    "TECNOLOGIA",
    "FINANCIERO",
    "ADMISIONES",
    "ACADEMICO",
    "BIENESTAR",
    ROLE_CONSULTA,
)


def _normalize_roles(role_names: list[str] | tuple[str, ...]) -> set[str]:
    return {str(role).strip().upper() for role in role_names if str(role).strip()}


def _normalize_permissions(permission_codes: list[str] | tuple[str, ...]) -> set[str]:
    return {str(code).strip().lower() for code in permission_codes if str(code).strip()}


def _has_matching_role(normalized_roles: set[str], allowed_roles: tuple[str, ...]) -> bool:
    if not allowed_roles:
        return True
    return any(role in normalized_roles for role in allowed_roles)


def _has_matching_permission(
    normalized_permissions: set[str],
    allowed_permissions: tuple[str, ...],
) -> bool:
    if not allowed_permissions:
        return True
    if not normalized_permissions:
        return False
    return any(permission in normalized_permissions for permission in allowed_permissions)


def build_navigation_groups(*, role_names=(), permission_codes=()):
    normalized_roles = _normalize_roles(role_names)
    normalized_permissions = _normalize_permissions(permission_codes)
    has_global_access = ROLE_ADMIN in normalized_roles
    visible_groups = []

    for group in NAVIGATION_GROUPS:
        visible_items = []
        for item in group["items"]:
            if has_global_access:
                visible_items.append(item)
                continue
            role_ok = _has_matching_role(normalized_roles, item.roles)
            permission_ok = _has_matching_permission(normalized_permissions, item.permissions)
            if role_ok or permission_ok:
                visible_items.append(item)
        if visible_items:
            visible_groups.append(
                {
                    "label": group["label"],
                    "items": visible_items,
                }
            )
    return visible_groups


def get_primary_role(role_names=()) -> str | None:
    normalized_roles = _normalize_roles(role_names)
    for role in ROLE_PRIORITY:
        if role in normalized_roles:
            return role.title()
    return next(iter(role_names), None)


def get_user_profile_context(
    *,
    user_id: int | None,
    role_names=(),
    permission_codes=(),
    operational_roles=(),
    active_assignment_id: int | None = None,
    assignment_options=(),
):
    effective_roles = tuple(dict.fromkeys([*tuple(role_names), *tuple(operational_roles)]))
    if not user_id:
        return {
            "display_name": "SIG",
            "primary_role": None,
            "roles": [],
            "area_cargo": None,
            "assignment_options": [],
            "active_assignment_id": None,
            "navigation_groups": build_navigation_groups(
                role_names=effective_roles,
                permission_codes=permission_codes,
            ),
        }

    usuario = (
        Usuario.objects.only(
            "id_user",
            "primer_nombre",
            "segundo_nombre",
            "primer_apellido",
            "segundo_apellido",
            "correo",
        )
        .filter(pk=user_id)
        .first()
    )
    if usuario is None:
        return {
            "display_name": "SIG",
            "primary_role": None,
            "roles": [],
            "area_cargo": None,
            "assignment_options": [],
            "active_assignment_id": None,
            "navigation_groups": build_navigation_groups(
                role_names=effective_roles,
                permission_codes=permission_codes,
            ),
        }

    assignments_queryset = (
        UsuarioAreaCargo.objects.select_related("area", "cargo")
        .filter(usuario_id=user_id, activo=True, area__activo=True, cargo__activo=True)
        .order_by("cargo__nivel_jerarquico", "-fecha_asignacion")
    )

    active_area_cargo = None
    if active_assignment_id:
        active_area_cargo = assignments_queryset.filter(pk=active_assignment_id).first()
    if active_area_cargo is None:
        active_area_cargo = assignments_queryset.first()

    area_cargo = None
    if active_area_cargo is not None:
        area_cargo = {
            "area": active_area_cargo.area.nombre_area,
            "cargo": active_area_cargo.cargo.nombre_cargo,
        }

    resolved_options = list(assignment_options or [])
    if not resolved_options:
        resolved_options = [
            {
                "id": assignment.pk,
                "area": assignment.area.nombre_area,
                "cargo": assignment.cargo.nombre_cargo,
            }
            for assignment in assignments_queryset
        ]

    return {
        "display_name": usuario.nombre_completo or usuario.correo,
        "primary_role": get_primary_role(effective_roles),
        "roles": list(effective_roles),
        "area_cargo": area_cargo,
        "assignment_options": resolved_options,
        "active_assignment_id": getattr(active_area_cargo, "pk", None),
        "navigation_groups": build_navigation_groups(
            role_names=effective_roles,
            permission_codes=permission_codes,
        ),
    }
