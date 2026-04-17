from django.db import models
from django.utils import timezone

from apps.integraciones.models.api_servicio import ApiServicio
from apps.usuarios.models import Usuario


class ApiConsumoLog(models.Model):
    id_api_log = models.BigAutoField(primary_key=True)
    api_servicio = models.ForeignKey(
        ApiServicio,
        on_delete=models.CASCADE,
        related_name="logs_consumo",
        db_column="id_api_servicio",
    )
    endpoint = models.CharField(max_length=500)
    metodo_http = models.CharField(max_length=20)
    usuario_sistema = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        related_name="consumos_api",
        null=True,
        blank=True,
        db_column="usuario_sistema",
    )
    fecha_consumo = models.DateTimeField(default=timezone.now)
    ip = models.CharField(max_length=45, null=True, blank=True)
    resultado = models.CharField(max_length=50, null=True, blank=True)
    detalle = models.CharField(max_length=1000, null=True, blank=True)

    class Meta:
        db_table = "api_consumo_log"
        managed = False
        verbose_name = "Log de consumo API"
        verbose_name_plural = "Logs de consumo API"
        ordering = ("-fecha_consumo",)
        indexes = [
            models.Index(fields=["api_servicio", "-fecha_consumo"], name="ix_api_log_srv_fecha")
        ]

    def __str__(self) -> str:
        return f"{self.metodo_http} {self.endpoint} - {self.resultado or 'N/D'}"
