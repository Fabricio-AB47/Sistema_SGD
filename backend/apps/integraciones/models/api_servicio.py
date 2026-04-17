from django.db import models
from django.utils import timezone


class ApiServicio(models.Model):
    id_api_servicio = models.AutoField(primary_key=True)
    nombre_servicio = models.CharField(max_length=150)
    proveedor = models.CharField(max_length=150)
    descripcion = models.CharField(max_length=500, null=True, blank=True)
    url_base = models.CharField(max_length=500, null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "api_servicio"
        managed = False
        verbose_name = "Servicio API"
        verbose_name_plural = "Servicios API"
        ordering = ("nombre_servicio", "proveedor")
        constraints = [
            models.UniqueConstraint(
                fields=["nombre_servicio", "proveedor"],
                name="uq_api_servicio",
            )
        ]

    def __str__(self) -> str:
        return f"{self.nombre_servicio} ({self.proveedor})"
