from __future__ import annotations

import json
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.core.services.email_theme_service import get_email_theme_tokens
from apps.core.services.notification_service import crear_notificacion
from apps.evaluacion.models import AlertaSeguimientoEvaluacion, Evaluacion
from apps.evidencias.models import RegistroEvidencia
from apps.seguridad.services.notification_service import send_transactional_email
from apps.usuarios.models import Usuario


logger = logging.getLogger(__name__)

ALERTA_ENVIO_EVALUADOR = "registro_evidencia_envio_evaluador"
PLANTILLA_RECORDATORIO_EVALUADOR = "evaluator_release_reminder"

PENDING_EVIDENCE_STATES = {
    "ENVIADA_EVALUADOR",
    "EN_REVISION_EVALUADOR",
    "EN_ANALISIS",
    "EN_REVISION",
}
FINAL_EVIDENCE_STATES = {
    "APROBADA",
    "RECHAZADA",
    "OBSERVADA",
    "DEVUELTA_INTERNA",
    "REENVIADA",
    "CERRADA",
    "ATENDIDA",
}


def _site_name() -> str:
    return getattr(settings, "SIG_SITE_NAME", "SIG")


def _reminder_interval_days() -> int:
    return max(int(getattr(settings, "SIG_ALERT_REMINDER_INTERVAL_DAYS", 2) or 2), 1)


def _reminder_count() -> int:
    return max(int(getattr(settings, "SIG_ALERT_REMINDER_COUNT", 3) or 3), 0)


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _safe_context(context: dict) -> dict:
    keys = {
        "actor_name",
        "documento_nombre",
        "elemento_codigo",
        "elemento_nombre",
        "indicador_codigo",
        "indicador_nombre",
        "ciclo_nombre",
        "fecha_evento",
        "evidence_url",
    }
    return {key: context.get(key) for key in keys if context.get(key) not in (None, "")}


def _load_context(alerta: AlertaSeguimientoEvaluacion) -> dict:
    if not alerta.contexto_json:
        return {}
    try:
        payload = json.loads(alerta.contexto_json)
    except json.JSONDecodeError:
        logger.warning("Contexto JSON invalido para alerta %s.", alerta.pk)
        return {}
    return payload if isinstance(payload, dict) else {}


def _render_email(template_name: str, context: dict) -> tuple[str, str]:
    merged_context = {
        **context,
        "theme": get_email_theme_tokens(),
        "site_name": _site_name(),
    }
    text_body = render_to_string(f"evaluacion/emails/{template_name}.txt", merged_context)
    html_body = render_to_string(f"evaluacion/emails/{template_name}.html", merged_context)
    return text_body.strip(), html_body


def _estado_normalizado(registro: RegistroEvidencia) -> str:
    return ((getattr(getattr(registro, "estado", None), "descripcion", "") or "").strip().upper())


def _registro_sigue_pendiente(registro: RegistroEvidencia | None) -> tuple[bool, str]:
    if registro is None:
        return False, "registro_no_encontrado"
    estado = _estado_normalizado(registro)
    if estado in FINAL_EVIDENCE_STATES:
        return False, f"estado_{estado.lower()}"
    if Evaluacion.objects.filter(registro=registro).exists():
        return False, "evaluacion_registrada"
    if registro.fecha_envio_revision is None:
        return False, "sin_fecha_envio_revision"
    if estado in PENDING_EVIDENCE_STATES or "EVALUADOR" in estado or "REVISION" in estado:
        return True, "pendiente_evaluacion"
    return False, f"estado_no_pendiente_{estado.lower() or 'sin_estado'}"


def _cerrar_alerta(alerta: AlertaSeguimientoEvaluacion, *, motivo: str, now=None):
    now = now or timezone.now()
    alerta.activa = False
    alerta.fecha_cierre = now
    alerta.motivo_cierre = motivo[:200]
    alerta.proximo_envio = None
    alerta.save(update_fields=["activa", "fecha_cierre", "motivo_cierre", "proximo_envio"])


