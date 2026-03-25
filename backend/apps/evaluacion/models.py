from django.db import models

from apps.core.models import EstadoEvaluacion
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
                fields=["registro", "estado", "-fecha_evaluacion"],
                name="ix_evaluacion_registro_estado",
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
