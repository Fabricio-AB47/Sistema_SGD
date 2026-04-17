from django import forms
from django.utils import timezone

from apps.integraciones.models import ApiServicio


class ServicioForm(forms.ModelForm):
    def save(self, commit=True):
        servicio = super().save(commit=False)
        if not servicio.pk and not servicio.fecha_creacion:
            servicio.fecha_creacion = timezone.now()
        if commit:
            servicio.save()
        return servicio

    class Meta:
        model = ApiServicio
        fields = [
            "nombre_servicio",
            "proveedor",
            "descripcion",
            "url_base",
            "activo",
        ]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 4}),
        }
