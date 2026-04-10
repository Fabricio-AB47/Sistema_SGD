from django import forms

from apps.acreditacion.models import (
    CicloEvaluacion,
    Criterio,
    ElementoFundamental,
    Indicador,
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
        fields = [
            "codigo_criterio",
            "nombre_criterio",
            "descripcion",
            "ponderacion",
            "orden_visual",
            "activo",
        ]

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
        fields = [
            "criterio",
            "codigo_subcriterio",
            "nombre_subcriterio",
            "descripcion",
            "ponderacion",
            "orden_visual",
            "activo",
        ]

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
            "indicador",
            "clasificacion",
            "codigo_elemento",
            "nombre_elemento",
            "descripcion",
            "medio_verificacion",
            "tipo_elemento",
            "orden_visual",
            "activo",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["indicador"].queryset = Indicador.objects.select_related(
            "subcriterio__criterio"
        ).order_by(
            "subcriterio__criterio__codigo_criterio",
            "subcriterio__codigo_subcriterio",
            "codigo_indicador",
        )
        self.fields["indicador"].label_from_instance = (
            lambda indicador: (
                f"{indicador.subcriterio.criterio.codigo_criterio} / "
                f"{indicador.subcriterio.codigo_subcriterio} / "
                f"{indicador.codigo_indicador} - {indicador.nombre_indicador}"
            )
        )
        self.fields["tipo_elemento"].initial = self.instance.tipo_elemento or "ESENCIAL"

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
        queryset=ElementoFundamental.objects.select_related("indicador").order_by("codigo_elemento"),
        label="Elemento fundamental",
    )

    def __init__(self, *args, **kwargs):
        fixed_indicador = kwargs.pop("fixed_indicador", None)
        super().__init__(*args, **kwargs)
        self.fields["elemento_fundamental"].label_from_instance = self._elemento_label
        if fixed_indicador is not None:
            self.fields["elemento_fundamental"].queryset = self.fields[
                "elemento_fundamental"
            ].queryset.exclude(indicador_id=fixed_indicador.pk)
            self.fields["indicador"].queryset = Indicador.objects.filter(pk=fixed_indicador.pk)
            self.fields["indicador"].initial = fixed_indicador
            self.fields["indicador"].widget = forms.HiddenInput()

    @staticmethod
    def _elemento_label(elemento):
        indicador = getattr(elemento, "indicador", None)
        if indicador is None:
            indicador_text = "SIN INDICADOR"
        else:
            indicador_text = (
                f"{getattr(indicador, 'codigo_indicador', '')} - "
                f"{getattr(indicador, 'nombre_indicador', '')}"
            )
        return (
            f"IND {getattr(elemento, 'indicador_id', None) or 'NULL'} | "
            f"{indicador_text} | "
            f"{elemento.codigo_elemento} - {elemento.nombre_elemento}"
        )

    def clean(self):
        cleaned_data = super().clean()
        indicador = cleaned_data.get("indicador")
        elemento_fundamental = cleaned_data.get("elemento_fundamental")
        if indicador and elemento_fundamental and elemento_fundamental.indicador_id == indicador.pk:
            self.add_error("elemento_fundamental", "El elemento ya pertenece al indicador seleccionado.")
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
        clasificacion = self.fields["clasificacion"].queryset.filter(codigo="AUT_CICLO").first()
        if clasificacion is None:
            clasificacion = self.fields["clasificacion"].queryset.filter(codigo="ACTA").first()
        if clasificacion:
            self.fields["clasificacion"].initial = clasificacion
        estado_inicial = self.fields["estado"].queryset.filter(descripcion__iexact="ENVIADO").first()
        if estado_inicial and not self.instance.pk:
            self.fields["estado"].initial = estado_inicial

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
    observacion_aprobacion = forms.CharField(
        max_length=1000,
        required=False,
        label="Observacion",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_observacion_aprobacion(self):
        return _normalize_optional_text(self.cleaned_data.get("observacion_aprobacion"))


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
