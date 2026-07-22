from decimal import Decimal

from django import forms

from apps.core.models import EstadoEvaluacion
from apps.evaluacion.models import Evaluacion
from apps.evidencias.models import RegistroEvidencia


QUALITATIVE_TYPE_TOKENS = {"CUALITATIVO", "CUALITATIVA"}
QUALITATIVE_RESULT_CHOICES = (
    ("CUMPLE", "Cumple"),
    ("NO_CUMPLE", "No cumple"),
)
QUALITATIVE_RESULT_SCORES = {
    "CUMPLE": Decimal("100.00"),
    "NO_CUMPLE": Decimal("0.00"),
}
QUALITATIVE_RESULT_DETAILS = (
    {
        "value": "CUMPLE",
        "label": "Cumple",
        "codigo": "CUMPLE",
        "estado": "APROBADA",
        "cumplimiento": "100%",
        "utility": "1,00",
        "description": "La evidencia cumple con el elemento evaluado.",
    },
    {
        "value": "NO_CUMPLE",
        "label": "No cumple",
        "codigo": "NO_CUMPLE",
        "estado": "RECHAZADA",
        "cumplimiento": "0%",
        "utility": "0,00",
        "description": "La evidencia no cumple con el elemento evaluado.",
    },
)
QUANTITATIVE_CACES_RANGES = {
    "SATISFACTORIO": (Decimal("100.00"), Decimal("100.00")),
    "CUASI_SATISFACTORIO": (Decimal("70.00"), Decimal("99.99")),
    "POCO_SATISFACTORIO": (Decimal("35.00"), Decimal("69.99")),
    "DEFICIENTE": (Decimal("0.00"), Decimal("34.99")),
}
QUANTITATIVE_CACES_OPTIONS = (
    {
        "value": "SATISFACTORIO",
        "label": "Satisfactorio",
        "range_label": "100",
        "score": Decimal("100.00"),
        "estado": "APROBADA",
    },
    {
        "value": "CUASI_SATISFACTORIO",
        "label": "Cuasi satisfactorio",
        "range_label": "70 a 99.99",
        "score": Decimal("70.00"),
        "estado": "APROBADA",
    },
    {
        "value": "POCO_SATISFACTORIO",
        "label": "Poco satisfactorio",
        "range_label": "35 a 69.99",
        "score": Decimal("35.00"),
        "estado": "RECHAZADA",
    },
    {
        "value": "DEFICIENTE",
        "label": "Deficiente",
        "range_label": "0 a 34.99",
        "score": Decimal("0.00"),
        "estado": "RECHAZADA",
    },
)


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().split())
    return normalized or None


def _normalize_token(value: str | None) -> str:
    return " ".join((value or "").strip().upper().split())


def _get_indicator_type(registro) -> str:
    return _normalize_token(
        getattr(
            getattr(getattr(registro, "indicador", None), "tipo_indicador", None),
            "descripcion",
            "",
        )
    )


def is_qualitative_register(registro) -> bool:
    return _get_indicator_type(registro) in QUALITATIVE_TYPE_TOKENS


def _estado_by_description(description: str):
    return EstadoEvaluacion.objects.filter(
        descripcion__iexact=description,
        activo=True,
    ).first()


def _range_code_for_score(score) -> str | None:
    if score is None:
        return None
    value = score if isinstance(score, Decimal) else Decimal(str(score))
    for code, (minimum, maximum) in QUANTITATIVE_CACES_RANGES.items():
        if minimum <= value <= maximum:
            return code
    return None


def _state_description_for_quantitative_score(score) -> str:
    range_code = _range_code_for_score(score)
    if range_code in {"SATISFACTORIO", "CUASI_SATISFACTORIO"}:
        return "APROBADA"
    return "RECHAZADA"


def _quantitative_option_by_code(code: str | None) -> dict | None:
    normalized = _normalize_token(code)
    return next(
        (option for option in QUANTITATIVE_CACES_OPTIONS if option["value"] == normalized),
        None,
    )


