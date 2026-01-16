from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.seguridad.models import EmailVerificationToken


class Command(BaseCommand):
    help = "Elimina tokens de verificacion expirados"

    def handle(self, *args, **options):
        now = timezone.now()
        qs = EmailVerificationToken.objects.filter(expires_at__lt=now)
        count = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Eliminados {count} tokens expirados"))