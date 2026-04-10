from __future__ import annotations

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def get_default_from_email() -> str:
    return (
        getattr(settings, "DEFAULT_FROM_EMAIL", "")
        or getattr(settings, "EMAIL_HOST_USER", "")
        or "no-reply@sig.local"
    )


def send_plain_email(
    *,
    subject: str,
    body: str,
    recipient_list: list[str] | tuple[str, ...],
    html_body: str | None = None,
):
    recipients = [item.strip() for item in recipient_list if str(item).strip()]
    if not recipients:
        return {"sent": False, "error": "recipient_missing"}

    message = EmailMultiAlternatives(
        subject=subject.strip(),
        body=body.strip(),
        from_email=get_default_from_email(),
        to=recipients,
    )
    if html_body:
        message.attach_alternative(html_body, "text/html")

    try:
        sent = message.send(fail_silently=False)
    except Exception as exc:  # pragma: no cover - depende del backend SMTP real
        return {"sent": False, "error": str(exc)}

    return {"sent": bool(sent), "error": None}
