from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from application.services import ensure_local_mirror_folder, get_drive_root_path, get_local_storage_root
from application.services.storage_path_service import get_ciclo_auth_drive_root, get_criterio_drive_root
from apps.core.models import (
    EstadoCiclo,
    EstadoEvaluacion,
    EstadoEvidencia,
    EstadoInforme,
    EstadoTareaEvidencia,
)
from apps.core.services.navigation_service import ROLE_ADMIN, ROLE_CONSULTA, ROLE_EVALUATOR
from apps.integraciones.services.graph_service import get_connection_summary, is_graph_configured
from apps.usuarios.models import Rol


REQUIRED_TABLES = (
    "usuario",
    "rol",
    "usuario_rol",
    "area_institucional",
    "cargo_area",
    "usuario_area_cargo",
    "usuario_supervisor",
    "criterio",
    "subcriterio",
    "indicador",
    "elemento_fundamental",
    "ciclo_evaluacion",
    "documento",
    "version_documento",
    "registro_evidencia",
    "historial_estado_evidencia",
    "estado_tarea_evidencia",
    "tarea_evidencia",
    "evaluacion",
    "observacion_evaluacion",
    "auditoria",
    "notificacion",
    "seguimiento_alerta_evaluacion",
    "informe_autoevaluacion",
    "seguimiento_accion_mejora",
    "categoria_valoracion_caces",
    "escenario_ponderacion_caces",
    "modelo_indicador_caces",
    "indicador_caces_mapeo",
    "ciclo_configuracion_caces",
    "indicador_formula_caces",
    "indicador_formula_variable_caces",
    "evaluacion_variable_caces",
    "evaluacion_indicador_caces",
)

REQUIRED_EVIDENCE_STATES = ("APROBADA", "OBSERVADA", "RECHAZADA")
RELEASE_EVIDENCE_STATES = ("ENVIADA_EVALUADOR", "EN_REVISION_EVALUADOR")
REQUIRED_EVALUATION_STATES = ("EN_ANALISIS", "APROBADA", "OBSERVADA", "RECHAZADA")
REQUIRED_CYCLE_STATES = ("APROBADO",)
FINALIZATION_CYCLE_STATES = (
    "EN_FINALIZACION",
    "EN PROCESO DE FINALIZACION",
    "FINALIZACION",
    "CERRADO",
    "FINALIZADO",
    "FINALIZADA",
)
REQUIRED_ROLES = (ROLE_ADMIN, ROLE_EVALUATOR, ROLE_CONSULTA)


def _normalize(value: str) -> str:
    return " ".join((value or "").strip().upper().split())