def programar_alertas_envio_evaluador(
    *,
    registro,
    evaluadores,
    subject: str,
    context: dict,
):
    """
    Registra el calendario de seguimiento posterior al correo inicial.
    El correo inicial cuenta como envio 1; luego se envian 3 recordatorios mas.
    """
    registro_id = getattr(registro, "pk", None)
    if not registro_id:
        return 0

    max_envios = 1 + _reminder_count()
    if max_envios <= 1:
        return 0

    interval_days = _reminder_interval_days()
    now = timezone.now()
    next_send = now + timedelta(days=interval_days)
    payload = json.dumps(_safe_context(context), ensure_ascii=False, default=_json_default)

    unique_users = []
    seen = set()
    for usuario in evaluadores or []:
        user_id = getattr(usuario, "pk", None)
        correo = (getattr(usuario, "correo", "") or "").strip().lower()
        if not user_id or not correo or user_id in seen or not getattr(usuario, "activo", True):
            continue
        seen.add(user_id)
        unique_users.append((user_id, correo))

    def _schedule():
        scheduled = 0
        for user_id, correo in unique_users:
            _, created = AlertaSeguimientoEvaluacion.objects.update_or_create(
                referencia_tipo=ALERTA_ENVIO_EVALUADOR,
                referencia_id=registro_id,
                id_user=user_id,
                plantilla=PLANTILLA_RECORDATORIO_EVALUADOR,
                defaults={
                    "correo": correo,
                    "asunto": subject[:200],
                    "contexto_json": payload,
                    "numero_envios": 1,
                    "max_envios": max_envios,
                    "intervalo_dias": interval_days,
                    "activa": True,
                    "fecha_inicio": now,
                    "fecha_ultimo_envio": now,
                    "proximo_envio": next_send,
                    "fecha_cierre": None,
                    "motivo_cierre": None,
                    "ultimo_error": None,
                },
            )
            scheduled += 1
            if created:
                logger.info("Programada alerta de evaluacion %s para usuario %s.", registro_id, user_id)
        return scheduled

    transaction.on_commit(_schedule)
    return len(unique_users)


