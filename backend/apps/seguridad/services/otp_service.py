"""
Servicios para OTP de login usando usuario_otp.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.seguridad.services.notification_service import send_login_otp_email
from apps.usuarios.models import Usuario, UsuarioOTP
from apps.usuarios.services import permission_service, session_service


OTP_LOGIN_TYPE = "LOGIN"
OTP_CODE_LENGTH = int(getattr(settings, "SIG_OTP_CODE_LENGTH", 6) or 6)
OTP_EXPIRATION_MINUTES = int(getattr(settings, "SIG_OTP_EXPIRATION_MINUTES", 10) or 10)
OTP_MAX_ATTEMPTS = int(getattr(settings, "SIG_OTP_MAX_ATTEMPTS", 5) or 5)


def _hash_code(codigo: str) -> str:
    return hashlib.sha256(codigo.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(max(OTP_CODE_LENGTH, 6)))


def _request_ip(request) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _lock_user_for_otp(*, usuario: Usuario | None = None, usuario_id: int | None = None):
    target_user_id = getattr(usuario, "pk", None) or usuario_id
    if not target_user_id:
        return None
    return (
        Usuario.objects.select_for_update()
        .only(Usuario._meta.pk.name)
        .filter(pk=target_user_id)
        .first()
    )


def get_pending_login_otp(usuario: Usuario):
    now = timezone.now()
    return (
        UsuarioOTP.objects.filter(
            usuario=usuario,
            tipo_otp=OTP_LOGIN_TYPE,
            usado=False,
            fecha_expiracion__gt=now,
        )
        .order_by("-fecha_generacion", "-id_otp")
        .first()
    )


@transaction.atomic
def invalidate_login_otp(
    *,
    usuario: Usuario | None = None,
    usuario_id: int | None = None,
    otp_id: int | None = None,
    actor=None,
    request=None,
    reason: str = "cancelled",
) -> int:
    target_user_id = getattr(usuario, "pk", None) or usuario_id
    _lock_user_for_otp(usuario=usuario, usuario_id=usuario_id)

    queryset = UsuarioOTP.objects.select_for_update().filter(
        tipo_otp=OTP_LOGIN_TYPE,
        usado=False,
    )
    if target_user_id:
        queryset = queryset.filter(usuario_id=target_user_id)
    if otp_id:
        queryset = queryset.filter(pk=otp_id)

    otp_ids = list(queryset.values_list("pk", flat=True))
    if not otp_ids:
        return 0

    updated = UsuarioOTP.objects.filter(pk__in=otp_ids).update(usado=True)
    registrar_evento(
        accion="INVALIDAR_OTP_LOGIN",
        descripcion="Se invalido un OTP pendiente de login antes de generar o validar otro acceso.",
        usuario=actor or usuario,
        tipo_evento="SEGURIDAD",
        tabla_afectada="usuario_otp",
        id_registro=otp_ids[0] if len(otp_ids) == 1 else None,
        valores_nuevos={
            "usuario_id": target_user_id,
            "otp_ids": otp_ids,
            "cantidad": updated,
            "motivo": reason,
        },
        criticidad="MEDIA",
        request=request,
    )
    return updated


@transaction.atomic
def create_login_otp(*, usuario: Usuario, actor=None, request=None):
    now = timezone.now()
    _lock_user_for_otp(usuario=usuario)
    pending_otp_ids = list(
        UsuarioOTP.objects.select_for_update()
        .filter(
            usuario=usuario,
            tipo_otp=OTP_LOGIN_TYPE,
            usado=False,
        )
        .values_list("pk", flat=True)
    )
    if pending_otp_ids:
        UsuarioOTP.objects.filter(pk__in=pending_otp_ids).update(usado=True)

    codigo_plain = _generate_code()
    otp = UsuarioOTP.objects.create(
        usuario=usuario,
        codigo_otp_hash=_hash_code(codigo_plain),
        tipo_otp=OTP_LOGIN_TYPE,
        fecha_generacion=now,
        fecha_expiracion=now + timedelta(minutes=OTP_EXPIRATION_MINUTES),
        usado=False,
        intentos=0,
        ip=_request_ip(request),
    )

    delivery = send_login_otp_email(
        usuario=usuario,
        codigo=codigo_plain,
        fecha_expiracion=otp.fecha_expiracion,
    )

    registrar_evento(
        accion="GENERAR_OTP_LOGIN",
        descripcion=f"Se genero un OTP de login para el usuario {usuario}.",
        usuario=actor or usuario,
        tipo_evento="SEGURIDAD",
        tabla_afectada="usuario_otp",
        id_registro=otp.id_otp,
        valores_nuevos={
            "usuario_id": usuario.pk,
            "tipo_otp": OTP_LOGIN_TYPE,
            "fecha_expiracion": otp.fecha_expiracion,
            "correo_enviado": bool(delivery["sent"]),
        },
        criticidad="MEDIA",
        request=request,
    )

    return {
        "otp": otp,
        "codigo": codigo_plain,
        "email_sent": bool(delivery["sent"]),
        "delivery_error": delivery.get("error"),
    }


@transaction.atomic
def verify_login_otp(*, usuario: Usuario, codigo: str, otp_id: int | None = None, actor=None, request=None):
    _lock_user_for_otp(usuario=usuario)
    pending_otps = list(
        UsuarioOTP.objects.select_for_update()
        .filter(usuario=usuario, tipo_otp=OTP_LOGIN_TYPE, usado=False)
        .order_by("-fecha_generacion", "-id_otp")
    )
    if otp_id:
        otp = next((candidate for candidate in pending_otps if candidate.pk == otp_id), None)
    else:
        otp = pending_otps[0] if pending_otps else None
    now = timezone.now()
    if otp is None:
        return {"success": False, "status": "missing"}

    if otp.fecha_expiracion and otp.fecha_expiracion <= now:
        otp.usado = True
        otp.save(update_fields=["usado"])
        return {"success": False, "status": "expired"}

    if (otp.intentos or 0) >= OTP_MAX_ATTEMPTS:
        otp.usado = True
        otp.save(update_fields=["usado"])
        return {"success": False, "status": "blocked"}

    if _hash_code(codigo) != otp.codigo_otp_hash:
        otp.intentos = (otp.intentos or 0) + 1
        update_fields = ["intentos"]
        status = "invalid"
        if otp.intentos >= OTP_MAX_ATTEMPTS:
            otp.usado = True
            update_fields.append("usado")
            status = "blocked"
        otp.save(update_fields=update_fields)
        registrar_evento(
            accion="OTP_LOGIN_INVALIDO",
            descripcion=f"Codigo OTP invalido para el usuario {usuario}.",
            usuario=actor or usuario,
            tipo_evento="SEGURIDAD",
            tabla_afectada="usuario_otp",
            id_registro=otp.id_otp,
            valores_nuevos={"intentos": otp.intentos, "estado": status},
            criticidad="MEDIA",
            request=request,
        )
        return {"success": False, "status": status, "attempts": otp.intentos}

    otp.usado = True
    otp.intentos = (otp.intentos or 0) + 1
    otp.save(update_fields=["usado", "intentos"])
    other_pending_ids = [candidate.pk for candidate in pending_otps if candidate.pk != otp.pk]
    if other_pending_ids:
        UsuarioOTP.objects.filter(pk__in=other_pending_ids, usado=False).update(usado=True)

    registrar_evento(
        accion="OTP_LOGIN_VALIDO",
        descripcion=f"OTP validado para el usuario {usuario}.",
        usuario=actor or usuario,
        tipo_evento="SEGURIDAD",
        tabla_afectada="usuario_otp",
        id_registro=otp.id_otp,
        valores_nuevos={"intentos": otp.intentos, "validado": True},
        criticidad="BAJA",
        request=request,
    )
    return {"success": True, "status": "valid", "otp": otp}


def complete_login_after_otp(
    *,
    usuario: Usuario,
    remember: bool,
    roles=(),
    permissions=(),
    requires_password_change: bool = False,
    ip: str = "",
    user_agent: str = "",
    request=None,
):
    resolved_roles = tuple(roles) or permission_service.get_user_role_names(usuario)
    resolved_permissions = tuple(permissions) or permission_service.get_user_permissions(usuario)
    session_data = session_service.create_session(
        usuario=usuario,
        remember=remember,
        ip=ip,
        user_agent=user_agent,
        actor=usuario,
        request=request,
    )
    return {
        "usuario": usuario,
        "roles": tuple(resolved_roles),
        "permissions": tuple(resolved_permissions),
        "requires_password_change": bool(requires_password_change),
        "session_data": session_data,
    }
