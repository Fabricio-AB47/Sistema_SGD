from django.db import models

from apps.acreditacion.models import CicloEvaluacion, ElementoFundamental, Indicador
from apps.core.models import ClasificacionDocumento, EstadoEvidencia
from apps.usuarios.models import Usuario


class Documento(models.Model):
    id_documento = models.AutoField(primary_key=True)
    descripcion_documento = models.CharField(max_length=500, null=True, blank=True)
    nombre_archivo = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=150, null=True, blank=True)
    extension_archivo = models.CharField(max_length=15, null=True, blank=True)
    tamano_archivo = models.BigIntegerField(null=True, blank=True)
    ruta_local = models.CharField(max_length=500, null=True, blank=True)
    hash_documento = models.CharField(max_length=128, unique=True)
    checksum_archivo = models.CharField(max_length=128, null=True, blank=True)
    clasificacion = models.ForeignKey(
        ClasificacionDocumento,
        on_delete=models.PROTECT,
        related_name="documentos",
        db_column="id_clasificacion_documento",
    )
    esta_cifrado = models.BooleanField(default=True)
    algoritmo_cifrado = models.CharField(max_length=50, null=True, blank=True)
    referencia_clave_cifrado = models.CharField(max_length=200, null=True, blank=True)
    graph_site_id = models.CharField(max_length=200, null=True, blank=True)
    graph_drive_id = models.CharField(max_length=200, null=True, blank=True)
    graph_item_id = models.CharField(max_length=200, null=True, blank=True)
    graph_web_url = models.CharField(max_length=500, null=True, blank=True)
    graph_etag = models.CharField(max_length=200, null=True, blank=True)
    graph_ctag = models.CharField(max_length=200, null=True, blank=True)
    graph_last_modified = models.DateTimeField(null=True, blank=True)
    graph_size = models.BigIntegerField(null=True, blank=True)
    fecha_subida = models.DateTimeField(null=True, blank=True)
    subido_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documentos_subidos",
        db_column="subido_por",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "documento"
        managed = False
        verbose_name = "Documento"
        verbose_name_plural = "Documentos"
        ordering = ("-fecha_subida", "nombre_archivo")
        indexes = [
            models.Index(fields=["graph_item_id"], name="ix_documento_graph_item"),
            models.Index(
                fields=["clasificacion", "-fecha_subida"],
                name="ix_doc_clasif_fecha",
            ),
        ]

    def __str__(self) -> str:
        return self.nombre_archivo


class VersionDocumento(models.Model):
    id_version = models.AutoField(primary_key=True)
    documento = models.ForeignKey(
        Documento,
        on_delete=models.CASCADE,
        related_name="versiones",
        db_column="id_documento",
    )
    numero_version = models.PositiveIntegerField()
    descripcion_cambio = models.CharField(max_length=500, null=True, blank=True)
    fecha_version = models.DateTimeField(null=True, blank=True)
    subido_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="versiones_subidas",
        db_column="subido_por",
    )
    graph_item_id = models.CharField(max_length=200, null=True, blank=True)
    ruta_local = models.CharField(max_length=500, null=True, blank=True)
    hash_documento = models.CharField(max_length=128)
    checksum_archivo = models.CharField(max_length=128, null=True, blank=True)
    esta_cifrado = models.BooleanField(default=True)
    algoritmo_cifrado = models.CharField(max_length=50, null=True, blank=True)
    referencia_clave_cifrado = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        db_table = "version_documento"
        managed = False
        verbose_name = "Version de documento"
        verbose_name_plural = "Versiones de documento"
        constraints = [
            models.UniqueConstraint(
                fields=["documento", "numero_version"],
                name="uq_version_documento",
            )
        ]
        ordering = ("-fecha_version",)

    def __str__(self) -> str:
        return f"{self.documento_id} v{self.numero_version}"


class RegistroEvidencia(models.Model):
    id_registro = models.AutoField(primary_key=True)
    documento = models.ForeignKey(
        Documento,
        on_delete=models.CASCADE,
        related_name="registros_evidencia",
        db_column="id_documento",
    )
    elemento_fundamental = models.ForeignKey(
        ElementoFundamental,
        on_delete=models.PROTECT,
        related_name="registros_evidencia",
        db_column="id_elemento_fundamental",
    )
    indicador = models.ForeignKey(
        Indicador,
        on_delete=models.PROTECT,
        related_name="registros_evidencia",
        null=True,
        blank=True,
        db_column="id_indicador",
    )
    ciclo = models.ForeignKey(
        CicloEvaluacion,
        on_delete=models.PROTECT,
        related_name="registros_evidencia",
        db_column="id_ciclo",
    )
    estado = models.ForeignKey(
        EstadoEvidencia,
        on_delete=models.PROTECT,
        related_name="registros_evidencia",
        db_column="id_estado_evidencia",
    )
    fecha_registro = models.DateTimeField(null=True, blank=True)
    registrado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="evidencias_registradas",
        db_column="registrado_por",
    )
    comentario = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        db_table = "registro_evidencia"
        managed = False
        verbose_name = "Registro de evidencia"
        verbose_name_plural = "Registros de evidencia"
        constraints = [
            models.UniqueConstraint(
                fields=["documento", "elemento_fundamental", "ciclo"],
                name="uq_registro_evidencia",
            )
        ]
        indexes = [
            models.Index(
                fields=["elemento_fundamental", "ciclo"],
                name="ix_reg_ev_elem_ciclo",
            ),
            models.Index(
                fields=["indicador", "ciclo"],
                name="ix_reg_ev_ind_ciclo",
            ),
        ]


class DocumentoAccesoLog(models.Model):
    id_documento_acceso_log = models.BigAutoField(primary_key=True)
    documento = models.ForeignKey(
        Documento,
        on_delete=models.CASCADE,
        related_name="logs_acceso",
        db_column="id_documento",
    )
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs_documento",
        db_column="id_user",
    )
    accion = models.CharField(max_length=50)
    fecha_evento = models.DateTimeField(null=True, blank=True)
    ip = models.CharField(max_length=45, null=True, blank=True)
    user_agent = models.CharField(max_length=300, null=True, blank=True)
    resultado = models.CharField(max_length=50, null=True, blank=True)
    detalle = models.CharField(max_length=1000, null=True, blank=True)

    class Meta:
        db_table = "documento_acceso_log"
        managed = False
        verbose_name = "Log de acceso a documento"
        verbose_name_plural = "Logs de acceso a documentos"
        ordering = ("-fecha_evento",)
        indexes = [
            models.Index(
                fields=["documento", "-fecha_evento"],
                name="ix_doc_acc_doc_fecha",
            )
        ]
