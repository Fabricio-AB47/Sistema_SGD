from django.db import models

from apps.acreditacion.models import CicloEvaluacion, ElementoFundamental, Indicador
from apps.core.models import EstadoEvaluacion, EstadoTareaEvidencia
from apps.evidencias.models import RegistroEvidencia
from apps.usuarios.models import Usuario


class Evaluacion(models.Model):
    id_evaluacion = models.AutoField(primary_key=True)
    registro = models.ForeignKey(
        RegistroEvidencia,
        on_delete=models.CASCADE,
        related_name="evaluaciones",
        db_column="id_registro",
    )
    usuario_evaluador = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="evaluaciones_realizadas",
        db_column="id_usuario_evaluador",
    )
    estado = models.ForeignKey(
        EstadoEvaluacion,
        on_delete=models.PROTECT,
        related_name="evaluaciones",
        db_column="id_estado_evaluacion",
    )
    fecha_evaluacion = models.DateTimeField(null=True, blank=True)
    calificacion = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    comentario = models.CharField(max_length=1000, null=True, blank=True)
    aprobado = models.BooleanField(default=False)

    class Meta:
        db_table = "evaluacion"
        managed = False
        verbose_name = "Evaluacion"
        verbose_name_plural = "Evaluaciones"
        ordering = ("-fecha_evaluacion",)
        indexes = [
            models.Index(
                fields=["estado", "-fecha_evaluacion"],
                name="ix_evaluacion_estado_fecha",
            )
        ]


class ObservacionEvaluacion(models.Model):
    id_observacion = models.AutoField(primary_key=True)
    evaluacion = models.ForeignKey(
        Evaluacion,
        on_delete=models.CASCADE,
        related_name="observaciones",
        db_column="id_evaluacion",
    )
    observacion = models.CharField(max_length=1000)
    fecha_observacion = models.DateTimeField(null=True, blank=True)
    usuario_emisor = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="observaciones_emitidas",
        db_column="id_usuario_emisor",
    )
    atendida = models.BooleanField(default=False)
    fecha_atendida = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "observacion_evaluacion"
        managed = False
        verbose_name = "Observacion de evaluacion"
        verbose_name_plural = "Observaciones de evaluacion"
        ordering = ("-fecha_observacion",)


class RevisionInternaEvidencia(models.Model):
    RESULTADO_APROBADA = "APROBADA_INTERNA"
    RESULTADO_DEVUELTA = "DEVUELTA_INTERNA"
    RESULTADO_CHOICES = (
        (RESULTADO_APROBADA, "Aprobada interna"),
        (RESULTADO_DEVUELTA, "Devuelta interna"),
    )

    id_revision_interna = models.AutoField(primary_key=True)
    registro = models.ForeignKey(
        RegistroEvidencia,
        on_delete=models.CASCADE,
        related_name="revisiones_internas",
        db_column="id_registro",
    )
    usuario_revisor = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="revisiones_internas",
        db_column="id_usuario_revisor",
    )
    fecha_revision = models.DateTimeField()
    resultado = models.CharField(max_length=30, choices=RESULTADO_CHOICES)
    comentario = models.CharField(max_length=1000, null=True, blank=True)
    enviado_a_evaluador = models.BooleanField(default=False)

    class Meta:
        db_table = "revision_interna_evidencia"
        managed = False
        verbose_name = "Revision interna de evidencia"
        verbose_name_plural = "Revisiones internas de evidencia"
        ordering = ("-fecha_revision", "-id_revision_interna")

    def __str__(self) -> str:
        return f"{self.registro_id} - {self.resultado}"


