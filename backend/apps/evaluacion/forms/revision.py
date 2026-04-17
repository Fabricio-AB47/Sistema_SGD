from django import forms

from apps.core.models import EstadoEvaluacion
from apps.evaluacion.models import Evaluacion
from apps.evidencias.models import RegistroEvidencia


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().split())
    return normalized or None


class EvaluacionGestionForm(forms.Form):
    registro = forms.ModelChoiceField(
        queryset=RegistroEvidencia.objects.select_related(
            "ciclo",
            "indicador",
            "elemento_fundamental",
        ).order_by("-fecha_registro", "-id_registro"),
        label="Registro de evidencia",
    )
    estado = forms.ModelChoiceField(
        queryset=EstadoEvaluacion.objects.filter(activo=True).order_by("descripcion"),
        label="Estado de evaluacion",
    )
    calificacion = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        label="Calificacion",
    )
    comentario = forms.CharField(
        max_length=1000,
        required=False,
        label="Comentario",
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, **kwargs):
        registro_initial = kwargs.pop("registro_initial", None)
        super().__init__(*args, **kwargs)
        if registro_initial:
            self.fields["registro"].initial = registro_initial

    def clean_comentario(self):
        return _normalize_optional_text(self.cleaned_data.get("comentario"))


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
