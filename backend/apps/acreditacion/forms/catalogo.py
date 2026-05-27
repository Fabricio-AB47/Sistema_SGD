from django import forms
from django.db.models import Max

from apps.acreditacion.models import (
    CicloEvaluacion,
    Criterio,
    ElementoFundamental,
    Indicador,
    Subcriterio,
)
from apps.core.models import ClasificacionDocumento, EstadoCiclo
from apps.core.services.upload_security import validate_uploaded_file
from apps.usuarios.models import UsuarioAreaCargo


DATETIME_LOCAL_FORMAT = "%Y-%m-%dT%H:%M"
DATETIME_LOCAL_FORMAT_WITH_SECONDS = "%Y-%m-%dT%H:%M:%S"
DATETIME_INPUT_FORMATS = [
    DATETIME_LOCAL_FORMAT,
    DATETIME_LOCAL_FORMAT_WITH_SECONDS,
]

TEXTAREA_ROWS = 3
TEXTAREA_ATTRS = {"rows": TEXTAREA_ROWS}

AUTHORIZED_DOCUMENT_LABEL = "documento de autorizacion"
AUTHORIZED_DOCUMENT_FIELD_LABEL = "Documento de autorizacion"
AUTHORIZED_DOCUMENT_DESCRIPTION_LABEL = "Descripcion del documento"
SIGNED_DOCUMENT_LABEL = "documento firmado"
SIGNED_DOCUMENT_FIELD_LABEL = "Nuevo documento firmado"

ALLOWED_DOCUMENT_TYPES = ".pdf,.doc,.docx,.xls,.xlsx,.csv"

ERROR_DUPLICATE_CRITERIO_CODE = "Ya existe un criterio con ese codigo."
ERROR_DUPLICATE_SUBCRITERIO_CODE = "Ya existe un subcriterio con ese codigo."
ERROR_DUPLICATE_INDICADOR_CODE = "Ya existe un indicador con ese codigo."
ERROR_DUPLICATE_ELEMENTO_CODE = "Ya existe un elemento con ese codigo."
ERROR_ELEMENT_ALREADY_LINKED = "El elemento ya pertenece al indicador seleccionado."
ERROR_END_DATE_BEFORE_START = "La fecha fin no puede ser menor a la fecha inicio."
ERROR_ASSIGNMENT_REQUIRED = "Debes tener un area/cargo activo para gestionar este recurso."

CLASIFICACION_AUT_CICLO = "AUT_CICLO"
CLASIFICACION_ACTA = "ACTA"
ESTADO_ENVIADO = "ENVIADO"
ESTADO_EN_EJECUCION = "EN_EJECUCION"
ESTADO_APROBADO = "APROBADO"
ESTADO_RECHAZADO = "RECHAZADO"

ESTADOS_FLUJO_CICLO = (
    ESTADO_ENVIADO,
    ESTADO_EN_EJECUCION,
    ESTADO_APROBADO,
    ESTADO_RECHAZADO,
)

ESTADOS_RECTOR_DECISION = (
    ESTADO_APROBADO,
    ESTADO_RECHAZADO,
)


def _normalize_required_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = _normalize_required_text(value or "")
    return normalized or None


def _normalize_code(value: str) -> str:
    return _normalize_required_text(value).upper()


def _normalize_estado(value: str | None) -> str:
    return _normalize_required_text(value or "").upper().replace(" ", "_")


def _filter_estados(queryset, allowed_states: tuple[str, ...]):
    normalized_allowed = {_normalize_estado(item) for item in (allowed_states or ()) if item}
    allowed_ids = [
        estado.pk
        for estado in queryset
        if _normalize_estado(getattr(estado, "descripcion", "")) in normalized_allowed
    ]
    return queryset.filter(pk__in=allowed_ids).order_by("id_estado_ciclo")


def _next_elemento_orden_visual(indicador_id, *, exclude_elemento_id=None) -> int:
    if not indicador_id:
        return 1
    queryset = ElementoFundamental.objects.filter(indicador_id=indicador_id)
    if exclude_elemento_id:
        queryset = queryset.exclude(pk=exclude_elemento_id)
    max_order = queryset.aggregate(max_order=Max("orden_visual"))["max_order"] or 0
    return int(max_order) + 1


