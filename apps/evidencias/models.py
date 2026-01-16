from django.db import models


class EstadoEvidencia(models.Model):
    id_estado_evidencia = models.AutoField(
        primary_key=True, db_column="id_estado_evidencia"
    )
    descripcion_estado_evidencia = models.CharField(max_length=150)

    class Meta:
        db_table = "estado_evidencia"

    def __str__(self) -> str:
        return self.descripcion_estado_evidencia


class Documento(models.Model):
    id_documento = models.AutoField(primary_key=True, db_column="id_documento")
    descipcion_documento = models.CharField(max_length=500)
    graph_site_id = models.CharField(max_length=200, null=True, blank=True)
    graph_drive_id = models.CharField(max_length=200, null=True, blank=True)
    graph_item_id = models.CharField(max_length=200, null=True, blank=True)
    graph_web_url = models.CharField(max_length=500, null=True, blank=True)
    graph_etag = models.CharField(max_length=200, null=True, blank=True)
    graph_ctag = models.CharField(max_length=200, null=True, blank=True)
    graph_last_modified = models.DateTimeField(null=True, blank=True)
    graph_size = models.BigIntegerField(null=True, blank=True)
    nombre_archivo = models.CharField(max_length=255, null=True, blank=True)
    mime_type = models.CharField(max_length=150, null=True, blank=True)

    class Meta:
        db_table = "documento"

    def __str__(self) -> str:
        return self.nombre_archivo or ""


class RegistroDocumento(models.Model):
    id_registro_documento = models.AutoField(
        primary_key=True, db_column="id_registro_documento"
    )
    registro_asignacion = models.ForeignKey(
        "core.RegistroAsignacion",
        on_delete=models.PROTECT,
        db_column="id_registro_asignacion",
        related_name="documentos",
    )
    documento = models.ForeignKey(
        Documento,
        on_delete=models.PROTECT,
        db_column="id_documento",
        related_name="registros",
    )
    estado_evidencia = models.ForeignKey(
        EstadoEvidencia,
        on_delete=models.PROTECT,
        db_column="id_estado_evidencia",
        related_name="registros_documento",
    )

    class Meta:
        db_table = "registro_documento"


class PlanMejoraDoc(models.Model):
    id_doc_plan_m = models.AutoField(primary_key=True, db_column="id_doc_plan_m")
    plan_actividad = models.ForeignKey(
        "core.PlanMejoraActividad",
        on_delete=models.PROTECT,
        db_column="id_plan_actividad",
        related_name="documentos",
    )
    documento = models.ForeignKey(
        Documento,
        on_delete=models.PROTECT,
        db_column="id_documento",
        related_name="planes_mejora",
    )

    class Meta:
        db_table = "plan_mejora_doc"
