from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.usuarios.models import UserSession


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_token_hash(token_plain: str | None) -> str | None:
    if not token_plain:
        return None
    return _hash_token(token_plain)


def get_idle_timeout_seconds() -> int:
    return int(getattr(settings, "SIG_IDLE_TIMEOUT_SECONDS", 900) or 900)


def get_activity_touch_interval_seconds() -> int:
    return int(getattr(settings, "SIG_SESSION_TOUCH_INTERVAL_SECONDS", 60) or 60)


def get_session_duration(*, remember: bool) -> timedelta:
    if remember:
        return timedelta(days=int(getattr(settings, "SIG_REMEMBER_SESSION_DAYS", 7) or 7))
    return timedelta(hours=int(getattr(settings, "SIG_SESSION_LIFETIME_HOURS", 8) or 8))


def _session_last_activity(session: UserSession):
    return session.ultima_actividad or session.fecha_renovacion or session.fecha_inicio


def is_session_idle(session: UserSession, *, now=None) -> bool:
    if not session:
        return False
    now = now or timezone.now()
    last_activity = _session_last_activity(session)
    if last_activity is None:
        return False
    return (now - last_activity).total_seconds() >= get_idle_timeout_seconds()


def is_session_expired(session: UserSession, *, now=None) -> bool:
    if not session or not session.fecha_expiracion:
        return False
    now = now or timezone.now()
    return session.fecha_expiracion <= now


def create_session(usuario, remember: bool, ip: str = "", user_agent: str = "", *, actor=None, request=None):
    now = timezone.now()
    expires_at = now + get_session_duration(remember=remember)
    token_plain = secrets.token_urlsafe(32)
    token_hash = _hash_token(token_plain)

    session = UserSession.objects.create(
        usuario=usuario,
        token_sesion_hash=token_hash,
        fecha_inicio=now,
        fecha_expiracion=expires_at,
        fecha_renovacion=now,
        activa=True,
        ip=(ip or None),
        user_agent=(user_agent or "")[:300],
        ultima_actividad=now,
    )

    registrar_evento(
        accion="CREAR_SESION",
        descripcion=f"Se creo la sesion {session.id_sesion} para el usuario {usuario}.",
        usuario=actor or usuario,
        tipo_evento="SEGURIDAD",
        tabla_afectada="user_session",
        id_registro=session.id_sesion,
        valores_nuevos={
            "usuario_id": usuario.pk,
            "fecha_expiracion": expires_at.isoformat(),
            "remember": bool(remember),
        },
        criticidad="BAJA",
        request=request,
    )

    return {
        "token": token_plain,
        "token_hash": token_hash,
        "expires_at": expires_at,
        "session_id": session.id_sesion,
        "session": session,
    }


def get_request_user_session(request) -> UserSession | None:
    session_id = request.session.get("sig_session_id")
    token_hash = get_token_hash(request.session.get("sig_session_token"))

    queryset = UserSession.objects.select_related("usuario").filter(activa=True)
    session = None

    if session_id:
        session = queryset.filter(pk=session_id).first()

    if session is None and token_hash:
        session = queryset.filter(token_sesion_hash=token_hash).first()
        if session is not None:
            request.session["sig_session_id"] = session.id_sesion

    return session


def touch_session(*, session: UserSession, force: bool = False, now=None) -> UserSession:
    now = now or timezone.now()
    last_activity = _session_last_activity(session)
    min_interval = get_activity_touch_interval_seconds()

    if (
        not force
        and last_activity is not None
        and (now - last_activity).total_seconds() < min_interval
    ):
        return session

    session.ultima_actividad = now
    session.fecha_renovacion = now
    session.save(update_fields=["ultima_actividad", "fecha_renovacion"])
    return session


def close_session(
    *,
    request=None,
    session: UserSession | None = None,
    token_plain: str | None = None,
    session_id: int | None = None,
    actor=None,
    reason: str = "manual",
    flush_request: bool = False,
):
    if session is None and session_id:
        session = UserSession.objects.select_related("usuario").filter(pk=session_id).first()
    if session is None and token_plain:
        token_hash = get_token_hash(token_plain)
        session = UserSession.objects.select_related("usuario").filter(token_sesion_hash=token_hash).first()
    if session is None and request is not None:
        session = get_request_user_session(request)

    if not session:
        if request is not None and flush_request:
            request.session.flush()
        return {"updated": False, "reason": "not_found", "session": None}

    if session.activa:
        session.activa = False
        session.save(update_fields=["activa"])
        registrar_evento(
            accion={
                "manual": "CERRAR_SESION",
                "idle": "CIERRE_AUTOMATICO_SESION",
                "expired": "CIERRE_SESION_EXPIRADA",
            }.get(reason, "CERRAR_SESION"),
            descripcion=f"Se cerro la sesion {session.id_sesion} del usuario {session.usuario}.",
            usuario=actor or getattr(session, "usuario", None),
            tipo_evento="SEGURIDAD",
            tabla_afectada="user_session",
            id_registro=session.id_sesion,
            valores_nuevos={"activa": False, "motivo": reason},
            criticidad="MEDIA" if reason in {"idle", "expired"} else "BAJA",
            request=request,
        )

    if request is not None and flush_request:
        request.session.flush()

    return {"updated": True, "reason": reason, "session": session}


