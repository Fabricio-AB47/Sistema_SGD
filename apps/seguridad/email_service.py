import os
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_verification_email(to_email, verification_url, context):
    subject = "Verifica tu correo"
    html_content = render_to_string("emails/verify_email.html", {**context, "verification_url": verification_url})
    text_content = render_to_string("emails/verify_email.txt", {**context, "verification_url": verification_url})
    from_email = os.getenv("DEFAULT_FROM_EMAIL") or os.getenv("EMAIL_HOST_USER")
    msg = EmailMultiAlternatives(subject, text_content, from_email, [to_email])
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)