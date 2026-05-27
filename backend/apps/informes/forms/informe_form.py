from django import forms

from apps.acreditacion.models import CicloEvaluacion, Indicador
from apps.core.models import EstadoInforme
from apps.informes.models import InformeAutoevaluacion


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().split())
    return normalized or None


class InformeGeneracionForm(forms.ModelForm):
    class Meta:
        model = InformeAutoevaluacion
        fields = ["ciclo", "resumen", "conclusiones", "estado"]
        widgets = {
            "resumen": forms.Textarea(attrs={"rows": 4}),
            "conclusiones": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ciclo"].queryset = CicloEvaluacion.objects.select_related("estado").order_by(
            "-fecha_inicio",
            "-id_ciclo",
        )
        self.fields["estado"].queryset = EstadoInforme.objects.filter(activo=True).order_by("id_estado_informe")
        estado_borrador = self.fields["estado"].queryset.filter(descripcion__iexact="BORRADOR").first()
        if estado_borrador and not self.instance.pk:
            self.fields["estado"].initial = estado_borrador

    def clean_resumen(self):
        return _normalize_optional_text(self.cleaned_data.get("resumen"))

    def clean_conclusiones(self):
        return _normalize_optional_text(self.cleaned_data.get("conclusiones"))


class InformeAprobacionForm(forms.Form):
    informe = forms.ModelChoiceField(
        queryset=InformeAutoevaluacion.objects.select_related("ciclo", "estado").order_by("-fecha_generacion", "-id_informe"),
        label="Informe",
    )
    estado = forms.ModelChoiceField(
        queryset=EstadoInforme.objects.filter(activo=True).exclude(descripcion__iexact="BORRADOR").order_by("id_estado_informe"),
        label="Nuevo estado",
    )
    observacion_aprobacion = forms.CharField(
        max_length=1000,
        required=False,
        label="Observacion",
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, **kwargs):
        informe_initial = kwargs.pop("informe_initial", None)
        super().__init__(*args, **kwargs)
        if informe_initial:
            self.fields["informe"].initial = informe_initial

    def clean_observacion_aprobacion(self):
        return _normalize_optional_text(self.cleaned_data.get("observacion_aprobacion"))


class ReporteOperativoFilterForm(forms.Form):
    ciclo = forms.ModelChoiceField(
        queryset=CicloEvaluacion.objects.none(),
        required=False,
        label="Periodo",
    )
    indicador = forms.ModelChoiceField(
        queryset=Indicador.objects.none(),
        required=False,
        label="Indicador",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ciclo"].queryset = CicloEvaluacion.objects.select_related("estado").order_by(
            "-fecha_inicio",
            "-id_ciclo",
        )
        self.fields["indicador"].queryset = Indicador.objects.select_related(
            "subcriterio__criterio",
            "tipo_indicador",
        ).order_by(
            "subcriterio__criterio__orden_visual",
            "subcriterio__criterio__codigo_criterio",
            "subcriterio__orden_visual",
            "subcriterio__codigo_subcriterio",
            "orden_visual",
            "codigo_indicador",
        )
        self.fields["indicador"].label_from_instance = (
            lambda indicador: (
                f"{indicador.subcriterio.criterio.codigo_criterio} / "
                f"{indicador.subcriterio.codigo_subcriterio} / "
                f"{indicador.codigo_indicador} - {indicador.nombre_indicador}"
            )
        )
