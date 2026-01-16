from contextvars import ContextVar
from typing import Any, Dict, Optional, Tuple

from django.apps import apps
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.forms.models import model_to_dict

from apps.seguridad.utils import audit_log

# Contexto por request para saber quién ejecuta la operación
_request_ctx: ContextVar = ContextVar("audit_request_ctx", default=None)
# Estados previos por instancia para UPDATE/DELETE
_previous_ctx: ContextVar = ContextVar("audit_previous_ctx", default={})
_signals_connected = False


def set_request_context(request) -> Any:
    """Guarda el request actual en un ContextVar y devuelve el token de reseteo."""
    return _request_ctx.set(request)


def reset_request_context(token: Any) -> None:
    try:
        _request_ctx.reset(token)
    except Exception:
        _request_ctx.set(None)


def _get_request():
    return _request_ctx.get()


def _get_user_id() -> Optional[int]:
    request = _get_request()
    if not request:
        return None
    return request.session.get("usuario_id")


def _remember_previous(sender, instance) -> None:
    if not instance.pk:
        return
    try:
        current = sender.objects.filter(pk=instance.pk).first()
        if not current:
            return
        snapshot = model_to_dict(current)
        state = dict(_previous_ctx.get({}))
        state[(sender, instance.pk)] = snapshot
        _previous_ctx.set(state)
    except Exception:
        # No romper flujo si falla la captura de estado previo
        pass


def _pop_previous(sender, pk) -> Optional[Dict]:
    state = dict(_previous_ctx.get({}))
    prev = state.pop((sender, pk), None)
    _previous_ctx.set(state)
    return prev


def _should_audit(sender) -> bool:
    if sender.__name__ == "Auditoria":
        return False
    if sender._meta.app_label in {"auth", "contenttypes", "sessions", "admin"}:
        return False
    return True


def _log_change(sender, instance, accion: str, prev_values: Optional[Dict]) -> None:
    user_id = _get_user_id()
    if not user_id:
        return
    request = _get_request()
    try:
        audit_log(
            usuario_id=user_id,
            accion=accion,
            tabla=sender._meta.db_table,
            id_registro=getattr(instance, instance._meta.pk.attname, None),
            descripcion=f"{accion} en {sender._meta.model_name}",
            valores_nuevos=model_to_dict(instance) if accion != "DELETE" else None,
            valores_anteriores=prev_values,
            request=request,
        )
    except Exception:
        # Auditoría no debe romper la operación principal
        pass


def _pre_save(sender, instance, **kwargs):
    if _should_audit(sender):
        _remember_previous(sender, instance)


def _post_save(sender, instance, created, **kwargs):
    if not _should_audit(sender):
        return
    prev = _pop_previous(sender, instance.pk)
    accion = "INSERT" if created else "UPDATE"
    _log_change(sender, instance, accion, prev)


def _pre_delete(sender, instance, **kwargs):
    if _should_audit(sender):
        _remember_previous(sender, instance)


def _post_delete(sender, instance, **kwargs):
    if not _should_audit(sender):
        return
    prev = _pop_previous(sender, instance.pk)
    _log_change(sender, instance, "DELETE", prev)


def connect_signals() -> None:
    """
    Conecta señales post_save/post_delete para todas las tablas propias
    (excluye auditoria y tablas internas de Django).
    """
    global _signals_connected
    if _signals_connected:
        return

    for model in apps.get_models():
        if not _should_audit(model):
            continue
        pre_save.connect(_pre_save, sender=model, weak=False)
        post_save.connect(_post_save, sender=model, weak=False)
        pre_delete.connect(_pre_delete, sender=model, weak=False)
        post_delete.connect(_post_delete, sender=model, weak=False)

    _signals_connected = True
