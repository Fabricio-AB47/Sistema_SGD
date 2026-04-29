from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.core.services.email_theme_service import get_email_theme_tokens
from apps.core.services.notification_service import queue_notificaciones
from apps.seguridad.services.notification_service import send_transactional_email


logger = logging.getLogger(__name__)


def _site_name() -> str:
    return getattr(settings, "SIG_SITE_NAME", "SIG")


def _display_name(usuario) -> str:
    if usuario is None:
        return "-"
    return getattr(usuario, "nombre_completo", None) or getattr(usuario, "correo", "") or "-"


def _recipient_emails(*usuarios) -> list[str]:
    recipients = []
    seen = set()
    for usuario in usuarios:
        if usuario is None or not getattr(usuario, "activo", True):
            continue
        email = (getattr(usuario, "correo", "") or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        recipients.append(email)
    return recipients


def _recipient_user_ids(*usuarios) -> list[int]:
    recipients = []
    seen = set()
    for usuario in usuarios:
        user_id = getattr(usuario, "pk", None)
        if not user_id or user_id in seen:
            continue
        seen.add(user_id)
        recipients.append(user_id)
    return recipients


def _build_absolute_url(request, path: str) -> str:
    if request is None:
        return path
    return request.build_absolute_uri(path)


def _evidence_detail_url(*, request, registro) -> str:
    if registro is None:
        return _build_absolute_url(request, reverse("evaluacion-tareas-reasignacion"))
    path = f"{reverse('evaluacion-evidencia-detalle')}?{urlencode({'registro': registro.pk})}"
    return _build_absolute_url(request, path)


def _upload_url(*, request, tarea) -> str:
    path = (
        f"{reverse('acreditacion-matriz-registro')}?"
        f"{urlencode({
            'ciclo': tarea.ciclo_id,
            'indicador': tarea.indicador_id,
            'elemento': tarea.elemento_fundamental_id,
            'modal': 'upload',
        })}"
    )
    return _build_absolute_url(request, path)


def _render_email(template_name: str, context: dict) -> tuple[str, str]:
    merged_context = {
        **context,
        "theme": get_email_theme_tokens(),
        "site_name": _site_name(),
    }
    html_body = render_to_string(f"evaluacion/emails/{template_name}.html", merged_context)
    text_body = render_to_string(f"evaluacion/emails/{template_name}.txt", merged_context)
    return text_body.strip(), html_body


def _base_context(*, tarea, registro, documento, actor, request) -> dict:
    elemento = getattr(tarea, "elemento_fundamental", None) or getattr(registro, "elemento_fundamental", None)
    indicador = getattr(tarea, "indicador", None) or getattr(registro, "indicador", None)
    ciclo = getattr(tarea, "ciclo", None) or getattr(registro, "ciclo", None)
    documento = documento or getattr(registro, "documento", None)
    return {
        "actor": actor,
        "actor_name": _display_name(actor),
        "tarea": tarea,
        "registro": registro,
        "documento": documento,
        "documento_nombre": getattr(documento, "nombre_archivo", "-"),
        "elemento": elemento,
        "elemento_codigo": getattr(elemento, "codigo_elemento", "-"),
        "elemento_nombre": getattr(elemento, "nombre_elemento", "-"),
        "indicador": indicador,
        "indicador_codigo": getattr(indicador, "codigo_indicador", "-"),
        "indicador_nombre": getattr(indicador, "nombre_indicador", "-"),
        "ciclo": ciclo,
        "ciclo_nombre": getattr(ciclo, "nombre", "-"),
        "fecha_evento": timezone.localtime(timezone.now()),
        "evidence_url": _evidence_detail_url(request=request, registro=registro),
    }


def _send_email(*, subject: str, template_name: str, recipients: list[str], context: dict):
    if not recipients:
        return {"sent": False, "error": "recipient_missing", "backend": None}

    body, html_body = _render_email(template_name, {"subject": subject, **context})
    result = send_transactional_email(
        subject=subject,
        body=body,
        recipient_list=recipients,
        html_body=html_body,
    )
    if not result.get("sent"):
        logger.warning(
            "No se pudo enviar notificacion de evaluacion '%s': %s",
            subject,
            result.get("error"),
        )
    return result


def _queue_email(*, subject: str, template_name: str, recipients: list[str], context: dict):
    def _deliver():
        try:
            _send_email(
                subject=subject,
                template_name=template_name,
                recipients=recipients,
                context=context,
            )
        except Exception:
            logger.exception("Fallo no bloqueante enviando notificacion de evaluacion '%s'.", subject)

    transaction.on_commit(_deliver)


