from __future__ import annotations

from apps.usuarios.services.permission_service import (  # noqa: F401
    get_user_permissions,
    get_user_role_names,
    get_user_roles,
    has_any_permission,
    has_global_access,
    has_indicator_access,
    has_permission,
)
from apps.usuarios.services.permission_service import _resolve_actor as _resolve_actor  # noqa: F401


def get_request_actor(request):
    session_user_id = request.session.get("sig_user_id")
    if session_user_id:
        return _resolve_actor(session_user_id)
    return _resolve_actor(getattr(request, "user", None))


def usuario_tiene_acceso_global(actor) -> bool:
    return has_global_access(actor)


def usuario_tiene_permiso(actor, codigo_permiso: str) -> bool:
    return has_permission(actor, codigo_permiso)


def usuario_tiene_permiso_modulo(actor, modulo: str) -> bool:
    return has_any_permission(actor, modulos=(modulo,))


def usuario_tiene_algun_permiso(actor, *, codigos: tuple[str, ...] = (), modulos: tuple[str, ...] = ()) -> bool:
    return has_any_permission(actor, codigos=codigos, modulos=modulos)
