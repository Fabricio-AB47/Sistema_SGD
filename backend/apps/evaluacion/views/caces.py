from __future__ import annotations

import json
from decimal import Decimal

from django.contrib import messages
from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError, IntegrityError, OperationalError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from apps.evaluacion.forms import (
    CacesManualQuantitativeForm,
    CacesQualitativeEvaluationForm,
    CacesQuantitativeVariablesForm,
    EvaluacionGestionForm,
)
from apps.evaluacion.selectors import (
    get_actor_role_ids,
    get_caces_categories,
    get_caces_coverage_by_indicator,
    get_caces_cycle,
    get_caces_cycle_result,
    get_caces_cycles,
    get_caces_final_report,
    get_caces_indicator_detail,
    get_caces_indicator_matrix,
    get_caces_indicator_result,
    get_caces_pending_indicators,
    get_caces_required_variables,
    get_default_caces_cycle,
)
from apps.evaluacion.services import (
    CacesEvaluationError,
    EvaluacionWorkflowError,
    SQL_REFERENCES,
    calcular_evaluacion_cuantitativa_caces,
    guardar_escenario_ponderacion_caces,
    guardar_evaluacion_cualitativa_caces,
    guardar_evaluacion_cuantitativa_manual_caces,
    guardar_variables_cuantitativas_caces,
    registrar_evaluacion,
)
from apps.evaluacion.views.web import EvaluacionBaseView, EvaluacionEntryRoleRequiredMixin


QUALITATIVE_PAYLOAD_EXAMPLE = {
    "id_ciclo": 1,
    "id_indicador": 1,
    "id_categoria": 1,
    "observacion": "Cumple los componentes esenciales y complementarios.",
}

QUANTITATIVE_PAYLOAD_EXAMPLE = {
    "id_ciclo": 1,
    "id_indicador": 8,
    "variables": [
        {"codigo_variable": "PTD", "valor_variable": 24},
        {"codigo_variable": "NTC", "valor_variable": 18},
        {"codigo_variable": "NMT", "valor_variable": 6},
    ],
    "observacion": "Variables verificadas contra la evidencia documental.",
}

USER_FLOW_STEPS = (
    "Seleccionar el ciclo de evaluacion.",
    "Abrir la matriz CACES y revisar criterio, subcriterio, indicador y evidencias.",
    "Ingresar al detalle del indicador.",
    "Si es cualitativo, seleccionar categoria CACES y registrar observacion.",
    "Si es cuantitativo, registrar variables, calcular y revisar utilidad, ponderacion y aporte.",
    "Consultar el resultado por indicador y el consolidado final del ciclo.",
)


def _decimal_to_json(value):
    if isinstance(value, Decimal):
        return str(value)
    return value


def _serialize_result(result):
    if not result:
        return None
    return {
        key: _decimal_to_json(value)
        for key, value in result.items()
        if key not in {"version_fila"}
    }


def _serialize_cycle(ciclo):
    if ciclo is None:
        return None
    return {
        "id_ciclo": ciclo.pk,
        "nombre": ciclo.nombre,
        "anio": ciclo.anio,
        "fecha_inicio": ciclo.fecha_inicio,
        "fecha_fin": ciclo.fecha_fin,
        "estado": getattr(getattr(ciclo, "estado", None), "descripcion", None),
        "resultado": _serialize_result(getattr(ciclo, "resultado_caces", None)),
    }


def _serialize_category(category):
    return {
        "id_categoria": category.pk,
        "codigo": category.codigo,
        "nombre": category.nombre,
        "utilidad": str(category.utilidad),
        "descripcion": category.descripcion,
    }


def _serialize_indicator_node(node):
    indicador = node["indicador"]
    modelo = node.get("modelo")
    return {
        "id_indicador": indicador.pk,
        "codigo_indicador": indicador.codigo_indicador,
        "nombre_indicador": indicador.nombre_indicador,
        "tipo_evaluacion": node.get("tipo_evaluacion"),
        "criterio": indicador.subcriterio.criterio.nombre_criterio,
        "subcriterio": indicador.subcriterio.nombre_subcriterio,
        "numero_modelo": getattr(modelo, "numero_modelo", None),
        "codigo_modelo": getattr(modelo, "codigo_modelo", None),
        "mapeado": node.get("mapping") is not None,
        "advertencia": node.get("mapping_warning"),
        "resultado": _serialize_result(node.get("result")),
        "cobertura": _serialize_result(node.get("coverage")),
    }


