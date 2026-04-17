from django.db import models
from django.utils import timezone

from apps.integraciones.models.api_credencial import ApiCredencial


class ApiToken(models.Model):
    id_api_token = models.AutoField(primary_key=True)
    api_credencial = models.ForeignKey(
        ApiCredencial,
        on_delete=models.CASCADE,
        related_name="tokens",
        db_column="id_api_credencial",
    )
    access_token_encriptado = models.BinaryField(null=True, blank=True)
    iv_access_token = models.BinaryField(null=True, blank=True)
    refresh_token_encriptado = models.BinaryField(null=True, blank=True)
    iv_refresh_token = models.BinaryField(null=True, blank=True)
    fecha_generacion = models.DateTimeField(default=timezone.now)
    fecha_expiracion = models.DateTimeField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    referencia_clave_cifrado = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        db_table = "api_token"
        managed = False
        verbose_name = "Token API"
        verbose_name_plural = "Tokens API"
        ordering = ("-fecha_generacion",)

    def __str__(self) -> str:
        return f"Token {self.id_api_token} - {self.api_credencial.nombre_aplicacion}"