class Command(BaseCommand):
    help = "Valida los prerequisitos operativos principales del SIG antes de dar cierre funcional."

    def add_arguments(self, parser):
        parser.add_argument(
            "--graph-live",
            action="store_true",
            help="Valida la conexion real contra Microsoft Graph, no solo la configuracion.",
        )
        parser.add_argument(
            "--skip-graph",
            action="store_true",
            help="Omite la validacion de Microsoft Graph para entornos sin credenciales.",
        )

    def handle(self, *args, **options):
        errors = []

        self._check_database_connection(errors)
        self._check_tables(errors)
        self._check_catalogs(errors)
        self._check_roles(errors)
        self._check_local_mirror(errors)
        if not options["skip_graph"]:
            self._check_graph(errors, validate_live=options["graph_live"])

        if errors:
            raise CommandError("Validacion SIG fallida:\n - " + "\n - ".join(errors))

        self.stdout.write(self.style.SUCCESS("Validacion SIG completada correctamente."))

    def _check_database_connection(self, errors):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            self.stdout.write(self.style.SUCCESS("Base de datos: conexion correcta."))
        except Exception as exc:
            errors.append(f"Base de datos: no fue posible conectar ({exc}).")

    def _check_tables(self, errors):
        try:
            existing_tables = {table.lower() for table in connection.introspection.table_names()}
        except Exception as exc:
            errors.append(f"Tablas: no fue posible inspeccionar el esquema ({exc}).")
            return

        missing_tables = [table for table in REQUIRED_TABLES if table.lower() not in existing_tables]
        if missing_tables:
            errors.append("Tablas faltantes: " + ", ".join(missing_tables))
            return
        self.stdout.write(self.style.SUCCESS("Tablas base: completas."))

    def _active_descriptions(self, model):
        return {
            _normalize(description)
            for description in model.objects.filter(activo=True).values_list("descripcion", flat=True)
        }

    def _check_catalogs(self, errors):
        catalog_checks = (
            ("estado_evidencia", EstadoEvidencia, REQUIRED_EVIDENCE_STATES),
            ("estado_evaluacion", EstadoEvaluacion, REQUIRED_EVALUATION_STATES),
        )
        for name, model, required_values in catalog_checks:
            try:
                existing = self._active_descriptions(model)
            except Exception as exc:
                errors.append(f"{name}: no fue posible validar catalogo ({exc}).")
                continue

            missing = [value for value in required_values if _normalize(value) not in existing]
            if missing:
                errors.append(f"{name}: faltan estados activos {', '.join(missing)}.")
            elif name == "estado_evidencia" and not any(
                _normalize(value) in existing for value in RELEASE_EVIDENCE_STATES
            ):
                errors.append(
                    "estado_evidencia: falta ENVIADA_EVALUADOR o EN_REVISION_EVALUADOR para liberar evidencias."
                )
            else:
                self.stdout.write(self.style.SUCCESS(f"{name}: catalogo operativo correcto."))

        minimum_catalogs = (
            ("estado_tarea_evidencia", EstadoTareaEvidencia),
            ("estado_informe", EstadoInforme),
        )
        for name, model in minimum_catalogs:
            try:
                if not model.objects.filter(activo=True).exists():
                    errors.append(f"{name}: no tiene valores activos.")
                else:
                    self.stdout.write(self.style.SUCCESS(f"{name}: tiene valores activos."))
            except Exception as exc:
                errors.append(f"{name}: no fue posible validar catalogo ({exc}).")

        try:
            estados_ciclo = self._active_descriptions(EstadoCiclo)
        except Exception as exc:
            errors.append(f"estado_ciclo: no fue posible validar catalogo ({exc}).")
        else:
            missing = [
                value for value in REQUIRED_CYCLE_STATES if _normalize(value) not in estados_ciclo
            ]
            has_finalization = any(
                _normalize(value) in estados_ciclo for value in FINALIZATION_CYCLE_STATES
            )
            if missing:
                errors.append(f"estado_ciclo: faltan estados activos {', '.join(missing)}.")
            elif not has_finalization:
                errors.append(
                    "estado_ciclo: falta EN_FINALIZACION, CERRADO o FINALIZADO para cerrar el ciclo."
                )
            else:
                self.stdout.write(self.style.SUCCESS("estado_ciclo: catalogo operativo correcto."))

    def _check_roles(self, errors):
        try:
            existing_roles = {
                _normalize(name)
                for name in Rol.objects.filter(activo=True).values_list("nombre_rol", flat=True)
            }
        except Exception as exc:
            errors.append(f"Roles: no fue posible validar roles ({exc}).")
            return

        missing_roles = [role for role in REQUIRED_ROLES if _normalize(role) not in existing_roles]
        if missing_roles:
            errors.append("Roles faltantes: " + ", ".join(missing_roles))
            return
        self.stdout.write(self.style.SUCCESS("Roles base: ADMINISTRADOR, EVALUADOR y CONSULTA activos."))

    def _check_local_mirror(self, errors):
        if not getattr(settings, "SIG_LOCAL_DOCUMENT_MIRROR_ENABLED", True):
            self.stdout.write(self.style.WARNING("Espejo local documental: deshabilitado."))
            return
        try:
            mirror_root = ensure_local_mirror_folder(get_drive_root_path()) or get_local_storage_root()
            ensure_local_mirror_folder(get_ciclo_auth_drive_root())
            ensure_local_mirror_folder(get_criterio_drive_root())
        except Exception as exc:
            errors.append(f"Espejo local documental: no fue posible preparar la carpeta ({exc}).")
            return
        self.stdout.write(self.style.SUCCESS(f"Espejo local documental: disponible en {mirror_root}."))

    def _check_graph(self, errors, *, validate_live: bool):
        try:
            configured = is_graph_configured()
        except Exception as exc:
            errors.append(f"Microsoft Graph: no fue posible validar configuracion ({exc}).")
            return

        if not configured:
            errors.append("Microsoft Graph: falta configuracion o credencial activa.")
            return

        if not validate_live:
            self.stdout.write(self.style.SUCCESS("Microsoft Graph: configuracion detectada."))
            return

        summary = get_connection_summary(validate=True)
        if not summary.enabled:
            errors.append(f"Microsoft Graph: {summary.message}")
            return
        self.stdout.write(self.style.SUCCESS("Microsoft Graph: conexion validada contra el drive."))