def _closest_available_elemento_orden_visual(indicador_id, orden_visual, *, exclude_elemento_id=None) -> int:
    if not indicador_id:
        return int(orden_visual or 1)
    orden = max(int(orden_visual or 1), 1)
    queryset = ElementoFundamental.objects.filter(
        indicador_id=indicador_id,
        orden_visual__isnull=False,
    )
    if exclude_elemento_id:
        queryset = queryset.exclude(pk=exclude_elemento_id)
    used_orders = set(queryset.values_list("orden_visual", flat=True))
    while orden in used_orders:
        orden += 1
    return orden


def get_elemento_orden_visual_defaults():
    indicator_ids = list(
        Indicador.objects.filter(activo=True).values_list("pk", flat=True)
    )
    defaults = {str(indicator_id): 1 for indicator_id in indicator_ids}
    grouped_orders = (
        ElementoFundamental.objects.filter(indicador_id__in=indicator_ids)
        .values("indicador_id")
        .annotate(max_order=Max("orden_visual"))
    )
    for item in grouped_orders:
        defaults[str(item["indicador_id"])] = int(item["max_order"] or 0) + 1
    return defaults


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
            raise forms.ValidationError(ERROR_DUPLICATE_CRITERIO_CODE)
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
            raise forms.ValidationError(ERROR_DUPLICATE_SUBCRITERIO_CODE)
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
            raise forms.ValidationError(ERROR_DUPLICATE_INDICADOR_CODE)
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

        self._initial_indicator_id = self._selected_indicator_id()
        self._initial_orden_visual = None
        if self._initial_indicator_id and not self.is_bound and not self.instance.pk:
            default_order = _next_elemento_orden_visual(self._initial_indicator_id)
            self._initial_orden_visual = default_order
            self.fields["orden_visual"].initial = default_order
            self.initial.setdefault("orden_visual", default_order)
        elif self.instance.pk:
            self._initial_orden_visual = self.instance.orden_visual

        self.fields["tipo_elemento"].initial = self.instance.tipo_elemento or "ESENCIAL"

    def _selected_indicator_id(self):
        if self.is_bound:
            try:
                return int(self.data.get(self.add_prefix("indicador")) or 0) or None
            except (TypeError, ValueError):
                return None
        if self.instance.pk and self.instance.indicador_id:
            return self.instance.indicador_id
        try:
            initial_indicator = self.initial.get("indicador")
            if initial_indicator:
                return getattr(initial_indicator, "pk", initial_indicator)
        except (TypeError, ValueError):
            return None
        first_indicator = self.fields["indicador"].queryset.first()
        return first_indicator.pk if first_indicator else None

    def clean_orden_visual(self):
        indicador = self.cleaned_data.get("indicador")
        if indicador is None:
            return self.cleaned_data.get("orden_visual")

        submitted_order = self.cleaned_data.get("orden_visual")
        if submitted_order in (None, ""):
            return _next_elemento_orden_visual(
                indicador.pk,
                exclude_elemento_id=self.instance.pk,
            )

        if (
            self._initial_indicator_id
            and self._initial_indicator_id != indicador.pk
            and self._initial_orden_visual == submitted_order
        ):
            return _next_elemento_orden_visual(
                indicador.pk,
                exclude_elemento_id=self.instance.pk,
            )

        return _closest_available_elemento_orden_visual(
            indicador.pk,
            submitted_order,
            exclude_elemento_id=self.instance.pk,
        )

    def clean_codigo_elemento(self):
        codigo = _normalize_code(self.cleaned_data["codigo_elemento"])
        queryset = ElementoFundamental.objects.filter(codigo_elemento__iexact=codigo)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError(ERROR_DUPLICATE_ELEMENTO_CODE)
        return codigo

    def clean_nombre_elemento(self):
        return _normalize_required_text(self.cleaned_data["nombre_elemento"])

    def clean_descripcion(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion"))

    def clean_medio_verificacion(self):
        return _normalize_optional_text(self.cleaned_data.get("medio_verificacion"))


class IndicadorElementoForm(forms.Form):
    indicador = forms.ModelChoiceField(
        queryset=Indicador.objects.select_related("subcriterio__criterio").order_by(
            "codigo_indicador"
        ),
        label="Indicador",
    )
    elemento_fundamental = forms.ModelChoiceField(
        queryset=ElementoFundamental.objects.select_related("indicador").order_by(
            "codigo_elemento"
        ),
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
            self.fields["indicador"].queryset = Indicador.objects.filter(
                pk=fixed_indicador.pk
            )
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
        if (
            indicador
            and elemento_fundamental
            and elemento_fundamental.indicador_id == indicador.pk
        ):
            self.add_error(
                "elemento_fundamental",
                ERROR_ELEMENT_ALREADY_LINKED,
            )
        return cleaned_data


class CicloEvaluacionForm(forms.ModelForm):
    seleccionar_todos_indicadores = forms.BooleanField(
        required=False,
        initial=True,
        label="Seleccionar todos los indicadores",
    )
    indicadores_evaluar = forms.ModelMultipleChoiceField(
        queryset=Indicador.objects.none(),
        required=False,
        label="Indicadores a evaluar",
    )
    estado = forms.ModelChoiceField(
        queryset=EstadoCiclo.objects.filter(activo=True)
        .only("id_estado_ciclo", "descripcion", "activo")
        .order_by("id_estado_ciclo"),
        label="Estado del ciclo",
    )
    clasificacion = forms.ModelChoiceField(
        queryset=ClasificacionDocumento.objects.filter(activo=True)
        .only("id_clasificacion_documento", "codigo", "nombre", "activo")
        .order_by("codigo"),
        label="Clasificacion del documento",
    )
    descripcion_documento = forms.CharField(
        max_length=500,
        required=False,
        label=AUTHORIZED_DOCUMENT_DESCRIPTION_LABEL,
        widget=forms.Textarea(attrs=TEXTAREA_ATTRS),
    )
    archivo = forms.FileField(label=AUTHORIZED_DOCUMENT_FIELD_LABEL)

    class Meta:
        model = CicloEvaluacion
        fields = ["nombre", "descripcion", "anio", "fecha_inicio", "fecha_fin", "estado"]
        widgets = {
            "fecha_inicio": forms.DateTimeInput(
                format=DATETIME_LOCAL_FORMAT,
                attrs={"type": "datetime-local"},
            ),
            "fecha_fin": forms.DateTimeInput(
                format=DATETIME_LOCAL_FORMAT,
                attrs={"type": "datetime-local"},
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        if self.usuario_id and self.active_assignment is None:
            raise forms.ValidationError(ERROR_ASSIGNMENT_REQUIRED)
        fecha_inicio = cleaned_data.get("fecha_inicio")
        fecha_fin = cleaned_data.get("fecha_fin")
        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            self.add_error("fecha_fin", ERROR_END_DATE_BEFORE_START)
        return cleaned_data

    def __init__(self, *args, **kwargs):
        self.usuario_id = kwargs.pop("usuario_id", None)
        self.assignment_id = kwargs.pop("assignment_id", None)
        super().__init__(*args, **kwargs)
        self.fields["anio"].label = "Año"
        self.fields["fecha_inicio"].input_formats = DATETIME_INPUT_FORMATS
        self.fields["fecha_fin"].input_formats = DATETIME_INPUT_FORMATS
        self.fields["archivo"].widget.attrs.update({"accept": ALLOWED_DOCUMENT_TYPES})
        self.fields["indicadores_evaluar"].queryset = (
            Indicador.objects.select_related("subcriterio__criterio", "tipo_indicador")
            .filter(
                activo=True,
                subcriterio__activo=True,
                subcriterio__criterio__activo=True,
            )
            .order_by(
                "subcriterio__criterio__orden_visual",
                "subcriterio__criterio__codigo_criterio",
                "subcriterio__orden_visual",
                "subcriterio__codigo_subcriterio",
                "orden_visual",
                "codigo_indicador",
            )
        )
        self.fields["indicadores_evaluar"].widget = forms.CheckboxSelectMultiple()
        self.fields["indicadores_evaluar"].label_from_instance = (
            lambda indicador: f"{indicador.codigo_indicador} - {indicador.nombre_indicador}"
        )
        if not self.is_bound:
            self.fields["indicadores_evaluar"].initial = list(
                self.fields["indicadores_evaluar"].queryset.values_list("pk", flat=True)
            )

        self.active_assignment = None
        if self.usuario_id:
            assignments = UsuarioAreaCargo.objects.select_related("area", "cargo").filter(
                usuario_id=self.usuario_id,
                activo=True,
                area__activo=True,
                cargo__activo=True,
            )
            if self.assignment_id:
                self.active_assignment = assignments.filter(pk=self.assignment_id).first()
            if self.active_assignment is None:
                self.active_assignment = assignments.first()

        clasificacion = self.fields["clasificacion"].queryset.filter(
            codigo=CLASIFICACION_AUT_CICLO
        ).first()
        if clasificacion is None:
            clasificacion = self.fields["clasificacion"].queryset.filter(
                codigo=CLASIFICACION_ACTA
            ).first()
        if clasificacion:
            self.fields["clasificacion"].initial = clasificacion

        estado_inicial = self.fields["estado"].queryset.filter(
            descripcion__iexact=ESTADO_ENVIADO
        ).first()
        if estado_inicial and not self.instance.pk:
            self.fields["estado"].initial = estado_inicial

    def clean_nombre(self):
        return _normalize_required_text(self.cleaned_data["nombre"])

    def clean_descripcion(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion"))

    def clean_descripcion_documento(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion_documento"))

    def clean_indicadores_evaluar(self):
        indicadores = self.cleaned_data.get("indicadores_evaluar")
        select_all = bool(self.cleaned_data.get("seleccionar_todos_indicadores"))
        if select_all:
            return self.fields["indicadores_evaluar"].queryset
        if not indicadores:
            raise forms.ValidationError(
                "Selecciona al menos un indicador o marca la opcion de seleccionar todo."
            )
        return indicadores

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        validate_uploaded_file(archivo, label=AUTHORIZED_DOCUMENT_LABEL)
        return archivo


class CacesCatalogSyncForm(forms.Form):
    sincronizar = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.HiddenInput,
        label="Crear estructura faltante desde modelo CACES",
    )
    asegurar_carpetas_existentes = forms.BooleanField(
        required=False,
        initial=False,
        label="Validar carpetas de registros existentes",
    )

    def clean_sincronizar(self):
        return True


class CicloEstadoUpdateForm(forms.Form):
    ciclo_id = forms.IntegerField(widget=forms.HiddenInput)
    estado = forms.ModelChoiceField(
        queryset=EstadoCiclo.objects.filter(activo=True)
        .only("id_estado_ciclo", "descripcion", "activo")
        .order_by("id_estado_ciclo"),
        label="Estado",
    )
    observacion_aprobacion = forms.CharField(
        max_length=1000,
        required=False,
        label="Observacion",
        widget=forms.Textarea(attrs=TEXTAREA_ATTRS),
    )

    def __init__(self, *args, allowed_states: tuple[str, ...] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["estado"].queryset = _filter_estados(
            self.fields["estado"].queryset,
            allowed_states or ESTADOS_FLUJO_CICLO,
        )

    def clean_observacion_aprobacion(self):
        return _normalize_optional_text(self.cleaned_data.get("observacion_aprobacion"))


class CicloAuthorizationRevisionForm(forms.Form):
    descripcion_documento = forms.CharField(
        max_length=500,
        required=False,
        label="Descripcion de la nueva version",
        widget=forms.Textarea(attrs=TEXTAREA_ATTRS),
    )
    archivo = forms.FileField(label=SIGNED_DOCUMENT_FIELD_LABEL)

    def clean_descripcion_documento(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion_documento"))

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        validate_uploaded_file(archivo, label=SIGNED_DOCUMENT_LABEL)
        return archivo


class CicloEstadoAutorizacionForm(forms.Form):
    ciclo_id = forms.IntegerField(widget=forms.HiddenInput)
    estado = forms.ModelChoiceField(
        queryset=EstadoCiclo.objects.filter(activo=True)
        .only("id_estado_ciclo", "descripcion", "activo")
        .order_by("id_estado_ciclo"),
        label="Estado",
    )
    observacion_aprobacion = forms.CharField(
        max_length=1000,
        required=False,
        label="Observacion",
        widget=forms.Textarea(attrs=TEXTAREA_ATTRS),
    )
    descripcion_documento = forms.CharField(
        max_length=500,
        required=False,
        label="Descripcion de la nueva version",
        widget=forms.Textarea(attrs=TEXTAREA_ATTRS),
    )
    archivo = forms.FileField(
        label=SIGNED_DOCUMENT_FIELD_LABEL,
        required=False,
    )

    def __init__(self, *args, allowed_states: tuple[str, ...] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["estado"].queryset = _filter_estados(
            self.fields["estado"].queryset,
            allowed_states or ESTADOS_FLUJO_CICLO,
        )

    def clean_observacion_aprobacion(self):
        return _normalize_optional_text(self.cleaned_data.get("observacion_aprobacion"))

    def clean_descripcion_documento(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion_documento"))

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        if archivo:
            validate_uploaded_file(archivo, label=SIGNED_DOCUMENT_LABEL)
        return archivo
