from django.db import models

from apps.integraciones.models.api_servicio import ApiServicio
from apps.integraciones.services import credential_service
from apps.usuarios.models import Usuario


class ApiCredencial(models.Model):
    id_api_credencial = models.AutoField(primary_key=True)
    api_servicio = models.ForeignKey(
        ApiServicio,
        on_delete=models.CASCADE,
        related_name="credenciales",
        db_column="id_api_servicio",
    )
    nombre_aplicacion = models.CharField(max_length=150)
    client_id = models.CharField(max_length=200, null=True, blank=True)
    tenant_id = models.CharField(max_length=200, null=True, blank=True)
    secret_encriptado = models.BinaryField()
    iv_secret = models.BinaryField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(null=True, blank=True)
    fecha_expiracion = models.DateTimeField(null=True, blank=True)
    ultimo_uso = models.DateTimeField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        related_name="credenciales_api_creadas",
        null=True,
        blank=True,
        db_column="creado_por",
    )
    referencia_clave_cifrado = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        db_table = "api_credencial"
        managed = False
        verbose_name = "Credencial API"
        verbose_name_plural = "Credenciales API"
        ordering = ("-fecha_creacion",)

    def __str__(self) -> str:
        return f"{self.nombre_aplicacion} - {self.api_servicio.nombre_servicio}"

    @property
    def client_id_plain(self) -> str:
        return credential_service.get_client_id_plain(self)

    @property
    def tenant_id_plain(self) -> str:
        return credential_service.get_tenant_id_plain(self)

    @property
    def client_id_masked(self) -> str:
        return "Protegido" if self.client_id else "--"

    @property
    def tenant_id_masked(self) -> str:
        return "Protegido" if self.tenant_id else "--"
