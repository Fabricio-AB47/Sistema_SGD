from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal

from django.db import DatabaseError, connection
from django.db.models import Prefetch

from apps.acreditacion.models import (
    CicloEvaluacion,
    ElementoFundamental,
    Indicador,
    RolIndicador,
)
from apps.evaluacion.models import (
    CategoriaValoracionCaces,
    CicloConfiguracionCaces,
    EscenarioPonderacionCaces,
    Evaluacion,
    EvaluacionIndicadorCaces,
    EvaluacionVariableCaces,
    IndicadorCacesMapeo,
    IndicadorFormulaCaces,
    IndicadorFormulaVariableCaces,
)
from apps.evidencias.models import RegistroEvidencia
from apps.usuarios.models import UsuarioRol


QUALITATIVE_TYPE = "CUALITATIVO"
QUANTITATIVE_TYPE = "CUANTITATIVO"
CACES_ALLOWED_CYCLE_STATES = (
    "APROBADO",
    "APROBADA",
    "EN_FINALIZACION",
    "EN PROCESO DE FINALIZACION",
    "CERRADO",
    "CERRADA",
    "FINALIZADO",
    "FINALIZADA",
)


def _dictfetchall(cursor):
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _fetch_dicts(sql: str, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        if cursor.description is None:
            return []
        return _dictfetchall(cursor)


def _coerce_pk(value):
    try:
        pk = int(value)
    except (TypeError, ValueError):
        return None
    return pk if pk > 0 else None


def _cycle_indicator_scope_ids(ciclo_pk):
    ciclo_pk = _coerce_pk(ciclo_pk)
    if not ciclo_pk:
        return set()
    return set(
        RolIndicador.objects.filter(ciclo_id=ciclo_pk, activo=True)
        .values_list("indicador_id", flat=True)
        .distinct()
    )


def _decimal_or_zero(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _decimal_to_percent(value) -> Decimal:
    return (_decimal_or_zero(value) * Decimal("100")).quantize(Decimal("0.01"))


def _ratio_to_percent(numerator, denominator) -> Decimal:
    denominator = _decimal_or_zero(denominator)
    if denominator == 0:
        return Decimal("0.00")
    return (_decimal_or_zero(numerator) / denominator * Decimal("100")).quantize(Decimal("0.01"))


def _normalize_token(value: str | None) -> str:
    return " ".join((value or "").strip().upper().split())


def _element_type_group(elemento) -> str:
    element_type = _normalize_token(getattr(elemento, "tipo_elemento", ""))
    if element_type == "COMPLEMENTARIO":
        return "COMPLEMENTARIO"
    return "ESENCIAL"


def _caces_scenario_for_cycle(ciclo_pk) -> str:
    escenario = "A"
    if ciclo_pk:
        try:
            config = CicloConfiguracionCaces.objects.filter(ciclo_id=ciclo_pk).first()
        except DatabaseError:
            config = None
        if config and config.escenario_id:
            escenario = str(config.escenario_id).upper()
    return escenario


def _first_value(row: dict | None, *keys, default=None):
    if not row:
        return default
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
        lowered_key = str(key).lower()
        if lowered_key in lowered and lowered[lowered_key] is not None:
            return lowered[lowered_key]
    return default


def _normalize_result_row(row: dict | None) -> dict | None:
    if not row:
        return None

    aporte = _first_value(row, "aporte", "aporte_decimal", default=0)
    utilidad = _first_value(row, "utilidad", default=0)
    ponderacion = _first_value(row, "ponderacion", "ponderacion_normalizada", default=0)
    resultado_decimal = _first_value(row, "resultado_decimal", "aporte", default=aporte)
    resultado_porcentaje = _first_value(row, "resultado_porcentaje", default=None)
    if resultado_porcentaje is None:
        resultado_porcentaje = _decimal_to_percent(resultado_decimal)

    normalized = {
        **row,
        "utilidad": _decimal_or_zero(utilidad),
        "cumplimiento_porcentaje": _decimal_to_percent(utilidad),
        "ponderacion": _decimal_or_zero(ponderacion),
        "aporte": _decimal_or_zero(aporte),
        "resultado_decimal": _decimal_or_zero(resultado_decimal),
        "resultado_porcentaje": _decimal_or_zero(resultado_porcentaje),
        "valor_calculado": _first_value(row, "valor_calculado"),
        "estandar": _first_value(row, "estandar"),
        "categoria": _first_value(row, "categoria", "nombre_categoria", "categoria_nombre"),
        "id_categoria": _first_value(row, "id_categoria", "categoria_id"),
        "tipo_evaluacion": _first_value(row, "tipo_evaluacion", default=""),
        "observacion": _first_value(row, "observacion", default=""),
    }
    return normalized


def _normalize_weight(value) -> Decimal:
    weight = _decimal_or_zero(value)
    if weight > 1 and weight <= 100:
        weight = weight / Decimal("100")
    return weight.quantize(Decimal("0.0001"))


def _model_weight_for_cycle(modelo, ciclo_pk) -> Decimal:
    if modelo is None:
        return Decimal("0")

    escenario = _caces_scenario_for_cycle(ciclo_pk)
    field_name = {
        "A": "ponderacion_a",
        "B": "ponderacion_b",
        "C": "ponderacion_c",
    }.get(escenario, "ponderacion_a")
    value = getattr(modelo, field_name, None)
    if value is None:
        value = getattr(modelo, "ponderacion_a", None)
    return _normalize_weight(value)


def _indicator_weight_for_cycle(mapping, indicador, ciclo_pk) -> Decimal:
    if mapping is not None:
        return _model_weight_for_cycle(mapping.modelo, ciclo_pk)
    for value in (
        getattr(indicador, "ponderacion", None),
        getattr(getattr(indicador, "subcriterio", None), "ponderacion", None),
        getattr(getattr(getattr(indicador, "subcriterio", None), "criterio", None), "ponderacion", None),
    ):
        weight = _normalize_weight(value)
        if weight > 0:
            return weight
    return Decimal("0.0000")


def _weight_options_for_model(modelo, ciclo_pk):
    if modelo is None:
        return []

    selected_scenario = _caces_scenario_for_cycle(ciclo_pk)
    try:
        scenarios = {
            scenario.pk: scenario
            for scenario in EscenarioPonderacionCaces.objects.filter(activo=True)
        }
    except DatabaseError:
        scenarios = {}

    options = []
    for code, field_name, fallback_name in (
        ("A", "ponderacion_a", "Pesos de indicadores"),
        ("B", "ponderacion_b", "Pesos sin TP"),
        ("C", "ponderacion_c", "Pesos sin MT ni TP"),
    ):
        value = getattr(modelo, field_name, None)
        if value is None:
            continue
        scenario = scenarios.get(code)
        options.append(
            {
                "code": code,
                "nombre": getattr(scenario, "nombre", fallback_name),
                "descripcion": getattr(scenario, "descripcion", ""),
                "ponderacion": _normalize_weight(value),
                "selected": code == selected_scenario,
            }
        )
    return options


def _weight_options_for_indicator(mapping, indicador, ciclo_pk):
    if mapping is not None:
        return _weight_options_for_model(mapping.modelo, ciclo_pk)
    weight = _indicator_weight_for_cycle(mapping, indicador, ciclo_pk)
    return [
        {
            "code": "GENERAL",
            "nombre": "Ponderacion del indicador",
            "descripcion": "Indicador sin mapeo CACES; se usa la ponderacion propia del indicador.",
            "ponderacion": weight,
            "selected": True,
        }
    ] if weight else []


def _qualitative_options_for_weight(ponderacion: Decimal):
    options = []
    for category in get_caces_categories():
        utilidad = _decimal_or_zero(category.utilidad)
        options.append(
            {
                "category": category,
                "utilidad": utilidad,
                "aporte_estimado": (utilidad * ponderacion).quantize(Decimal("0.0001")),
            }
        )
    return options


def _clamp_decimal(value, *, minimum=Decimal("0"), maximum=Decimal("1")) -> Decimal:
    decimal = _decimal_or_zero(value)
    if decimal < minimum:
        return minimum
    if decimal > maximum:
        return maximum
    return decimal


def _element_weight_map(elementos, indicator_weight: Decimal) -> dict[int, Decimal]:
    if not elementos:
        return {}
    weight = _decimal_or_zero(indicator_weight)
    if weight <= 0:
        return {elemento.pk: Decimal("0.0000") for elemento in elementos}
    element_weight = (weight / Decimal(len(elementos))).quantize(Decimal("0.0001"))
    weights = {elemento.pk: element_weight for elemento in elementos}
    difference = weight - sum(weights.values(), Decimal("0"))
    if difference and elementos:
        first_key = elementos[0].pk
        weights[first_key] = (weights[first_key] + difference).quantize(Decimal("0.0001"))
    return weights


def _evaluation_score_ratio(evaluacion) -> Decimal:
    if evaluacion is None:
        return Decimal("0")
    calificacion = getattr(evaluacion, "calificacion", None)
    if calificacion is not None:
        return _clamp_decimal(_decimal_or_zero(calificacion) / Decimal("100"))
    if bool(getattr(evaluacion, "aprobado", False)):
        return Decimal("1")
    estado = _normalize_token(getattr(getattr(evaluacion, "estado", None), "descripcion", ""))
    if estado in {"APROBADA", "APROBADO", "CUMPLE"}:
        return Decimal("1")
    return Decimal("0")


def _normalize_coverage_row(row: dict | None) -> dict:
    if not row:
        return {
            "total_elementos": 0,
            "elementos_con_evidencia": 0,
            "elementos_pendientes": 0,
            "porcentaje_cobertura": Decimal("0.00"),
        }

    total = _first_value(
        row,
        "total_elementos",
        "elementos_total",
        "total",
        default=0,
    )
    loaded = _first_value(
        row,
        "elementos_con_evidencia",
        "elementos_cargados",
        "subidas",
        "cargados",
        default=0,
    )
    pending = _first_value(
        row,
        "elementos_pendientes",
        "faltantes",
        default=None,
    )
    pct = _first_value(
        row,
        "porcentaje_cobertura",
        "cobertura_porcentaje",
        "cobertura",
        default=None,
    )
    total = int(total or 0)
    loaded = int(loaded or 0)
    if pending is None:
        pending = max(total - loaded, 0)
    if pct is None:
        pct = (Decimal(loaded) / Decimal(total) * Decimal("100")) if total else Decimal("0")
    return {
        **row,
        "total_elementos": total,
        "elementos_con_evidencia": loaded,
        "elementos_pendientes": int(pending or 0),
        "porcentaje_cobertura": _decimal_or_zero(pct).quantize(Decimal("0.01")),
    }


def get_caces_categories():
    return CategoriaValoracionCaces.objects.filter(activo=True).order_by("-utilidad", "nombre")


def _caces_allowed_cycles_queryset():
    return CicloEvaluacion.objects.select_related("estado").filter(
        estado__descripcion__in=CACES_ALLOWED_CYCLE_STATES,
    )


def get_caces_cycles():
    ciclos = list(
        _caces_allowed_cycles_queryset().order_by("-fecha_inicio", "-id_ciclo")
    )
    result_map = get_caces_cycle_result_map([ciclo.pk for ciclo in ciclos])
    for ciclo in ciclos:
        ciclo.resultado_caces = result_map.get(ciclo.pk)
    return ciclos


def get_caces_cycle(ciclo_id):
    pk = _coerce_pk(ciclo_id)
    if not pk:
        return None
    return _caces_allowed_cycles_queryset().filter(pk=pk).first()


def get_default_caces_cycle():
    return (
        _caces_allowed_cycles_queryset().order_by("-fecha_inicio", "-id_ciclo").first()
    )


def get_caces_cycle_result(ciclo_id):
    pk = _coerce_pk(ciclo_id)
    if not pk:
        return None
    scope_ids = _cycle_indicator_scope_ids(pk)
    if not scope_ids:
        try:
            rows = _fetch_dicts(
                "SELECT * FROM dbo.vw_caces_resultado_ciclo WHERE id_ciclo = %s",
                [pk],
            )
        except DatabaseError:
            rows = []
        if rows:
            return _normalize_result_row(rows[0])

    evaluaciones = EvaluacionIndicadorCaces.objects.filter(ciclo_id=pk)
    if scope_ids:
        evaluaciones = evaluaciones.filter(indicador_id__in=scope_ids)
    aporte = sum((item.aporte for item in evaluaciones), Decimal("0"))
    if not evaluaciones.exists():
        return None
    return _normalize_result_row(
        {
            "id_ciclo": pk,
            "resultado_decimal": aporte,
            "resultado_porcentaje": _decimal_to_percent(aporte),
            "indicadores_evaluados": evaluaciones.count(),
        }
    )


def get_caces_cycle_result_map(cycle_ids):
    ids = [_coerce_pk(item) for item in cycle_ids]
    ids = [item for item in ids if item]
    if not ids:
        return {}
    placeholders = ", ".join(["%s"] * len(ids))
    try:
        rows = _fetch_dicts(
            f"SELECT * FROM dbo.vw_caces_resultado_ciclo WHERE id_ciclo IN ({placeholders})",
            ids,
        )
    except DatabaseError:
        rows = []
    result_map = {}
    for row in rows:
        cycle_id = _coerce_pk(_first_value(row, "id_ciclo"))
        if cycle_id:
            result_map[cycle_id] = _normalize_result_row(row)
    return result_map


def get_caces_indicator_result(ciclo_id, indicador_id):
    ciclo_pk = _coerce_pk(ciclo_id)
    indicador_pk = _coerce_pk(indicador_id)
    if not ciclo_pk or not indicador_pk:
        return None

    try:
        rows = _fetch_dicts(
            """
            SELECT *
            FROM dbo.vw_caces_resultado_indicador
            WHERE id_ciclo = %s AND id_indicador = %s
            """,
            [ciclo_pk, indicador_pk],
        )
    except DatabaseError:
        rows = []
    if rows:
        return _normalize_result_row(rows[0])

    evaluacion = (
        EvaluacionIndicadorCaces.objects.select_related("categoria")
        .filter(ciclo_id=ciclo_pk, indicador_id=indicador_pk)
        .first()
    )
    if evaluacion is None:
        return None
    return _normalize_result_row(
        {
            "id_ciclo": ciclo_pk,
            "id_indicador": indicador_pk,
            "tipo_evaluacion": evaluacion.tipo_evaluacion,
            "categoria": getattr(evaluacion.categoria, "nombre", None),
            "id_categoria": evaluacion.categoria_id,
            "valor_calculado": evaluacion.valor_calculado,
            "estandar": evaluacion.estandar,
            "sentido_calculo": evaluacion.sentido_calculo,
            "utilidad": evaluacion.utilidad,
            "ponderacion": evaluacion.ponderacion,
            "aporte": evaluacion.aporte,
            "observacion": evaluacion.observacion,
            "fecha_calculo": evaluacion.fecha_calculo,
        }
    )


def get_caces_indicator_result_map(ciclo_id):
    ciclo_pk = _coerce_pk(ciclo_id)
    if not ciclo_pk:
        return {}
    scope_ids = _cycle_indicator_scope_ids(ciclo_pk)
    try:
        rows = _fetch_dicts(
            "SELECT * FROM dbo.vw_caces_resultado_indicador WHERE id_ciclo = %s",
            [ciclo_pk],
        )
    except DatabaseError:
        rows = []
    result_map = {}
    for row in rows:
        indicador_pk = _coerce_pk(_first_value(row, "id_indicador"))
        if scope_ids and indicador_pk not in scope_ids:
            continue
        if indicador_pk:
            result_map[indicador_pk] = _normalize_result_row(row)

    if result_map:
        return result_map

    evaluaciones = EvaluacionIndicadorCaces.objects.filter(ciclo_id=ciclo_pk)
    if scope_ids:
        evaluaciones = evaluaciones.filter(indicador_id__in=scope_ids)
    for evaluacion in evaluaciones:
        result_map[evaluacion.indicador_id] = _normalize_result_row(
            {
                "id_ciclo": ciclo_pk,
                "id_indicador": evaluacion.indicador_id,
                "tipo_evaluacion": evaluacion.tipo_evaluacion,
                "utilidad": evaluacion.utilidad,
                "ponderacion": evaluacion.ponderacion,
                "aporte": evaluacion.aporte,
                "valor_calculado": evaluacion.valor_calculado,
                "estandar": evaluacion.estandar,
            }
        )
    return result_map


def get_caces_coverage_by_indicator(ciclo_id, indicador_id=None):
    ciclo_pk = _coerce_pk(ciclo_id)
    indicador_pk = _coerce_pk(indicador_id)
    if not ciclo_pk:
        return {} if indicador_pk is None else _normalize_coverage_row(None)
    scope_ids = _cycle_indicator_scope_ids(ciclo_pk)
    if indicador_pk and scope_ids and indicador_pk not in scope_ids:
        return _normalize_coverage_row(None)

    sql = "SELECT * FROM dbo.vw_caces_cobertura_evidencias_indicador WHERE id_ciclo = %s"
    params = [ciclo_pk]
    if indicador_pk:
        sql += " AND id_indicador = %s"
        params.append(indicador_pk)

    try:
        rows = _fetch_dicts(sql, params)
    except DatabaseError:
        rows = []

    if rows:
        if indicador_pk:
            return _normalize_coverage_row(rows[0])
        coverage_map = {}
        for row in rows:
            row_indicator = _coerce_pk(_first_value(row, "id_indicador"))
            if scope_ids and row_indicator not in scope_ids:
                continue
            if row_indicator:
                coverage_map[row_indicator] = _normalize_coverage_row(row)
        return coverage_map

    indicator_ids = [indicador_pk] if indicador_pk else list(
        Indicador.objects.filter(activo=True).values_list("pk", flat=True)
    )
    if scope_ids:
        indicator_ids = [indicator_id for indicator_id in indicator_ids if indicator_id in scope_ids]
    coverage_map = {}
    for indicator_id in indicator_ids:
        total = ElementoFundamental.objects.filter(
            indicador_id=indicator_id,
            activo=True,
        ).count()
        loaded = (
            RegistroEvidencia.objects.filter(ciclo_id=ciclo_pk, indicador_id=indicator_id)
            .values("elemento_fundamental_id")
            .distinct()
            .count()
        )
        coverage_map[indicator_id] = _normalize_coverage_row(
            {
                "id_ciclo": ciclo_pk,
                "id_indicador": indicator_id,
                "total_elementos": total,
                "elementos_con_evidencia": loaded,
            }
        )
    return coverage_map.get(indicador_pk, _normalize_coverage_row(None)) if indicador_pk else coverage_map


def get_actor_role_ids(user_id):
    if not user_id:
        return []
    return list(
        UsuarioRol.objects.filter(
            usuario_id=user_id,
            activo=True,
            rol__activo=True,
        ).values_list("rol_id", flat=True)
    )


def get_accessible_element_ids_for_roles(
    *,
    ciclo_id,
    indicador_id,
    role_ids,
    allow_unrestricted=False,
):
    indicador_pk = _coerce_pk(indicador_id)
    ciclo_pk = _coerce_pk(ciclo_id)
    all_ids = set(
        ElementoFundamental.objects.filter(indicador_id=indicador_pk, activo=True)
        .values_list("pk", flat=True)
    )
    if allow_unrestricted:
        return all_ids
    if not ciclo_pk or not indicador_pk or not role_ids:
        return set()

    placeholders = ", ".join(["%s"] * len(role_ids))
    try:
        rows = _fetch_dicts(
            f"""
            SELECT *
            FROM dbo.vw_caces_rol_acceso_elemento
            WHERE id_ciclo = %s
              AND id_indicador = %s
              AND id_rol IN ({placeholders})
            """,
            [ciclo_pk, indicador_pk, *role_ids],
        )
    except DatabaseError:
        return set()

    if not rows:
        return set()
    if any(bool(_first_value(row, "acceso_total", default=False)) for row in rows):
        return all_ids
    return {
        int(_first_value(row, "id_elemento_fundamental"))
        for row in rows
        if _first_value(row, "id_elemento_fundamental") is not None
    }


def get_caces_required_variables(indicador_id, *, ciclo_id=None):
    indicador_pk = _coerce_pk(indicador_id)
    ciclo_pk = _coerce_pk(ciclo_id)
    if not indicador_pk:
        return {
            "mapping": None,
            "formula": None,
            "variables": [],
            "existing_values": {},
            "warning": "No se pudo identificar el indicador.",
        }

    mapping = (
        IndicadorCacesMapeo.objects.select_related("modelo")
        .filter(indicador_id=indicador_pk)
        .first()
    )
    if mapping is None:
        return {
            "mapping": None,
            "formula": None,
            "variables": [],
            "existing_values": {},
            "warning": "Indicador sin formula CACES: usa la evaluacion cuantitativa manual general.",
        }

    formula = (
        IndicadorFormulaCaces.objects.filter(modelo_id=mapping.modelo.numero_modelo, activo=True)
        .first()
    )
    if formula is None:
        return {
            "mapping": mapping,
            "formula": None,
            "variables": [],
            "existing_values": {},
            "warning": "El indicador CACES no tiene formula cuantitativa configurada.",
        }

    variables = list(
        IndicadorFormulaVariableCaces.objects.filter(formula_id=formula.codigo_formula)
        .order_by("codigo_variable")
    )
    existing_values = {}
    if ciclo_pk:
        existing_values = {
            item.codigo_variable: item
            for item in EvaluacionVariableCaces.objects.filter(
                ciclo_id=ciclo_pk,
                indicador_id=indicador_pk,
            )
        }
    return {
        "mapping": mapping,
        "formula": formula,
        "variables": variables,
        "existing_values": existing_values,
        "warning": None,
    }


def get_caces_indicator_detail(
    *,
    ciclo_id,
    indicador_id,
    role_ids=None,
    allow_unrestricted=False,
):
    ciclo_pk = _coerce_pk(ciclo_id)
    indicador_pk = _coerce_pk(indicador_id)
    if not ciclo_pk or not indicador_pk:
        return None

    indicador = (
        Indicador.objects.select_related("subcriterio__criterio", "tipo_indicador")
        .filter(pk=indicador_pk)
        .first()
    )
    if indicador is None:
        return None
    scope_ids = _cycle_indicator_scope_ids(ciclo_pk)
    if scope_ids and indicador.pk not in scope_ids:
        return None

    mapping = (
        IndicadorCacesMapeo.objects.select_related("modelo")
        .filter(indicador_id=indicador.pk)
        .first()
    )
    formula = None
    if mapping is not None:
        formula = IndicadorFormulaCaces.objects.filter(
            modelo_id=mapping.modelo.numero_modelo,
            activo=True,
        ).first()

    elementos = list(
        ElementoFundamental.objects.filter(
            indicador_id=indicador.pk,
            activo=True,
        ).order_by("orden_visual", "codigo_elemento")
    )

    registros_by_element = {}
    latest_evaluation_by_registro = {}
    if elementos:
        registros = (
            RegistroEvidencia.objects.select_related("documento", "estado", "registrado_por")
            .filter(
                ciclo_id=ciclo_pk,
                indicador_id=indicador.pk,
                elemento_fundamental_id__in=[elemento.pk for elemento in elementos],
            )
            .order_by("elemento_fundamental_id", "-fecha_registro", "-id_registro")
        )
        for registro in registros:
            registros_by_element.setdefault(registro.elemento_fundamental_id, []).append(registro)
        registro_ids = [registro.pk for registro in registros]
        latest_evaluations = (
            Evaluacion.objects.select_related("estado", "usuario_evaluador")
            .filter(registro_id__in=registro_ids)
            .order_by("registro_id", "-fecha_evaluacion", "-id_evaluacion")
        )
        for evaluacion in latest_evaluations:
            latest_evaluation_by_registro.setdefault(evaluacion.registro_id, evaluacion)

    indicator_type = _normalize_token(
        getattr(getattr(indicador, "tipo_indicador", None), "descripcion", "")
    )
    if mapping is not None:
        indicator_type = _normalize_token(mapping.modelo.tipo_evaluacion)
    ponderacion_referencial = _indicator_weight_for_cycle(mapping, indicador, ciclo_pk)
    ponderacion_options = _weight_options_for_indicator(mapping, indicador, ciclo_pk)
    element_weights = _element_weight_map(elementos, ponderacion_referencial)
    elements_data = []
    element_type_summary = {
        "essential_total": 0,
        "complementary_total": 0,
        "total": 0,
    }
    element_score_summary = {
        "ponderacion_total": _decimal_or_zero(ponderacion_referencial),
        "puntaje_obtenido": Decimal("0"),
        "cumplimiento_ponderado": Decimal("0.00"),
    }
    for elemento in elementos:
        element_type_group = _element_type_group(elemento)
        if element_type_group == "COMPLEMENTARIO":
            element_type_summary["complementary_total"] += 1
        else:
            element_type_summary["essential_total"] += 1
        element_type_summary["total"] += 1
        latest_registro = (registros_by_element.get(elemento.pk) or [None])[0]
        latest_evaluacion = (
            latest_evaluation_by_registro.get(latest_registro.pk)
            if latest_registro
            else None
        )
        element_weight = element_weights.get(elemento.pk, Decimal("0"))
        score_ratio = _evaluation_score_ratio(latest_evaluacion)
        element_score = (element_weight * score_ratio).quantize(Decimal("0.0001"))
        element_score_summary["puntaje_obtenido"] += element_score
        elements_data.append(
            {
                "elemento": elemento,
                "element_type_group": element_type_group,
                "element_weight": element_weight,
                "element_score_ratio": score_ratio,
                "element_score": element_score,
                "element_score_percentage": _decimal_to_percent(score_ratio),
                "registros": registros_by_element.get(elemento.pk, []),
                "latest_registro": latest_registro,
                "latest_evaluacion": latest_evaluacion,
            }
        )
    element_score_summary["puntaje_obtenido"] = element_score_summary["puntaje_obtenido"].quantize(Decimal("0.0001"))
    if element_score_summary["ponderacion_total"] > 0:
        element_score_summary["cumplimiento_ponderado"] = _decimal_to_percent(
            element_score_summary["puntaje_obtenido"] / element_score_summary["ponderacion_total"]
        )

    return {
        "ciclo": get_caces_cycle(ciclo_pk),
        "indicador": indicador,
        "mapping": mapping,
        "modelo": mapping.modelo if mapping else None,
        "formula": formula,
        "ponderacion_referencial": ponderacion_referencial,
        "ponderacion_options": ponderacion_options,
        "escenario_ponderacion": _caces_scenario_for_cycle(ciclo_pk),
        "qualitative_options": _qualitative_options_for_weight(ponderacion_referencial)
        if indicator_type == QUALITATIVE_TYPE
        else [],
        "indicator_type": indicator_type,
        "is_qualitative": indicator_type == QUALITATIVE_TYPE,
        "is_quantitative": indicator_type == QUANTITATIVE_TYPE,
        "elements_data": elements_data,
        "element_type_summary": element_type_summary,
        "element_score_summary": element_score_summary,
        "result": get_caces_indicator_result(ciclo_pk, indicador.pk),
        "coverage": get_caces_coverage_by_indicator(ciclo_pk, indicador.pk),
        "variables_context": get_caces_required_variables(indicador.pk, ciclo_id=ciclo_pk),
        "mapping_warning": None if mapping else "Indicador sin mapeo CACES: se evaluara con tipo y ponderacion general del indicador.",
    }


def get_caces_indicator_matrix(ciclo_id):
    ciclo_pk = _coerce_pk(ciclo_id)
    scope_ids = _cycle_indicator_scope_ids(ciclo_pk)
    result_map = get_caces_indicator_result_map(ciclo_pk)
    coverage_map = get_caces_coverage_by_indicator(ciclo_pk) if ciclo_pk else {}
    mappings = {
        item.indicador_id: item
        for item in IndicadorCacesMapeo.objects.select_related("modelo")
    }
    formulas = {
        formula.modelo_id: formula
        for formula in IndicadorFormulaCaces.objects.filter(activo=True)
    }

    indicadores = (
        Indicador.objects.filter(activo=True)
        .select_related("subcriterio__criterio", "tipo_indicador")
        .prefetch_related(
            Prefetch(
                "elementos",
                queryset=ElementoFundamental.objects.filter(activo=True).order_by(
                    "orden_visual",
                    "codigo_elemento",
                ),
                to_attr="caces_elementos",
            )
        )
        .order_by(
            "subcriterio__criterio__orden_visual",
            "subcriterio__criterio__codigo_criterio",
            "subcriterio__orden_visual",
            "subcriterio__codigo_subcriterio",
            "orden_visual",
            "codigo_indicador",
        )
    )
    if scope_ids:
        indicadores = indicadores.filter(pk__in=scope_ids)

    criteria_map = OrderedDict()
    type_sections_map = OrderedDict(
        (
            (
                "qualitative",
                {
                    "key": "qualitative",
                    "title": "Evaluacion cualitativa",
                    "label": "Cualitativos",
                    "tipo_evaluacion": QUALITATIVE_TYPE,
                    "groups": OrderedDict(),
                    "summary": {
                        "total": 0,
                        "evaluated": 0,
                        "pending": 0,
                        "weight_total": Decimal("0"),
                        "aporte_total": Decimal("0"),
                    },
                },
            ),
            (
                "quantitative",
                {
                    "key": "quantitative",
                    "title": "Evaluacion cuantitativa",
                    "label": "Cuantitativos",
                    "tipo_evaluacion": QUANTITATIVE_TYPE,
                    "groups": OrderedDict(),
                    "summary": {
                        "total": 0,
                        "evaluated": 0,
                        "pending": 0,
                        "weight_total": Decimal("0"),
                        "aporte_total": Decimal("0"),
                    },
                },
            ),
        )
    )
    totals = {
        "criteria_total": 0,
        "subcriteria_total": 0,
        "indicators_total": 0,
        "qualitative_total": 0,
        "quantitative_total": 0,
        "qualitative_evaluated_total": 0,
        "quantitative_evaluated_total": 0,
        "mapped_total": 0,
        "unmapped_total": 0,
        "evaluated_total": 0,
        "pending_total": 0,
        "elements_total": 0,
        "evidence_total": 0,
        "qualitative_weight_total": Decimal("0"),
        "quantitative_weight_total": Decimal("0"),
        "qualitative_aporte_total": Decimal("0"),
        "quantitative_aporte_total": Decimal("0"),
    }

    for indicador in indicadores:
        criterio = indicador.subcriterio.criterio
        subcriterio = indicador.subcriterio
        mapping = mappings.get(indicador.pk)
        modelo = mapping.modelo if mapping else None
        result = result_map.get(indicador.pk)
        coverage = coverage_map.get(indicador.pk, _normalize_coverage_row(None))
        indicator_type = _normalize_token(modelo.tipo_evaluacion) if modelo else _normalize_token(
            getattr(getattr(indicador, "tipo_indicador", None), "descripcion", "")
        )
        formula = formulas.get(getattr(modelo, "numero_modelo", None))
        reference_weight = _indicator_weight_for_cycle(mapping, indicador, ciclo_pk)
        result_weight = _decimal_or_zero(result.get("ponderacion") if result else reference_weight)
        result_aporte = _decimal_or_zero(result.get("aporte") if result else 0)
        node = {
            "indicador": indicador,
            "mapping": mapping,
            "modelo": modelo,
            "formula": formula,
            "tipo_evaluacion": indicator_type,
            "is_qualitative": indicator_type == QUALITATIVE_TYPE,
            "is_quantitative": indicator_type == QUANTITATIVE_TYPE,
            "ponderacion_referencial": reference_weight,
            "result": result,
            "coverage": coverage,
            "elementos": list(getattr(indicador, "caces_elementos", [])),
            "evaluated": result is not None,
            "mapping_warning": None if mapping else "Evaluacion general",
        }
        criterion_node = criteria_map.setdefault(
            criterio.pk,
            {
                "criterio": criterio,
                "subcriteria": OrderedDict(),
                "indicators_total": 0,
                "evaluated_total": 0,
            },
        )
        subcriterion_node = criterion_node["subcriteria"].setdefault(
            subcriterio.pk,
            {
                "subcriterio": subcriterio,
                "indicators": [],
                "indicators_total": 0,
                "evaluated_total": 0,
            },
        )
        subcriterion_node["indicators"].append(node)
        subcriterion_node["indicators_total"] += 1
        subcriterion_node["evaluated_total"] += 1 if node["evaluated"] else 0
        criterion_node["indicators_total"] += 1
        criterion_node["evaluated_total"] += 1 if node["evaluated"] else 0

        if indicator_type == QUALITATIVE_TYPE:
            section = type_sections_map["qualitative"]
        elif indicator_type == QUANTITATIVE_TYPE:
            section = type_sections_map["quantitative"]
        else:
            section = type_sections_map.setdefault(
                "other",
                {
                    "key": "other",
                    "title": "Evaluacion sin tipo CACES",
                    "label": "Sin tipo",
                    "tipo_evaluacion": indicator_type or "SIN_TIPO",
                    "groups": OrderedDict(),
                    "summary": {
                        "total": 0,
                        "evaluated": 0,
                        "pending": 0,
                        "weight_total": Decimal("0"),
                        "aporte_total": Decimal("0"),
                    },
                },
            )
        section_criterion_node = section["groups"].setdefault(
            criterio.pk,
            {
                "criterio": criterio,
                "subcriteria": OrderedDict(),
                "indicators_total": 0,
                "evaluated_total": 0,
            },
        )
        section_subcriterion_node = section_criterion_node["subcriteria"].setdefault(
            subcriterio.pk,
            {
                "subcriterio": subcriterio,
                "indicators": [],
                "indicators_total": 0,
                "evaluated_total": 0,
            },
        )
        section_subcriterion_node["indicators"].append(node)
        section_subcriterion_node["indicators_total"] += 1
        section_subcriterion_node["evaluated_total"] += 1 if node["evaluated"] else 0
        section_criterion_node["indicators_total"] += 1
        section_criterion_node["evaluated_total"] += 1 if node["evaluated"] else 0
        section["summary"]["total"] += 1
        section["summary"]["evaluated"] += 1 if node["evaluated"] else 0
        section["summary"]["weight_total"] += result_weight
        section["summary"]["aporte_total"] += result_aporte

        totals["indicators_total"] += 1
        totals["qualitative_total"] += 1 if indicator_type == QUALITATIVE_TYPE else 0
        totals["quantitative_total"] += 1 if indicator_type == QUANTITATIVE_TYPE else 0
        totals["qualitative_evaluated_total"] += (
            1 if indicator_type == QUALITATIVE_TYPE and result is not None else 0
        )
        totals["quantitative_evaluated_total"] += (
            1 if indicator_type == QUANTITATIVE_TYPE and result is not None else 0
        )
        totals["mapped_total"] += 1 if mapping else 0
        totals["unmapped_total"] += 0 if mapping else 1
        totals["evaluated_total"] += 1 if result is not None else 0
        totals["elements_total"] += len(node["elementos"])
        totals["evidence_total"] += int(coverage["elementos_con_evidencia"])
        if indicator_type == QUALITATIVE_TYPE:
            totals["qualitative_weight_total"] += result_weight
            totals["qualitative_aporte_total"] += result_aporte
        elif indicator_type == QUANTITATIVE_TYPE:
            totals["quantitative_weight_total"] += result_weight
            totals["quantitative_aporte_total"] += result_aporte

    groups = []
    for criterion_node in criteria_map.values():
        criterion_node["subcriteria"] = list(criterion_node["subcriteria"].values())
        groups.append(criterion_node)
    type_sections = []
    for section in type_sections_map.values():
        section_groups = []
        for criterion_node in section["groups"].values():
            criterion_node["subcriteria"] = list(criterion_node["subcriteria"].values())
            section_groups.append(criterion_node)
        section["groups"] = section_groups
        section["summary"]["pending"] = (
            section["summary"]["total"] - section["summary"]["evaluated"]
        )
        section["summary"]["evaluation_progress"] = _ratio_to_percent(
            section["summary"]["evaluated"],
            section["summary"]["total"],
        )
        section["summary"]["compliance_percentage"] = _ratio_to_percent(
            section["summary"]["aporte_total"],
            section["summary"]["weight_total"],
        )
        type_sections.append(section)
    totals["criteria_total"] = len(groups)
    totals["subcriteria_total"] = sum(len(group["subcriteria"]) for group in groups)
    totals["pending_total"] = totals["indicators_total"] - totals["evaluated_total"]
    totals["qualitative_pending_total"] = (
        totals["qualitative_total"] - totals["qualitative_evaluated_total"]
    )
    totals["quantitative_pending_total"] = (
        totals["quantitative_total"] - totals["quantitative_evaluated_total"]
    )
    totals["evaluation_progress"] = _ratio_to_percent(
        totals["evaluated_total"],
        totals["indicators_total"],
    )
    totals["qualitative_evaluation_progress"] = _ratio_to_percent(
        totals["qualitative_evaluated_total"],
        totals["qualitative_total"],
    )
    totals["quantitative_evaluation_progress"] = _ratio_to_percent(
        totals["quantitative_evaluated_total"],
        totals["quantitative_total"],
    )
    totals["qualitative_compliance_percentage"] = _ratio_to_percent(
        totals["qualitative_aporte_total"],
        totals["qualitative_weight_total"],
    )
    totals["quantitative_compliance_percentage"] = _ratio_to_percent(
        totals["quantitative_aporte_total"],
        totals["quantitative_weight_total"],
    )
    totals["caces_aporte_total"] = (
        totals["qualitative_aporte_total"] + totals["quantitative_aporte_total"]
    )
    totals["caces_compliance_percentage"] = _decimal_to_percent(totals["caces_aporte_total"])
    totals["evidence_coverage"] = _ratio_to_percent(
        totals["evidence_total"],
        totals["elements_total"],
    )

    return {
        "groups": groups,
        "type_sections": type_sections,
        "summary": totals,
        "result": get_caces_cycle_result(ciclo_pk),
    }


def get_caces_pending_indicators(ciclo_id):
    ciclo_pk = _coerce_pk(ciclo_id)
    if not ciclo_pk:
        return []
    scope_ids = _cycle_indicator_scope_ids(ciclo_pk)
    try:
        rows = _fetch_dicts(
            "SELECT * FROM dbo.vw_caces_indicadores_pendientes_evaluacion WHERE id_ciclo = %s",
            [ciclo_pk],
        )
        if scope_ids:
            rows = [
                row
                for row in rows
                if _coerce_pk(_first_value(row, "id_indicador")) in scope_ids
            ]
        return rows
    except DatabaseError:
        evaluated_ids = set(
            EvaluacionIndicadorCaces.objects.filter(ciclo_id=ciclo_pk)
            .values_list("indicador_id", flat=True)
        )
        indicadores = Indicador.objects.filter(activo=True).exclude(pk__in=evaluated_ids)
        if scope_ids:
            indicadores = indicadores.filter(pk__in=scope_ids)
        return [
            {
                "id_ciclo": ciclo_pk,
                "id_indicador": indicador.pk,
                "codigo_indicador": indicador.codigo_indicador,
                "nombre_indicador": indicador.nombre_indicador,
            }
            for indicador in indicadores
        ]


def get_caces_final_report(ciclo_id):
    ciclo = get_caces_cycle(ciclo_id)
    if ciclo is None:
        return None
    matrix = get_caces_indicator_matrix(ciclo.pk)
    summary = matrix["summary"]
    result = matrix["result"]
    final_percentage = _first_value(result, "resultado_porcentaje") if result else None
    if final_percentage is None:
        final_percentage = summary["caces_compliance_percentage"]
    final_percentage = _decimal_or_zero(final_percentage)
    type_summary = {
        "qualitative": {
            "label": "Cualitativo",
            "total": summary["qualitative_total"],
            "evaluated": summary["qualitative_evaluated_total"],
            "pending": summary["qualitative_pending_total"],
            "evaluation_progress": summary["qualitative_evaluation_progress"],
            "weight_total": summary["qualitative_weight_total"],
            "aporte_total": summary["qualitative_aporte_total"],
            "compliance_percentage": summary["qualitative_compliance_percentage"],
        },
        "quantitative": {
            "label": "Cuantitativo",
            "total": summary["quantitative_total"],
            "evaluated": summary["quantitative_evaluated_total"],
            "pending": summary["quantitative_pending_total"],
            "evaluation_progress": summary["quantitative_evaluation_progress"],
            "weight_total": summary["quantitative_weight_total"],
            "aporte_total": summary["quantitative_aporte_total"],
            "compliance_percentage": summary["quantitative_compliance_percentage"],
        },
        "overall": {
            "label": "Consolidado final",
            "total": summary["indicators_total"],
            "evaluated": summary["evaluated_total"],
            "pending": summary["pending_total"],
            "evaluation_progress": summary["evaluation_progress"],
            "aporte_total": summary["caces_aporte_total"],
            "compliance_percentage": final_percentage,
        },
    }
    return {
        "ciclo": ciclo,
        "summary": summary,
        "type_summary": type_summary,
        "result": result,
        "groups": matrix["groups"],
        "type_sections": matrix["type_sections"],
    }
