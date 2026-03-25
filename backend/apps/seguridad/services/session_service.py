"""
Servicio para creación e invalidación de sesiones en user_session.
"""

import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.seguridad.models import UserSession


def _hash_token(token: str) -> str:
    """Hashea el token plano con SHA256 (no se guarda el token en claro)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(usuario, remember: bool, ip: str = "", user_agent: str = ""):
    """
    Crea una sesión de aplicación:
    - Genera token aleatorio (se devuelve plano para almacenarlo en cookie/session).
    - Guarda solo el hash en la tabla user_session.
    """
    now = timezone.now()
    exp = now + (timedelta(days=7) if remember else timedelta(hours=8))

    token_plain = secrets.token_urlsafe(32)
    token_hash = _hash_token(token_plain)

    session = UserSession.objects.create(
        usuario=usuario,
        token_sesion_hash=token_hash,
        fecha_inicio=now,
        fecha_expiracion=exp,
        ip=ip or None,
        user_agent=(user_agent or "")[:300],
        activa=True,
        ultima_actividad=now,
    )

    return {
        "token": token_plain,
        "expires_at": exp,
        "session_id": session.id_sesion,
    }


def invalidate_session(token_plain: str) -> int:
    """
    Marca una sesión como inactiva a partir del token plano.
    Devuelve la cantidad de filas actualizadas.
    """
    token_hash = _hash_token(token_plain)
    return UserSession.objects.filter(
        token_sesion_hash=token_hash, activa=True
    ).update(activa=False)


def get_token_hash(token_plain: str | None) -> str | None:
    if not token_plain:
        return None
    return _hash_token(token_plain)


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

    session.activa = False
    session.save(update_fields=["activa"])

    registrar_evento(
        accion="REVOCAR_SESION",
        descripcion=f"Se revoco la sesion {session.id_sesion} del usuario {session.usuario}.",
        usuario=actor,
        tipo_evento="SEGURIDAD",
        tabla_afectada="user_session",
        id_registro=session.id_sesion,
        valores_anteriores={
            "activa": True,
            "usuario_id": session.usuario_id,
            "ip": session.ip,
        },
        valores_nuevos={
            "activa": False,
        },
        criticidad="ALTA",
        request=request,
    )

    return {
        "updated": True,
        "reason": "revoked",
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
            valores_nuevos={
                "sesiones_revocadas": updated,
                "ids": affected_ids,
            },
            criticidad="MEDIA",
            request=request,
        )

    return updated
