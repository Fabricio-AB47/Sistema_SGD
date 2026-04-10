from django.db import models

from apps.acreditacion.models import CicloEvaluacion, ElementoFundamental, Indicador
from apps.core.models import EstadoEvaluacion, EstadoTareaEvidencia
from apps.evidencias.models import RegistroEvidencia
from apps.usuarios.models import Usuario


class Evaluacion(models.Model):
    id_evaluacion = models.AutoField(primary_key=True)
    registro = models.ForeignKey(
        RegistroEvidencia,
        on_delete=models.CASCADE,
        related_name="evaluaciones",
        db_column="id_registro",
    )
    usuario_evaluador = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="evaluaciones_realizadas",
        db_column="id_usuario_evaluador",
    )
    estado = models.ForeignKey(
        EstadoEvaluacion,
        on_delete=models.PROTECT,
        related_name="evaluaciones",
        db_column="id_estado_evaluacion",
    )
    fecha_evaluacion = models.DateTimeField(null=True, blank=True)
    calificacion = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    comentario = models.CharField(max_length=1000, null=True, blank=True)
    aprobado = models.BooleanField(default=False)

    class Meta:
        db_table = "evaluacion"
        managed = False
        verbose_name = "Evaluacion"
        verbose_name_plural = "Evaluaciones"
        ordering = ("-fecha_evaluacion",)
        indexes = [
            models.Index(
                fields=["estado", "-fecha_evaluacion"],
                name="ix_evaluacion_estado_fecha",
            )
        ]


class ObservacionEvaluacion(models.Model):
    id_observacion = models.AutoField(primary_key=True)
    evaluacion = models.ForeignKey(
        Evaluacion,
        on_delete=models.CASCADE,
        related_name="observaciones",
        db_column="id_evaluacion",
    )
    observacion = models.CharField(max_length=1000)
    fecha_observacion = models.DateTimeField(null=True, blank=True)
    usuario_emisor = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="observaciones_emitidas",
        db_column="id_usuario_emisor",
    )
    atendida = models.BooleanField(default=False)
    fecha_atendida = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "observacion_evaluacion"
        managed = False
        verbose_name = "Observacion de evaluacion"
        verbose_name_plural = "Observaciones de evaluacion"
        ordering = ("-fecha_observacion",)


class TareaEvidencia(models.Model):
    PRIORIDAD_CHOICES = (
        ("BAJA", "Baja"),
        ("MEDIA", "Media"),
        ("ALTA", "Alta"),
        ("CRITICA", "Critica"),
    )

    id_tarea_evidencia = models.AutoField(primary_key=True)
    ciclo = models.ForeignKey(
        CicloEvaluacion,
        on_delete=models.CASCADE,
        related_name="tareas_evidencia",
        db_column="id_ciclo",
    )
    indicador = models.ForeignKey(
        Indicador,
        on_delete=models.CASCADE,
        related_name="tareas_evidencia",
        db_column="id_indicador",
    )
    elemento_fundamental = models.ForeignKey(
        ElementoFundamental,
        on_delete=models.CASCADE,
        related_name="tareas_evidencia",
        db_column="id_elemento_fundamental",
    )
    usuario_responsable = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="tareas_evidencia_responsable",
        db_column="id_usuario_responsable",
    )
    estado = models.ForeignKey(
        EstadoTareaEvidencia,
        on_delete=models.PROTECT,
        related_name="tareas",
        db_column="id_estado_tarea",
    )
    fecha_asignacion = models.DateTimeField(null=True, blank=True)
    fecha_limite = models.DateTimeField(null=True, blank=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    prioridad = models.CharField(
        max_length=20,
        choices=PRIORIDAD_CHOICES,
        null=True,
        blank=True,
    )
    observacion = models.CharField(max_length=1000, null=True, blank=True)
    resultado_tarea = models.CharField(max_length=1000, null=True, blank=True)
    asignado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas_evidencia_asignadas",
        db_column="asignado_por",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "tarea_evidencia"
        managed = False
        verbose_name = "Tarea de evidencia"
        verbose_name_plural = "Tareas de evidencia"
        ordering = ("-fecha_asignacion", "-id_tarea_evidencia")
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "ciclo",
                    "indicador",
                    "elemento_fundamental",
                    "usuario_responsable",
                    "activo",
                ],
                name="uq_tarea_evidencia_operativa",
            )
        ]


class EstadoEvidenciasCiclo(models.Model):
    pk = models.CompositePrimaryKey(
        "id_ciclo",
        "id_indicador",
        "id_elemento_fundamental",
        "estado_evidencia",
    )
    id_ciclo = models.IntegerField()
    ciclo = models.CharField(max_length=150)
    id_indicador = models.IntegerField()
    codigo_indicador = models.CharField(max_length=20)
    nombre_indicador = models.CharField(max_length=200)
    id_elemento_fundamental = models.IntegerField()
    codigo_elemento = models.CharField(max_length=20)
    nombre_elemento = models.CharField(max_length=200)
    estado_evidencia = models.CharField(max_length=100)
    total = models.IntegerField()

    class Meta:
        db_table = "vw_estado_evidencias_ciclo"
        managed = False
        verbose_name = "Estado de evidencias por ciclo"
        verbose_name_plural = "Estados de evidencias por ciclo"
