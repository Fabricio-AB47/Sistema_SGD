"""
Servicios para recuperacion y cambio de contrasena usando token_recuperacion.
"""

import hashlib
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.seguridad.services.notification_service import send_password_recovery_email
from apps.usuarios.models import HistorialPassword, TokenRecuperacion, UserSession, Usuario, UsuarioCredencial
from apps.usuarios.services import password_service


RESET_TOKEN_MINUTES = 30


def _hash_token(token_plain: str) -> str:
    return hashlib.sha256(token_plain.encode("utf-8")).hexdigest()


def get_valid_reset_token(token_plain: str):
    if not token_plain:
        return None

    token_hash = _hash_token(token_plain)
    now = timezone.now()
    return (
        TokenRecuperacion.objects.select_related("usuario")
        .filter(
            token_hash=token_hash,
            usado=False,
            fecha_expiracion__gt=now,
        )
        .first()
    )


@transaction.atomic
def create_recovery_token(*, correo: str, actor=None, request=None):
    usuario = (
        Usuario.objects.filter(correo__iexact=correo.strip(), activo=True)
        .only("id_user", "primer_nombre", "primer_apellido", "correo")
        .first()
    )
    if not usuario:
        return {"usuario": None, "token": None}

    now = timezone.now()
    TokenRecuperacion.objects.filter(
        usuario=usuario,
        usado=False,
        fecha_expiracion__gt=now,
    ).update(usado=True)

    token_plain = secrets.token_urlsafe(32)
    token_hash = _hash_token(token_plain)

    TokenRecuperacion.objects.create(
        usuario=usuario,
        token_hash=token_hash,
        fecha_creacion=now,
        fecha_expiracion=now + timedelta(minutes=RESET_TOKEN_MINUTES),
        usado=False,
        ip_solicitud=request.META.get("REMOTE_ADDR") if request else None,
    )

    delivery = send_password_recovery_email(
        usuario=usuario,
        token_plain=token_plain,
        request=request,
    )

    registrar_evento(
        accion="SOLICITAR_RECUPERACION_PASSWORD",
        descripcion=f"Se genero un token de recuperacion para el usuario {usuario}.",
        usuario=actor,
        tipo_evento="SEGURIDAD",
        tabla_afectada="token_recuperacion",
        id_registro=usuario.pk,
        valores_nuevos={
            "correo": usuario.correo,
            "expira_en_minutos": RESET_TOKEN_MINUTES,
            "correo_enviado": bool(delivery["sent"]),
        },
        criticidad="MEDIA",
        request=request,
    )

    return {
        "usuario": usuario,
        "token": token_plain,
        "email_sent": bool(delivery["sent"]),
        "delivery_error": delivery.get("error"),
    }


@transaction.atomic
def reset_password_with_token(*, token_plain: str, new_password: str, actor=None, request=None):
    token_record = get_valid_reset_token(token_plain)
    if not token_record:
        return {"success": False, "reason": "invalid_token"}

    usuario = token_record.usuario
    try:
        credencial = UsuarioCredencial.objects.select_for_update().get(usuario=usuario)
    except UsuarioCredencial.DoesNotExist:
        return {"success": False, "reason": "credential_missing"}

    previous_hash = credencial.password_hash
    previous_algorithm = credencial.algoritmo_hash

    HistorialPassword.objects.create(
        usuario=usuario,
        password_hash=previous_hash,
        algoritmo_hash=previous_algorithm or password_service.ARGON2_ALGORITHM,
    )

    credencial.password_hash = password_service.hash_password_argon2(new_password)
    credencial.algoritmo_hash = "argon2"
    credencial.password_version = (credencial.password_version or 0) + 1
    credencial.fecha_cambio = timezone.now()
    credencial.requiere_cambio = False
    credencial.intentos_fallidos = 0
    credencial.ultimo_intento_fallido = None
    credencial.bloqueado_hasta = None
    credencial.save(
        update_fields=[
            "password_hash",
            "algoritmo_hash",
            "password_version",
            "fecha_cambio",
            "requiere_cambio",
            "intentos_fallidos",
            "ultimo_intento_fallido",
            "bloqueado_hasta",
        ]
    )

    token_record.usado = True
    token_record.save(update_fields=["usado"])

    sesiones_revocadas = UserSession.objects.filter(usuario=usuario, activa=True).update(activa=False)

    registrar_evento(
        accion="CAMBIAR_PASSWORD_RECUPERACION",
        descripcion=f"Se actualizo la contrasena del usuario {usuario} usando token de recuperacion.",
        usuario=actor or usuario,
        tipo_evento="SEGURIDAD",
        tabla_afectada="usuario_credencial",
        id_registro=usuario.pk,
        valores_nuevos={
            "algoritmo_hash": "argon2",
            "password_version": credencial.password_version,
            "sesiones_revocadas": sesiones_revocadas,
        },
        valores_anteriores={
            "algoritmo_hash": previous_algorithm,
        },
        criticidad="ALTA",
        request=request,
    )

    return {
        "success": True,
        "usuario": usuario,
        "sessions_revoked": sesiones_revocadas,
    }
