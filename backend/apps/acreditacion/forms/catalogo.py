from django import forms

from apps.acreditacion.models import (
    CicloEvaluacion,
    Criterio,
    ElementoFundamental,
    Indicador,
    IndicadorElementoFundamental,
    Subcriterio,
)
from apps.core.services.upload_security import validate_uploaded_file
from apps.core.models import ClasificacionDocumento, EstadoCiclo


def _normalize_required_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = _normalize_required_text(value or "")
    return normalized or None


def _normalize_code(value: str) -> str:
    return _normalize_required_text(value).upper()


class CriterioForm(forms.ModelForm):
    class Meta:
        model = Criterio
        fields = ["codigo_criterio", "nombre_criterio", "descripcion", "orden_visual", "activo"]

    def clean_codigo_criterio(self):
        codigo = _normalize_code(self.cleaned_data["codigo_criterio"])
        queryset = Criterio.objects.filter(codigo_criterio__iexact=codigo)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("Ya existe un criterio con ese codigo.")
        return codigo

    def clean_nombre_criterio(self):
        return _normalize_required_text(self.cleaned_data["nombre_criterio"])

    def clean_descripcion(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion"))


class SubcriterioForm(forms.ModelForm):
    class Meta:
        model = Subcriterio
        fields = ["criterio", "codigo_subcriterio", "nombre_subcriterio", "descripcion", "orden_visual", "activo"]

    def clean_codigo_subcriterio(self):
        codigo = _normalize_code(self.cleaned_data["codigo_subcriterio"])
        queryset = Subcriterio.objects.filter(codigo_subcriterio__iexact=codigo)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("Ya existe un subcriterio con ese codigo.")
        return codigo

    def clean_nombre_subcriterio(self):
        return _normalize_required_text(self.cleaned_data["nombre_subcriterio"])

    def clean_descripcion(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion"))


class IndicadorForm(forms.ModelForm):
    class Meta:
        model = Indicador
        fields = [
            "subcriterio",
            "tipo_indicador",
            "codigo_indicador",
            "nombre_indicador",
            "descripcion",
            "medio_verificacion",
            "ponderacion",
            "orden_visual",
            "activo",
        ]

    def clean_codigo_indicador(self):
        codigo = _normalize_code(self.cleaned_data["codigo_indicador"])
        queryset = Indicador.objects.filter(codigo_indicador__iexact=codigo)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("Ya existe un indicador con ese codigo.")
        return codigo

    def clean_nombre_indicador(self):
        return _normalize_required_text(self.cleaned_data["nombre_indicador"])

    def clean_descripcion(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion"))

    def clean_medio_verificacion(self):
        return _normalize_optional_text(self.cleaned_data.get("medio_verificacion"))


class ElementoFundamentalForm(forms.ModelForm):
    class Meta:
        model = ElementoFundamental
        fields = [
            "clasificacion",
            "codigo_elemento",
            "nombre_elemento",
            "descripcion",
            "medio_verificacion",
            "orden_visual",
            "activo",
        ]

    def clean_codigo_elemento(self):
        codigo = _normalize_code(self.cleaned_data["codigo_elemento"])
        queryset = ElementoFundamental.objects.filter(codigo_elemento__iexact=codigo)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("Ya existe un elemento con ese codigo.")
        return codigo

    def clean_nombre_elemento(self):
        return _normalize_required_text(self.cleaned_data["nombre_elemento"])

    def clean_descripcion(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion"))

    def clean_medio_verificacion(self):
        return _normalize_optional_text(self.cleaned_data.get("medio_verificacion"))


class IndicadorElementoForm(forms.Form):
    indicador = forms.ModelChoiceField(
        queryset=Indicador.objects.select_related("subcriterio__criterio").order_by("codigo_indicador"),
        label="Indicador",
    )
    elemento_fundamental = forms.ModelChoiceField(
        queryset=ElementoFundamental.objects.select_related("clasificacion").order_by("codigo_elemento"),
        label="Elemento fundamental",
    )

    def clean(self):
        cleaned_data = super().clean()
        indicador = cleaned_data.get("indicador")
        elemento_fundamental = cleaned_data.get("elemento_fundamental")
        if indicador and elemento_fundamental:
            exists = IndicadorElementoFundamental.objects.filter(
                indicador=indicador,
                elemento_fundamental=elemento_fundamental,
            ).exists()
            if exists:
                self.add_error("elemento_fundamental", "La relacion ya existe.")
        return cleaned_data


class CicloEvaluacionForm(forms.ModelForm):
    estado = forms.ModelChoiceField(
        queryset=EstadoCiclo.objects.filter(activo=True).only(
            "id_estado_ciclo",
            "descripcion",
            "activo",
        ).order_by("id_estado_ciclo"),
        label="Estado del ciclo",
    )
    clasificacion = forms.ModelChoiceField(
        queryset=ClasificacionDocumento.objects.filter(activo=True).only(
            "id_clasificacion_documento",
            "codigo",
            "nombre",
            "activo",
        ).order_by("codigo"),
        label="Clasificacion del documento",
    )
    descripcion_documento = forms.CharField(
        max_length=500,
        required=False,
        label="Descripcion del documento",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    archivo = forms.FileField(label="Documento de autorizacion")

    class Meta:
        model = CicloEvaluacion
        fields = ["nombre", "descripcion", "anio", "fecha_inicio", "fecha_fin", "estado"]
        widgets = {
            "fecha_inicio": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
            "fecha_fin": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get("fecha_inicio")
        fecha_fin = cleaned_data.get("fecha_fin")
        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            self.add_error("fecha_fin", "La fecha fin no puede ser menor a la fecha inicio.")
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["anio"].label = "Año"
        self.fields["fecha_inicio"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
        self.fields["fecha_fin"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
        self.fields["archivo"].widget.attrs.update({"accept": ".pdf,.doc,.docx,.xls,.xlsx,.csv"})
        clasificacion = self.fields["clasificacion"].queryset.filter(codigo="ACTA").first()
        if clasificacion:
            self.fields["clasificacion"].initial = clasificacion

    def clean_nombre(self):
        return _normalize_required_text(self.cleaned_data["nombre"])

    def clean_descripcion(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion"))

    def clean_descripcion_documento(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion_documento"))

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        validate_uploaded_file(archivo, label="documento de autorizacion")
        return archivo


class CicloEstadoUpdateForm(forms.Form):
    ciclo_id = forms.IntegerField(widget=forms.HiddenInput)
    estado = forms.ModelChoiceField(
        queryset=EstadoCiclo.objects.filter(activo=True).only(
            "id_estado_ciclo",
            "descripcion",
            "activo",
        ).order_by("id_estado_ciclo"),
        label="Estado",
    )


class CicloAuthorizationRevisionForm(forms.Form):
    descripcion_documento = forms.CharField(
        max_length=500,
        required=False,
        label="Descripcion de la nueva version",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    archivo = forms.FileField(label="Nuevo documento firmado")

    def clean_descripcion_documento(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion_documento"))

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        validate_uploaded_file(archivo, label="documento firmado")
        return archivo
