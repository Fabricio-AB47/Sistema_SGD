from django.db import models

from apps.usuarios.models import Usuario


class Auditoria(models.Model):
    id_auditoria = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auditorias",
        db_column="id_usuario",
    )
    tipo_evento = models.CharField(max_length=50, null=True, blank=True)
    accion = models.CharField(max_length=150)
    tabla_afectada = models.CharField(max_length=150, null=True, blank=True)
    id_registro = models.BigIntegerField(null=True, blank=True)
    descripcion = models.CharField(max_length=1000)
    valores_nuevos = models.TextField(null=True, blank=True)
    valores_anteriores = models.TextField(null=True, blank=True)
    fecha_evento = models.DateTimeField(null=True, blank=True)
    ip = models.CharField(max_length=50, null=True, blank=True)
    user_agent = models.CharField(max_length=300, null=True, blank=True)
    criticidad = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        db_table = "auditoria"
        managed = False
        verbose_name = "Auditoria"
        verbose_name_plural = "Auditoria"
        ordering = ("-fecha_evento",)
        indexes = [
            models.Index(fields=["-fecha_evento", "tabla_afectada"], name="ix_auditoria_fecha_tabla")
        ]

    def __str__(self) -> str:
        return f"{self.accion} - {self.fecha_evento:%d/%m/%Y %H:%M}" if self.fecha_evento else self.accion
