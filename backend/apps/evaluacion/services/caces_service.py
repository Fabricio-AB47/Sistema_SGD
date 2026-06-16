from __future__ import annotations

import ast
import operator
import re
from decimal import Decimal, DivisionByZero, InvalidOperation

from django.utils import timezone
from django.db import DatabaseError, connection, transaction

from apps.acreditacion.models import Indicador
from apps.auditoria.services.auditoria_service import registrar_evento
from apps.core.models import EstadoCiclo
from apps.evaluacion.models import (
    CategoriaValoracionCaces,
    CicloConfiguracionCaces,
    EscenarioPonderacionCaces,
    EvaluacionIndicadorCaces,
    EvaluacionVariableCaces,
    IndicadorCacesMapeo,
    IndicadorFormulaCaces,
)
from apps.evaluacion.selectors.caces_selector import (
    QUANTITATIVE_TYPE,
    get_caces_indicator_matrix,
    get_caces_indicator_result,
    get_caces_required_variables,
)


class CacesEvaluationError(Exception):
    pass


PROC_GUARDAR_CUALITATIVA = "dbo.sp_caces_guardar_evaluacion_cualitativa"
PROC_GUARDAR_VARIABLE = "dbo.sp_caces_guardar_variable_cuantitativa"
PROC_CALCULAR_CUANTITATIVA = "dbo.sp_caces_calcular_evaluacion_cuantitativa"
PROC_GUARDAR_CUANTITATIVA_MANUAL = "dbo.sp_caces_guardar_evaluacion_cuantitativa_manual"

SQL_REFERENCES = {
    "categorias": "SELECT * FROM dbo.categoria_valoracion_caces WHERE activo = 1 ORDER BY utilidad DESC;",
    "variables_formula": (
        "SELECT v.* FROM dbo.indicador_formula_variable_caces v "
        "INNER JOIN dbo.indicador_formula_caces f ON f.codigo_formula = v.codigo_formula "
        "WHERE f.numero_modelo = @numero_modelo;"
    ),
    "resultado_indicador": "SELECT * FROM dbo.vw_caces_resultado_indicador WHERE id_ciclo = @id_ciclo AND id_indicador = @id_indicador;",
    "resultado_ciclo": "SELECT * FROM dbo.vw_caces_resultado_ciclo WHERE id_ciclo = @id_ciclo;",
    "cobertura": "SELECT * FROM dbo.vw_caces_cobertura_evidencias_indicador WHERE id_ciclo = @id_ciclo;",
}

FINALIZATION_CYCLE_STATES = (
    "EN_FINALIZACION",
    "EN PROCESO DE FINALIZACION",
    "FINALIZACION",
    "CERRADO",
    "FINALIZADO",
    "FINALIZADA",
)
DECIMAL_FOUR_PLACES = Decimal("0.0001")
DECIMAL_SIX_PLACES = Decimal("0.000001")
ALLOWED_FORMULA_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().split())
    return normalized or None


def _normalize_code(value: str | None) -> str:
    return " ".join((value or "").strip().upper().split())


def _normalize_state(value: str | None) -> str:
    return _normalize_code(value).replace(" ", "_")


