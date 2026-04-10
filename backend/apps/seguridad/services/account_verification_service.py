"""
Servicios para verificacion de correo usando token_verificacion.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.seguridad.services.notification_service import send_verification_email
from apps.usuarios.models import TokenVerificacion, Usuario


VERIFICATION_TOKEN_MINUTES = int(getattr(settings, "SIG_EMAIL_VERIFICATION_MINUTES", 60 * 24) or (60 * 24))


def _hash_token(token_plain: str) -> str:
    return hashlib.sha256(token_plain.encode("utf-8")).hexdigest()


def get_valid_verification_token(token_plain: str):
    if not token_plain:
        return None

    token_hash = _hash_token(token_plain)
    now = timezone.now()
    return (
        TokenVerificacion.objects.select_related("usuario")
        .filter(
            token_hash=token_hash,
            verificado=False,
            fecha_expiracion__gt=now,
        )
        .first()
    )


@transaction.atomic
def create_verification_token(*, correo: str, actor=None, request=None):
    usuario = (
        Usuario.objects.filter(correo__iexact=correo.strip(), activo=True)
        .only("id_user", "primer_nombre", "primer_apellido", "correo", "correo_verificado")
        .first()
    )
    if not usuario:
        return {"usuario": None, "token": None, "already_verified": False}

    if usuario.correo_verificado:
        return {"usuario": usuario, "token": None, "already_verified": True}

    now = timezone.now()
    TokenVerificacion.objects.filter(
        usuario=usuario,
        verificado=False,
        fecha_expiracion__gt=now,
    ).update(fecha_expiracion=now)

    token_plain = secrets.token_urlsafe(32)
    token_hash = _hash_token(token_plain)

    token = TokenVerificacion.objects.create(
        usuario=usuario,
        token_hash=token_hash,
        fecha_creacion=now,
        fecha_expiracion=now + timedelta(minutes=VERIFICATION_TOKEN_MINUTES),
        verificado=False,
        ip_solicitud=request.META.get("REMOTE_ADDR") if request else None,
    )

    delivery = send_verification_email(
        usuario=usuario,
        token_plain=token_plain,
        request=request,
    )

    registrar_evento(
        accion="SOLICITAR_VERIFICACION_CORREO",
        descripcion=f"Se genero token de verificacion para {usuario.correo}.",
        usuario=actor,
        tipo_evento="SEGURIDAD",
        tabla_afectada="token_verificacion",
        id_registro=token.id_token_verificacion,
        valores_nuevos={
            "correo": usuario.correo,
            "expira_en_minutos": VERIFICATION_TOKEN_MINUTES,
            "correo_enviado": bool(delivery["sent"]),
        },
        criticidad="MEDIA",
        request=request,
    )

    return {
        "usuario": usuario,
        "token": token_plain,
        "already_verified": False,
        "email_sent": bool(delivery["sent"]),
        "delivery_error": delivery.get("error"),
    }


@transaction.atomic
def verify_email_with_token(*, token_plain: str, actor=None, request=None):
    token_record = get_valid_verification_token(token_plain)
    if not token_record:
        return {"success": False, "reason": "invalid_token"}

    usuario = token_record.usuario
    token_record.verificado = True
    token_record.save(update_fields=["verificado"])

    if not usuario.correo_verificado:
        usuario.correo_verificado = True
        usuario.save(update_fields=["correo_verificado"])

    registrar_evento(
        accion="VERIFICAR_CORREO",
        descripcion=f"Correo verificado para el usuario {usuario}.",
        usuario=actor or usuario,
        tipo_evento="SEGURIDAD",
        tabla_afectada="usuario",
        id_registro=usuario.pk,
        valores_nuevos={"correo_verificado": True},
        criticidad="MEDIA",
        request=request,
    )

    return {"success": True, "usuario": usuario}
