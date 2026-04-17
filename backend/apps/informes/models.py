from django.db import models

from apps.acreditacion.models import CicloEvaluacion
from apps.core.fields import RowVersionField
from apps.core.models import EstadoInforme
from apps.evidencias.models import Documento
from apps.usuarios.models import Usuario


class InformeAutoevaluacion(models.Model):
    id_informe = models.AutoField(primary_key=True)
    ciclo = models.ForeignKey(
        CicloEvaluacion,
        on_delete=models.PROTECT,
        related_name="informes_autoevaluacion",
        db_column="id_ciclo",
    )
    fecha_generacion = models.DateTimeField(null=True, blank=True)
    resumen = models.CharField(max_length=2000, null=True, blank=True)
    conclusiones = models.CharField(max_length=4000, null=True, blank=True)
    ruta_archivo = models.CharField(max_length=1000, null=True, blank=True)
    documento = models.ForeignKey(
        Documento,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="informes_asociados",
        db_column="id_documento",
    )
    elaborado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="informes_elaborados",
        db_column="elaborado_por",
    )
    aprobado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="informes_aprobados",
        db_column="aprobado_por",
    )
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)
    observacion_aprobacion = models.CharField(max_length=1000, null=True, blank=True)
    estado = models.ForeignKey(
        EstadoInforme,
        on_delete=models.PROTECT,
        related_name="informes",
        db_column="id_estado_informe",
    )
    version_fila = RowVersionField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "informe_autoevaluacion"
        managed = False
        verbose_name = "Informe de autoevaluacion"
        verbose_name_plural = "Informes de autoevaluacion"
        ordering = ("-fecha_generacion",)
