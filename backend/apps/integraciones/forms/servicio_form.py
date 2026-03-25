from django import forms

from apps.integraciones.models import ApiServicio


class ServicioForm(forms.ModelForm):
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
