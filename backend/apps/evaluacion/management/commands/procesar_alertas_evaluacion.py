from django.core.management.base import BaseCommand

from apps.evaluacion.services.alertas_service import procesar_alertas_evaluacion


class Command(BaseCommand):
    help = "Procesa alertas de seguimiento de evaluacion vencidas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Cantidad maxima de alertas a procesar.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra cuantas alertas estan vencidas sin enviar correos ni actualizar registros.",
        )

    def handle(self, *args, **options):
        totals = procesar_alertas_evaluacion(
            limit=options.get("limit"),
            dry_run=options.get("dry_run", False),
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Alertas procesadas: "
                f"{totals['processed']} | "
                f"enviadas: {totals['sent']} | "
                f"cerradas: {totals['closed']} | "
                f"fallos correo: {totals['email_failed']} | "
                f"errores: {totals['errors']}"
            )
        )
