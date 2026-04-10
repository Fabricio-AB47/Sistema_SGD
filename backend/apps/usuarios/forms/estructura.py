from django import forms

from apps.usuarios.models import AreaInstitucional, CargoArea, Usuario, UsuarioSupervisor


class AreaInstitucionalForm(forms.ModelForm):
    class Meta:
        model = AreaInstitucional
        fields = ["codigo_area", "nombre_area", "activo"]

    def clean_codigo_area(self):
        codigo = (self.cleaned_data["codigo_area"] or "").strip().upper()
        if AreaInstitucional.objects.filter(codigo_area__iexact=codigo).exists():
            raise forms.ValidationError("Ya existe un area con este codigo.")
        return codigo


class CargoAreaForm(forms.ModelForm):
    class Meta:
        model = CargoArea
        fields = ["area", "codigo_cargo", "nombre_cargo", "nivel_jerarquico", "aprueba_interno", "activo"]

    def clean_codigo_cargo(self):
        return (self.cleaned_data["codigo_cargo"] or "").strip().upper()

    def clean(self):
        cleaned = super().clean()
        area = cleaned.get("area")
        codigo = cleaned.get("codigo_cargo")
        if area and codigo and CargoArea.objects.filter(area=area, codigo_cargo__iexact=codigo).exists():
            self.add_error("codigo_cargo", "Ya existe este codigo de cargo para el area seleccionada.")
        return cleaned


class UsuarioAreaCargoForm(forms.Form):
    area = forms.ModelChoiceField(
        queryset=AreaInstitucional.objects.filter(activo=True).order_by("nombre_area"),
        empty_label="Seleccione area",
        label="Area",
    )
    cargo = forms.ModelChoiceField(
        queryset=CargoArea.objects.filter(activo=True).select_related("area").order_by("area__nombre_area", "nombre_cargo"),
        empty_label="Seleccione cargo",
        label="Cargo",
    )

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)

        area_id = (self.data.get("area") if self.is_bound else None) or self.initial.get("area")
        cargos = CargoArea.objects.filter(activo=True).select_related("area").order_by("area__nombre_area", "nombre_cargo")
        if area_id:
            cargos = cargos.filter(area_id=area_id)
        self.fields["cargo"].queryset = cargos

    def clean(self):
        cleaned = super().clean()
        area = cleaned.get("area")
        cargo = cleaned.get("cargo")
        if area and cargo and cargo.area_id != area.id_area:
            self.add_error("cargo", "El cargo seleccionado no corresponde al area elegida.")
        return cleaned


class UsuarioSupervisorForm(forms.Form):
    supervisor = forms.ModelChoiceField(queryset=Usuario.objects.none(), label="Supervisor")

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)
        queryset = Usuario.objects.filter(activo=True).order_by("primer_apellido", "primer_nombre")
        if usuario is not None:
            queryset = queryset.exclude(pk=usuario.pk)
        self.fields["supervisor"].queryset = queryset

    def clean_supervisor(self):
        supervisor = self.cleaned_data["supervisor"]
        if self.usuario and supervisor.pk == self.usuario.pk:
            raise forms.ValidationError("El supervisor no puede ser el mismo usuario.")
        if self.usuario and UsuarioSupervisor.objects.filter(
            usuario=self.usuario,
            supervisor=supervisor,
            activo=True,
        ).exists():
            raise forms.ValidationError("Este supervisor ya esta asignado al usuario.")
        return supervisor
