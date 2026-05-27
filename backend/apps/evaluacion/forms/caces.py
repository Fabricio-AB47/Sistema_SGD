from __future__ import annotations

from django import forms

from apps.evaluacion.models import CategoriaValoracionCaces


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().split())
    return normalized or None


def _field_name_for_variable(code: str) -> str:
    safe_code = "".join(char if char.isalnum() else "_" for char in code.lower())
    return f"var_{safe_code}"


def _select_field_name_for_variable(code: str) -> str:
    safe_code = "".join(char if char.isalnum() else "_" for char in code.lower())
    return f"select_{safe_code}"


class CacesQualitativeEvaluationForm(forms.Form):
    categoria = forms.ModelChoiceField(
        queryset=CategoriaValoracionCaces.objects.filter(activo=True).order_by("-utilidad", "nombre"),
        label="Categoria CACES",
        widget=forms.RadioSelect,
    )
    observacion = forms.CharField(
        max_length=1000,
        required=False,
        label="Observaciones de evaluacion",
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def clean_observacion(self):
        return _normalize_optional_text(self.cleaned_data.get("observacion"))


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
