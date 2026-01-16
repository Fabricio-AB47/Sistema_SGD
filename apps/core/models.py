from django.db import models


class Responsable(models.Model):
    # Responsable operativo, ligado a un usuario_rol (quién carga evidencias / responde)
    id_responsable = models.AutoField(primary_key=True, db_column="id_responsable")
    descripcion_responsabilidad = models.CharField(max_length=500)
    usuario_rol = models.ForeignKey(
        "seguridad.UsuarioRol",
        on_delete=models.PROTECT,
        db_column="id_user_rol",
        related_name="responsabilidades",
    )

    class Meta:
        db_table = "responsable"

    def __str__(self) -> str:
        return self.descripcion_responsabilidad


class Criterio(models.Model):
    # CACES: nivel superior
    id_criterio = models.AutoField(primary_key=True, db_column="id_criterio")
    nombre_criterio = models.CharField(max_length=150)

    class Meta:
        db_table = "criterio"

    def __str__(self) -> str:
        return self.nombre_criterio


class Subcriterio(models.Model):
    # CACES: subnivel del criterio
    id_subcriterio = models.AutoField(primary_key=True, db_column="id_subcriterio")
    criterio = models.ForeignKey(
        Criterio,
        on_delete=models.PROTECT,
        db_column="id_criterio",
        related_name="subcriterios",
    )
    nombre_subcriterio = models.CharField(max_length=150)

    class Meta:
        db_table = "subcriterio"

    def __str__(self) -> str:
        return self.nombre_subcriterio


class TipoIndicador(models.Model):
    # Catálogo de tipo de indicador (cuantitativo, cualitativo, mixto)
    id_tipo_ind = models.AutoField(primary_key=True, db_column="id_tipo_ind")
    descripcion_tipo_ind = models.CharField(max_length=75)

    class Meta:
        db_table = "tipo_indicador"

    def __str__(self) -> str:
        return self.descripcion_tipo_ind


class Indicador(models.Model):
    # Indicador asociado a un subcriterio y a un tipo
    id_indicador = models.AutoField(primary_key=True, db_column="id_indicador")
    subcriterio = models.ForeignKey(
        Subcriterio,
        on_delete=models.PROTECT,
        db_column="id_subcriterio",
        related_name="indicadores",
    )
    nombre_indicador = models.CharField(max_length=150)
    tipo_ind = models.ForeignKey(
        TipoIndicador,
        on_delete=models.PROTECT,
        db_column="id_tipo_ind",
        related_name="indicadores",
    )

    class Meta:
        db_table = "indicador"

    def __str__(self) -> str:
        return self.nombre_indicador


class CicloEvaluacion(models.Model):
    # Periodo/ciclo de evaluación
    id_ciclo = models.AutoField(primary_key=True, db_column="id_ciclo")
    nombre = models.CharField(max_length=150)
    fecha_in = models.DateTimeField()
    fecha_fin = models.DateTimeField()

    class Meta:
        db_table = "ciclo_evaluacion"

    def __str__(self) -> str:
        return self.nombre


class Activacion(models.Model):
    # Etapa/estado de activación de un indicador dentro del ciclo
    id_activacion = models.AutoField(primary_key=True, db_column="id_activacion")
    descripcion_activacion = models.CharField(max_length=75)

    class Meta:
        db_table = "activacion"

    def __str__(self) -> str:
        return self.descripcion_activacion


class CicloActivacion(models.Model):
    # Vincula indicador + activación + ciclo (qué indicadores están vigentes en qué ciclo y fase)
    id_ciclo_act = models.AutoField(primary_key=True, db_column="id_ciclo_act")
    indicador = models.ForeignKey(
        Indicador,
        on_delete=models.PROTECT,
        db_column="id_indicador",
        related_name="ciclos_activacion",
    )
    activacion = models.ForeignKey(
        Activacion,
        on_delete=models.PROTECT,
        db_column="id_activacion",
        related_name="ciclos_activacion",
    )
    ciclo = models.ForeignKey(
        CicloEvaluacion,
        on_delete=models.PROTECT,
        db_column="id_ciclo",
        related_name="ciclos_activacion",
    )

    class Meta:
        db_table = "ciclo_activacion"


class EstadoIndicador(models.Model):
    # Estado de evaluación del indicador
    id_estado_ind = models.AutoField(primary_key=True, db_column="id_estado_ind")
    descripcion_estado = models.CharField(max_length=75)

    class Meta:
        db_table = "estado_indicador"

    def __str__(self) -> str:
        return self.descripcion_estado


class EstadoAsignacion(models.Model):
    # Estado de asignación (pendiente, en proceso, entregado, etc.)
    id_estado = models.AutoField(primary_key=True, db_column="id_estado")
    descripcion_estado = models.CharField(max_length=75)

    class Meta:
        db_table = "estado_asignacion"

    def __str__(self) -> str:
        return self.descripcion_estado


