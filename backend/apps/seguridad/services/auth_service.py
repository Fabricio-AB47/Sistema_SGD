"""
Servicio de autenticación usando el modelo de seguridad personalizado.
"""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.seguridad.services import (
    password_service,
    session_service,
    login_attempt_service,
)
from apps.usuarios.models import Usuario
from apps.seguridad.models import UsuarioCredencial, HistorialLogin, HistorialPassword


@dataclass
class AuthResult:
    """Objeto de resultado de autenticación."""

    status: str
    usuario: Optional[Usuario] = None
    session_token: Optional[str] = None
    session_expires_at: Optional[timezone.datetime] = None
    session_id: Optional[int] = None


@transaction.atomic
def authenticate(correo: str, password: str, remember: bool, ip: str = "", user_agent: str = "") -> AuthResult:
    """
    Autentica a un usuario usando correo + contraseña en el modelo personalizado.
    Maneja bloqueos, rehash Argon2, intentos fallidos y registro de historial.
    """
    now = timezone.now()
    user = (
        Usuario.objects.filter(correo__iexact=correo)
        .select_related(None)
        .first()
    )

    if not user or not user.activo:
        _log_login(None, correo, False, "usuario_inexistente_o_inactivo", ip, user_agent)
        return AuthResult(status="invalid_credentials")

    try:
        cred = UsuarioCredencial.objects.select_for_update().get(usuario=user)
    except UsuarioCredencial.DoesNotExist:
        _log_login(user, correo, False, "credencial_inexistente", ip, user_agent)
        return AuthResult(status="invalid_credentials")

    # ¿Bloqueado?
    if login_attempt_service.is_blocked(cred):
        _log_login(user, correo, False, "bloqueado_temporal", ip, user_agent)
        return AuthResult(status="blocked")

    # Verificar contraseña
    check = password_service.verify_password(password, cred.password_hash)
    if not check.valid:
        login_attempt_service.register_failure(cred)
        _log_login(user, correo, False, "password_incorrecto", ip, user_agent)
        return AuthResult(status="invalid_credentials")

    # Reset de intentos y timestamps de éxito
    cred.intentos_fallidos = 0
    cred.bloqueado_hasta = None
    cred.ultimo_intento_fallido = None
    cred.ultimo_login = now

    # Rehash obligatorio si no es Argon2 o está desactualizado
    if check.needs_rehash:
        new_hash = password_service.hash_password(password)
        HistorialPassword.objects.create(
            usuario=user,
            password_hash=cred.password_hash,
            algoritmo_hash=cred.algoritmo_hash,
        )
        cred.password_hash = new_hash
        cred.algoritmo_hash = "argon2"  # Deja constancia explícita del algoritmo estándar.
        cred.password_version = cred.password_version + 1
        cred.fecha_cambio = now

    cred.save(
        update_fields=[
            "intentos_fallidos",
            "bloqueado_hasta",
            "ultimo_intento_fallido",
            "ultimo_login",
            "password_hash",
            "algoritmo_hash",
            "password_version",
            "fecha_cambio",
        ]
    )

    _log_login(user, correo, True, "login_ok", ip, user_agent)

    # Si tiene MFA, no creamos sesión todavía.
    if cred.mfa_activo:
        return AuthResult(status="requires_otp", usuario=user)

    # Crear sesión de aplicación
    session = session_service.create_session(
        usuario=user,
        remember=remember,
        ip=ip,
        user_agent=user_agent,
    )

    return AuthResult(
        status="success",
        usuario=user,
        session_token=session["token"],
        session_expires_at=session["expires_at"],
        session_id=session["session_id"],
    )


def _log_login(usuario, correo_intento, exito: bool, motivo: str, ip: str, user_agent: str):
    """Registra evento en historial_login."""
    HistorialLogin.objects.create(
        usuario=usuario,
        correo_intento=correo_intento,
        fecha_intento=timezone.now(),
        exito=exito,
        motivo=motivo,
        ip=ip or None,
        user_agent=(user_agent or "")[:300],
    )
