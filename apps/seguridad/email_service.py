import os
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def _format_from(default_email: str) -> str:
    """
    Construye el remitente para activación de cuenta usando MAIL_FROM_3 si está definido.
    Si MAIL_FROM_3 solo es un nombre, se combina con el correo de envío.
    """
    display_name = os.getenv("MAIL_FROM_3")
    mail_user = os.getenv("MAIL_USER") or os.getenv("EMAIL_HOST_USER") or default_email

    if display_name:
        if "@" not in display_name:
            return f"{display_name} <{mail_user}>"
        return display_name  # Ya incluye correo

    return default_email or mail_user


def send_verification_email(to_email, verification_url, context):
    subject = "Verifica tu correo"
    html_content = render_to_string("emails/verify_email.html", {**context, "verification_url": verification_url})
    text_content = render_to_string("emails/verify_email.txt", {**context, "verification_url": verification_url})

    default_from = os.getenv("DEFAULT_FROM_EMAIL") or os.getenv("EMAIL_HOST_USER")
    from_email = _format_from(default_from)

    msg = EmailMultiAlternatives(subject, text_content, from_email, [to_email])
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)
