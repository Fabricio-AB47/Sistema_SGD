from django import forms

from apps.acreditacion.models import (
    CicloEvaluacion,
    ElementoFundamental,
    Indicador,
    IndicadorElementoFundamental,
)
from apps.core.services.upload_security import validate_uploaded_file
from apps.core.models import ClasificacionDocumento


def _normalize_required_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = _normalize_required_text(value or "")
    return normalized or None


class StructuredDocumentUploadForm(forms.Form):
    ciclo = forms.ModelChoiceField(
        queryset=CicloEvaluacion.objects.select_related("estado").only(
            "id_ciclo",
            "nombre",
            "anio",
            "fecha_inicio",
            "estado",
            "estado__descripcion",
        )
        .filter(estado__descripcion__iexact="APROBADO")
        .order_by("-fecha_inicio", "-id_ciclo"),
        label="Ciclo aprobado",
        empty_label="Selecciona un ciclo aprobado",
    )
    indicador = forms.ModelChoiceField(
        queryset=Indicador.objects.select_related("subcriterio__criterio").only(
            "id_indicador",
            "codigo_indicador",
            "nombre_indicador",
            "subcriterio",
            "subcriterio__codigo_subcriterio",
            "subcriterio__criterio",
            "subcriterio__criterio__codigo_criterio",
        ).order_by("codigo_indicador"),
        label="Indicador",
    )
    elemento_fundamental = forms.ModelChoiceField(
        queryset=ElementoFundamental.objects.select_related("clasificacion").only(
            "id_elemento_fundamental",
            "codigo_elemento",
            "nombre_elemento",
            "clasificacion",
            "clasificacion__codigo",
        ).order_by("codigo_elemento"),
        label="Elemento fundamental",
    )
    clasificacion = forms.ModelChoiceField(
        queryset=ClasificacionDocumento.objects.filter(activo=True).only(
            "id_clasificacion_documento",
            "codigo",
            "nombre",
            "activo",
        ).order_by("codigo"),
        label="Clasificacion documental",
    )
    descripcion_documento = forms.CharField(
        max_length=500,
        required=False,
        label="Descripcion del documento",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    archivo = forms.FileField(label="Archivo")

    def __init__(self, *args, **kwargs):
        ciclo_initial = kwargs.pop("ciclo_initial", None)
        super().__init__(*args, **kwargs)
        if ciclo_initial:
            self.fields["ciclo"].initial = ciclo_initial

    def clean_descripcion_documento(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion_documento"))

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        validate_uploaded_file(archivo, label="archivo")
        return archivo

    def clean(self):
        cleaned_data = super().clean()
        indicador = cleaned_data.get("indicador")
        elemento = cleaned_data.get("elemento_fundamental")
        ciclo = cleaned_data.get("ciclo")

        if ciclo and (getattr(ciclo.estado, "descripcion", "") or "").strip().upper() != "APROBADO":
            self.add_error("ciclo", "Solo se puede cargar documentacion en ciclos aprobados.")

        if indicador and elemento:
            relation_exists = IndicadorElementoFundamental.objects.filter(
                indicador=indicador,
                elemento_fundamental=elemento,
            ).exists()
            if not relation_exists:
                self.add_error(
                    "elemento_fundamental",
                    "El elemento fundamental no pertenece al indicador seleccionado.",
                )
        return cleaned_data
