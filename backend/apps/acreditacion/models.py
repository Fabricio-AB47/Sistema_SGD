from django.db import models

from apps.core.models import (
    ClasificacionElementoFundamental as CoreClasificacionElementoFundamental,
    EstadoCiclo,
    TipoIndicador,
)
from apps.usuarios.models import Rol, Usuario


class Criterio(models.Model):
    id_criterio = models.AutoField(primary_key=True)
    codigo_criterio = models.CharField(max_length=20, unique=True)
    nombre_criterio = models.CharField(max_length=150)
    descripcion = models.CharField(max_length=1000, null=True, blank=True)
    orden_visual = models.PositiveIntegerField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "criterio"
        managed = False
        verbose_name = "Criterio"
        verbose_name_plural = "Criterios"
        ordering = ("orden_visual", "codigo_criterio")

    def __str__(self) -> str:
        return f"{self.codigo_criterio} - {self.nombre_criterio}"


class Subcriterio(models.Model):
    id_subcriterio = models.AutoField(primary_key=True)
    criterio = models.ForeignKey(
        Criterio,
        on_delete=models.PROTECT,
        related_name="subcriterios",
        db_column="id_criterio",
    )
    codigo_subcriterio = models.CharField(max_length=20, unique=True)
    nombre_subcriterio = models.CharField(max_length=150)
    descripcion = models.CharField(max_length=1000, null=True, blank=True)
    orden_visual = models.PositiveIntegerField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "subcriterio"
        managed = False
        verbose_name = "Subcriterio"
        verbose_name_plural = "Subcriterios"
        ordering = ("orden_visual", "codigo_subcriterio")

    def __str__(self) -> str:
        return f"{self.codigo_subcriterio} - {self.nombre_subcriterio}"


class Indicador(models.Model):
    id_indicador = models.AutoField(primary_key=True)
    subcriterio = models.ForeignKey(
        Subcriterio,
        on_delete=models.PROTECT,
        related_name="indicadores",
        db_column="id_subcriterio",
    )
    tipo_indicador = models.ForeignKey(
        TipoIndicador,
        on_delete=models.PROTECT,
        related_name="indicadores",
        db_column="id_tipo_ind",
    )
    codigo_indicador = models.CharField(max_length=20, unique=True)
    nombre_indicador = models.CharField(max_length=200)
    descripcion = models.CharField(max_length=2000, null=True, blank=True)
    medio_verificacion = models.CharField(max_length=1000, null=True, blank=True)
    ponderacion = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    orden_visual = models.PositiveIntegerField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "indicador"
        managed = False
        verbose_name = "Indicador"
        verbose_name_plural = "Indicadores"
        ordering = ("orden_visual", "codigo_indicador")

    def __str__(self) -> str:
        return f"{self.codigo_indicador} - {self.nombre_indicador}"


class ClasificacionElementoFundamental(CoreClasificacionElementoFundamental):
    class Meta:
        proxy = True
        app_label = "acreditacion"
        verbose_name = "Clasificacion elemento fundamental"
        verbose_name_plural = "Clasificaciones elemento fundamental"


class ElementoFundamental(models.Model):
    id_elemento_fundamental = models.AutoField(primary_key=True)
    indicador = models.ForeignKey(
        Indicador,
        on_delete=models.PROTECT,
        related_name="elementos",
        db_column="id_indicador",
        null=True,
        blank=True,
    )
    codigo_elemento = models.CharField(max_length=20, unique=True)
    nombre_elemento = models.CharField(max_length=200)
    descripcion = models.CharField(max_length=2000, null=True, blank=True)
    medio_verificacion = models.CharField(max_length=1000, null=True, blank=True)
    orden_visual = models.PositiveIntegerField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "elemento_fundamental"
        managed = False
        verbose_name = "Elemento fundamental"
        verbose_name_plural = "Elementos fundamentales"
        ordering = ("orden_visual", "codigo_elemento")

    def __str__(self) -> str:
        return f"{self.codigo_elemento} - {self.nombre_elemento}"


class IndicadorElementoFundamental(models.Model):
    pk = models.CompositePrimaryKey("indicador", "elemento_fundamental")
    indicador = models.ForeignKey(
        Indicador,
        on_delete=models.CASCADE,
        related_name="elementos_fundamentales",
        db_column="id_indicador",
    )
    elemento_fundamental = models.ForeignKey(
        ElementoFundamental,
        on_delete=models.CASCADE,
        related_name="indicadores",
        db_column="id_elemento_fundamental",
    )

    class Meta:
        db_table = "indicador_elemento_fundamental"
        managed = False
        verbose_name = "Indicador - Elemento fundamental"
        verbose_name_plural = "Indicadores - Elementos fundamentales"


class CicloEvaluacion(models.Model):
    id_ciclo = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=150)
    descripcion = models.CharField(max_length=500, null=True, blank=True)
    anio = models.PositiveIntegerField(null=True, blank=True)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    estado = models.ForeignKey(
        EstadoCiclo,
        on_delete=models.PROTECT,
        related_name="ciclos",
        db_column="id_estado_ciclo",
    )

    class Meta:
        db_table = "ciclo_evaluacion"
        managed = False
        verbose_name = "Ciclo de evaluacion"
        verbose_name_plural = "Ciclos de evaluacion"
        ordering = ("-fecha_inicio",)

    def __str__(self) -> str:
        return self.nombre


class RolIndicador(models.Model):
    id_rol_indicador = models.AutoField(primary_key=True)
    rol = models.ForeignKey(
        Rol,
        on_delete=models.CASCADE,
        related_name="indicadores_asignados",
        db_column="id_rol",
    )
    indicador = models.ForeignKey(
        Indicador,
        on_delete=models.CASCADE,
        related_name="roles_asignados",
        db_column="id_indicador",
    )
    ciclo = models.ForeignKey(
        CicloEvaluacion,
        on_delete=models.CASCADE,
        related_name="roles_indicador",
        db_column="id_ciclo",
    )
    acceso_total = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    fecha_asignacion = models.DateTimeField(null=True, blank=True)
    asignado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roles_indicador_asignados",
        db_column="asignado_por",
    )

    class Meta:
        db_table = "rol_indicador"
        managed = False
        verbose_name = "Rol por indicador"
        verbose_name_plural = "Roles por indicador"
        constraints = [
            models.UniqueConstraint(
                fields=["rol", "indicador", "ciclo"],
                name="uq_rol_indicador",
            )
        ]
        indexes = [
            models.Index(fields=["rol", "ciclo", "activo"], name="ix_rol_indicador_rol_ciclo")
        ]

    def __str__(self) -> str:
        return f"{self.rol} - {self.indicador}"


class RolIndicadorElemento(models.Model):
    pk = models.CompositePrimaryKey("rol_indicador", "elemento_fundamental")
    rol_indicador = models.ForeignKey(
        RolIndicador,
        on_delete=models.CASCADE,
        related_name="elementos_asignados",
        db_column="id_rol_indicador",
    )
    elemento_fundamental = models.ForeignKey(
        ElementoFundamental,
        on_delete=models.CASCADE,
        related_name="roles_indicador",
        db_column="id_elemento_fundamental",
    )
    fecha_asignacion = models.DateTimeField(null=True, blank=True)
    asignado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roles_elemento_asignados",
        db_column="asignado_por",
    )

    class Meta:
        db_table = "rol_indicador_elemento"
        managed = False
        verbose_name = "Rol - Indicador - Elemento"
        verbose_name_plural = "Roles - Indicadores - Elementos"