def expire_sessions(
    *,
    usuario=None,
    actor=None,
    request=None,
    exclude_session_id: int | None = None,
    expired_only: bool = False,
) -> int:
    queryset = UserSession.objects.filter(activa=True)
    if usuario is not None:
        queryset = queryset.filter(usuario=usuario)
    if exclude_session_id:
        queryset = queryset.exclude(pk=exclude_session_id)
    if expired_only:
        queryset = queryset.filter(fecha_expiracion__lte=timezone.now())

    affected_ids = list(queryset.values_list("id_sesion", flat=True))
    updated = queryset.update(activa=False)
    if updated:
        registrar_evento(
            accion="EXPIRAR_SESIONES",
            descripcion=f"Se invalidaron {updated} sesiones activas.",
            usuario=actor or usuario,
            tipo_evento="SEGURIDAD",
            tabla_afectada="user_session",
            id_registro=getattr(usuario, "pk", None),
            valores_nuevos={"ids": affected_ids, "total": updated},
            criticidad="MEDIA",
            request=request,
        )
    return updated


def validate_session(
    *,
    request=None,
    token_plain: str | None = None,
    session_id: int | None = None,
    touch: bool = False,
    force_touch: bool = False,
):
    session = None
    if request is not None:
        session = get_request_user_session(request)
    if session is None and session_id:
        session = UserSession.objects.select_related("usuario").filter(pk=session_id, activa=True).first()
    if session is None and token_plain:
        token_hash = get_token_hash(token_plain)
        session = UserSession.objects.select_related("usuario").filter(token_sesion_hash=token_hash, activa=True).first()

    if session is None or not session.activa:
        return {"valid": False, "reason": "missing", "session": None, "usuario": None}

    now = timezone.now()
    if is_session_expired(session, now=now):
        close_session(request=request, session=session, actor=getattr(session, "usuario", None), reason="expired")
        return {"valid": False, "reason": "expired", "session": session, "usuario": session.usuario}

    if is_session_idle(session, now=now):
        close_session(request=request, session=session, actor=getattr(session, "usuario", None), reason="idle")
        return {"valid": False, "reason": "idle", "session": session, "usuario": session.usuario}

    if touch:
        session = touch_session(session=session, force=force_touch, now=now)

    if request is not None:
        request.session["sig_session_id"] = session.id_sesion
        request.session["sig_session_exp"] = session.fecha_expiracion.isoformat()

    return {"valid": True, "reason": "ok", "session": session, "usuario": session.usuario}


def ensure_request_session_active(*, request, touch: bool = False, force_touch: bool = False):
    user_id = request.session.get("sig_user_id")
    if not user_id:
        return {"valid": False, "reason": "missing", "session": None}

    status = validate_session(request=request, touch=touch, force_touch=force_touch)
    session = status.get("session")
    if not status["valid"]:
        request.session.flush()
        return status

    if session and session.usuario_id != user_id:
        close_session(request=request, session=session, actor=session.usuario, reason="manual", flush_request=True)
        return {"valid": False, "reason": "mismatch", "session": session}

    return status


def revoke_session(
    *,
    session_id: int,
    actor=None,
    request=None,
    current_session_hash: str | None = None,
    current_session_id: int | None = None,
):
    session = (
        UserSession.objects.select_related("usuario")
        .only(
            "id_sesion",
            "usuario_id",
            "token_sesion_hash",
            "activa",
            "fecha_expiracion",
            "ip",
            "user_agent",
            "usuario__id_user",
            "usuario__primer_nombre",
            "usuario__primer_apellido",
            "usuario__correo",
        )
        .filter(pk=session_id)
        .first()
    )
    if not session:
        return {"updated": False, "reason": "not_found", "is_current": False}
    if not session.activa:
        return {"updated": False, "reason": "inactive", "is_current": False}

    result = close_session(request=request, session=session, actor=actor, reason="manual")
    return {
        "updated": result["updated"],
        "reason": result["reason"],
        "is_current": bool(
            (current_session_id and session.id_sesion == current_session_id)
            or (current_session_hash and session.token_sesion_hash == current_session_hash)
        ),
        "session": session,
    }


def revoke_other_sessions_for_user(
    *,
    usuario,
    actor=None,
    request=None,
    current_session_hash: str | None = None,
    current_session_id: int | None = None,
):
    queryset = UserSession.objects.filter(usuario=usuario, activa=True)
    if current_session_id:
        queryset = queryset.exclude(pk=current_session_id)
    if current_session_hash:
        queryset = queryset.exclude(token_sesion_hash=current_session_hash)

    affected_ids = list(queryset.values_list("id_sesion", flat=True))
    updated = queryset.update(activa=False)
    if updated:
        registrar_evento(
            accion="REVOCAR_OTRAS_SESIONES",
            descripcion=f"Se revocaron {updated} sesiones activas del usuario {usuario}.",
            usuario=actor,
            tipo_evento="SEGURIDAD",
            tabla_afectada="user_session",
            id_registro=usuario.pk,
            valores_nuevos={"ids": affected_ids, "sesiones_revocadas": updated},
            criticidad="MEDIA",
            request=request,
        )
    return updated
