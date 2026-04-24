from collections import OrderedDict
from datetime import datetime, time

from django import forms
from django.db.models import Q
from django.utils import timezone

from apps.acreditacion.models import CicloEvaluacion, ElementoFundamental, Indicador
from apps.core.models import EstadoTareaEvidencia
from apps.evaluacion.models import TareaEvidencia
from apps.usuarios.models import AreaInstitucional, Usuario, UsuarioAreaCargo


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().split())
    return normalized or None


def _date_to_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    combined = datetime.combine(value, time(hour=23, minute=59, second=59))
    return timezone.make_aware(combined)


def _resolve_default_task_state():
    return (
        EstadoTareaEvidencia.objects.filter(activo=True, descripcion__iexact="PENDIENTE").first()
        or EstadoTareaEvidencia.objects.filter(activo=True, descripcion__iexact="ASIGNADA").first()
        or EstadoTareaEvidencia.objects.filter(activo=True).order_by("descripcion").first()
    )


def _director_or_manager_assignment_queryset(*, area_id=None):
    area_id = getattr(area_id, "pk", area_id)
    queryset = (
        UsuarioAreaCargo.objects.select_related("usuario", "area", "cargo")
        .filter(
            activo=True,
            area__activo=True,
            cargo__activo=True,
            usuario__activo=True,
        )
        .filter(
            Q(cargo__aprueba_interno=True)
            | Q(cargo__nivel_jerarquico=1)
            | Q(cargo__nombre_cargo__icontains="DIRECTOR")
            | Q(cargo__nombre_cargo__icontains="JEFE")
        )
        .order_by(
            "area__nombre_area",
            "cargo__nivel_jerarquico",
            "cargo__nombre_cargo",
            "usuario__primer_apellido",
            "usuario__primer_nombre",
        )
    )
    if area_id:
        queryset = queryset.filter(area_id=area_id)
    return queryset


def _build_responsable_queryset(*, area_id=None):
    area_id = getattr(area_id, "pk", area_id)
    assignments = list(_director_or_manager_assignment_queryset(area_id=area_id))
    if not assignments and area_id:
        return Usuario.objects.none(), {}
    if not assignments:
        assignments = list(_director_or_manager_assignment_queryset())
    if not assignments:
        return (
            Usuario.objects.filter(activo=True).order_by("primer_apellido", "primer_nombre"),
            {},
        )

    summaries = OrderedDict()
    for assignment in assignments:
        bucket = summaries.setdefault(
            assignment.usuario_id,
            {
                "usuario": assignment.usuario,
                "segments": [],
            },
        )
        bucket["segments"].append(
            f"{assignment.area.codigo_area} - {assignment.area.nombre_area} / {assignment.cargo.nombre_cargo}"
        )

    user_ids = tuple(summaries.keys())
    director_queryset = Usuario.objects.filter(activo=True, pk__in=user_ids).order_by(
        "primer_apellido",
        "primer_nombre",
    )

    labels = {}
    for usuario in director_queryset:
        segments = summaries.get(usuario.pk, {}).get("segments", [])
        preview = ", ".join(segments[:2])
        if len(segments) > 2:
            preview = f"{preview} (+{len(segments) - 2})"
        labels[usuario.pk] = (
            f"{usuario.nombre_completo or usuario.correo} · {preview}"
            if preview
            else (usuario.nombre_completo or usuario.correo)
        )

    return director_queryset, labels


class _ResponsableAreaMixin:
    def _configure_responsable_fields(self):
        selected_area_id = (self.data.get("area") if self.is_bound else None) or self.initial.get("area")
        director_queryset, labels = _build_responsable_queryset(area_id=selected_area_id)
        self.fields["usuario_responsable"].queryset = director_queryset
        self.fields["usuario_responsable"].label_from_instance = (
            lambda value: labels.get(value.pk, value.nombre_completo or value.correo)
        )