def queue_evidence_uploaded_email(*, registro, documento=None, tarea=None, actor=None, requires_director_check=False, request=None):
    director = getattr(tarea, "asignado_por", None) if requires_director_check else None
    responsable = getattr(tarea, "usuario_responsable", None)
    recipients = _recipient_emails(
        actor,
        director,
        responsable,
    )
    context = _base_context(
        tarea=tarea,
        registro=registro,
        documento=documento,
        actor=actor,
        request=request,
    )
    context.update(
        {
            "requires_director_check": requires_director_check,
            "responsable_name": _display_name(getattr(tarea, "usuario_responsable", None)),
            "director_name": _display_name(getattr(tarea, "asignado_por", None)),
        }
    )
    subject = f"{_site_name()} - Evidencia cargada {context['elemento_codigo']}"
    queue_notificaciones(
        user_ids=_recipient_user_ids(actor, director, responsable),
        titulo=f"Evidencia cargada: {context['elemento_codigo']}",
        mensaje=(
            f"{context['actor_name']} cargo {context['documento_nombre']} "
            f"en {context['ciclo_nombre']}."
        ),
        tipo="INFO" if requires_director_check else "SUCCESS",
        modulo="EVALUACION",
        actor_id=getattr(actor, "pk", None),
        referencia_tipo="registro_evidencia",
        referencia_id=getattr(registro, "pk", None),
        url=context["evidence_url"],
    )
    _queue_email(
        subject=subject,
        template_name="evidence_uploaded",
        recipients=recipients,
        context=context,
    )


def queue_task_reassigned_notification(*, tarea, nuevo_responsable, actor=None, comentario=None, request=None):
    upload_url = _upload_url(request=request, tarea=tarea)
    elemento = getattr(tarea, "elemento_fundamental", None)
    elemento_codigo = getattr(elemento, "codigo_elemento", "-")
    elemento_nombre = getattr(elemento, "nombre_elemento", "-")
    actor_name = _display_name(actor)
    note = " ".join((comentario or "").strip().split())
    message = f"{actor_name} te reasigno la carga de {elemento_codigo} - {elemento_nombre}."
    if note:
        message = f"{message} Nota: {note}"
    queue_notificaciones(
        user_ids=_recipient_user_ids(nuevo_responsable),
        titulo=f"Tarea reasignada: {elemento_codigo}",
        mensaje=message,
        tipo="INFO",
        modulo="EVALUACION",
        actor_id=getattr(actor, "pk", None),
        referencia_tipo="tarea_evidencia",
        referencia_id=getattr(tarea, "pk", None),
        url=upload_url,
    )


def queue_director_signoff_email(*, tarea, registro, actor=None, comentario=None, request=None):
    responsable = getattr(tarea, "usuario_responsable", None)
    registrador = getattr(registro, "registrado_por", None)
    recipients = _recipient_emails(
        responsable,
        registrador,
    )
    context = _base_context(
        tarea=tarea,
        registro=registro,
        documento=getattr(registro, "documento", None),
        actor=actor,
        request=request,
    )
    context.update(
        {
            "comentario": " ".join((comentario or "").strip().split()),
            "responsable_name": _display_name(getattr(tarea, "usuario_responsable", None)),
        }
    )
    subject = f"{_site_name()} - Documento aprobado {context['elemento_codigo']}"
    queue_notificaciones(
        user_ids=_recipient_user_ids(responsable, registrador),
        titulo=f"Documento aprobado: {context['elemento_codigo']}",
        mensaje=(
            f"{context['actor_name']} aprobo {context['documento_nombre']} "
            "mediante el check de subida."
        ),
        tipo="SUCCESS",
        modulo="EVALUACION",
        actor_id=getattr(actor, "pk", None),
        referencia_tipo="registro_evidencia",
        referencia_id=getattr(registro, "pk", None),
        url=context["evidence_url"],
    )
    _queue_email(
        subject=subject,
        template_name="evidence_check_approved",
        recipients=recipients,
        context=context,
    )


def queue_correction_requested_email(*, tarea, registro, actor=None, comentario=None, request=None):
    responsable = getattr(tarea, "usuario_responsable", None)
    registrador = getattr(registro, "registrado_por", None)
    recipients = _recipient_emails(
        responsable,
        registrador,
    )
    context = _base_context(
        tarea=tarea,
        registro=registro,
        documento=getattr(registro, "documento", None),
        actor=actor,
        request=request,
    )
    context.update(
        {
            "comentario": " ".join((comentario or "").strip().split()),
            "upload_url": _upload_url(request=request, tarea=tarea),
            "responsable_name": _display_name(getattr(tarea, "usuario_responsable", None)),
        }
    )
    subject = f"{_site_name()} - Correcciones solicitadas {context['elemento_codigo']}"
    queue_notificaciones(
        user_ids=_recipient_user_ids(responsable, registrador),
        titulo=f"Correcciones solicitadas: {context['elemento_codigo']}",
        mensaje=(
            f"{context['actor_name']} solicito correcciones sobre "
            f"{context['documento_nombre']}: {context['comentario']}"
        ),
        tipo="WARNING",
        modulo="EVALUACION",
        actor_id=getattr(actor, "pk", None),
        referencia_tipo="registro_evidencia",
        referencia_id=getattr(registro, "pk", None),
        url=context["upload_url"],
    )
    _queue_email(
        subject=subject,
        template_name="evidence_corrections_requested",
        recipients=recipients,
        context=context,
    )