def _coerce_positive_int(value, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CacesEvaluationError(f"{field_name} debe ser un entero valido.") from exc
    if parsed <= 0:
        raise CacesEvaluationError(f"{field_name} debe ser mayor a cero.")
    return parsed


def _coerce_decimal(value, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception as exc:
        raise CacesEvaluationError(f"{field_name} debe ser numerico.") from exc
    return parsed


def _first_present(mapping: dict, *keys):
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _ensure_indicator_active(indicador_id):
    indicador_pk = _coerce_positive_int(indicador_id, "id_indicador")
    indicador = (
        Indicador.objects.select_related("subcriterio__criterio", "tipo_indicador")
        .filter(pk=indicador_pk)
        .first()
    )
    if indicador is None:
        raise CacesEvaluationError("El indicador seleccionado no existe.")
    if not indicador.activo:
        raise CacesEvaluationError("No se permite evaluar un indicador inactivo.")
    return indicador


def _ensure_mapping(indicador):
    return (
        IndicadorCacesMapeo.objects.select_related("modelo")
        .filter(indicador_id=indicador.pk)
        .first()
    )


def _evaluation_type_for_indicator(indicador, mapping) -> str:
    if mapping is not None:
        return _normalize_code(mapping.modelo.tipo_evaluacion)
    return _normalize_code(
        getattr(getattr(indicador, "tipo_indicador", None), "descripcion", "")
    )


def _ensure_active_scenario(codigo_escenario):
    scenario_code = _normalize_code(codigo_escenario) or "A"
    escenario = EscenarioPonderacionCaces.objects.filter(
        pk=scenario_code,
        activo=True,
    ).first()
    if escenario is None:
        raise CacesEvaluationError("El escenario de ponderacion CACES seleccionado no existe o esta inactivo.")
    return escenario


def _validate_unit_interval(value, field_name: str):
    decimal = _coerce_decimal(value, field_name)
    if decimal < 0 or decimal > 1:
        raise CacesEvaluationError(f"{field_name} debe estar entre 0 y 1.")
    return decimal


def _get_proc_parameters(proc_name: str):
    if not re.match(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$", proc_name):
        raise CacesEvaluationError("Nombre de procedimiento no permitido.")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT LOWER(REPLACE(name, '@', '')) AS parameter_name
            FROM sys.parameters
            WHERE object_id = OBJECT_ID(%s)
              AND is_output = 0
            ORDER BY parameter_id
            """,
            [proc_name],
        )
        return [row[0] for row in cursor.fetchall()]


def _execute_stored_procedure(proc_name: str, values_by_parameter: dict):
    parameters = _get_proc_parameters(proc_name)
    if not parameters:
        return False

    assignments = []
    values = []
    for parameter in parameters:
        if parameter not in values_by_parameter:
            continue
        assignments.append(f"@{parameter} = %s")
        values.append(values_by_parameter[parameter])

    if not assignments:
        raise CacesEvaluationError(
            f"No se pudo mapear ningun parametro para {proc_name}."
        )

    sql = f"EXEC {proc_name} {', '.join(assignments)}"
    with connection.cursor() as cursor:
        cursor.execute(sql, values)
    return True


def _quantize(value, places: Decimal) -> Decimal:
    return _coerce_decimal(value, "valor").quantize(places)


def _selected_scenario_code(ciclo_id) -> str:
    config = CicloConfiguracionCaces.objects.filter(ciclo_id=ciclo_id).first()
    if config and config.escenario_id:
        return str(config.escenario_id).upper()
    return "A"


def _normalize_weight(value, field_name: str) -> Decimal:
    weight = _coerce_decimal(value or 0, field_name)
    if weight > 1 and weight <= 100:
        weight = weight / Decimal("100")
    return _validate_unit_interval(weight, field_name)


def _weight_for_indicator(indicador) -> Decimal:
    for field_name, value in (
        ("ponderacion", getattr(indicador, "ponderacion", None)),
        ("ponderacion_subcriterio", getattr(getattr(indicador, "subcriterio", None), "ponderacion", None)),
        (
            "ponderacion_criterio",
            getattr(getattr(getattr(indicador, "subcriterio", None), "criterio", None), "ponderacion", None),
        ),
    ):
        weight = _normalize_weight(value, field_name)
        if weight > 0:
            return weight
    return Decimal("0")


def _weight_for_mapping(mapping, ciclo_id, *, indicador=None) -> Decimal:
    if mapping is None:
        return _weight_for_indicator(indicador)
    field_name = {
        "A": "ponderacion_a",
        "B": "ponderacion_b",
        "C": "ponderacion_c",
    }.get(_selected_scenario_code(ciclo_id), "ponderacion_a")
    weight = getattr(mapping.modelo, field_name, None)
    if weight is None:
        weight = getattr(mapping.modelo, "ponderacion_a", None)
    return _normalize_weight(weight, "ponderacion")


def _clamp_unit_interval(value) -> Decimal:
    decimal = _coerce_decimal(value, "utilidad")
    if decimal < 0:
        return Decimal("0")
    if decimal > 1:
        return Decimal("1")
    return decimal


def _active_formula_for_mapping(mapping):
    if mapping is None:
        raise CacesEvaluationError(
            "El indicador no tiene formula CACES; usa la evaluacion cuantitativa manual general."
        )
    formula = IndicadorFormulaCaces.objects.filter(
        modelo_id=mapping.modelo.numero_modelo,
        activo=True,
    ).first()
    if formula is None:
        raise CacesEvaluationError("El indicador CACES no tiene formula cuantitativa configurada.")
    return formula


def _formula_body(expression: str | None) -> str:
    body = (expression or "").strip()
    if "=" in body:
        body = body.split("=", 1)[1].strip()
    if not body:
        raise CacesEvaluationError("La formula CACES no tiene expresion de calculo.")
    return body


def _evaluate_formula_node(node, values_by_code: dict[str, Decimal]) -> Decimal:
    if isinstance(node, ast.Expression):
        return _evaluate_formula_node(node.body, values_by_code)
    if isinstance(node, ast.BinOp):
        operator_fn = ALLOWED_FORMULA_OPERATORS.get(type(node.op))
        if operator_fn is None:
            raise CacesEvaluationError("La formula CACES contiene un operador no permitido.")
        left = _evaluate_formula_node(node.left, values_by_code)
        right = _evaluate_formula_node(node.right, values_by_code)
        try:
            return operator_fn(left, right)
        except (DivisionByZero, InvalidOperation, ZeroDivisionError) as exc:
            raise CacesEvaluationError("No se puede calcular: la formula divide para cero.") from exc
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate_formula_node(node.operand, values_by_code)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.Name):
        code = _normalize_code(node.id)
        if code not in values_by_code:
            raise CacesEvaluationError(f"No se encontro valor para la variable {node.id}.")
        return values_by_code[code]
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value))
    if hasattr(ast, "Num") and isinstance(node, ast.Num):
        return Decimal(str(node.n))
    raise CacesEvaluationError("La formula CACES contiene una expresion no permitida.")


def _evaluate_formula(expression: str | None, values_by_code: dict[str, Decimal]) -> Decimal:
    try:
        parsed = ast.parse(_formula_body(expression), mode="eval")
    except SyntaxError as exc:
        raise CacesEvaluationError("La formula CACES no tiene sintaxis valida.") from exc
    return _evaluate_formula_node(parsed, values_by_code)


def _utility_from_quantitative_value(value, formula) -> Decimal:
    calculated = _coerce_decimal(value, "valor_calculado")
    if calculated < 0:
        calculated = Decimal("0")
    standard = _coerce_decimal(formula.estandar, "estandar")
    if standard <= 0:
        raise CacesEvaluationError("El estandar de la formula CACES debe ser mayor a cero.")

    sentido = _normalize_code(formula.sentido_calculo)
    if sentido == "MENOR_IGUAL":
        utility = Decimal("1") if calculated <= standard else standard / calculated
    else:
        utility = calculated / standard
    return _clamp_unit_interval(utility).quantize(DECIMAL_FOUR_PLACES)


def _utility_from_general_score(value) -> Decimal:
    score = _coerce_decimal(value, "calificacion_general")
    if score < 0 or score > 100:
        raise CacesEvaluationError("La calificacion general debe estar entre 0 y 100.")
    return (score / Decimal("100")).quantize(DECIMAL_FOUR_PLACES)


def _store_indicator_evaluation(
    *,
    ciclo_id,
    indicador,
    mapping,
    tipo_evaluacion,
    utilidad,
    ponderacion,
    actor,
    observacion=None,
    categoria=None,
    formula=None,
    valor_calculado=None,
):
    utility = _validate_unit_interval(utilidad, "utilidad").quantize(DECIMAL_FOUR_PLACES)
    weight = _validate_unit_interval(ponderacion, "ponderacion").quantize(DECIMAL_FOUR_PLACES)
    contribution = (utility * weight).quantize(DECIMAL_SIX_PLACES)
    defaults = {
        "numero_modelo": mapping.modelo.numero_modelo if mapping is not None else None,
        "tipo_evaluacion": tipo_evaluacion,
        "categoria": categoria,
        "codigo_formula": getattr(formula, "codigo_formula", None),
        "valor_calculado": _quantize(valor_calculado, DECIMAL_FOUR_PLACES)
        if valor_calculado is not None
        else None,
        "estandar": getattr(formula, "estandar", None),
        "sentido_calculo": getattr(formula, "sentido_calculo", None),
        "utilidad": utility,
        "ponderacion": weight,
        "aporte": contribution,
        "observacion": observacion,
        "calculado_por": actor,
        "fecha_calculo": timezone.now(),
    }
    evaluation, _created = EvaluacionIndicadorCaces.objects.update_or_create(
        ciclo_id=ciclo_id,
        indicador_id=indicador.pk,
        defaults=defaults,
    )
    return evaluation


def _store_qualitative_evaluation(*, ciclo_id, indicador, mapping, categoria, observacion, actor, utilidad=None):
    return _store_indicator_evaluation(
        ciclo_id=ciclo_id,
        indicador=indicador,
        mapping=mapping,
        tipo_evaluacion="CUALITATIVO",
        categoria=categoria,
        utilidad=utilidad if utilidad is not None else categoria.utilidad,
        ponderacion=_weight_for_mapping(mapping, ciclo_id, indicador=indicador),
        observacion=observacion,
        actor=actor,
    )


def _store_quantitative_variable(*, ciclo_id, indicador, variable, value, observacion, actor):
    EvaluacionVariableCaces.objects.update_or_create(
        ciclo_id=ciclo_id,
        indicador_id=indicador.pk,
        codigo_variable=variable.codigo_variable,
        defaults={
            "nombre_variable": variable.nombre_variable,
            "valor_variable": _quantize(value, DECIMAL_FOUR_PLACES),
            "observacion": observacion,
            "registrado_por": actor,
            "fecha_registro": timezone.now(),
        },
    )


def _stored_formula_values(*, ciclo_id, indicador) -> dict[str, Decimal]:
    values = {}
    for item in EvaluacionVariableCaces.objects.filter(
        ciclo_id=ciclo_id,
        indicador_id=indicador.pk,
    ):
        values[_normalize_code(item.codigo_variable)] = _coerce_decimal(
            item.valor_variable,
            item.codigo_variable,
        )
    return values


def _calculate_and_store_quantitative(*, ciclo_id, indicador, mapping, observacion, actor, manual_value=None):
    formula = _active_formula_for_mapping(mapping) if mapping is not None else None
    if manual_value is not None:
        value = _coerce_decimal(manual_value, "valor_calculado")
    else:
        if formula is None:
            raise CacesEvaluationError(
                "El indicador no tiene formula CACES; usa la evaluacion cuantitativa manual general."
            )
        value = _evaluate_formula(
            formula.expresion_formula,
            _stored_formula_values(ciclo_id=ciclo_id, indicador=indicador),
        )
    utility = (
        _utility_from_quantitative_value(value, formula)
        if formula is not None
        else _utility_from_general_score(value)
    )
    return _store_indicator_evaluation(
        ciclo_id=ciclo_id,
        indicador=indicador,
        mapping=mapping,
        tipo_evaluacion=QUANTITATIVE_TYPE,
        formula=formula,
        valor_calculado=value,
        utilidad=utility,
        ponderacion=_weight_for_mapping(mapping, ciclo_id, indicador=indicador),
        observacion=observacion,
        actor=actor,
    )


def _parameter_aliases(**values):
    actor_id = values.get("actor_id")
    id_ciclo = values.get("id_ciclo")
    id_indicador = values.get("id_indicador")
    id_categoria = values.get("id_categoria")
    codigo_categoria = values.get("codigo_categoria")
    codigo_variable = values.get("codigo_variable")
    nombre_variable = values.get("nombre_variable")
    valor_variable = values.get("valor_variable")
    valor_calculado = values.get("valor_calculado")
    utilidad = values.get("utilidad")
    observacion = values.get("observacion")
    return {
        "id_ciclo": id_ciclo,
        "ciclo_id": id_ciclo,
        "p_id_ciclo": id_ciclo,
        "id_indicador": id_indicador,
        "indicador_id": id_indicador,
        "p_id_indicador": id_indicador,
        "id_categoria": id_categoria,
        "categoria_id": id_categoria,
        "p_id_categoria": id_categoria,
        "codigo_categoria": codigo_categoria,
        "categoria_codigo": codigo_categoria,
        "codigo_valoracion": codigo_categoria,
        "p_codigo_categoria": codigo_categoria,
        "codigo_variable": codigo_variable,
        "variable_codigo": codigo_variable,
        "p_codigo_variable": codigo_variable,
        "nombre_variable": nombre_variable,
        "p_nombre_variable": nombre_variable,
        "valor_variable": valor_variable,
        "valor": valor_variable if valor_variable is not None else valor_calculado,
        "p_valor_variable": valor_variable,
        "valor_calculado": valor_calculado,
        "p_valor_calculado": valor_calculado,
        "utilidad": utilidad,
        "p_utilidad": utilidad,
        "observacion": observacion,
        "comentario": observacion,
        "p_observacion": observacion,
        "calculado_por": actor_id,
        "registrado_por": actor_id,
        "id_usuario": actor_id,
        "id_user": actor_id,
        "usuario_id": actor_id,
        "id_usuario_evaluador": actor_id,
        "p_calculado_por": actor_id,
    }


def _audit_caces_event(*, action, description, actor, request, values):
    registrar_evento(
        accion=action,
        descripcion=description,
        usuario=actor,
        tipo_evento="EVALUACION_CACES",
        tabla_afectada="evaluacion_indicador_caces",
        id_registro=values.get("id_indicador"),
        valores_nuevos=values,
        criticidad="MEDIA",
        request=request,
    )


def _resolve_cycle_finalization_state():
    normalized_targets = {_normalize_state(value) for value in FINALIZATION_CYCLE_STATES}
    for estado in EstadoCiclo.objects.filter(activo=True).order_by("id_estado_ciclo"):
        if _normalize_state(estado.descripcion) in normalized_targets:
            return estado
    return None


def _cycle_caces_evaluation_is_complete(ciclo_id) -> tuple[bool, dict]:
    matrix = get_caces_indicator_matrix(ciclo_id)
    summary = matrix.get("summary") or {}
    total = int(summary.get("indicators_total") or 0)
    pending = int(summary.get("pending_total") or 0)
    return total > 0 and pending == 0, summary


def avanzar_ciclo_a_finalizacion_si_corresponde(*, ciclo_id, actor=None, request=None) -> dict:
    from apps.acreditacion.models import CicloEvaluacion

    id_ciclo = _coerce_positive_int(ciclo_id, "id_ciclo")
    ciclo = (
        CicloEvaluacion.objects.select_for_update()
        .select_related("estado")
        .filter(pk=id_ciclo)
        .first()
    )
    if ciclo is None:
        return {"status": "ciclo_no_encontrado"}

    current_state = _normalize_state(getattr(getattr(ciclo, "estado", None), "descripcion", ""))
    finalization_states = {_normalize_state(value) for value in FINALIZATION_CYCLE_STATES}
    if current_state in finalization_states:
        return {"status": "ya_en_finalizacion"}

    complete, summary = _cycle_caces_evaluation_is_complete(id_ciclo)
    if not complete:
        return {
            "status": "evaluacion_pendiente",
            "indicadores_total": int(summary.get("indicators_total") or 0),
            "pendientes": int(summary.get("pending_total") or 0),
        }

    estado_finalizacion = _resolve_cycle_finalization_state()
    if estado_finalizacion is None:
        return {"status": "estado_finalizacion_no_configurado"}

    estado_anterior = getattr(getattr(ciclo, "estado", None), "descripcion", None)
    ciclo.estado = estado_finalizacion
    ciclo.save(update_fields=["estado"])
    registrar_evento(
        accion="AVANZAR_CICLO_FINALIZACION_CACES",
        descripcion=(
            f"El ciclo {ciclo.nombre} avanzo a {estado_finalizacion.descripcion} "
            "porque todos los indicadores CACES fueron evaluados."
        ),
        usuario=actor,
        tipo_evento="EVALUACION_CACES",
        tabla_afectada="ciclo_evaluacion",
        id_registro=ciclo.pk,
        valores_anteriores={"estado": estado_anterior},
        valores_nuevos={
            "estado": estado_finalizacion.descripcion,
            "indicadores_total": int(summary.get("indicators_total") or 0),
            "pendientes": int(summary.get("pending_total") or 0),
            "avance": str(summary.get("evaluation_progress") or ""),
        },
        criticidad="MEDIA",
        request=request,
    )
    return {"status": "actualizado", "estado": estado_finalizacion.descripcion}


@transaction.atomic
def guardar_escenario_ponderacion_caces(
    *,
    ciclo_id,
    codigo_escenario,
    actor=None,
    request=None,
):
    if actor is None:
        raise CacesEvaluationError("No se pudo identificar al usuario que configura la ponderacion.")
    id_ciclo = _coerce_positive_int(ciclo_id, "id_ciclo")
    escenario = _ensure_active_scenario(codigo_escenario)
    config, _ = CicloConfiguracionCaces.objects.update_or_create(
        ciclo_id=id_ciclo,
        defaults={
            "escenario": escenario,
            "observacion": f"Escenario seleccionado en evaluacion CACES: {escenario.codigo_escenario}.",
            "fecha_configuracion": timezone.now(),
        },
    )
    registrar_evento(
        accion="CONFIGURAR_ESCENARIO_PONDERACION_CACES",
        descripcion=f"Se configuro el escenario {escenario.codigo_escenario} para el ciclo CACES {id_ciclo}.",
        usuario=actor,
        tipo_evento="EVALUACION_CACES",
        tabla_afectada="ciclo_configuracion_caces",
        id_registro=id_ciclo,
        valores_nuevos={
            "id_ciclo": id_ciclo,
            "codigo_escenario": escenario.codigo_escenario,
        },
        criticidad="MEDIA",
        request=request,
    )
    return config


@transaction.atomic
def guardar_evaluacion_cualitativa_caces(
    *,
    ciclo_id,
    indicador_id,
    categoria_id,
    utilidad_calculada=None,
    observacion=None,
    actor=None,
    request=None,
):
    if actor is None:
        raise CacesEvaluationError("No se pudo identificar al evaluador.")
    id_ciclo = _coerce_positive_int(ciclo_id, "id_ciclo")
    indicador = _ensure_indicator_active(indicador_id)
    mapping = _ensure_mapping(indicador)
    if _evaluation_type_for_indicator(indicador, mapping) != "CUALITATIVO":
        raise CacesEvaluationError("El indicador no es cualitativo.")

    categoria = CategoriaValoracionCaces.objects.filter(
        pk=_coerce_positive_int(categoria_id, "id_categoria"),
        activo=True,
    ).first()
    if categoria is None:
        raise CacesEvaluationError("La categoria cualitativa seleccionada no existe o esta inactiva.")
    _validate_unit_interval(categoria.utilidad, "utilidad")
    utility_override = None
    if utilidad_calculada is not None:
        utility_override = _validate_unit_interval(utilidad_calculada, "utilidad_calculada")

    observacion = _normalize_optional_text(observacion)
    proc_executed = False
    if mapping is not None and utility_override is None:
        proc_executed = _execute_stored_procedure(
            PROC_GUARDAR_CUALITATIVA,
            _parameter_aliases(
                id_ciclo=id_ciclo,
                id_indicador=indicador.pk,
                id_categoria=categoria.pk,
                codigo_categoria=categoria.codigo,
                utilidad=utility_override,
                observacion=observacion,
                actor_id=actor.pk,
            ),
        )
    if not proc_executed or utility_override is not None:
        _store_qualitative_evaluation(
            ciclo_id=id_ciclo,
            indicador=indicador,
            mapping=mapping,
            categoria=categoria,
            utilidad=utility_override,
            observacion=observacion,
            actor=actor,
        )
    result = get_caces_indicator_result(id_ciclo, indicador.pk)
    if result:
        _validate_unit_interval(result["utilidad"], "utilidad")
        _validate_unit_interval(result["ponderacion"], "ponderacion")
    avanzar_ciclo_a_finalizacion_si_corresponde(
        ciclo_id=id_ciclo,
        actor=actor,
        request=request,
    )
    _audit_caces_event(
        action="GUARDAR_EVALUACION_CUALITATIVA_CACES",
        description=f"Se guardo evaluacion cualitativa CACES para el indicador {indicador.codigo_indicador}.",
        actor=actor,
        request=request,
        values={
            "id_ciclo": id_ciclo,
            "id_indicador": indicador.pk,
            "id_categoria": categoria.pk,
            "codigo_categoria": categoria.codigo,
            "utilidad_calculada": str(utility_override) if utility_override is not None else None,
            "observacion": observacion,
        },
    )
    return result


@transaction.atomic
def guardar_variable_cuantitativa_caces(
    *,
    ciclo_id,
    indicador_id,
    codigo_variable,
    valor_variable,
    observacion=None,
    actor=None,
    request=None,
):
    if actor is None:
        raise CacesEvaluationError("No se pudo identificar al usuario que registra variables.")
    id_ciclo = _coerce_positive_int(ciclo_id, "id_ciclo")
    indicador = _ensure_indicator_active(indicador_id)
    mapping = _ensure_mapping(indicador)
    if _evaluation_type_for_indicator(indicador, mapping) != QUANTITATIVE_TYPE:
        raise CacesEvaluationError("El indicador no es cuantitativo.")
    if mapping is None:
        raise CacesEvaluationError(
            "El indicador no tiene formula CACES; usa la evaluacion cuantitativa manual general."
        )

    variable_code = _normalize_code(codigo_variable)
    variables_context = get_caces_required_variables(indicador.pk, ciclo_id=id_ciclo)
    variable = next(
        (
            item
            for item in variables_context["variables"]
            if _normalize_code(item.codigo_variable) == variable_code
        ),
        None,
    )
    if variable is None:
        raise CacesEvaluationError("La variable no pertenece a la formula del indicador.")

    value = _coerce_decimal(valor_variable, "valor_variable")
    observacion = _normalize_optional_text(observacion)
    if not _execute_stored_procedure(
        PROC_GUARDAR_VARIABLE,
        _parameter_aliases(
            id_ciclo=id_ciclo,
            id_indicador=indicador.pk,
            codigo_variable=variable.codigo_variable,
            nombre_variable=variable.nombre_variable,
            valor_variable=value,
            observacion=observacion,
            actor_id=actor.pk,
        ),
    ):
        _store_quantitative_variable(
            ciclo_id=id_ciclo,
            indicador=indicador,
            variable=variable,
            value=value,
            observacion=observacion,
            actor=actor,
        )
    _audit_caces_event(
        action="GUARDAR_VARIABLE_CUANTITATIVA_CACES",
        description=f"Se guardo variable {variable.codigo_variable} para {indicador.codigo_indicador}.",
        actor=actor,
        request=request,
        values={
            "id_ciclo": id_ciclo,
            "id_indicador": indicador.pk,
            "codigo_variable": variable.codigo_variable,
            "valor_variable": str(value),
        },
    )
    return get_caces_required_variables(indicador.pk, ciclo_id=id_ciclo)


@transaction.atomic
def guardar_variables_cuantitativas_caces(
    *,
    ciclo_id,
    indicador_id,
    variables,
    observacion=None,
    actor=None,
    request=None,
):
    if not variables:
        raise CacesEvaluationError("Selecciona al menos una variable cuantitativa.")

    result = None
    for variable in variables:
        result = guardar_variable_cuantitativa_caces(
            ciclo_id=ciclo_id,
            indicador_id=indicador_id,
            codigo_variable=_first_present(variable, "codigo_variable", "codigo"),
            valor_variable=_first_present(variable, "valor_variable", "valor"),
            observacion=variable.get("observacion") or observacion,
            actor=actor,
            request=request,
        )
    return result


def _missing_required_variables(indicador, ciclo_id):
    variables_context = get_caces_required_variables(indicador.pk, ciclo_id=ciclo_id)
    if variables_context["warning"]:
        raise CacesEvaluationError(variables_context["warning"])
    existing_codes = {
        _normalize_code(code)
        for code in variables_context["existing_values"].keys()
    }
    required_codes = {
        _normalize_code(variable.codigo_variable)
        for variable in variables_context["variables"]
        if variable.obligatorio
    }
    return sorted(required_codes - existing_codes)


@transaction.atomic
def calcular_evaluacion_cuantitativa_caces(
    *,
    ciclo_id,
    indicador_id,
    observacion=None,
    actor=None,
    request=None,
):
    if actor is None:
        raise CacesEvaluationError("No se pudo identificar al evaluador.")
    id_ciclo = _coerce_positive_int(ciclo_id, "id_ciclo")
    indicador = _ensure_indicator_active(indicador_id)
    mapping = _ensure_mapping(indicador)
    if _evaluation_type_for_indicator(indicador, mapping) != QUANTITATIVE_TYPE:
        raise CacesEvaluationError("El indicador no es cuantitativo.")
    if mapping is None:
        raise CacesEvaluationError(
            "El indicador no tiene formula CACES; usa la evaluacion cuantitativa manual general."
        )

    missing = _missing_required_variables(indicador, id_ciclo)
    if missing:
        raise CacesEvaluationError(
            "No se puede calcular: faltan variables obligatorias "
            + ", ".join(missing)
            + "."
        )

    observacion = _normalize_optional_text(observacion)
    if not _execute_stored_procedure(
        PROC_CALCULAR_CUANTITATIVA,
        _parameter_aliases(
            id_ciclo=id_ciclo,
            id_indicador=indicador.pk,
            observacion=observacion,
            actor_id=actor.pk,
        ),
    ):
        _calculate_and_store_quantitative(
            ciclo_id=id_ciclo,
            indicador=indicador,
            mapping=mapping,
            observacion=observacion,
            actor=actor,
        )
    result = get_caces_indicator_result(id_ciclo, indicador.pk)
    if result:
        _validate_unit_interval(result["utilidad"], "utilidad")
        _validate_unit_interval(result["ponderacion"], "ponderacion")
    avanzar_ciclo_a_finalizacion_si_corresponde(
        ciclo_id=id_ciclo,
        actor=actor,
        request=request,
    )
    _audit_caces_event(
        action="CALCULAR_EVALUACION_CUANTITATIVA_CACES",
        description=f"Se calculo evaluacion cuantitativa CACES para {indicador.codigo_indicador}.",
        actor=actor,
        request=request,
        values={
            "id_ciclo": id_ciclo,
            "id_indicador": indicador.pk,
            "observacion": observacion,
        },
    )
    return result


@transaction.atomic
def guardar_evaluacion_cuantitativa_manual_caces(
    *,
    ciclo_id,
    indicador_id,
    valor_calculado,
    observacion=None,
    actor=None,
    request=None,
):
    if actor is None:
        raise CacesEvaluationError("No se pudo identificar al evaluador.")
    id_ciclo = _coerce_positive_int(ciclo_id, "id_ciclo")
    indicador = _ensure_indicator_active(indicador_id)
    mapping = _ensure_mapping(indicador)
    if _evaluation_type_for_indicator(indicador, mapping) != QUANTITATIVE_TYPE:
        raise CacesEvaluationError("El indicador no es cuantitativo.")

    value = _coerce_decimal(valor_calculado, "valor_calculado")
    observacion = _normalize_optional_text(observacion)
    proc_executed = False
    if mapping is not None:
        proc_executed = _execute_stored_procedure(
            PROC_GUARDAR_CUANTITATIVA_MANUAL,
            _parameter_aliases(
                id_ciclo=id_ciclo,
                id_indicador=indicador.pk,
                valor_calculado=value,
                observacion=observacion,
                actor_id=actor.pk,
            ),
        )
    if not proc_executed:
        _calculate_and_store_quantitative(
            ciclo_id=id_ciclo,
            indicador=indicador,
            mapping=mapping,
            observacion=observacion,
            actor=actor,
            manual_value=value,
        )
    result = get_caces_indicator_result(id_ciclo, indicador.pk)
    if result:
        _validate_unit_interval(result["utilidad"], "utilidad")
        _validate_unit_interval(result["ponderacion"], "ponderacion")
    avanzar_ciclo_a_finalizacion_si_corresponde(
        ciclo_id=id_ciclo,
        actor=actor,
        request=request,
    )
    _audit_caces_event(
        action="GUARDAR_EVALUACION_CUANTITATIVA_MANUAL_CACES",
        description=f"Se guardo valor cuantitativo manual CACES para {indicador.codigo_indicador}.",
        actor=actor,
        request=request,
        values={
            "id_ciclo": id_ciclo,
            "id_indicador": indicador.pk,
            "valor_calculado": str(value),
            "observacion": observacion,
        },
    )
    return result
