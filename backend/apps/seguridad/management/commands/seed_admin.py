"""
Crea o actualiza un usuario administrador por defecto para el SIG.
Usa Argon2 (configurado en PASSWORD_HASHERS) y permite definir la
clave por variable de entorno ADMIN_PASSWORD. No sobreescribe si
ya existe un superusuario a menos que se fuerce con --reset.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Crea un superusuario administrativo con rol de administrador."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reestablece la contraseña del admin si ya existe.",
        )

    def handle(self, *args, **options):
        User = get_user_model()  # Obtiene el modelo de usuario activo.

        username = os.getenv("ADMIN_USERNAME", "admin")  # Usuario admin por defecto.
        email = os.getenv("ADMIN_EMAIL", "admin@localhost")  # Correo admin.
        password = os.getenv("ADMIN_PASSWORD", "Admin123!")  # Clave segura por defecto.

        # Busca si ya existe el usuario admin.
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )

        if created:
            # Si se creó, asigna la contraseña.
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Superusuario '{username}' creado."))
        else:
            # Si ya existe, sólo resetea si se pasa --reset.
            if options["reset"]:
                user.set_password(password)
                user.is_staff = True
                user.is_superuser = True
                user.is_active = True
                user.save()
                self.stdout.write(
                    self.style.WARNING(f"Contraseña de '{username}' reseteada.")
                )
            else:
                self.stdout.write(
                    self.style.NOTICE(
                        f"El usuario '{username}' ya existe. Use --reset para cambiar la contraseña."
                    )
                )

        # Mensaje final de ayuda.
        self.stdout.write(
            self.style.SUCCESS(
                "Admin listo. Inicia sesión con las credenciales configuradas."
            )
        )
