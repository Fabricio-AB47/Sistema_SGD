"""
Crea un administrador inicial idempotente usando Argon2 obligatorio.
Ejecuta: python manage.py crear_admin_inicial
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.seguridad.services import password_service
from apps.usuarios.models import (
    Usuario,
    UsuarioCredencial,
    Rol,
    UsuarioRol,
)


ADMIN_DATA = {
    "primer_nombre": "Admin",
    "segundo_nombre": "Sistema",
    "primer_apellido": "SIG",
    "segundo_apellido": "INTEC",
    "identificacion": "0000000000",
    "correo": "admin@sig.local",
    "telefono": "0999999999",
    "correo_verificado": True,
    "activo": True,
}

ADMIN_PASSWORD = "AdminSIG2026*"
ADMIN_ROL = "Administrador"


class Command(BaseCommand):
    help = "Crea el usuario admin inicial con rol Administrador (idempotente)."

    @transaction.atomic
    def handle(self, *args, **options):
        # 1. Crear rol Administrador si no existe
        rol, _ = Rol.objects.get_or_create(
            nombre_rol=ADMIN_ROL,
            defaults={
                "descripcion": "Rol administrativo con acceso completo",
                "acceso_global": True,
                "activo": True,
            },
        )

        # 2. Crear usuario admin si no existe
        usuario, creado_usuario = Usuario.objects.get_or_create(
            correo=ADMIN_DATA["correo"],
            defaults=ADMIN_DATA,
        )

        # 3. Crear o actualizar credencial con Argon2 obligatorio
        hashed = password_service.hash_password(ADMIN_PASSWORD)
        UsuarioCredencial.objects.update_or_create(
            usuario=usuario,
            defaults={
                "password_hash": hashed,
                "algoritmo_hash": "argon2",
                "requiere_cambio": False,
                "mfa_activo": False,
                "intentos_fallidos": 0,
                "bloqueado_hasta": None,
            },
        )

        # 4. Asignar rol Administrador (idempotente)
        UsuarioRol.objects.get_or_create(
            usuario=usuario,
            rol=rol,
            defaults={"activo": True},
        )

        msg_user = "creado" if creado_usuario else "actualizado"
        self.stdout.write(self.style.SUCCESS(f"Usuario admin {msg_user}: {usuario.correo}"))
        self.stdout.write(self.style.SUCCESS("Rol Administrador asegurado y asignado."))
        self.stdout.write(self.style.SUCCESS("Credencial configurada con Argon2."))
        self.stdout.write(self.style.SUCCESS("Listo."))