def _serialize_variables_context(context):
    formula = context.get("formula")
    existing = context.get("existing_values", {})
    return {
        "advertencia": context.get("warning"),
        "formula": None
        if formula is None
        else {
            "codigo_formula": formula.codigo_formula,
            "nombre_formula": formula.nombre_formula,
            "expresion_formula": formula.expresion_formula,
            "estandar": str(formula.estandar),
            "sentido_calculo": formula.sentido_calculo,
        },
        "variables": [
            {
                "codigo_variable": variable.codigo_variable,
                "nombre_variable": variable.nombre_variable,
                "descripcion": variable.descripcion,
                "obligatorio": variable.obligatorio,
                "valor_actual": str(existing[variable.codigo_variable].valor_variable)
                if variable.codigo_variable in existing
                else None,
            }
            for variable in context.get("variables", [])
        ],
    }


def _parse_json_request(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise CacesEvaluationError("El cuerpo JSON no es valido.") from exc
    return request.POST.dict()


def _normalize_variables_payload(variables):
    if isinstance(variables, dict):
        return [
            {"codigo_variable": code, "valor_variable": value}
            for code, value in variables.items()
        ]
    return variables or []


class CacesBaseView(EvaluacionEntryRoleRequiredMixin, EvaluacionBaseView):
    page_status = "CACES"

    def _selected_cycle(self):
        ciclo = get_caces_cycle(self.request.GET.get("ciclo") or self.request.POST.get("ciclo"))
        return ciclo or get_default_caces_cycle()

    def _actor_role_ids(self):
        actor = self._actor()
        return get_actor_role_ids(getattr(actor, "pk", None))

    def _allow_unrestricted_caces_access(self):
        scope = self._actor_scope_flags()
        return bool(scope.get("is_admin") or scope.get("is_quality"))

    def _caces_detail_url(self, *, ciclo_id, indicador_id):
        return f"{reverse('evaluacion-caces-indicador')}?ciclo={ciclo_id}&indicador={indicador_id}"


class CacesDashboardView(CacesBaseView):
    template_name = "evaluacion/caces_dashboard.html"
    page_title = "Bandeja de evaluacion CACES"
    page_description = "Panel CACES para ciclos, avance de evidencias, evaluacion y resultado consolidado."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ciclos = get_caces_cycles()
        selected_cycle = self._selected_cycle()
        matrix = get_caces_indicator_matrix(selected_cycle.pk) if selected_cycle else None
        context.update(
            {
                "ciclos": ciclos,
                "selected_cycle": selected_cycle,
                "cycle_result": get_caces_cycle_result(selected_cycle.pk) if selected_cycle else None,
                "matrix_summary": matrix["summary"] if matrix else None,
                "pending_indicators": get_caces_pending_indicators(selected_cycle.pk)[:10]
                if selected_cycle
                else [],
                "sql_references": SQL_REFERENCES,
                "qualitative_payload_example": QUALITATIVE_PAYLOAD_EXAMPLE,
                "quantitative_payload_example": QUANTITATIVE_PAYLOAD_EXAMPLE,
                "user_flow_steps": USER_FLOW_STEPS,
            }
        )
        return context


class CacesCycleDashboardView(CacesBaseView):
    template_name = "evaluacion/caces_ciclo.html"
    page_title = "Bandeja CACES del ciclo"
    page_description = "Matriz jerarquica de criterio, subcriterio e indicador con cobertura, avance y aporte."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_cycle = self._selected_cycle()
        if selected_cycle is None:
            context.update({"selected_cycle": None, "matrix": None})
            return context
        context.update(
            {
                "selected_cycle": selected_cycle,
                "ciclos": get_caces_cycles(),
                "matrix": get_caces_indicator_matrix(selected_cycle.pk),
                "pending_indicators": get_caces_pending_indicators(selected_cycle.pk),
            }
        )
        return context


class CacesIndicatorDetailView(CacesBaseView):
    template_name = "evaluacion/caces_indicador.html"
    page_title = "Evaluar indicador CACES"
    page_description = "Consulta evidencias y registra evaluaciones cualitativas o cuantitativas."

    @staticmethod
    def _evidence_form_prefix(registro_id):
        return f"evidence_{registro_id}"

    @staticmethod
    def _evidence_form_initial(evaluacion):
        if evaluacion is None:
            return {}
        estado_description = (
            getattr(getattr(evaluacion, "estado", None), "descripcion", "") or ""
        ).strip().upper()
        initial = {
            "estado": getattr(evaluacion, "estado_id", None),
            "calificacion": getattr(evaluacion, "calificacion", None),
            "comentario": getattr(evaluacion, "comentario", None),
        }
        if estado_description == "APROBADA":
            initial["resultado_cualitativo"] = "CUMPLE"
        elif estado_description in {"RECHAZADA", "OBSERVADA"}:
            initial["resultado_cualitativo"] = "NO_CUMPLE"
        return initial

    def _attach_evidence_review_forms(
        self,
        detail,
        *,
        bound_form=None,
        bound_registro_id=None,
    ):
        for item in detail.get("elements_data", []):
            registro = item.get("latest_registro")
            if registro is None:
                item["evidence_review_form"] = None
                continue
            if bound_form is not None and str(registro.pk) == str(bound_registro_id):
                form = bound_form
            else:
                form = EvaluacionGestionForm(
                    prefix=self._evidence_form_prefix(registro.pk),
                    registro_initial=registro,
                    initial=self._evidence_form_initial(item.get("latest_evaluacion")),
                )
            item["evidence_review_form"] = form

    def _detail_context(self, *, qualitative_form=None, variables_form=None, manual_form=None):
        selected_cycle = self._selected_cycle()
        indicador_id = self.request.GET.get("indicador") or self.request.POST.get("indicador")
        if selected_cycle is None or not indicador_id:
            return None
        detail = get_caces_indicator_detail(
            ciclo_id=selected_cycle.pk,
            indicador_id=indicador_id,
            role_ids=self._actor_role_ids(),
            allow_unrestricted=self._allow_unrestricted_caces_access(),
        )
        if detail is None:
            return None
        qualitative_initial = {}
        if detail.get("result") and detail["result"].get("id_categoria"):
            qualitative_initial["categoria"] = detail["result"]["id_categoria"]
        self._attach_evidence_review_forms(detail)
        return {
            "selected_cycle": selected_cycle,
            "detail": detail,
            "qualitative_form": qualitative_form
            or CacesQualitativeEvaluationForm(
                prefix="qualitative",
                initial=qualitative_initial,
                elements_data=detail["elements_data"],
            ),
            "variables_form": variables_form
            or CacesQuantitativeVariablesForm(
                prefix="variables",
                variables_context=detail["variables_context"],
            ),
            "manual_form": manual_form or CacesManualQuantitativeForm(prefix="manual"),
            "detail_url": self._caces_detail_url(
                ciclo_id=selected_cycle.pk,
                indicador_id=detail["indicador"].pk,
            ),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        detail_context = kwargs or self._detail_context()
        if detail_context is None:
            raise Http404("El indicador CACES solicitado no existe.")
        context.update(detail_context)
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip()
        selected_cycle = self._selected_cycle()
        indicador_id = request.POST.get("indicador")
        if selected_cycle is None or not indicador_id:
            raise Http404("No se pudo identificar el ciclo o indicador.")

        detail = get_caces_indicator_detail(
            ciclo_id=selected_cycle.pk,
            indicador_id=indicador_id,
            role_ids=self._actor_role_ids(),
            allow_unrestricted=self._allow_unrestricted_caces_access(),
        )
        if detail is None:
            raise Http404("El indicador CACES solicitado no existe.")

        qualitative_form = CacesQualitativeEvaluationForm(
            prefix="qualitative",
            elements_data=detail["elements_data"],
        )
        variables_form = CacesQuantitativeVariablesForm(
            prefix="variables",
            variables_context=detail["variables_context"],
        )
        manual_form = CacesManualQuantitativeForm(prefix="manual")
        evidence_review_form = None
        evidence_review_registro_id = None

        try:
            if action == "save_qualitative":
                qualitative_form = CacesQualitativeEvaluationForm(
                    request.POST,
                    prefix="qualitative",
                    elements_data=detail["elements_data"],
                )
                if qualitative_form.is_valid():
                    guardar_evaluacion_cualitativa_caces(
                        ciclo_id=selected_cycle.pk,
                        indicador_id=detail["indicador"].pk,
                        categoria_id=qualitative_form.cleaned_data["categoria"].pk,
                        utilidad_calculada=qualitative_form.cleaned_data.get("utilidad_calculada"),
                        observacion=qualitative_form.cleaned_data.get("observacion_caces"),
                        actor=self._actor(),
                        request=request,
                    )
                    messages.success(
                        request,
                        "Evaluacion cualitativa CACES calculada y guardada correctamente.",
                    )
                    return redirect(self._caces_detail_url(ciclo_id=selected_cycle.pk, indicador_id=detail["indicador"].pk))

            elif action == "save_variables":
                variables_form = CacesQuantitativeVariablesForm(
                    request.POST,
                    prefix="variables",
                    variables_context=detail["variables_context"],
                )
                if variables_form.is_valid():
                    guardar_variables_cuantitativas_caces(
                        ciclo_id=selected_cycle.pk,
                        indicador_id=detail["indicador"].pk,
                        variables=variables_form.cleaned_data["variables_payload"],
                        observacion=variables_form.cleaned_data.get("observacion"),
                        actor=self._actor(),
                        request=request,
                    )
                    messages.success(request, "Variables cuantitativas guardadas correctamente.")
                    return redirect(self._caces_detail_url(ciclo_id=selected_cycle.pk, indicador_id=detail["indicador"].pk))

            elif action == "calculate_quantitative":
                guardar_escenario_ponderacion_caces(
                    ciclo_id=selected_cycle.pk,
                    codigo_escenario=request.POST.get("codigo_escenario"),
                    actor=self._actor(),
                    request=request,
                )
                calcular_evaluacion_cuantitativa_caces(
                    ciclo_id=selected_cycle.pk,
                    indicador_id=detail["indicador"].pk,
                    observacion=request.POST.get("observacion_calculo"),
                    actor=self._actor(),
                    request=request,
                )
                messages.success(request, "Evaluacion cuantitativa CACES calculada correctamente.")
                return redirect(self._caces_detail_url(ciclo_id=selected_cycle.pk, indicador_id=detail["indicador"].pk))

            elif action == "save_manual":
                manual_form = CacesManualQuantitativeForm(request.POST, prefix="manual")
                if manual_form.is_valid():
                    if detail["mapping"] is not None:
                        guardar_escenario_ponderacion_caces(
                            ciclo_id=selected_cycle.pk,
                            codigo_escenario=request.POST.get("codigo_escenario"),
                            actor=self._actor(),
                            request=request,
                        )
                    guardar_evaluacion_cuantitativa_manual_caces(
                        ciclo_id=selected_cycle.pk,
                        indicador_id=detail["indicador"].pk,
                        valor_calculado=manual_form.cleaned_data["valor_calculado"],
                        observacion=manual_form.cleaned_data.get("observacion"),
                        actor=self._actor(),
                        request=request,
                    )
                    messages.success(request, "Valor cuantitativo manual guardado correctamente.")
                    return redirect(self._caces_detail_url(ciclo_id=selected_cycle.pk, indicador_id=detail["indicador"].pk))

            elif action == "save_evidence_review":
                evidence_review_registro_id = request.POST.get("registro")
                selected_item = next(
                    (
                        item
                        for item in detail["elements_data"]
                        if item.get("latest_registro")
                        and str(item["latest_registro"].pk) == str(evidence_review_registro_id)
                    ),
                    None,
                )
                if selected_item is None:
                    messages.error(request, "La evidencia seleccionada no pertenece a este indicador.")
                else:
                    registro = selected_item["latest_registro"]
                    evidence_review_form = EvaluacionGestionForm(
                        request.POST,
                        prefix=self._evidence_form_prefix(registro.pk),
                        registro_initial=registro,
                    )
                    if evidence_review_form.is_valid():
                        result = registrar_evaluacion(
                            registro=evidence_review_form.cleaned_data["registro"],
                            estado=evidence_review_form.cleaned_data["estado"],
                            calificacion=evidence_review_form.cleaned_data.get("calificacion"),
                            comentario=evidence_review_form.cleaned_data.get("comentario"),
                            actor=self._actor(),
                            request=request,
                        )
                        messages.success(
                            request,
                            "Evaluacion de evidencia guardada correctamente."
                            if result["created"]
                            else "Evaluacion de evidencia actualizada correctamente.",
                        )
                        return redirect(
                            self._caces_detail_url(
                                ciclo_id=selected_cycle.pk,
                                indicador_id=detail["indicador"].pk,
                            )
                        )
            else:
                messages.error(request, "Selecciona una accion CACES valida.")

        except (
            CacesEvaluationError,
            EvaluacionWorkflowError,
            IntegrityError,
            OperationalError,
            DatabaseError,
            ValueError,
        ) as exc:
            messages.error(request, str(exc))

        self._attach_evidence_review_forms(
            detail,
            bound_form=evidence_review_form,
            bound_registro_id=evidence_review_registro_id,
        )
        return self.render_to_response(
            self.get_context_data(
                selected_cycle=selected_cycle,
                detail=detail,
                qualitative_form=qualitative_form,
                variables_form=variables_form,
                manual_form=manual_form,
                detail_url=self._caces_detail_url(
                    ciclo_id=selected_cycle.pk,
                    indicador_id=detail["indicador"].pk,
                ),
            )
        )


class CacesFinalReportView(CacesBaseView):
    template_name = "evaluacion/caces_reporte.html"
    page_title = "Reporte CACES"
    page_description = "Resultado final por ciclo con aporte acumulado por indicadores."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_cycle = self._selected_cycle()
        context.update(
            {
                "selected_cycle": selected_cycle,
                "report": get_caces_final_report(selected_cycle.pk) if selected_cycle else None,
                "ciclos": get_caces_cycles(),
            }
        )
        return context


class CacesJsonView(CacesBaseView):
    http_method_names = ["get", "post"]

    def _json(self, payload, *, status=200):
        return JsonResponse(payload, status=status, encoder=DjangoJSONEncoder, safe=False)

    def _json_error(self, message, *, status=400):
        return self._json({"ok": False, "message": message}, status=status)


class CacesCyclesApiView(CacesJsonView):
    def get(self, request, *args, **kwargs):
        return self._json({"ok": True, "ciclos": [_serialize_cycle(ciclo) for ciclo in get_caces_cycles()]})


class CacesIndicatorsApiView(CacesJsonView):
    def get(self, request, *args, **kwargs):
        ciclo = get_caces_cycle(request.GET.get("ciclo")) or get_default_caces_cycle()
        if ciclo is None:
            return self._json({"ok": True, "indicadores": []})
        matrix = get_caces_indicator_matrix(ciclo.pk)
        indicators = []
        for criterion in matrix["groups"]:
            for subcriterion in criterion["subcriteria"]:
                for node in subcriterion["indicators"]:
                    indicators.append(_serialize_indicator_node(node))
        return self._json({"ok": True, "id_ciclo": ciclo.pk, "indicadores": indicators})


class CacesPendingIndicatorsApiView(CacesJsonView):
    def get(self, request, *args, **kwargs):
        ciclo = get_caces_cycle(request.GET.get("ciclo")) or get_default_caces_cycle()
        pendientes = get_caces_pending_indicators(ciclo.pk) if ciclo else []
        return self._json({"ok": True, "pendientes": pendientes})


class CacesCategoriesApiView(CacesJsonView):
    def get(self, request, *args, **kwargs):
        return self._json({"ok": True, "categorias": [_serialize_category(item) for item in get_caces_categories()]})


class CacesVariablesApiView(CacesJsonView):
    def get(self, request, *args, **kwargs):
        context = get_caces_required_variables(
            request.GET.get("indicador"),
            ciclo_id=request.GET.get("ciclo"),
        )
        return self._json({"ok": True, **_serialize_variables_context(context)})


class CacesSaveQualitativeApiView(CacesJsonView):
    def post(self, request, *args, **kwargs):
        try:
            payload = _parse_json_request(request)
            result = guardar_evaluacion_cualitativa_caces(
                ciclo_id=payload.get("id_ciclo") or payload.get("ciclo"),
                indicador_id=payload.get("id_indicador") or payload.get("indicador"),
                categoria_id=payload.get("id_categoria") or payload.get("categoria"),
                observacion=payload.get("observacion"),
                actor=self._actor(),
                request=request,
            )
        except (CacesEvaluationError, DatabaseError, IntegrityError, OperationalError, ValueError) as exc:
            return self._json_error(str(exc))
        return self._json({"ok": True, "resultado": _serialize_result(result)})


class CacesSaveVariablesApiView(CacesJsonView):
    def post(self, request, *args, **kwargs):
        try:
            payload = _parse_json_request(request)
            context = guardar_variables_cuantitativas_caces(
                ciclo_id=payload.get("id_ciclo") or payload.get("ciclo"),
                indicador_id=payload.get("id_indicador") or payload.get("indicador"),
                variables=_normalize_variables_payload(payload.get("variables")),
                observacion=payload.get("observacion"),
                actor=self._actor(),
                request=request,
            )
        except (CacesEvaluationError, DatabaseError, IntegrityError, OperationalError, ValueError) as exc:
            return self._json_error(str(exc))
        return self._json({"ok": True, **_serialize_variables_context(context)})


class CacesCalculateQuantitativeApiView(CacesJsonView):
    def post(self, request, *args, **kwargs):
        try:
            payload = _parse_json_request(request)
            result = calcular_evaluacion_cuantitativa_caces(
                ciclo_id=payload.get("id_ciclo") or payload.get("ciclo"),
                indicador_id=payload.get("id_indicador") or payload.get("indicador"),
                observacion=payload.get("observacion"),
                actor=self._actor(),
                request=request,
            )
        except (CacesEvaluationError, DatabaseError, IntegrityError, OperationalError, ValueError) as exc:
            return self._json_error(str(exc))
        return self._json({"ok": True, "resultado": _serialize_result(result)})


class CacesSaveManualQuantitativeApiView(CacesJsonView):
    def post(self, request, *args, **kwargs):
        try:
            payload = _parse_json_request(request)
            result = guardar_evaluacion_cuantitativa_manual_caces(
                ciclo_id=payload.get("id_ciclo") or payload.get("ciclo"),
                indicador_id=payload.get("id_indicador") or payload.get("indicador"),
                valor_calculado=payload.get("valor_calculado"),
                observacion=payload.get("observacion"),
                actor=self._actor(),
                request=request,
            )
        except (CacesEvaluationError, DatabaseError, IntegrityError, OperationalError, ValueError) as exc:
            return self._json_error(str(exc))
        return self._json({"ok": True, "resultado": _serialize_result(result)})


class CacesIndicatorResultApiView(CacesJsonView):
    def get(self, request, *args, **kwargs):
        result = get_caces_indicator_result(
            request.GET.get("ciclo"),
            request.GET.get("indicador"),
        )
        return self._json({"ok": True, "resultado": _serialize_result(result)})


class CacesCycleResultApiView(CacesJsonView):
    def get(self, request, *args, **kwargs):
        result = get_caces_cycle_result(request.GET.get("ciclo"))
        return self._json({"ok": True, "resultado": _serialize_result(result)})


class CacesCoverageApiView(CacesJsonView):
    def get(self, request, *args, **kwargs):
        coverage = get_caces_coverage_by_indicator(
            request.GET.get("ciclo"),
            request.GET.get("indicador"),
        )
        return self._json({"ok": True, "cobertura": _serialize_result(coverage)})
