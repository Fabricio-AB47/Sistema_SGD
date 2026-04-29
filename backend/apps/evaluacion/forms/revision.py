from django import forms

from apps.core.models import EstadoEvaluacion
from apps.evaluacion.models import Evaluacion
from apps.evidencias.models import RegistroEvidencia


QUALITATIVE_TYPE_TOKENS = {"CUALITATIVO", "CUALITATIVA"}
QUALITATIVE_RESULT_CHOICES = (
    ("CUMPLE", "Cumple"),
    ("NO_CUMPLE", "No cumple"),
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
    )
    comentario = forms.CharField(
        max_length=1000,
        required=False,
        label="Retroalimentacion",
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
                self.add_error("comentario", "Registra la retroalimentacion de la evaluacion cualitativa.")

            estado_description = "APROBADA" if result == "CUMPLE" else "RECHAZADA"
            estado = _estado_by_description(estado_description)
            if estado is None:
                self.add_error(
                    "resultado_cualitativo",
                    f"No existe el estado de evaluacion {estado_description}.",
                )
            else:
                cleaned_data["estado"] = estado
            cleaned_data["calificacion"] = None
        else:
            if cleaned_data.get("estado") is None:
                self.add_error("estado", "Selecciona el estado final de la evaluacion cuantitativa.")
            if cleaned_data.get("calificacion") is None:
                self.add_error("calificacion", "Registra la calificacion cuantitativa.")
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
