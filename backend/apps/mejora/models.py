from django.db import models

from apps.core.models import EstadoPlanMejora
from apps.evidencias.models import Documento
from apps.evaluacion.models import Evaluacion
from apps.usuarios.models import Usuario


class PlanMejora(models.Model):
    id_plan_mejora = models.AutoField(primary_key=True)
    evaluacion = models.ForeignKey(
        Evaluacion,
        on_delete=models.CASCADE,
        related_name="planes_mejora",
        db_column="id_evaluacion",
    )
    descripcion = models.CharField(max_length=1000)
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    responsable = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="planes_mejora_responsable",
        db_column="responsable",
    )
    estado = models.ForeignKey(
        EstadoPlanMejora,
        on_delete=models.PROTECT,
        related_name="planes_mejora",
        db_column="id_estado_plan_mejora",
    )

    class Meta:
        db_table = "plan_mejora"
        managed = False
        verbose_name = "Plan de mejora"
        verbose_name_plural = "Planes de mejora"
        ordering = ("-fecha_inicio", "-id_plan_mejora")

    def __str__(self) -> str:
        return f"Plan #{self.id_plan_mejora}"


class AccionMejora(models.Model):
    id_accion = models.AutoField(primary_key=True)
    plan = models.ForeignKey(
        PlanMejora,
        on_delete=models.CASCADE,
        related_name="acciones",
        db_column="id_plan_mejora",
    )
    descripcion = models.CharField(max_length=1000)
    responsable = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="acciones_mejora_responsable",
        db_column="responsable",
    )
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    porcentaje_avance = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    observacion = models.CharField(max_length=1000, null=True, blank=True)

    class Meta:
        db_table = "accion_mejora"
        managed = False
        verbose_name = "Accion de mejora"
        verbose_name_plural = "Acciones de mejora"
        ordering = ("plan", "id_accion")

    def __str__(self) -> str:
        return f"Accion #{self.id_accion}"


class SeguimientoAccionMejora(models.Model):
    SEMAFORO_CHOICES = (
        ("VERDE", "Verde"),
        ("AMARILLO", "Amarillo"),
        ("ROJO", "Rojo"),
    )

    id_seguimiento_accion = models.AutoField(primary_key=True)
    accion = models.ForeignKey(
        AccionMejora,
        on_delete=models.CASCADE,
        related_name="seguimientos",
        db_column="id_accion",
    )
    fecha_seguimiento = models.DateTimeField(null=True, blank=True)
    porcentaje_avance = models.DecimalField(max_digits=5, decimal_places=2)
    observacion = models.CharField(max_length=1000, null=True, blank=True)
    documento = models.ForeignKey(
        Documento,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="seguimientos_mejora",
        db_column="id_documento",
    )
    registrado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="seguimientos_mejora_registrados",
        db_column="registrado_por",
    )
    semaforo = models.CharField(
        max_length=20,
        choices=SEMAFORO_CHOICES,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "seguimiento_accion_mejora"
        managed = False
        verbose_name = "Seguimiento de accion de mejora"
        verbose_name_plural = "Seguimientos de accion de mejora"
        ordering = ("-fecha_seguimiento", "-id_seguimiento_accion")

    def __str__(self) -> str:
        return f"Seguimiento #{self.id_seguimiento_accion}"