class RegistroAsignacion(models.Model):
    # Expediente de asignación de un indicador a un responsable dentro de un ciclo/activación
    id_registro_asignacion = models.AutoField(
        primary_key=True, db_column="id_registro_asignacion"
    )
    responsable = models.ForeignKey(
        Responsable,
        on_delete=models.PROTECT,
        db_column="id_responsable",
        related_name="registros_asignacion",
    )
    fecha_asignacion = models.DateTimeField()
    fecha_maxima = models.DateTimeField()
    argumentacion = models.CharField(max_length=500)
    observacion = models.CharField(max_length=500, null=True, blank=True)
    estado = models.ForeignKey(
        EstadoAsignacion,
        on_delete=models.PROTECT,
        db_column="id_estado",
        related_name="registros_asignacion",
    )
    estado_indicador = models.ForeignKey(
        EstadoIndicador,
        on_delete=models.PROTECT,
        db_column="id_estado_ind",
        related_name="registros_asignacion",
    )
    ciclo_activacion = models.ForeignKey(
        CicloActivacion,
        on_delete=models.PROTECT,
        db_column="id_ciclo_act",
        related_name="registros_asignacion",
    )

    class Meta:
        db_table = "registro_asignacion"

    def __str__(self) -> str:
        return f"Asignacion {self.id_registro_asignacion}"


class Evaluacion(models.Model):
    # Resultado de la evaluación (cuantitativa/cualitativa) de una asignación
    id_evaluacion = models.AutoField(primary_key=True, db_column="id_evaluacion")
    registro_asignacion = models.ForeignKey(
        RegistroAsignacion,
        on_delete=models.PROTECT,
        db_column="id_registro_asignacion",
        related_name="evaluaciones",
    )
    calificacion_cuantitativa = models.IntegerField()
    calificacion_cualitativa = models.IntegerField()

    class Meta:
        db_table = "evaluacion"


class EstadoMejora(models.Model):
    # Estado del plan/actividad de mejora
    id_estado_mejora = models.AutoField(primary_key=True, db_column="id_estado_mejora")
    descipcion_estado_mejora = models.CharField(max_length=75)

    class Meta:
        db_table = "estado_mejora"

    def __str__(self) -> str:
        return self.descipcion_estado_mejora


class PlanMejora(models.Model):
    # Plan de mejora ligado a evaluación y responsable
    id_plan_mejora = models.AutoField(primary_key=True, db_column="id_plan_mejora")
    evaluacion = models.ForeignKey(
        Evaluacion,
        on_delete=models.PROTECT,
        db_column="id_evaluacion",
        related_name="planes_mejora",
    )
    estandar = models.CharField(max_length=150, null=True, blank=True)
    linea_base = models.CharField(max_length=250, null=True, blank=True)
    meta = models.CharField(max_length=250, null=True, blank=True)
    aspectos_mejora = models.CharField(max_length=250, null=True, blank=True)
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    presupuesto = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    medios_verificacion = models.CharField(max_length=500, null=True, blank=True)
    responsable = models.ForeignKey(
        Responsable,
        on_delete=models.PROTECT,
        db_column="id_responsable",
        related_name="planes_mejora",
    )

    class Meta:
        db_table = "plan_mejora"


class PlanMejoraActividad(models.Model):
    # Actividades del plan de mejora, con estado y avance
    id_plan_actividad = models.AutoField(
        primary_key=True, db_column="id_plan_actividad"
    )
    plan_mejora = models.ForeignKey(
        PlanMejora,
        on_delete=models.PROTECT,
        db_column="id_plan_mejora",
        related_name="actividades",
    )
    descripcion = models.CharField(max_length=500)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    estado_mejora = models.ForeignKey(
        EstadoMejora,
        on_delete=models.PROTECT,
        db_column="id_estado_mejora",
        related_name="actividades",
    )
    avance = models.IntegerField()

    class Meta:
        db_table = "plan_mejora_actividad"


class Notificaciones(models.Model):
    # Notificaciones ligadas a un registro de asignación
    id_notificaciones = models.AutoField(
        primary_key=True, db_column="id_notificaciones"
    )
    registro_asignacion = models.ForeignKey(
        RegistroAsignacion,
        on_delete=models.PROTECT,
        db_column="id_registro_asignacion",
        related_name="notificaciones",
    )
    detalle_notificiacion = models.CharField(max_length=500)

    class Meta:
        db_table = "notificaciones"


class Auditoria(models.Model):
    # Trazabilidad/auditoría de acciones sobre tablas y registros
    id_auditoria = models.AutoField(primary_key=True, db_column="id_auditoria")
    usuario = models.ForeignKey(
        "seguridad.Usuario",
        on_delete=models.PROTECT,
        db_column="id_usuario",
        related_name="auditorias",
    )
    accion = models.CharField(max_length=150)
    tabla_afectada = models.CharField(max_length=150)
    id_registro = models.IntegerField(null=True, blank=True)
    descripcion = models.CharField(max_length=500)
    valores_nuevos = models.CharField(max_length=500, null=True, blank=True)
    valores_anteriores = models.CharField(
        max_length=500, null=True, blank=True, db_column="valores_anteriores"
    )
    fecha_evento = models.DateTimeField()
    ip = models.CharField(max_length=50, null=True, blank=True)
    user_agent = models.CharField(max_length=300, null=True, blank=True)

    class Meta:
        db_table = "auditoria"
