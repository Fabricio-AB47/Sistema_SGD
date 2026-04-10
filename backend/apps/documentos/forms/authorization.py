from django import forms

from apps.core.models import ClasificacionDocumento


def _normalize_required_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = _normalize_required_text(value or "")
    return normalized or None


class AuthorizationFolderForm(forms.Form):
    nombre_ciclo = forms.CharField(max_length=150, label="Nombre del ciclo")
    anio = forms.IntegerField(required=False, min_value=2000, max_value=2100, label="Anio")

    def clean_nombre_ciclo(self):
        return _normalize_required_text(self.cleaned_data["nombre_ciclo"])


class AuthorizationUploadForm(AuthorizationFolderForm):
    clasificacion = forms.ModelChoiceField(
        queryset=ClasificacionDocumento.objects.filter(activo=True).order_by("codigo"),
        label="Clasificacion documental",
    )
    descripcion_documento = forms.CharField(
        max_length=500,
        required=False,
        label="Descripcion",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    archivo = forms.FileField(label="Archivo")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clasificacion = ClasificacionDocumento.objects.filter(codigo="AUT_CICLO", activo=True).first()
        if clasificacion is None:
            clasificacion = ClasificacionDocumento.objects.filter(codigo="ACTA", activo=True).first()
        if clasificacion:
            self.fields["clasificacion"].initial = clasificacion

    def clean_descripcion_documento(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion_documento"))
