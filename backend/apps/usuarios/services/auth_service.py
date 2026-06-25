from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.usuarios.models import HistorialLogin, Usuario, UsuarioCredencial
from apps.usuarios.selectors.user_selector import get_user_credential_for_update, get_user_for_auth
from apps.usuarios.services import password_service, permission_service, session_service


@dataclass
class AuthResult:
    status: str
    usuario: Usuario | None = None
    session_token: str | None = None
    session_expires_at: timezone.datetime | None = None
    session_id: int | None = None
    roles: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    requires_password_change: bool = False
    requires_mfa: bool = False
    blocked_until: timezone.datetime | None = None


MAX_LOGIN_ATTEMPTS = int(getattr(settings, "SIG_MAX_LOGIN_ATTEMPTS", 5) or 5)
LOGIN_BLOCK_MINUTES = int(getattr(settings, "SIG_LOGIN_BLOCK_MINUTES", 15) or 15)


def _setting_enabled(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)



def _normalize_email(correo: str | None) -> str:
    return (correo or "").strip().lower()


def _is_blocked(credencial: UsuarioCredencial, *, now=None) -> bool:
    now = now or timezone.now()
    return bool(credencial.bloqueado_hasta and credencial.bloqueado_hasta > now)


def _requires_otp_for_login(credencial: UsuarioCredencial) -> bool:
    require_every_login = _setting_enabled(
        getattr(settings, "SIG_REQUIRE_OTP_EVERY_LOGIN", not settings.DEBUG)
    )
    return require_every_login or bool(credencial.mfa_activo)


def register_login_attempt(
    *,
    usuario: Usuario | None,
    correo: str,
    exito: bool,
    motivo: str,
    ip: str = "",
    user_agent: str = "",
    request=None,
):
    event = HistorialLogin.objects.create(
        usuario=usuario,
        correo_intento=_normalize_email(correo),
        fecha_intento=timezone.now(),
        exito=exito,
        motivo=motivo,
        ip=ip or None,
        user_agent=(user_agent or "")[:300],
    )
    registrar_evento(
        accion="LOGIN_EXITOSO" if exito else "LOGIN_FALLIDO",
        descripcion=(
            f"Autenticacion exitosa para {_normalize_email(correo)}."
            if exito
            else f"Fallo de autenticacion para {_normalize_email(correo)}."
        ),
        usuario=usuario,
        tipo_evento="SEGURIDAD",
        tabla_afectada="historial_login",
        id_registro=event.id_login,
        valores_nuevos={
            "correo": _normalize_email(correo),
            "motivo": motivo,
            "exito": bool(exito),
        },
        criticidad="BAJA" if exito else "MEDIA",
        request=request,
    )
    return event


@transaction.atomic
def handle_failed_login(
    *,
    usuario: Usuario | None,
    credencial: UsuarioCredencial | None,
    correo: str,
    motivo: str,
    ip: str = "",
    user_agent: str = "",
    request=None,
) -> AuthResult:
    blocked_until = None
    if credencial is not None:
        now = timezone.now()
        credencial.intentos_fallidos = (credencial.intentos_fallidos or 0) + 1
        credencial.ultimo_intento_fallido = now
        if credencial.intentos_fallidos >= MAX_LOGIN_ATTEMPTS:
            blocked_until = now + timedelta(minutes=LOGIN_BLOCK_MINUTES)
            credencial.bloqueado_hasta = blocked_until
        credencial.save(
            update_fields=["intentos_fallidos", "ultimo_intento_fallido", "bloqueado_hasta"]
        )

    register_login_attempt(
        usuario=usuario,
        correo=correo,
        exito=False,
        motivo=motivo,
        ip=ip,
        user_agent=user_agent,
        request=request,
    )

    return AuthResult(
        status="blocked" if blocked_until else "invalid_credentials",
        usuario=usuario,
        blocked_until=blocked_until,
    )