class TareaEvidencia(models.Model):
    PRIORIDAD_CHOICES = (
        ("BAJA", "Baja"),
        ("MEDIA", "Media"),
        ("ALTA", "Alta"),
        ("CRITICA", "Critica"),
    )

    id_tarea_evidencia = models.AutoField(primary_key=True)
    ciclo = models.ForeignKey(
        CicloEvaluacion,
        on_delete=models.CASCADE,
        related_name="tareas_evidencia",
        db_column="id_ciclo",
    )
    indicador = models.ForeignKey(
        Indicador,
        on_delete=models.CASCADE,
        related_name="tareas_evidencia",
        db_column="id_indicador",
    )
    elemento_fundamental = models.ForeignKey(
        ElementoFundamental,
        on_delete=models.CASCADE,
        related_name="tareas_evidencia",
        db_column="id_elemento_fundamental",
    )
    usuario_responsable = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="tareas_evidencia_responsable",
        db_column="id_usuario_responsable",
    )
    estado = models.ForeignKey(
        EstadoTareaEvidencia,
        on_delete=models.PROTECT,
        related_name="tareas",
        db_column="id_estado_tarea",
    )
    fecha_asignacion = models.DateTimeField(null=True, blank=True)
    fecha_limite = models.DateTimeField(null=True, blank=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    prioridad = models.CharField(
        max_length=20,
        choices=PRIORIDAD_CHOICES,
        null=True,
        blank=True,
    )
    observacion = models.CharField(max_length=1000, null=True, blank=True)
    resultado_tarea = models.CharField(max_length=1000, null=True, blank=True)
    asignado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas_evidencia_asignadas",
        db_column="asignado_por",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "tarea_evidencia"
        managed = False
        verbose_name = "Tarea de evidencia"
        verbose_name_plural = "Tareas de evidencia"
        ordering = ("-fecha_asignacion", "-id_tarea_evidencia")
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "ciclo",
                    "indicador",
                    "elemento_fundamental",
                    "usuario_responsable",
                    "activo",
                ],
                name="uq_tarea_evidencia_operativa",
            )
        ]


