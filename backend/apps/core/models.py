from django.db import models


class TimeStampedModel(models.Model):
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("-creado_en",)


class TipoIdentificacion(models.Model):
    id_tipo_identificacion = models.AutoField(primary_key=True)
    descripcion = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tipo_identificacion"
        managed = False
        verbose_name = "Tipo de identificacion"
        verbose_name_plural = "Tipos de identificacion"
        ordering = ("descripcion",)

    def __str__(self) -> str:
        return self.descripcion


class EstadoEvaluacion(models.Model):
    id_estado_evaluacion = models.AutoField(primary_key=True)
    descripcion = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "estado_evaluacion"
        managed = False
        verbose_name = "Estado de evaluacion"
        verbose_name_plural = "Estados de evaluacion"
        ordering = ("descripcion",)

    def __str__(self) -> str:
        return self.descripcion


class EstadoEvidencia(models.Model):
    id_estado_evidencia = models.AutoField(primary_key=True)
    descripcion = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "estado_evidencia"
        managed = False
        verbose_name = "Estado de evidencia"
        verbose_name_plural = "Estados de evidencia"
        ordering = ("descripcion",)

    def __str__(self) -> str:
        return self.descripcion


class EstadoPlanMejora(models.Model):
    id_estado_plan_mejora = models.AutoField(primary_key=True)
    descripcion = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "estado_plan_mejora"
        managed = False
        verbose_name = "Estado de plan de mejora"
        verbose_name_plural = "Estados de plan de mejora"
        ordering = ("descripcion",)

    def __str__(self) -> str:
        return self.descripcion


class EstadoCiclo(models.Model):
    id_estado_ciclo = models.AutoField(primary_key=True)
    descripcion = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "estado_ciclo"
        managed = False
        verbose_name = "Estado de ciclo"
        verbose_name_plural = "Estados de ciclo"
        ordering = ("descripcion",)

    def __str__(self) -> str:
        return self.descripcion


class EstadoInforme(models.Model):
    id_estado_informe = models.AutoField(primary_key=True)
    descripcion = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "estado_informe"
        managed = False
        verbose_name = "Estado de informe"
        verbose_name_plural = "Estados de informe"
        ordering = ("descripcion",)

    def __str__(self) -> str:
        return self.descripcion


class TipoIndicador(models.Model):
    id_tipo_ind = models.AutoField(primary_key=True)
    descripcion = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "tipo_indicador"
        managed = False
        verbose_name = "Tipo de indicador"
        verbose_name_plural = "Tipos de indicador"
        ordering = ("descripcion",)

    def __str__(self) -> str:
        return self.descripcion


class ClasificacionElementoFundamental(models.Model):
    id_clasificacion = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "clasificacion_elemento_fundamental"
        managed = False
        verbose_name = "Clasificacion de elemento fundamental"
        verbose_name_plural = "Clasificaciones de elemento fundamental"
        ordering = ("codigo",)

    def __str__(self) -> str:
        return f"{self.codigo} - {self.nombre}"


class ClasificacionDocumento(models.Model):
    NIVEL_CHOICES = (
        ("PUBLICO", "Publico"),
        ("INTERNO", "Interno"),
        ("CONFIDENCIAL", "Confidencial"),
        ("RESTRINGIDO", "Restringido"),
    )

    id_clasificacion_documento = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=120)
    nivel_confidencialidad = models.CharField(max_length=30, choices=NIVEL_CHOICES)
    requiere_cifrado = models.BooleanField(default=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "clasificacion_documento"
        managed = False
        verbose_name = "Clasificacion de documento"
        verbose_name_plural = "Clasificaciones de documento"
        ordering = ("codigo",)

    def __str__(self) -> str:
        return f"{self.codigo} - {self.nombre}"