class EvaluacionGestionForm(forms.Form):
    registro = forms.ModelChoiceField(
        queryset=RegistroEvidencia.objects.select_related(
            "ciclo",
            "indicador__tipo_indicador",
            "elemento_fundamental",
            "documento",
        ).order_by("-fecha_registro", "-id_registro"),
        label="Registro de evidencia",
    )
    estado = forms.ModelChoiceField(
        queryset=EstadoEvaluacion.objects.filter(activo=True).order_by("descripcion"),
        required=False,
        label="Estado final",
    )
    resultado_cualitativo = forms.ChoiceField(
        choices=QUALITATIVE_RESULT_CHOICES,
        required=False,
        label="Resultado cualitativo",
        widget=forms.RadioSelect,
    )
    calificacion = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=0,
        max_value=100,
        label="Calificacion cuantitativa",
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100"}),
    )
    calificacion_caces = forms.ChoiceField(
        choices=(),
        required=False,
        label="Calificacion cualitativa CACES",
    )
    comentario = forms.CharField(
        max_length=1000,
        required=False,
        label="Observaciones de evaluacion",
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, **kwargs):
        registro_initial = kwargs.pop("registro_initial", None)
        super().__init__(*args, **kwargs)
        self.registro_for_mode = registro_initial
        if self.is_bound and self.data.get(self.add_prefix("registro")):
            self.registro_for_mode = self.fields["registro"].queryset.filter(
                pk=self.data.get(self.add_prefix("registro"))
            ).first()
        if registro_initial:
            self.fields["registro"].initial = registro_initial
        self.evaluation_mode = (
            "qualitative" if is_qualitative_register(self.registro_for_mode) else "quantitative"
        )
        self.quantitative_caces_options = [
            {
                **option,
                "selected": False,
            }
            for option in QUANTITATIVE_CACES_OPTIONS
        ]
        self.fields["calificacion_caces"].choices = [("", "Seleccione la valoracion CACES")] + [
            (
                option["value"],
                f"{option['label']} ({option['range_label']})",
            )
            for option in QUANTITATIVE_CACES_OPTIONS
        ]
        if self.evaluation_mode == "quantitative":
            initial_code = _range_code_for_score(self.initial.get("calificacion"))
            selected_code = (
                self.data.get(self.add_prefix("calificacion_caces"))
                if self.is_bound
                else initial_code
            )
            if initial_code and not self.is_bound:
                self.fields["calificacion_caces"].initial = initial_code
            self.quantitative_caces_options = [
                {
                    **option,
                    "selected": option["value"] == selected_code,
                }
                for option in QUANTITATIVE_CACES_OPTIONS
            ]
            self.fields["calificacion"].widget.attrs.update(
                {
                    "data-caces-quantitative-score": "true",
                    "placeholder": "Ingrese un valor de 0 a 100",
                }
            )
            self.fields["calificacion_caces"].widget.attrs.update(
                {"data-caces-valuation-select": "true"}
            )
        selected_result = None
        if self.is_bound:
            selected_result = self.data.get(self.add_prefix("resultado_cualitativo"))
        else:
            selected_result = self.initial.get("resultado_cualitativo")
        self.qualitative_result_options = [
            {**option, "selected": option["value"] == selected_result}
            for option in QUALITATIVE_RESULT_DETAILS
        ]

    def clean_comentario(self):
        return _normalize_optional_text(self.cleaned_data.get("comentario"))

    def clean(self):
        cleaned_data = super().clean()
        registro = cleaned_data.get("registro")
        if registro is not None and getattr(registro, "fecha_envio_revision", None) is None:
            self.add_error(
                "registro",
                "La evidencia no esta habilitada para evaluacion. Primero habilita la salida al evaluador.",
            )
        if registro is None:
            return cleaned_data

        comentario = cleaned_data.get("comentario")
        if is_qualitative_register(registro):
            result = cleaned_data.get("resultado_cualitativo")
            if not result:
                self.add_error("resultado_cualitativo", "Selecciona si cumple o no cumple.")
            if not comentario:
                self.add_error("comentario", "Registra las observaciones de evaluacion cualitativa.")

            estado_description = "APROBADA" if result == "CUMPLE" else "RECHAZADA"
            estado = _estado_by_description(estado_description)
            if estado is None:
                self.add_error(
                    "resultado_cualitativo",
                    f"No existe el estado de evaluacion {estado_description}.",
                )
            else:
                cleaned_data["estado"] = estado
            if result in QUALITATIVE_RESULT_SCORES:
                cleaned_data["calificacion"] = QUALITATIVE_RESULT_SCORES[result]
        else:
            selected_option = _quantitative_option_by_code(cleaned_data.get("calificacion_caces"))
            if selected_option is None:
                self.add_error("calificacion_caces", "Selecciona la valoracion CACES.")
            else:
                score = selected_option["score"]
                cleaned_data["calificacion"] = score
                estado_description = selected_option["estado"]
                estado = _estado_by_description(estado_description)
                if estado is None:
                    self.add_error(
                        "calificacion_caces",
                        f"No existe el estado de evaluacion {estado_description}.",
                    )
                else:
                    cleaned_data["estado"] = estado
        return cleaned_data


class ObservacionGestionForm(forms.Form):
    evaluacion = forms.ModelChoiceField(
        queryset=Evaluacion.objects.select_related(
            "registro__ciclo",
            "registro__indicador",
            "registro__elemento_fundamental",
            "estado",
        ).order_by("-fecha_evaluacion", "-id_evaluacion"),
        label="Evaluacion",
    )
    observacion = forms.CharField(
        max_length=1000,
        label="Observacion",
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, **kwargs):
        evaluacion_initial = kwargs.pop("evaluacion_initial", None)
        super().__init__(*args, **kwargs)
        if evaluacion_initial:
            self.fields["evaluacion"].initial = evaluacion_initial

    def clean_observacion(self):
        return _normalize_optional_text(self.cleaned_data["observacion"])
