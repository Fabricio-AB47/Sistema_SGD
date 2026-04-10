from __future__ import annotations

from django.db.models import Q

from apps.acreditacion.models import RolIndicador, RolIndicadorElemento
from apps.usuarios.models import Permiso, RolPermiso, Usuario, UsuarioRol
from apps.usuarios.selectors.user_selector import get_active_permission_codes, get_active_roles


ROLE_ONLY_FIELDS = (
    "id_user_rol",
    "usuario_id",
    "rol_id",
    "activo",
    "rol__id_rol",
    "rol__nombre_rol",
    "rol__acceso_global",
    "rol__activo",
)


def _resolve_actor(actor) -> Usuario | None:
    if actor is None:
        return None
    if isinstance(actor, Usuario):
        return actor if actor.activo else None

    actor_id = getattr(actor, "pk", None) or getattr(actor, "id_user", None)
    if not actor_id:
        return None

    return Usuario.objects.filter(pk=actor_id, activo=True).first()


def _resolve_pk(value, attr_name: str) -> int | None:
    if value is None:
        return None
    return getattr(value, attr_name, None) or getattr(value, "pk", None) or value


def get_user_roles(actor):
    actor = _resolve_actor(actor)
    if actor is None:
        return UsuarioRol.objects.none()
    return get_active_roles(actor).only(*ROLE_ONLY_FIELDS)


def get_user_role_names(actor) -> tuple[str, ...]:
    return tuple(get_user_roles(actor).values_list("rol__nombre_rol", flat=True).distinct())


def get_user_permissions(actor) -> tuple[str, ...]:
    actor = _resolve_actor(actor)
    if actor is None:
        return ()
    return get_active_permission_codes(actor)


def get_user_permissions_queryset(actor):
    actor = _resolve_actor(actor)
    if actor is None:
        return Permiso.objects.none()

    return Permiso.objects.filter(
        activo=True,
        roles_asignados__rol__usuarios__usuario=actor,
        roles_asignados__rol__usuarios__activo=True,
        roles_asignados__rol__activo=True,
    ).distinct()


def has_global_access(actor) -> bool:
    return get_user_roles(actor).filter(rol__acceso_global=True).exists()


def has_permission(actor, codigo_permiso: str) -> bool:
    actor = _resolve_actor(actor)
    if actor is None or not codigo_permiso:
        return False
    if has_global_access(actor):
        return True

    return RolPermiso.objects.filter(
        rol__usuarios__usuario=actor,
        rol__usuarios__activo=True,
        rol__activo=True,
        permiso__activo=True,
        permiso__codigo_permiso__iexact=str(codigo_permiso).strip(),
    ).exists()


def has_any_permission(actor, *, codigos: tuple[str, ...] = (), modulos: tuple[str, ...] = ()) -> bool:
    actor = _resolve_actor(actor)
    if actor is None:
        return False
    if has_global_access(actor):
        return True

    normalized_codes = tuple(str(code).strip() for code in codigos if str(code).strip())
    normalized_modules = tuple(str(module).strip() for module in modulos if str(module).strip())

    if not normalized_codes and not normalized_modules:
        return True

    queryset = RolPermiso.objects.filter(
        rol__usuarios__usuario=actor,
        rol__usuarios__activo=True,
        rol__activo=True,
        permiso__activo=True,
    )

    if normalized_codes:
        code_filter = Q()
        for codigo in normalized_codes:
            code_filter |= Q(permiso__codigo_permiso__iexact=codigo)
        if queryset.filter(code_filter).exists():
            return True

    if normalized_modules:
        module_filter = Q()
        for modulo in normalized_modules:
            module_filter |= Q(permiso__modulo__iexact=modulo)
        if queryset.filter(module_filter).exists():
            return True

    return False


def has_indicator_access(actor, *, indicador, ciclo, elemento=None) -> bool:
    actor = _resolve_actor(actor)
    indicador_id = _resolve_pk(indicador, "id_indicador")
    ciclo_id = _resolve_pk(ciclo, "id_ciclo")
    elemento_id = _resolve_pk(elemento, "id_elemento_fundamental")

    if actor is None or not indicador_id or not ciclo_id:
        return False
    if has_global_access(actor):
        return True

    rol_ids = tuple(get_user_roles(actor).values_list("rol_id", flat=True))
    if not rol_ids:
        return False

    access_queryset = RolIndicador.objects.filter(
        rol_id__in=rol_ids,
        indicador_id=indicador_id,
        ciclo_id=ciclo_id,
        activo=True,
    )
    if not access_queryset.exists():
        return False

    if access_queryset.filter(acceso_total=True).exists() or elemento_id is None:
        return True

    return RolIndicadorElemento.objects.filter(
        rol_indicador__in=access_queryset,
        elemento_fundamental_id=elemento_id,
    ).exists()
