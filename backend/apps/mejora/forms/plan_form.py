from django import forms

from apps.core.models import EstadoPlanMejora
from apps.evaluacion.models import Evaluacion
from apps.mejora.models import AccionMejora, PlanMejora, SeguimientoAccionMejora
from apps.usuarios.models import Usuario


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().split())
    return normalized or None


class PlanMejoraForm(forms.ModelForm):
    class Meta:
        model = PlanMejora
        fields = ["evaluacion", "descripcion", "fecha_inicio", "fecha_fin", "responsable", "estado"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 4}),
            "fecha_inicio": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "fecha_fin": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["evaluacion"].queryset = Evaluacion.objects.select_related(
            "registro__ciclo",
            "registro__indicador",
            "estado",
        ).order_by("-fecha_evaluacion", "-id_evaluacion")
        self.fields["responsable"].queryset = Usuario.objects.filter(activo=True).order_by(
            "primer_apellido",
            "primer_nombre",
        )
        self.fields["estado"].queryset = EstadoPlanMejora.objects.filter(activo=True).order_by("id_estado_plan_mejora")
        estado_borrador = self.fields["estado"].queryset.filter(descripcion__iexact="BORRADOR").first()
        if estado_borrador and not self.instance.pk:
            self.fields["estado"].initial = estado_borrador

    def clean_descripcion(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion"))


class SeguimientoAccionForm(forms.ModelForm):
    class Meta:
        model = SeguimientoAccionMejora
        fields = ["accion", "porcentaje_avance", "observacion", "semaforo"]
        widgets = {
            "observacion": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        accion_initial = kwargs.pop("accion_initial", None)
        super().__init__(*args, **kwargs)
        self.fields["accion"].queryset = AccionMejora.objects.select_related("plan").order_by("plan_id", "id_accion")
        if accion_initial:
            self.fields["accion"].initial = accion_initial

    def clean_observacion(self):
        return _normalize_optional_text(self.cleaned_data.get("observacion"))
