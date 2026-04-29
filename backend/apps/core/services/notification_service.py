from __future__ import annotations

import logging
from typing import Iterable

from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.core.models import Notificacion


logger = logging.getLogger(__name__)


def _normalize_user_ids(user_ids: Iterable[int | str | None]) -> list[int]:
    normalized = []
    seen = set()
    for value in user_ids:
        try:
            user_id = int(value)
        except (TypeError, ValueError):
            continue
        if user_id <= 0 or user_id in seen:
            continue
        seen.add(user_id)
        normalized.append(user_id)
    return normalized


def crear_notificacion(
    *,
    user_id,
    titulo: str,
    mensaje: str,
    tipo: str = "INFO",
    modulo: str | None = None,
    actor_id=None,
    referencia_tipo: str | None = None,
    referencia_id=None,
    url: str | None = None,
):
    user_ids = _normalize_user_ids([user_id])
    if not user_ids:
        return None

    try:
        return Notificacion.objects.create(
            id_user=user_ids[0],
            actor_id=actor_id,
            titulo=(titulo or "Notificacion")[:160],
            mensaje=(mensaje or "")[:800],
            tipo=(tipo or "INFO")[:40],
            modulo=(modulo or "")[:80] or None,
            referencia_tipo=(referencia_tipo or "")[:80] or None,
            referencia_id=referencia_id,
            url=(url or "")[:500] or None,
        )
    except DatabaseError:
        logger.exception("No fue posible crear la notificacion para el usuario %s.", user_ids[0])
        return None


def crear_notificaciones(
    *,
    user_ids,
    titulo: str,
    mensaje: str,
    tipo: str = "INFO",
    modulo: str | None = None,
    actor_id=None,
    referencia_tipo: str | None = None,
    referencia_id=None,
    url: str | None = None,
):
    recipients = _normalize_user_ids(user_ids)
    if not recipients:
        return 0

    notifications = [
        Notificacion(
            id_user=user_id,
            actor_id=actor_id,
            titulo=(titulo or "Notificacion")[:160],
            mensaje=(mensaje or "")[:800],
            tipo=(tipo or "INFO")[:40],
            modulo=(modulo or "")[:80] or None,
            referencia_tipo=(referencia_tipo or "")[:80] or None,
            referencia_id=referencia_id,
            url=(url or "")[:500] or None,
        )
        for user_id in recipients
    ]
    try:
        Notificacion.objects.bulk_create(notifications)
    except DatabaseError:
        logger.exception("No fue posible crear notificaciones para %s.", recipients)
        return 0
    return len(notifications)


def queue_notificaciones(**kwargs):
    transaction.on_commit(lambda: crear_notificaciones(**kwargs))


def obtener_resumen_notificaciones(*, user_id, limit: int = 8) -> dict:
    recipients = _normalize_user_ids([user_id])
    if not recipients:
        return {"unread_count": 0, "items": []}

    try:
        queryset = Notificacion.objects.filter(id_user=recipients[0])
        return {
            "unread_count": queryset.filter(leida=False).count(),
            "items": list(queryset[:limit]),
        }
    except DatabaseError:
        return {"unread_count": 0, "items": []}


def marcar_notificacion_leida(*, user_id, notificacion_id=None):
    recipients = _normalize_user_ids([user_id])
    if not recipients:
        return 0

    queryset = Notificacion.objects.filter(id_user=recipients[0], leida=False)
    if notificacion_id:
        queryset = queryset.filter(pk=notificacion_id)
    return queryset.update(leida=True, fecha_lectura=timezone.now())
