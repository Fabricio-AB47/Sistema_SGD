from django.apps import AppConfig


class SeguridadConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.seguridad"
    verbose_name = "Seguridad y roles"

    def ready(self):
        # Lugar para registrar señales o auditoría de login si se requiere.
        return super().ready()
