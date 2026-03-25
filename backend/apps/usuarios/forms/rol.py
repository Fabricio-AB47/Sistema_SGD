from django import forms

from apps.usuarios.models import Rol


class RolCrearForm(forms.ModelForm):
    class Meta:
        model = Rol
        fields = ["nombre_rol", "descripcion", "acceso_global", "activo"]

    def clean_nombre_rol(self):
        nombre = self.cleaned_data["nombre_rol"].strip()
        if Rol.objects.filter(nombre_rol__iexact=nombre).exists():
            raise forms.ValidationError("Ya existe un rol con este nombre.")
        return nombre
