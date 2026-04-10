from django import forms

from apps.acreditacion.models import (
    CicloEvaluacion,
    ElementoFundamental,
    Indicador,
    RolIndicador,
)
from apps.permisos.models import Permiso, Rol
from apps.usuarios.models import Usuario


class RolGestionForm(forms.ModelForm):
    class Meta:
        model = Rol
        fields = ["nombre_rol", "descripcion", "acceso_global", "activo"]

    def clean_nombre_rol(self):
        nombre = self.cleaned_data["nombre_rol"].strip()
        qs = Rol.objects.filter(nombre_rol__iexact=nombre)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un rol con ese nombre.")
        return nombre


class PermisoGestionForm(forms.ModelForm):
    class Meta:
        model = Permiso
        fields = ["codigo_permiso", "descripcion", "modulo", "activo"]

    def clean_codigo_permiso(self):
        codigo = self.cleaned_data["codigo_permiso"].strip().upper()
        qs = Permiso.objects.filter(codigo_permiso__iexact=codigo)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un permiso con ese codigo.")
        return codigo

    def clean_modulo(self):
        return self.cleaned_data["modulo"].strip().title()


class RolPermisoForm(forms.Form):
    rol = forms.ModelChoiceField(
        queryset=Rol.objects.filter(activo=True).order_by("nombre_rol"),
        label="Rol",
    )
    permisos = forms.ModelMultipleChoiceField(
        queryset=Permiso.objects.filter(activo=True).order_by("modulo", "codigo_permiso"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Permisos",
    )

    def __init__(self, *args, role=None, **kwargs):
        super().__init__(*args, **kwargs)
        if role is not None:
            self.fields["rol"].initial = role
            self.fields["permisos"].initial = role.permisos_asignados.values_list(
                "permiso_id", flat=True
            )


class UsuarioRolGestionForm(forms.Form):
    usuario = forms.ModelChoiceField(
        queryset=Usuario.objects.filter(activo=True).order_by("primer_apellido", "primer_nombre"),
        label="Usuario",
    )
    rol = forms.ModelChoiceField(
        queryset=Rol.objects.filter(activo=True).order_by("nombre_rol"),
        label="Rol",
    )
    activo = forms.BooleanField(required=False, initial=True, label="Asignacion activa")


class RolIndicadorGestionForm(forms.Form):
    rol = forms.ModelChoiceField(
        queryset=Rol.objects.filter(activo=True).order_by("nombre_rol"),
        label="Rol",
    )
    indicador = forms.ModelChoiceField(
        queryset=Indicador.objects.filter(activo=True)
        .select_related("subcriterio__criterio")
        .order_by("codigo_indicador"),
        label="Indicador",
    )
    ciclo = forms.ModelChoiceField(
        queryset=CicloEvaluacion.objects.select_related("estado").order_by("-fecha_inicio"),
        label="Ciclo",
    )
    acceso_total = forms.BooleanField(required=False, initial=False, label="Acceso total")


class RolIndicadorElementoGestionForm(forms.Form):
    rol_indicador = forms.ModelChoiceField(
        queryset=RolIndicador.objects.filter(activo=True)
        .select_related("rol", "indicador", "ciclo")
        .order_by("rol__nombre_rol", "indicador__codigo_indicador"),
        label="Acceso a evaluacion",
    )
    elemento_fundamental = forms.ModelChoiceField(
        queryset=ElementoFundamental.objects.filter(activo=True).order_by("codigo_elemento"),
        label="Elemento fundamental",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show enough context in the selector to avoid assigning an element to the wrong cycle.
        self.fields["rol_indicador"].label_from_instance = (
            lambda acceso: (
                f"{acceso.rol.nombre_rol} | "
                f"{acceso.indicador.codigo_indicador} | "
                f"{acceso.ciclo.nombre}"
            )
        )
        self.fields["elemento_fundamental"].label_from_instance = (
            lambda elemento: f"{elemento.codigo_elemento} - {elemento.nombre_elemento}"
        )

    def clean(self):
        cleaned = super().clean()
        rol_indicador = cleaned.get("rol_indicador")
        elemento = cleaned.get("elemento_fundamental")
        if not rol_indicador or not elemento:
            return cleaned

        if elemento.indicador_id != rol_indicador.indicador_id:
            raise forms.ValidationError(
                "El elemento fundamental seleccionado no pertenece al indicador elegido."
            )
        return cleaned


class RolEstructuraAccesoForm(forms.Form):
    rol = forms.ModelChoiceField(
        queryset=Rol.objects.filter(activo=True).order_by("nombre_rol"),
        label="Rol",
    )
    ciclo = forms.ModelChoiceField(
        queryset=CicloEvaluacion.objects.select_related("estado").order_by("-fecha_inicio"),
        label="Ciclo",
    )
    indicadores = forms.MultipleChoiceField(
        required=False,
        choices=(),
        widget=forms.MultipleHiddenInput,
    )
    accesos_totales = forms.MultipleChoiceField(
        required=False,
        choices=(),
        widget=forms.MultipleHiddenInput,
    )
    elementos = forms.MultipleChoiceField(
        required=False,
        choices=(),
        widget=forms.MultipleHiddenInput,
    )

    def __init__(self, *args, indicator_groups=None, **kwargs):
        super().__init__(*args, **kwargs)
        indicator_groups = indicator_groups or []
        self._indicator_map = {}
        self._indicator_element_map = {}
        self._element_indicator_map = {}

        indicator_choices = []
        element_choices = []
        for group in indicator_groups:
            indicador = group["indicator"]
            self._indicator_map[indicador.pk] = indicador
            indicator_choices.append((str(indicador.pk), indicador.codigo_indicador))
            element_ids = set()
            for elemento in group["elements"]:
                element_choices.append((str(elemento.pk), elemento.codigo_elemento))
                self._element_indicator_map[elemento.pk] = indicador.pk
                element_ids.add(elemento.pk)
            self._indicator_element_map[indicador.pk] = element_ids

        self.fields["indicadores"].choices = indicator_choices
        self.fields["accesos_totales"].choices = indicator_choices
        self.fields["elementos"].choices = element_choices

    def clean(self):
        cleaned = super().clean()
        indicator_ids = {int(value) for value in cleaned.get("indicadores", [])}
        total_ids = {int(value) for value in cleaned.get("accesos_totales", [])}
        element_ids = {int(value) for value in cleaned.get("elementos", [])}

        valid_indicator_ids = set(self._indicator_map)
        valid_element_ids = set(self._element_indicator_map)

        indicator_ids &= valid_indicator_ids
        total_ids &= valid_indicator_ids
        element_ids &= valid_element_ids

        for element_id in list(element_ids):
            indicator_ids.add(self._element_indicator_map[element_id])

        for indicator_id in list(total_ids):
            indicator_ids.add(indicator_id)
            element_ids.update(self._indicator_element_map.get(indicator_id, set()))

        cleaned["indicadores"] = sorted(indicator_ids)
        cleaned["accesos_totales"] = sorted(total_ids)
        cleaned["elementos"] = sorted(element_ids)
        return cleaned
