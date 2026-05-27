from __future__ import annotations

import re
from decimal import Decimal

from django.utils import timezone
from django.db import DatabaseError, connection, transaction

from apps.acreditacion.models import Indicador
from apps.auditoria.services.auditoria_service import registrar_evento
from apps.core.models import EstadoCiclo
from apps.evaluacion.models import (
    CategoriaValoracionCaces,
    CicloConfiguracionCaces,
    EscenarioPonderacionCaces,
    IndicadorCacesMapeo,
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
    indicador = Indicador.objects.filter(pk=indicador_pk).first()
    if indicador is None:
        raise CacesEvaluationError("El indicador seleccionado no existe.")
    if not indicador.activo:
        raise CacesEvaluationError("No se permite evaluar un indicador inactivo.")
    return indicador


def _ensure_mapping(indicador):
    mapping = (
        IndicadorCacesMapeo.objects.select_related("modelo")
        .filter(indicador_id=indicador.pk)
        .first()
    )
    if mapping is None:
        raise CacesEvaluationError(
            "El indicador no esta mapeado a modelo_indicador_caces."
        )
    return mapping


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
        raise CacesEvaluationError(f"No existe el procedimiento {proc_name}.")

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
        rows = []
        if cursor.description:
            columns = [column[0] for column in cursor.description]
            rows.extend(dict(zip(columns, row)) for row in cursor.fetchall())
        return rows


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
    observacion=None,
    actor=None,
    request=None,
):
    if actor is None:
        raise CacesEvaluationError("No se pudo identificar al evaluador.")
    id_ciclo = _coerce_positive_int(ciclo_id, "id_ciclo")
    indicador = _ensure_indicator_active(indicador_id)
    mapping = _ensure_mapping(indicador)
    if mapping.modelo.tipo_evaluacion != "CUALITATIVO":
        raise CacesEvaluationError("El indicador no es cualitativo segun el modelo CACES.")

    categoria = CategoriaValoracionCaces.objects.filter(
        pk=_coerce_positive_int(categoria_id, "id_categoria"),
        activo=True,
    ).first()
    if categoria is None:
        raise CacesEvaluationError("La categoria cualitativa seleccionada no existe o esta inactiva.")
    _validate_unit_interval(categoria.utilidad, "utilidad")

    observacion = _normalize_optional_text(observacion)
    _execute_stored_procedure(
        PROC_GUARDAR_CUALITATIVA,
        _parameter_aliases(
            id_ciclo=id_ciclo,
            id_indicador=indicador.pk,
            id_categoria=categoria.pk,
            codigo_categoria=categoria.codigo,
            observacion=observacion,
            actor_id=actor.pk,
        ),
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
    if mapping.modelo.tipo_evaluacion != QUANTITATIVE_TYPE:
        raise CacesEvaluationError("El indicador no es cuantitativo segun el modelo CACES.")

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
    _execute_stored_procedure(
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
    if mapping.modelo.tipo_evaluacion != QUANTITATIVE_TYPE:
        raise CacesEvaluationError("El indicador no es cuantitativo segun el modelo CACES.")

    missing = _missing_required_variables(indicador, id_ciclo)
    if missing:
        raise CacesEvaluationError(
            "No se puede calcular: faltan variables obligatorias "
            + ", ".join(missing)
            + "."
        )

    observacion = _normalize_optional_text(observacion)
    _execute_stored_procedure(
        PROC_CALCULAR_CUANTITATIVA,
        _parameter_aliases(
            id_ciclo=id_ciclo,
            id_indicador=indicador.pk,
            observacion=observacion,
            actor_id=actor.pk,
        ),
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
    if mapping.modelo.tipo_evaluacion != QUANTITATIVE_TYPE:
        raise CacesEvaluationError("El indicador no es cuantitativo segun el modelo CACES.")

    value = _coerce_decimal(valor_calculado, "valor_calculado")
    observacion = _normalize_optional_text(observacion)
    _execute_stored_procedure(
        PROC_GUARDAR_CUANTITATIVA_MANUAL,
        _parameter_aliases(
            id_ciclo=id_ciclo,
            id_indicador=indicador.pk,
            valor_calculado=value,
            observacion=observacion,
            actor_id=actor.pk,
        ),
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
