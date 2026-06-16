from __future__ import annotations

from decimal import Decimal

from django import forms

from apps.evaluacion.models import CategoriaValoracionCaces


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().split())
    return normalized or None


def _normalize_caces_code(value: str | None) -> str:
    return " ".join((value or "").strip().upper().split())


def _decimal_or_zero(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _field_name_for_element(element_id) -> str:
    return f"element_{element_id}"


def _element_type_group(value: str | None) -> str:
    normalized = _normalize_caces_code(value)
    if normalized == "COMPLEMENTARIO":
        return "COMPLEMENTARIO"
    return "ESENCIAL"


def _field_name_for_variable(code: str) -> str:
    safe_code = "".join(char if char.isalnum() else "_" for char in code.lower())
    return f"var_{safe_code}"


def _select_field_name_for_variable(code: str) -> str:
    safe_code = "".join(char if char.isalnum() else "_" for char in code.lower())
    return f"select_{safe_code}"


class CacesQualitativeEvaluationForm(forms.Form):
    COMPLIANCE_CHOICES = (
        ("CUMPLE", "Cumple"),
        ("NO_CUMPLE", "No cumple"),
    )

    categoria = forms.ModelChoiceField(
        queryset=CategoriaValoracionCaces.objects.filter(activo=True).order_by("-utilidad", "nombre"),
        label="Categoria CACES",
        required=False,
        widget=forms.HiddenInput,
    )
    observacion = forms.CharField(
        max_length=1000,
        required=False,
        label="Observaciones de evaluacion",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, elements_data=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.elements_data = elements_data or []
        self.element_field_map = {}
        self.element_decision_rows = []
        for item in self.elements_data:
            elemento = item.get("elemento")
            if elemento is None:
                continue
            field_name = _field_name_for_element(elemento.pk)
            latest_evaluation = item.get("latest_evaluacion")
            latest_score = _decimal_or_zero(item.get("element_score_ratio"))
            self.fields[field_name] = forms.ChoiceField(
                choices=self.COMPLIANCE_CHOICES,
                label=f"{elemento.codigo_elemento} - {elemento.nombre_elemento}",
                required=False,
                widget=forms.RadioSelect,
                initial=("CUMPLE" if latest_score > 0 else "NO_CUMPLE") if latest_evaluation else None,
            )
            element_type = item.get("element_type_group") or _element_type_group(
                getattr(elemento, "tipo_elemento", "")
            )
            self.element_field_map[field_name] = {
                "elemento": elemento,
                "element_type": element_type,
                "item": item,
            }
            self.element_decision_rows.append(
                {
                    "field_name": field_name,
                    "field": self[field_name],
                    "item": item,
                    "elemento": elemento,
                    "element_type": element_type,
                    "element_weight": _decimal_or_zero(item.get("element_weight")),
                }
            )

    def clean_observacion(self):
        return _normalize_optional_text(self.cleaned_data.get("observacion"))

    @staticmethod
    def _category_code_from_counts(*, essential_total, essential_failed, complementary_total, complementary_failed):
        if essential_failed == 0 and complementary_failed == 0:
            return "SATISFACTORIO"
        if essential_failed == 0:
            if complementary_failed < complementary_total:
                return "CUASI_SATISFACTORIO"
            return "POCO_SATISFACTORIO"
        if essential_total and essential_failed >= essential_total:
            return "DEFICIENTE"
        return "POCO_SATISFACTORIO"

    def clean(self):
        cleaned_data = super().clean()
        if not self.element_field_map:
            category = cleaned_data.get("categoria")
            if not category:
                raise forms.ValidationError(
                    "Selecciona una categoria CACES para calcular el puntaje cualitativo."
                )
            observacion = cleaned_data.get("observacion")
            summary = f"Categoria seleccionada {category.codigo}; utilidad {category.utilidad}."
            cleaned_data["categoria_calculada_codigo"] = category.codigo
            cleaned_data["resumen_componentes"] = {
                "puntaje_total": Decimal("0"),
                "puntaje_obtenido": Decimal("0"),
                "utilidad_ponderada": category.utilidad,
            }
            cleaned_data["elementos_payload"] = []
            cleaned_data["utilidad_calculada"] = category.utilidad
            full_observation = f"{summary} {observacion}".strip() if observacion else summary
            if len(full_observation) > 1000:
                full_observation = f"{full_observation[:997]}..."
            cleaned_data["observacion_caces"] = full_observation
            return cleaned_data

        essential_total = 0
        essential_failed = 0
        complementary_total = 0
        complementary_failed = 0
        score_total = Decimal("0")
        score_earned = Decimal("0")
        decisions = []
        selected_category = cleaned_data.get("categoria")

        for field_name, context in self.element_field_map.items():
            element_weight = _decimal_or_zero(context["item"].get("element_weight"))
            score_total += element_weight
            decision = cleaned_data.get(field_name)
            if not decision:
                continue
            element_type = context["element_type"]
            failed = decision == "NO_CUMPLE"
            if not failed:
                score_earned += element_weight
            if element_type == "COMPLEMENTARIO":
                complementary_total += 1
                complementary_failed += 1 if failed else 0
            else:
                essential_total += 1
                essential_failed += 1 if failed else 0
            elemento = context["elemento"]
            decisions.append(
                {
                    "codigo": elemento.codigo_elemento,
                    "tipo": element_type,
                    "decision": decision,
                    "ponderacion": str(element_weight.quantize(Decimal("0.0001"))),
                    "puntaje": str((Decimal("0") if failed else element_weight).quantize(Decimal("0.0001"))),
                }
            )

        if self.errors:
            return cleaned_data

        score_total = score_total.quantize(Decimal("0.0001"))
        if len(decisions) != len(self.element_field_map):
            if not selected_category:
                raise forms.ValidationError(
                    "Marca todos los elementos o selecciona una categoria CACES para calcular el puntaje."
                )
            score_earned = (score_total * _decimal_or_zero(selected_category.utilidad)).quantize(Decimal("0.0001"))
            observacion = cleaned_data.get("observacion")
            summary = (
                f"Categoria seleccionada {selected_category.codigo}; "
                f"puntaje {score_earned}/{score_total}."
            )
            full_observation = f"{summary} {observacion}".strip() if observacion else summary
            if len(full_observation) > 1000:
                full_observation = f"{full_observation[:997]}..."
            cleaned_data["categoria"] = selected_category
            cleaned_data["categoria_calculada_codigo"] = selected_category.codigo
            cleaned_data["resumen_componentes"] = {
                "puntaje_total": score_total,
                "puntaje_obtenido": score_earned,
                "utilidad_ponderada": selected_category.utilidad,
            }
            cleaned_data["elementos_payload"] = decisions
            cleaned_data["utilidad_calculada"] = selected_category.utilidad
            cleaned_data["observacion_caces"] = full_observation
            return cleaned_data

        category_code = self._category_code_from_counts(
            essential_total=essential_total,
            essential_failed=essential_failed,
            complementary_total=complementary_total,
            complementary_failed=complementary_failed,
        )
        category = CategoriaValoracionCaces.objects.filter(
            codigo__iexact=category_code,
            activo=True,
        ).first()
        if category is None:
            raise forms.ValidationError(
                f"No existe la categoria CACES activa {category_code} en la base de datos."
            )

        essential_ok = essential_total - essential_failed
        complementary_ok = complementary_total - complementary_failed
        score_earned = score_earned.quantize(Decimal("0.0001"))
        weighted_utility = (
            (score_earned / score_total).quantize(Decimal("0.0001"))
            if score_total > 0
            else Decimal("0.0000")
        )
        summary = (
            f"Esenciales {essential_ok}/{essential_total} cumplen; "
            f"complementarios {complementary_ok}/{complementary_total} cumplen; "
            f"puntaje {score_earned}/{score_total}; "
            f"categoria calculada {category_code}."
        )
        observacion = cleaned_data.get("observacion")
        full_observation = f"{summary} {observacion}".strip() if observacion else summary
        if len(full_observation) > 1000:
            full_observation = f"{full_observation[:997]}..."

        cleaned_data["categoria"] = category
        cleaned_data["categoria_calculada_codigo"] = category_code
        cleaned_data["resumen_componentes"] = {
            "essential_total": essential_total,
            "essential_failed": essential_failed,
            "essential_ok": essential_ok,
            "complementary_total": complementary_total,
            "complementary_failed": complementary_failed,
            "complementary_ok": complementary_ok,
            "puntaje_total": score_total,
            "puntaje_obtenido": score_earned,
            "utilidad_ponderada": weighted_utility,
        }
        cleaned_data["elementos_payload"] = decisions
        cleaned_data["utilidad_calculada"] = weighted_utility
        cleaned_data["observacion_caces"] = full_observation
        return cleaned_data


class CacesQuantitativeVariablesForm(forms.Form):
    observacion = forms.CharField(
        max_length=1000,
        required=False,
        label="Observaciones de evaluacion",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, variables_context=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.variables_context = variables_context or {
            "variables": [],
            "existing_values": {},
        }
        self.variable_field_map = {}
        self.variable_rows = []
        for variable in self.variables_context.get("variables", []):
            field_name = _field_name_for_variable(variable.codigo_variable)
            select_field_name = _select_field_name_for_variable(variable.codigo_variable)
            existing = self.variables_context.get("existing_values", {}).get(
                variable.codigo_variable
            )
            has_existing_value = existing is not None
            self.fields[select_field_name] = forms.BooleanField(
                required=False,
                label="Seleccionar",
                initial=has_existing_value,
            )
            self.fields[field_name] = forms.DecimalField(
                max_digits=18,
                decimal_places=4,
                required=False,
                min_value=0,
                label=f"{variable.codigo_variable} - {variable.nombre_variable}",
                help_text=variable.descripcion or "",
                initial=getattr(existing, "valor_variable", None),
            )
            self.variable_field_map[field_name] = (variable, select_field_name)
            self.variable_rows.append(
                {
                    "variable": variable,
                    "required": bool(variable.obligatorio),
                    "current_value": getattr(existing, "valor_variable", None),
                    "select": self[select_field_name],
                    "value": self[field_name],
                }
            )

    def clean_observacion(self):
        return _normalize_optional_text(self.cleaned_data.get("observacion"))

    def clean(self):
        cleaned_data = super().clean()
        variables_payload = []
        for field_name, (variable, select_field_name) in self.variable_field_map.items():
            is_selected = bool(cleaned_data.get(select_field_name))
            value = cleaned_data.get(field_name)
            if value is not None and not is_selected:
                is_selected = True
                cleaned_data[select_field_name] = True
            if not is_selected:
                continue
            if value is None:
                self.add_error(field_name, "Ingresa el valor de la variable seleccionada.")
                continue
            variables_payload.append(
                {
                    "codigo_variable": variable.codigo_variable,
                    "valor_variable": value,
                    "observacion": cleaned_data.get("observacion"),
                }
            )
        if self.variable_field_map and not variables_payload and not self.errors:
            raise forms.ValidationError("Selecciona al menos una variable cuantitativa.")
        cleaned_data["variables_payload"] = variables_payload
        return cleaned_data


class CacesManualQuantitativeForm(forms.Form):
    valor_calculado = forms.DecimalField(
        max_digits=18,
        decimal_places=4,
        min_value=0,
        label="Valor calculado",
    )
    observacion = forms.CharField(
        max_length=1000,
        required=False,
        label="Observaciones de evaluacion",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_observacion(self):
        return _normalize_optional_text(self.cleaned_data.get("observacion"))