@transaction.atomic
def handle_success_login(
    *,
    usuario: Usuario,
    credencial: UsuarioCredencial,
    password: str,
    password_check: password_service.PasswordCheckResult | None = None,
    remember: bool,
    ip: str = "",
    user_agent: str = "",
    request=None,
) -> AuthResult:
    now = timezone.now()
    credencial.intentos_fallidos = 0
    credencial.ultimo_intento_fallido = None
    credencial.bloqueado_hasta = None
    credencial.ultimo_login = now
    credencial.save(
        update_fields=[
            "intentos_fallidos",
            "ultimo_intento_fallido",
            "bloqueado_hasta",
            "ultimo_login",
        ]
    )

    password_service.upgrade_password_if_needed(
        credencial,
        password,
        check=password_check,
        actor=usuario,
        request=request,
    )

    register_login_attempt(
        usuario=usuario,
        correo=usuario.correo,
        exito=True,
        motivo="login_ok",
        ip=ip,
        user_agent=user_agent,
        request=request,
    )

    roles = permission_service.get_user_role_names(usuario)
    permissions = permission_service.get_user_permissions(usuario)

    if _requires_otp_for_login(credencial):
        return AuthResult(
            status="requires_otp",
            usuario=usuario,
            roles=roles,
            permissions=permissions,
            requires_password_change=bool(credencial.requiere_cambio),
            requires_mfa=True,
        )

    session_data = session_service.create_session(
        usuario=usuario,
        remember=remember,
        ip=ip,
        user_agent=user_agent,
        actor=usuario,
        request=request,
    )

    return AuthResult(
        status="success",
        usuario=usuario,
        session_token=session_data["token"],
        session_expires_at=session_data["expires_at"],
        session_id=session_data["session_id"],
        roles=roles,
        permissions=permissions,
        requires_password_change=bool(credencial.requiere_cambio),
        requires_mfa=False,
    )


@transaction.atomic
def authenticate_user(
    *,
    correo: str,
    password: str,
    remember: bool = False,
    ip: str = "",
    user_agent: str = "",
    request=None,
) -> AuthResult:
    correo = _normalize_email(correo)
    usuario = get_user_for_auth(correo)
    if usuario is None:
        register_login_attempt(
            usuario=None,
            correo=correo,
            exito=False,
            motivo="usuario_inexistente_o_inactivo",
            ip=ip,
            user_agent=user_agent,
            request=request,
        )
        return AuthResult(status="invalid_credentials")

    credencial = get_user_credential_for_update(usuario)
    if credencial is None:
        return handle_failed_login(
            usuario=usuario,
            credencial=None,
            correo=correo,
            motivo="credencial_inexistente",
            ip=ip,
            user_agent=user_agent,
            request=request,
        )

    if _is_blocked(credencial):
        register_login_attempt(
            usuario=usuario,
            correo=correo,
            exito=False,
            motivo="bloqueado_temporal",
            ip=ip,
            user_agent=user_agent,
            request=request,
        )
        return AuthResult(status="blocked", usuario=usuario, blocked_until=credencial.bloqueado_hasta)

    check = password_service.verify_password(password, credencial.password_hash)
    if not check.valid:
        return handle_failed_login(
            usuario=usuario,
            credencial=credencial,
            correo=correo,
            motivo="password_incorrecto",
            ip=ip,
            user_agent=user_agent,
            request=request,
        )

    if getattr(settings, "SIG_REQUIRE_EMAIL_VERIFICATION", False) and not usuario.correo_verificado:
        register_login_attempt(
            usuario=usuario,
            correo=correo,
            exito=False,
            motivo="correo_no_verificado",
            ip=ip,
            user_agent=user_agent,
            request=request,
        )
        return AuthResult(status="email_not_verified", usuario=usuario)

    return handle_success_login(
        usuario=usuario,
        credencial=credencial,
        password=password,
        password_check=check,
        remember=remember,
        ip=ip,
        user_agent=user_agent,
        request=request,
    )


def authenticate(*, correo: str, password: str, remember: bool, ip: str = "", user_agent: str = "") -> AuthResult:
    return authenticate_user(
        correo=correo,
        password=password,
        remember=remember,
        ip=ip,
        user_agent=user_agent,
    )
