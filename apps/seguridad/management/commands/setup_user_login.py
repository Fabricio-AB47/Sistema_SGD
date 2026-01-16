from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.hashers import make_password
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from django.conf import settings

from apps.seguridad.models import Usuario, UsuarioCredencial, Rol, UsuarioRol


class Command(BaseCommand):
    help = "Configura credencial y rol para un usuario (correo + contraseña) y envía correo de notificación."

    def add_arguments(self, parser):
        parser.add_argument("--correo", required=True, help="Correo del usuario (tabla usuario.correo)")
        parser.add_argument("--password", required=True, help="Contraseña a asignar")
        parser.add_argument(
            "--rol-id",
            type=int,
            help="ID de rol a asignar (tabla rol.id_rol). Opcional si usa --rol-nombre.",
        )
        parser.add_argument(
            "--rol-nombre",
            help="Nombre de rol a asignar (tabla rol.nombre_rol). Opcional si usa --rol-id.",
        )

    def handle(self, *args, **options):
        correo = options["correo"].strip()
        password = options["password"]
        rol_id = options.get("rol_id")
        rol_nombre = options.get("rol_nombre")

        if not (rol_id or rol_nombre):
            raise CommandError("Debe especificar --rol-id o --rol-nombre")

        try:
            usuario = Usuario.objects.get(correo=correo)
        except Usuario.DoesNotExist:
            raise CommandError(f"Usuario con correo {correo} no existe")

        # Rol
        rol = None
        if rol_id:
            try:
                rol = Rol.objects.get(id_rol=rol_id)
            except Rol.DoesNotExist:
                raise CommandError(f"Rol con id {rol_id} no existe")
        else:
            try:
                rol = Rol.objects.get(nombre_rol=rol_nombre)
            except Rol.DoesNotExist:
                raise CommandError(f"Rol con nombre {rol_nombre} no existe")

        # Credencial
        UsuarioCredencial.objects.update_or_create(
            usuario=usuario,
            defaults={
                "password_hash": make_password(password).encode(),
                "algoritmo_hash": "pbkdf2_sha256",
                "fecha_cambio": timezone.now(),
                "requiere_cambio": False,
                "intentos_fallidos": 0,
                "bloqueado_hasta": None,
                "ultimo_login": None,
            },
        )
        # Verificado
        if not usuario.correo_verificado:
            usuario.correo_verificado = True
            usuario.save(update_fields=["correo_verificado"])

        # Asignar rol si no lo tiene
        UsuarioRol.objects.get_or_create(
            usuario=usuario,
            rol=rol,
            defaults={"fecha_asignacion": timezone.now(), "asignado_por": None},
        )

        self.stdout.write(self.style.SUCCESS(f"Usuario listo: {correo} con rol {rol.nombre_rol}"))

        # Enviar correo
        if settings.EMAIL_HOST_USER and settings.DEFAULT_FROM_EMAIL:
            subject = "Acceso SGD configurado"
            body = (
                f"Hola {usuario.primer_nombre},\n\n"
                f"Tu acceso ha sido configurado.\n"
                f"Correo: {correo}\n"
                f"Contraseña: {password}\n\n"
                "Por seguridad, cambia tu contraseña después de ingresar."
            )
            msg = EmailMultiAlternatives(
                subject=subject,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[correo],
                cc=[settings.MAIL_CC] if getattr(settings, "MAIL_CC", "") else [],
            )
            try:
                msg.send()
                self.stdout.write(self.style.SUCCESS("Correo de notificación enviado."))
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"Correo no enviado: {exc}"))
        else:
            self.stdout.write(self.style.WARNING("EMAIL_HOST_USER/DEFAULT_FROM_EMAIL no configurados; no se envió correo."))
