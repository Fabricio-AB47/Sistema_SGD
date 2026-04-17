from django.db import models
from django.utils import timezone

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
    fecha_creacion = models.DateTimeField(default=timezone.now)
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

    def set_client_id_plain(self, value: str | None):
        self.client_id = credential_service.encrypt_text_value(value)

    def set_tenant_id_plain(self, value: str | None):
        self.tenant_id = credential_service.encrypt_text_value(value)

    def set_secret_plain(self, value: str):
        encrypted, iv_secret, key_reference = credential_service.encrypt_secret(value)
        self.secret_encriptado = encrypted
        self.iv_secret = iv_secret
        self.referencia_clave_cifrado = key_reference

    def save(self, *args, **kwargs):
        if isinstance(self.client_id, str):
            self.client_id = credential_service.encrypt_text_value(self.client_id)
        if isinstance(self.tenant_id, str):
            self.tenant_id = credential_service.encrypt_text_value(self.tenant_id)
        if isinstance(self.secret_encriptado, str):
            self.set_secret_plain(self.secret_encriptado)
        if self.secret_encriptado and not self.iv_secret:
            raise ValueError("api_credencial requiere `iv_secret` cuando `secret_encriptado` tiene valor.")
        super().save(*args, **kwargs)

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
