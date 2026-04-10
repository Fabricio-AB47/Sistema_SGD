from __future__ import annotations

from django.db.models import Prefetch

from apps.usuarios.models import Permiso, RolPermiso, Usuario, UsuarioCredencial, UsuarioRol


USER_AUTH_ONLY_FIELDS = (
    "id_user",
    "primer_nombre",
    "segundo_nombre",
    "primer_apellido",
    "segundo_apellido",
    "correo",
    "activo",
)

USER_AUTH_RELATED_ONLY_FIELDS = tuple(f"usuario__{field}" for field in USER_AUTH_ONLY_FIELDS)

CREDENTIAL_ONLY_FIELDS = (
    "usuario_id",
    "password_hash",
    "algoritmo_hash",
    "requiere_cambio",
    "mfa_activo",
    "intentos_fallidos",
    "ultimo_intento_fallido",
    "bloqueado_hasta",
    "ultimo_login",
    "fecha_cambio",
    "password_version",
)


def normalize_email(correo: str | None) -> str:
    return (correo or "").strip().lower()


def get_user_for_auth(correo: str) -> Usuario | None:
    correo = normalize_email(correo)
    if not correo:
        return None

    active_roles = UsuarioRol.objects.select_related("rol").filter(
        activo=True,
        rol__activo=True,
    )
    return (
        Usuario.objects.filter(correo__iexact=correo, activo=True)
        .only(*USER_AUTH_ONLY_FIELDS)
        .prefetch_related(Prefetch("roles_asignados", queryset=active_roles))
        .first()
    )


def get_user_credential_for_update(usuario: Usuario | int) -> UsuarioCredencial | None:
    usuario_id = getattr(usuario, "pk", None) or getattr(usuario, "id_user", None) or usuario
    if not usuario_id:
        return None

    return (
        UsuarioCredencial.objects
        .select_related("usuario")
        .only(*CREDENTIAL_ONLY_FIELDS, *USER_AUTH_RELATED_ONLY_FIELDS)
        .filter(usuario_id=usuario_id)
        .first()
    )


def get_active_roles(usuario: Usuario | int):
    usuario_id = getattr(usuario, "pk", None) or getattr(usuario, "id_user", None) or usuario
    if not usuario_id:
        return UsuarioRol.objects.none()

    return UsuarioRol.objects.select_related("rol").filter(
        usuario_id=usuario_id,
        activo=True,
        rol__activo=True,
    )


def get_active_permission_codes(usuario: Usuario | int) -> tuple[str, ...]:
    usuario_id = getattr(usuario, "pk", None) or getattr(usuario, "id_user", None) or usuario
    if not usuario_id:
        return ()

    return tuple(
        RolPermiso.objects.filter(
            rol__usuarios__usuario_id=usuario_id,
            rol__usuarios__activo=True,
            rol__activo=True,
            permiso__activo=True,
        )
        .order_by("permiso__codigo_permiso")
        .values_list("permiso__codigo_permiso", flat=True)
        .distinct()
    )


def get_active_permissions_queryset(usuario: Usuario | int):
    usuario_id = getattr(usuario, "pk", None) or getattr(usuario, "id_user", None) or usuario
    if not usuario_id:
        return Permiso.objects.none()

    return Permiso.objects.filter(
        activo=True,
        roles_asignados__rol__usuarios__usuario_id=usuario_id,
        roles_asignados__rol__usuarios__activo=True,
        roles_asignados__rol__activo=True,
    ).distinct()
