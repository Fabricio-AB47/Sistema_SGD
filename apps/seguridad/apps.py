from django.apps import AppConfig


class SeguridadConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.seguridad"

    def ready(self):
        # Conectar trazabilidad de auditoría global
        try:
            from apps.seguridad.audit_trail import connect_signals

            connect_signals()
        except Exception:
            # No bloquear el arranque si falla la conexión de señales
            pass
