from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from apps.usuarios.models import Usuario, UsuarioAreaCargo


ROLE_ADMIN = "ADMINISTRADOR"
ROLE_QUALITY = "CALIDAD ACADEMICA"
ROLE_QUALITY_ALIASES = {
    "DIRECTOR DE CALIDAD",
    "DIRECCION DE CALIDAD",
    "CALIDAD",
}
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
HEAD_CARGO_ROLES = {
    "DIRECTOR DE TECNOLOGIA",
    "DIRECTOR FINANCIERO",
    "DIRECTOR DE ADMISIONES",
    "DIRECTOR ACADEMICO",
    "DIRECTOR DE BIENESTAR",
    "DIRECTOR DE CALIDAD",
    ROLE_RECTOR,
}
REASSIGNMENT_BLOCKED_ROLES = {ROLE_EVALUATOR, ROLE_CONSULTA}
QUALITY_ALLOWED_GROUPS = {
    "Acreditacion y estructura",
    "Operacion documental",
    "Informes y mejora",
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
                roles=(ROLE_ADMIN,),
                icon="users",
            ),
            NavigationItem(
                label="Roles",
                url_name="roles-lista",
                active_names=("roles-lista", "roles-crear"),
                roles=(ROLE_ADMIN,),
                icon="shield",
            ),
            NavigationItem(
                label="Areas institucionales",
                url_name="usuarios-areas",
                active_names=("usuarios-areas",),
                roles=(ROLE_ADMIN,),
                icon="map",
            ),
            NavigationItem(
                label="Cargos por area",
                url_name="usuarios-cargos",
                active_names=("usuarios-cargos",),
                roles=(ROLE_ADMIN,),
                icon="briefcase",
            ),
            NavigationItem(
                label="Organigrama institucional",
                url_name="usuarios-organigrama",
                active_names=("usuarios-organigrama",),
                roles=(ROLE_ADMIN,),
                icon="orgchart",
            ),
            NavigationItem(
                label="Sesiones",
                url_name="seguridad-sesiones",
                active_names=("seguridad-sesiones",),
                roles=(ROLE_ADMIN,),
                icon="clock",
            ),
            NavigationItem(
                label="Permisos por rol",
                url_name="permisos-roles-permisos",
                active_names=("permisos-roles-permisos", "permisos-roles-detalle"),
                roles=(ROLE_ADMIN,),
                icon="key",
            ),
            NavigationItem(
                label="Asignacion usuario-rol",
                url_name="permisos-usuario-rol",
                active_names=("permisos-usuario-rol",),
                roles=(ROLE_ADMIN,),
                icon="swap",
            ),
            NavigationItem(
                label="Acceso a evaluacion",
                url_name="permisos-acceso-evaluacion",
                active_names=(
                    "permisos-acceso-evaluacion",
                    "permisos-acceso-evaluacion-directores",
                    "permisos-acceso-estructural",
                    "permisos-acceso-indicador",
                    "permisos-acceso-elemento",
                ),
                roles=(ROLE_ADMIN,),
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
                label="Importar matriz CACES",
                url_name="acreditacion-caces-importar",
                active_names=("acreditacion-caces-importar",),
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
                    "acreditacion-matriz-registro-subir",
                    "acreditacion-matriz-evidencias",
                ),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA, *AREA_ROLES),
                permissions=(PERM_ACREDITACION_VER, PERM_EVIDENCIAS_REGISTRAR, PERM_CONSULTA_VER),
            ),
            NavigationItem(
                label="Matriz de acreditacion",
                url_name="acreditacion-matriz",
                active_names=("acreditacion-matriz",),
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
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA),
                permissions=("documentos.ver", PERM_CONSULTA_VER),
            ),
            NavigationItem(
                label="Subir documento",
                url_name="documentos-subir",
                active_names=("documentos-subir",),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=("documentos.subir", "documentos.versionar"),
            ),
            NavigationItem(
                label="Evidencias",
                url_name="evaluacion-evidencias-lista",
                active_names=(
                    "evaluacion-evidencias-lista",
                    "evaluacion-evidencia-registrar",
                    "evaluacion-evidencia-detalle",
                ),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA),
                permissions=(PERM_EVALUACION_REVISAR, PERM_CONSULTA_VER),
            ),
            NavigationItem(
                label="Tareas de evidencia",
                url_name="evaluacion-tareas",
                active_names=("evaluacion-tareas",),
                roles=(ROLE_ADMIN, ROLE_QUALITY),
                permissions=(PERM_EVALUACION_REVISAR,),
            ),
            NavigationItem(
                label="Reasignacion de tareas",
                url_name="evaluacion-tareas-reasignacion",
                active_names=("evaluacion-tareas-reasignacion",),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, *HEAD_CARGO_ROLES),
                permissions=(PERM_EVALUACION_REVISAR,),
            ),
            NavigationItem(
                label="Bandeja de evaluacion",
                url_name="evaluacion-bandeja",
                active_names=(
                    "evaluacion-bandeja",
                    "evaluacion-caces",
                    "evaluacion-caces-ciclo",
                    "evaluacion-caces-indicador",
                    "evaluacion-caces-reporte",
                ),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_EVALUATOR),
            ),
            NavigationItem(
                label="Observaciones",
                url_name="evaluacion-observaciones",
                active_names=("evaluacion-observaciones",),
                roles=(ROLE_ADMIN,),
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
                label="Reporte por indicador",
                url_name="informes-reporte-indicador",
                active_names=("informes-reporte-indicador",),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA),
                permissions=(PERM_CONSULTA_VER,),
            ),
            NavigationItem(
                label="Reporte por estado",
                url_name="informes-reporte-estado",
                active_names=("informes-reporte-estado",),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA),
                permissions=(PERM_CONSULTA_VER,),
            ),
            NavigationItem(
                label="Reporte por periodo",
                url_name="informes-reporte-periodo",
                active_names=("informes-reporte-periodo",),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA),
                permissions=(PERM_CONSULTA_VER,),
            ),
            NavigationItem(
                label="Proceso de mejora",
                url_name="mejora-lista",
                active_names=("mejora-lista", "mejora-detalle"),
                roles=(ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA),
                permissions=(PERM_MEJORA_GESTIONAR, PERM_CONSULTA_VER),
            ),
            NavigationItem(
                label="Iniciar proceso",
                url_name="mejora-crear",
                active_names=(
                    "mejora-crear",
                    "mejora-ciclo-aprobacion",
                    "mejora-asignacion-responsables",
                    "mejora-carga-informacion",
                    "mejora-revision-jefatura",
                    "mejora-detalle",
                    "mejora-envio-formal",
                    "mejora-recepcion-evaluador",
                ),
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
    normalized_roles = set()
    for role in role_names:
        raw_role = str(role).strip()
        if not raw_role:
            continue
        normalized = unicodedata.normalize("NFKD", raw_role)
        ascii_role = normalized.encode("ascii", "ignore").decode("ascii")
        normalized_roles.add(" ".join(ascii_role.upper().split()))
    if normalized_roles.intersection(ROLE_QUALITY_ALIASES):
        normalized_roles.add(ROLE_QUALITY)
    return normalized_roles


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
            if (
                item.url_name == "evaluacion-tareas-reasignacion"
                and normalized_roles.intersection(REASSIGNMENT_BLOCKED_ROLES)
            ):
                continue
            if not item.roles and not item.permissions:
                visible_items.append(item)
                continue
            role_ok = bool(item.roles) and _has_matching_role(normalized_roles, item.roles)
            permission_ok = bool(item.permissions) and _has_matching_permission(
                normalized_permissions,
                item.permissions,
            )
            if role_ok or permission_ok:
                visible_items.append(item)
        if visible_items:
            active_names = tuple(
                dict.fromkeys(
                    active_name
                    for item in visible_items
                    for active_name in item.active_names
                )
            )
            visible_groups.append(
                {
                    "label": group["label"],
                    "items": visible_items,
                    "active_names": active_names,
                }
            )

    # The quality role must only see the operational modules requested by business.
    if ROLE_QUALITY in normalized_roles and not has_global_access:
        visible_groups = [
            group for group in visible_groups if group["label"] in QUALITY_ALLOWED_GROUPS
        ]

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