def _procesar_alerta(alerta: AlertaSeguimientoEvaluacion, *, dry_run: bool = False) -> dict:
    now = timezone.now()
    registro = (
        RegistroEvidencia.objects.select_related(
            "estado",
            "documento",
            "ciclo",
            "indicador",
            "elemento_fundamental",
        )
        .filter(pk=alerta.referencia_id)
        .first()
    )
    pendiente, motivo = _registro_sigue_pendiente(registro)
    if not pendiente:
        if not dry_run:
            _cerrar_alerta(alerta, motivo=motivo, now=now)
            registrar_evento(
                accion="CERRAR_ALERTA_SEGUIMIENTO",
                descripcion=f"Se cerro la alerta de seguimiento {alerta.pk}: {motivo}.",
                tipo_evento="EVALUACION",
                tabla_afectada="seguimiento_alerta_evaluacion",
                id_registro=alerta.pk,
                valores_nuevos={
                    "registro_id": alerta.referencia_id,
                    "motivo": motivo,
                },
                criticidad="BAJA",
            )
        return {"status": "closed", "reason": motivo}

    usuario = Usuario.objects.filter(pk=alerta.id_user, activo=True).first()
    if usuario is None:
        if not dry_run:
            _cerrar_alerta(alerta, motivo="usuario_inactivo_o_no_encontrado", now=now)
        return {"status": "closed", "reason": "usuario_inactivo_o_no_encontrado"}

    reminder_number = max(alerta.numero_envios, 1)
    context = _load_context(alerta)
    context.update(
        {
            "subject": alerta.asunto,
            "recordatorio_numero": reminder_number,
            "recordatorios_totales": max(alerta.max_envios - 1, 0),
            "recordatorios_restantes": max(alerta.max_envios - alerta.numero_envios - 1, 0),
            "fecha_recordatorio": timezone.localtime(now),
            "correo_destino": alerta.correo,
            "usuario_destino": getattr(usuario, "nombre_completo", None) or usuario.correo,
        }
    )

    if dry_run:
        return {"status": "due", "registro_id": alerta.referencia_id, "user_id": alerta.id_user}

    body, html_body = _render_email(alerta.plantilla, context)
    result = send_transactional_email(
        subject=f"{alerta.asunto} - Recordatorio {reminder_number}",
        body=body,
        recipient_list=[alerta.correo],
        html_body=html_body,
    )
    if not result.get("sent"):
        alerta.ultimo_error = (result.get("error") or "No se pudo enviar el correo.")[:1000]
        alerta.save(update_fields=["ultimo_error"])
        registrar_evento(
            accion="FALLO_ALERTA_SEGUIMIENTO",
            descripcion=f"No se pudo enviar la alerta de seguimiento {alerta.pk}.",
            usuario=usuario,
            tipo_evento="EVALUACION",
            tabla_afectada="seguimiento_alerta_evaluacion",
            id_registro=alerta.pk,
            valores_nuevos={
                "registro_id": alerta.referencia_id,
                "recordatorio": reminder_number,
                "error": alerta.ultimo_error,
            },
            criticidad="MEDIA",
        )
        return {"status": "email_failed", "error": alerta.ultimo_error}

    crear_notificacion(
        user_id=alerta.id_user,
        titulo=f"Recordatorio {reminder_number}: evidencia pendiente",
        mensaje=(
            f"La evidencia {context.get('elemento_codigo', '')} "
            f"sigue pendiente de evaluacion."
        ).strip(),
        tipo="WARNING",
        modulo="EVALUACION",
        referencia_tipo=ALERTA_ENVIO_EVALUADOR,
        referencia_id=alerta.referencia_id,
        url=context.get("evidence_url"),
    )

    alerta.numero_envios += 1
    alerta.fecha_ultimo_envio = now
    alerta.ultimo_error = None
    if alerta.numero_envios >= alerta.max_envios:
        alerta.activa = False
        alerta.fecha_cierre = now
        alerta.motivo_cierre = "recordatorios_completados"
        alerta.proximo_envio = None
        update_fields = [
            "numero_envios",
            "fecha_ultimo_envio",
            "ultimo_error",
            "activa",
            "fecha_cierre",
            "motivo_cierre",
            "proximo_envio",
        ]
    else:
        alerta.proximo_envio = now + timedelta(days=max(alerta.intervalo_dias, 1))
        update_fields = ["numero_envios", "fecha_ultimo_envio", "ultimo_error", "proximo_envio"]
    alerta.save(update_fields=update_fields)

    registrar_evento(
        accion="ENVIAR_ALERTA_SEGUIMIENTO",
        descripcion=(
            f"Se envio el recordatorio {reminder_number} de seguimiento "
            f"para la evidencia {alerta.referencia_id}."
        ),
        usuario=usuario,
        tipo_evento="EVALUACION",
        tabla_afectada="seguimiento_alerta_evaluacion",
        id_registro=alerta.pk,
        valores_nuevos={
            "registro_id": alerta.referencia_id,
            "recordatorio": reminder_number,
            "correo": alerta.correo,
            "numero_envios": alerta.numero_envios,
            "activo": alerta.activa,
        },
        criticidad="MEDIA",
    )
    return {"status": "sent", "reminder": reminder_number}


def procesar_alertas_evaluacion(*, limit: int | None = None, dry_run: bool = False) -> dict:
    now = timezone.now()
    queryset = AlertaSeguimientoEvaluacion.objects.filter(
        activa=True,
        proximo_envio__lte=now,
        numero_envios__lt=models.F("max_envios"),
    ).order_by("proximo_envio", "id_alerta")
    if limit:
        queryset = queryset[:limit]

    totals = {
        "processed": 0,
        "sent": 0,
        "closed": 0,
        "due": 0,
        "email_failed": 0,
        "errors": 0,
    }
    for alerta in queryset:
        try:
            result = _procesar_alerta(alerta, dry_run=dry_run)
        except Exception:
            logger.exception("No se pudo procesar la alerta de evaluacion %s.", alerta.pk)
            totals["errors"] += 1
            continue
        totals["processed"] += 1
        status = result.get("status")
        if status in totals:
            totals[status] += 1
    return totals