class AlertaSeguimientoEvaluacion(models.Model):
    id_alerta = models.AutoField(primary_key=True)
    referencia_tipo = models.CharField(max_length=80)
    referencia_id = models.IntegerField()
    id_user = models.IntegerField(db_index=True)
    correo = models.EmailField(max_length=254)
    asunto = models.CharField(max_length=200)
    plantilla = models.CharField(max_length=100)
    contexto_json = models.TextField(null=True, blank=True)
    numero_envios = models.IntegerField(default=0)
    max_envios = models.IntegerField(default=4)
    intervalo_dias = models.IntegerField(default=2)
    activa = models.BooleanField(default=True, db_index=True)
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_ultimo_envio = models.DateTimeField(null=True, blank=True)
    proximo_envio = models.DateTimeField(null=True, blank=True, db_index=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    motivo_cierre = models.CharField(max_length=200, null=True, blank=True)
    ultimo_error = models.CharField(max_length=1000, null=True, blank=True)

    class Meta:
        db_table = "seguimiento_alerta_evaluacion"
        managed = False
        verbose_name = "Seguimiento de alerta de evaluacion"
        verbose_name_plural = "Seguimientos de alertas de evaluacion"
        ordering = ("proximo_envio", "id_alerta")
        constraints = [
            models.UniqueConstraint(
                fields=["referencia_tipo", "referencia_id", "id_user", "plantilla"],
                name="uq_seguimiento_alerta_eval",
            )
        ]
        indexes = [
            models.Index(
                fields=["activa", "proximo_envio"],
                name="ix_seg_alerta_activa_prox",
            ),
            models.Index(
                fields=["referencia_tipo", "referencia_id"],
                name="ix_seg_alerta_referencia",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.referencia_tipo}:{self.referencia_id} -> {self.correo}"


class EstadoEvidenciasCiclo(models.Model):
    pk = models.CompositePrimaryKey(
        "id_ciclo",
        "id_indicador",
        "id_elemento_fundamental",
        "estado_evidencia",
    )
    id_ciclo = models.IntegerField()
    ciclo = models.CharField(max_length=150)
    id_indicador = models.IntegerField()
    codigo_indicador = models.CharField(max_length=20)
    nombre_indicador = models.CharField(max_length=200)
    id_elemento_fundamental = models.IntegerField()
    codigo_elemento = models.CharField(max_length=20)
    nombre_elemento = models.CharField(max_length=200)
    estado_evidencia = models.CharField(max_length=100)
    total = models.IntegerField()

    class Meta:
        db_table = "vw_estado_evidencias_ciclo"
        managed = False
        verbose_name = "Estado de evidencias por ciclo"
        verbose_name_plural = "Estados de evidencias por ciclo"


class CategoriaValoracionCaces(models.Model):
    id_categoria = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120)
    utilidad = models.DecimalField(max_digits=5, decimal_places=2)
    descripcion = models.CharField(max_length=500, null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "categoria_valoracion_caces"
        managed = False
        verbose_name = "Categoria de valoracion CACES"
        verbose_name_plural = "Categorias de valoracion CACES"
        ordering = ("-utilidad", "nombre")

    def __str__(self) -> str:
        return f"{self.nombre} ({self.utilidad})"


class EscenarioPonderacionCaces(models.Model):
    codigo_escenario = models.CharField(max_length=1, primary_key=True)
    nombre = models.CharField(max_length=120)
    descripcion = models.CharField(max_length=500, null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "escenario_ponderacion_caces"
        managed = False
        verbose_name = "Escenario de ponderacion CACES"
        verbose_name_plural = "Escenarios de ponderacion CACES"
        ordering = ("codigo_escenario",)

    def __str__(self) -> str:
        return f"{self.codigo_escenario} - {self.nombre}"


class ModeloIndicadorCaces(models.Model):
    TIPO_EVALUACION_CHOICES = (
        ("CUALITATIVO", "Cualitativo"),
        ("CUANTITATIVO", "Cuantitativo"),
    )

    id_modelo_indicador = models.AutoField(primary_key=True)
    numero_modelo = models.IntegerField(unique=True)
    codigo_modelo = models.CharField(max_length=20, unique=True)
    criterio = models.CharField(max_length=120)
    subcriterio = models.CharField(max_length=180, null=True, blank=True)
    nombre_indicador = models.CharField(max_length=250)
    tipo_evaluacion = models.CharField(max_length=20, choices=TIPO_EVALUACION_CHOICES)
    ponderacion_a = models.DecimalField(max_digits=10, decimal_places=4)
    ponderacion_b = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    ponderacion_c = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "modelo_indicador_caces"
        managed = False
        verbose_name = "Modelo de indicador CACES"
        verbose_name_plural = "Modelo de indicadores CACES"
        ordering = ("numero_modelo",)

    def __str__(self) -> str:
        return f"{self.codigo_modelo} - {self.nombre_indicador}"


class IndicadorCacesMapeo(models.Model):
    id_mapeo = models.AutoField(primary_key=True)
    indicador = models.OneToOneField(
        Indicador,
        on_delete=models.CASCADE,
        related_name="caces_mapeo",
        db_column="id_indicador",
    )
    modelo = models.OneToOneField(
        ModeloIndicadorCaces,
        on_delete=models.CASCADE,
        related_name="indicador_mapeado",
        db_column="numero_modelo",
        to_field="numero_modelo",
    )
    fecha_mapeo = models.DateTimeField(null=True, blank=True)
    observacion = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        db_table = "indicador_caces_mapeo"
        managed = False
        verbose_name = "Mapeo indicador CACES"
        verbose_name_plural = "Mapeos indicador CACES"
        ordering = ("modelo__numero_modelo",)

    def __str__(self) -> str:
        return f"{self.indicador_id} -> {self.modelo_id}"


class CicloConfiguracionCaces(models.Model):
    ciclo = models.OneToOneField(
        CicloEvaluacion,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="configuracion_caces",
        db_column="id_ciclo",
    )
    escenario = models.ForeignKey(
        EscenarioPonderacionCaces,
        on_delete=models.PROTECT,
        related_name="ciclos_configurados",
        db_column="codigo_escenario",
    )
    observacion = models.CharField(max_length=500, null=True, blank=True)
    fecha_configuracion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ciclo_configuracion_caces"
        managed = False
        verbose_name = "Configuracion CACES de ciclo"
        verbose_name_plural = "Configuraciones CACES de ciclo"


class IndicadorFormulaCaces(models.Model):
    SENTIDO_CALCULO_CHOICES = (
        ("MAYOR_IGUAL", "Mayor o igual"),
        ("MENOR_IGUAL", "Menor o igual"),
    )

    id_formula = models.AutoField(primary_key=True)
    modelo = models.OneToOneField(
        ModeloIndicadorCaces,
        on_delete=models.CASCADE,
        related_name="formula",
        db_column="numero_modelo",
        to_field="numero_modelo",
    )
    codigo_formula = models.CharField(max_length=50, unique=True)
    nombre_formula = models.CharField(max_length=250)
    expresion_formula = models.CharField(max_length=1000)
    estandar = models.DecimalField(max_digits=18, decimal_places=4)
    sentido_calculo = models.CharField(max_length=20, choices=SENTIDO_CALCULO_CHOICES)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "indicador_formula_caces"
        managed = False
        verbose_name = "Formula CACES"
        verbose_name_plural = "Formulas CACES"
        ordering = ("modelo__numero_modelo",)

    def __str__(self) -> str:
        return f"{self.codigo_formula} - {self.nombre_formula}"


class IndicadorFormulaVariableCaces(models.Model):
    id_formula_variable = models.AutoField(primary_key=True)
    formula = models.ForeignKey(
        IndicadorFormulaCaces,
        on_delete=models.CASCADE,
        related_name="variables",
        db_column="codigo_formula",
        to_field="codigo_formula",
    )
    codigo_variable = models.CharField(max_length=50)
    nombre_variable = models.CharField(max_length=250)
    descripcion = models.CharField(max_length=1000, null=True, blank=True)
    obligatorio = models.BooleanField(default=True)

    class Meta:
        db_table = "indicador_formula_variable_caces"
        managed = False
        verbose_name = "Variable de formula CACES"
        verbose_name_plural = "Variables de formula CACES"
        ordering = ("formula_id", "codigo_variable")
        constraints = [
            models.UniqueConstraint(
                fields=["formula", "codigo_variable"],
                name="uq_indicador_formula_variable_caces",
            )
        ]

    def __str__(self) -> str:
        return f"{self.codigo_variable} - {self.nombre_variable}"


class EvaluacionVariableCaces(models.Model):
    id_variable_evaluacion = models.AutoField(primary_key=True)
    ciclo = models.ForeignKey(
        CicloEvaluacion,
        on_delete=models.CASCADE,
        related_name="variables_caces",
        db_column="id_ciclo",
    )
    indicador = models.ForeignKey(
        Indicador,
        on_delete=models.CASCADE,
        related_name="variables_caces",
        db_column="id_indicador",
    )
    codigo_variable = models.CharField(max_length=50)
    nombre_variable = models.CharField(max_length=250)
    valor_variable = models.DecimalField(max_digits=18, decimal_places=4)
    observacion = models.CharField(max_length=500, null=True, blank=True)
    registrado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        related_name="variables_caces_registradas",
        db_column="registrado_por",
        null=True,
        blank=True,
    )
    fecha_registro = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "evaluacion_variable_caces"
        managed = False
        verbose_name = "Variable evaluada CACES"
        verbose_name_plural = "Variables evaluadas CACES"
        ordering = ("ciclo", "indicador", "codigo_variable")
        constraints = [
            models.UniqueConstraint(
                fields=["ciclo", "indicador", "codigo_variable"],
                name="uq_evaluacion_variable_caces",
            )
        ]


class EvaluacionIndicadorCaces(models.Model):
    id_evaluacion_indicador = models.AutoField(primary_key=True)
    ciclo = models.ForeignKey(
        CicloEvaluacion,
        on_delete=models.CASCADE,
        related_name="evaluaciones_indicador_caces",
        db_column="id_ciclo",
    )
    indicador = models.ForeignKey(
        Indicador,
        on_delete=models.CASCADE,
        related_name="evaluaciones_caces",
        db_column="id_indicador",
    )
    numero_modelo = models.IntegerField(null=True, blank=True)
    tipo_evaluacion = models.CharField(max_length=20)
    categoria = models.ForeignKey(
        CategoriaValoracionCaces,
        on_delete=models.PROTECT,
        related_name="evaluaciones_caces",
        db_column="id_categoria",
        null=True,
        blank=True,
    )
    codigo_formula = models.CharField(max_length=50, null=True, blank=True)
    valor_calculado = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    estandar = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    sentido_calculo = models.CharField(max_length=20, null=True, blank=True)
    utilidad = models.DecimalField(max_digits=10, decimal_places=4)
    ponderacion = models.DecimalField(max_digits=10, decimal_places=4)
    aporte = models.DecimalField(max_digits=12, decimal_places=6)
    observacion = models.CharField(max_length=1000, null=True, blank=True)
    calculado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        related_name="evaluaciones_caces_calculadas",
        db_column="calculado_por",
        null=True,
        blank=True,
    )
    fecha_calculo = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "evaluacion_indicador_caces"
        managed = False
        verbose_name = "Evaluacion de indicador CACES"
        verbose_name_plural = "Evaluaciones de indicador CACES"
        ordering = ("-fecha_calculo", "-id_evaluacion_indicador")
        constraints = [
            models.UniqueConstraint(
                fields=["ciclo", "indicador"],
                name="uq_evaluacion_indicador_caces",
            )
        ]