class TareaEvidenciaForm(_ResponsableAreaMixin, forms.Form):
    ciclo = forms.ModelChoiceField(
        queryset=CicloEvaluacion.objects.select_related("estado").order_by("-fecha_inicio", "-id_ciclo"),
        label="Ciclo",
    )
    area = forms.ModelChoiceField(
        queryset=AreaInstitucional.objects.filter(activo=True).order_by("nombre_area"),
        required=False,
        label="Area responsable",
    )
    indicador = forms.ModelChoiceField(
        queryset=Indicador.objects.select_related("subcriterio__criterio")
        .filter(activo=True)
        .order_by("codigo_indicador"),
        label="Indicador",
    )
    elemento_fundamental = forms.ModelChoiceField(
        queryset=ElementoFundamental.objects.select_related("indicador")
        .filter(activo=True)
        .order_by("codigo_elemento"),
        label="Elemento fundamental",
    )
    usuario_responsable = forms.ModelChoiceField(
        queryset=Usuario.objects.none(),
        label="Director o jefe de area",
    )
    estado = forms.ModelChoiceField(
        queryset=EstadoTareaEvidencia.objects.filter(activo=True).order_by("descripcion"),
        label="Estado",
    )
    fecha_limite = forms.DateField(
        required=False,
        label="Fecha limite",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    prioridad = forms.ChoiceField(
        required=False,
        choices=(("", "Selecciona prioridad"), *TareaEvidencia.PRIORIDAD_CHOICES),
        label="Prioridad",
    )
    observacion = forms.CharField(
        max_length=1000,
        required=False,
        label="Observacion",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_responsable_fields()

        default_state = _resolve_default_task_state()
        if default_state and not self.is_bound:
            self.fields["estado"].initial = default_state

    def clean_observacion(self):
        return _normalize_optional_text(self.cleaned_data.get("observacion"))

    def clean_fecha_limite(self):
        return _date_to_datetime(self.cleaned_data.get("fecha_limite"))

    def clean(self):
        cleaned_data = super().clean()
        area = cleaned_data.get("area")
        indicador = cleaned_data.get("indicador")
        elemento = cleaned_data.get("elemento_fundamental")
        usuario_responsable = cleaned_data.get("usuario_responsable")
        if indicador and elemento and elemento.indicador_id != indicador.pk:
            self.add_error(
                "elemento_fundamental",
                "El elemento fundamental seleccionado no pertenece al indicador.",
            )
        if (
            area
            and usuario_responsable
            and not _director_or_manager_assignment_queryset(area_id=area.pk)
            .filter(usuario_id=usuario_responsable.pk)
            .exists()
        ):
            self.add_error(
                "usuario_responsable",
                "El responsable seleccionado no tiene un cargo directivo o de jefatura activo en el area.",
            )
        return cleaned_data


class TareaEvidenciaBulkForm(_ResponsableAreaMixin, forms.Form):
    ciclo = forms.ModelChoiceField(
        queryset=CicloEvaluacion.objects.select_related("estado").order_by("-fecha_inicio", "-id_ciclo"),
        label="Ciclo",
    )
    area = forms.ModelChoiceField(
        queryset=AreaInstitucional.objects.filter(activo=True).order_by("nombre_area"),
        required=False,
        label="Area responsable",
    )
    usuario_responsable = forms.ModelChoiceField(
        queryset=Usuario.objects.none(),
        label="Director o jefe de area",
    )
    estado = forms.ModelChoiceField(
        queryset=EstadoTareaEvidencia.objects.filter(activo=True).order_by("descripcion"),
        label="Estado",
    )
    fecha_limite = forms.DateField(
        required=False,
        label="Fecha limite",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    prioridad = forms.ChoiceField(
        required=False,
        choices=(("", "Selecciona prioridad"), *TareaEvidencia.PRIORIDAD_CHOICES),
        label="Prioridad",
    )
    observacion = forms.CharField(
        max_length=1000,
        required=False,
        label="Observacion",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    elementos_fundamentales = forms.ModelMultipleChoiceField(
        queryset=ElementoFundamental.objects.none(),
        required=False,
        label="Elementos fundamentales",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_responsable_fields()

        self.fields["elementos_fundamentales"].queryset = (
            ElementoFundamental.objects.select_related("indicador")
            .filter(activo=True, indicador__activo=True)
            .order_by("indicador__codigo_indicador", "orden_visual", "codigo_elemento")
        )

        default_state = _resolve_default_task_state()
        if default_state and not self.is_bound:
            self.fields["estado"].initial = default_state

    def clean_observacion(self):
        return _normalize_optional_text(self.cleaned_data.get("observacion"))

    def clean_fecha_limite(self):
        return _date_to_datetime(self.cleaned_data.get("fecha_limite"))

    def clean(self):
        cleaned_data = super().clean()
        area = cleaned_data.get("area")
        usuario_responsable = cleaned_data.get("usuario_responsable")
        elementos = cleaned_data.get("elementos_fundamentales")
        if not elementos:
            self.add_error(
                "elementos_fundamentales",
                "Debes seleccionar al menos un elemento fundamental para la asignacion parcial.",
            )
        if (
            area
            and usuario_responsable
            and not _director_or_manager_assignment_queryset(area_id=area.pk)
            .filter(usuario_id=usuario_responsable.pk)
            .exists()
        ):
            self.add_error(
                "usuario_responsable",
                "El responsable seleccionado no tiene un cargo directivo o de jefatura activo en el area.",
            )
        return cleaned_data


class CerrarTareaEvidenciaForm(forms.Form):
    tarea_id = forms.IntegerField(widget=forms.HiddenInput)
    resultado_tarea = forms.CharField(
        max_length=1000,
        label="Resultado",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_resultado_tarea(self):
        resultado = _normalize_optional_text(self.cleaned_data.get("resultado_tarea"))
        if not resultado:
            raise forms.ValidationError("Debes registrar el resultado de cierre.")
        return resultado
