from __future__ import annotations

import json
import os
from urllib.parse import urlencode
from urllib import error, parse, request

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.core.services.email_theme_service import get_email_theme_tokens
from apps.core.services.email_service import send_plain_email
from apps.integraciones.models import ApiServicio
from apps.integraciones.services import api_log_service, graph_service


def _site_name() -> str:
    return getattr(settings, "SIG_SITE_NAME", "SIG")


def _mail_sender() -> str:
    return (
        getattr(settings, "SIG_MAIL_SENDER", "").strip()
        or getattr(settings, "GRAPH_DRIVE_USER", "").strip()
        or os.getenv("GRAPH_DRIVE_USER", "").strip()
    )


def _build_absolute_url(request, path: str) -> str:
    if request is None:
        return path
    return request.build_absolute_uri(path)


def _graph_mail_service():
    return (
        ApiServicio.objects.filter(
            activo=True,
            nombre_servicio__iexact="Microsoft Graph",
        )
        .order_by("-id_api_servicio")
        .first()
    )


def _graph_mail_configured() -> bool:
    if not getattr(settings, "SIG_USE_GRAPH_EMAIL", True):
        return False
    return bool(_mail_sender())


def _smtp_configured() -> bool:
    host = getattr(settings, "EMAIL_HOST", "").strip()
    user = getattr(settings, "EMAIL_HOST_USER", "").strip()
    password = getattr(settings, "EMAIL_HOST_PASSWORD", "")
    return bool(host and user and password)


def _send_graph_email(
    *,
    subject: str,
    body: str,
    recipient_list: list[str] | tuple[str, ...],
    html_body: str | None = None,
):
    sender = _mail_sender()
    if not sender:
        return {"sent": False, "error": "graph_sender_missing", "backend": "graph"}

    try:
        _, access_token = graph_service.get_graph_session()
    except Exception as exc:  # pragma: no cover - depende de credenciales reales
        return {"sent": False, "error": str(exc), "backend": "graph"}

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML" if html_body else "Text",
                "content": html_body or body,
            },
            "toRecipients": [
                {"emailAddress": {"address": recipient}}
                for recipient in recipient_list
            ],
        },
        "saveToSentItems": False,
    }
    api_path = f"/users/{parse.quote(sender, safe='')}/sendMail"
    http_request = request.Request(
        f"{graph_service.GRAPH_API_BASE}{api_path}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    service = _graph_mail_service()
    try:
        with request.urlopen(http_request, timeout=getattr(settings, "GRAPH_REQUEST_TIMEOUT_SECONDS", 10)) as response:
            if response.status not in (200, 202):
                raise ValueError(f"Respuesta inesperada de Graph: {response.status}")
            if service is not None:
                api_log_service.registrar_consumo_api(
                    api_servicio=service,
                    endpoint=api_path,
                    metodo_http="POST",
                    resultado=str(response.status),
                    detalle="Correo transaccional enviado por Microsoft Graph.",
                )
            return {"sent": True, "error": None, "backend": "graph"}
    except error.HTTPError as exc:  # pragma: no cover - depende del proveedor
        details = exc.read().decode("utf-8", errors="ignore")
        if service is not None:
            api_log_service.registrar_consumo_api(
                api_servicio=service,
                endpoint=api_path,
                metodo_http="POST",
                resultado=str(exc.code),
                detalle=details,
            )
        return {"sent": False, "error": details or str(exc), "backend": "graph"}
    except Exception as exc:  # pragma: no cover - depende de conectividad real
        if service is not None:
            api_log_service.registrar_consumo_api(
                api_servicio=service,
                endpoint=api_path,
                metodo_http="POST",
                resultado="ERROR",
                detalle=str(exc),
            )
        return {"sent": False, "error": str(exc), "backend": "graph"}


def send_transactional_email(
    *,
    subject: str,
    body: str,
    recipient_list: list[str] | tuple[str, ...],
    html_body: str | None = None,
):
    recipients = [item.strip() for item in recipient_list if str(item).strip()]
    if not recipients:
        return {"sent": False, "error": "recipient_missing", "backend": None}

    if _graph_mail_configured():
        graph_result = _send_graph_email(
            subject=subject,
            body=body,
            recipient_list=recipients,
            html_body=html_body,
        )
        if graph_result["sent"]:
            return graph_result

    if _smtp_configured():
        smtp_result = send_plain_email(
            subject=subject,
            body=body,
            recipient_list=recipients,
            html_body=html_body,
        )
        smtp_result["backend"] = "smtp"
        return smtp_result

    error_message = "No existe configuracion de envio de correo valida."
    if _graph_mail_configured():
        error_message = graph_result.get("error") or error_message
    return {"sent": False, "error": error_message, "backend": None}


def _render_email(template_name: str, context: dict) -> tuple[str, str]:
    merged_context = {
        **context,
        "theme": get_email_theme_tokens(),
        "site_name": _site_name(),
    }
    html_body = render_to_string(f"seguridad/emails/{template_name}.html", merged_context)
    text_body = render_to_string(f"seguridad/emails/{template_name}.txt", merged_context)
    return text_body.strip(), html_body


def send_login_otp_email(*, usuario, codigo: str, fecha_expiracion):
    expires_local = timezone.localtime(fecha_expiracion) if fecha_expiracion else None
    subject = f"{_site_name()} - Codigo temporal para completar tu ingreso"
    body, html_body = _render_email(
        "login_otp",
        {
            "usuario": usuario,
            "codigo": codigo,
            "fecha_expiracion": expires_local,
            "otp_minutes": int(getattr(settings, "SIG_OTP_EXPIRATION_MINUTES", 10) or 10),
        },
    )
    return send_transactional_email(
        subject=subject,
        body=body,
        recipient_list=[usuario.correo],
        html_body=html_body,
    )


def send_verification_email(*, usuario, token_plain: str, request=None):
    verification_path = reverse("seguridad-verificar-cuenta")
    verification_url = _build_absolute_url(
        request,
        f"{verification_path}?{urlencode({'token': token_plain})}",
    )
    subject = f"{_site_name()} - Verificacion de correo"
    body, html_body = _render_email(
        "verification_email",
        {
            "usuario": usuario,
            "verification_url": verification_url,
        },
    )
    return send_transactional_email(
        subject=subject,
        body=body,
        recipient_list=[usuario.correo],
        html_body=html_body,
    )


def send_password_recovery_email(*, usuario, token_plain: str, request=None):
    reset_path = reverse("seguridad-cambiar-password")
    reset_url = _build_absolute_url(
        request,
        f"{reset_path}?{urlencode({'token': token_plain})}",
    )
    subject = f"{_site_name()} - Recuperacion de contrasena"
    body, html_body = _render_email(
        "password_recovery",
        {
            "usuario": usuario,
            "reset_url": reset_url,
        },
    )
    return send_transactional_email(
        subject=subject,
        body=body,
        recipient_list=[usuario.correo],
        html_body=html_body,
    )
