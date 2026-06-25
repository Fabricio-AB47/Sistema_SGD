import json
import logging

from django.db import DatabaseError
from django.utils import timezone

from apps.auditoria.models import Auditoria

logger = logging.getLogger(__name__)


def _serializar_payload(payload):
    if payload in (None, "", {}):
        return None
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False, default=str, indent=2)


def _request_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def registrar_evento(
    *,
    accion,
    descripcion,
    usuario=None,
    tipo_evento=None,
    tabla_afectada=None,
    id_registro=None,
    valores_nuevos=None,
    valores_anteriores=None,
    criticidad=None,
    request=None,
):
    try:
        return Auditoria.objects.create(
            usuario=usuario,
            tipo_evento=tipo_evento,
            accion=accion,
            tabla_afectada=tabla_afectada,
            id_registro=id_registro,
            descripcion=descripcion,
            valores_nuevos=_serializar_payload(valores_nuevos),
            valores_anteriores=_serializar_payload(valores_anteriores),
            fecha_evento=timezone.now(),
            ip=_request_ip(request) if request else None,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:300] if request else None,
            criticidad=(criticidad or "").upper() or None,
        )
    except DatabaseError:
        logger.exception("No fue posible registrar el evento de auditoria %s.", accion)
        return None
