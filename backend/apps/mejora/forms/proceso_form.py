from django import forms


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().split())
    return normalized or None


class CicloAprobacionForm(forms.Form):
    ciclo_nombre = forms.CharField(max_length=200, label="Nombre del ciclo")
    fecha_aprobacion = forms.DateField(
        label="Fecha de aprobacion",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    aprobado_por = forms.CharField(max_length=200, label="Aprobado por")
    acta_reunion = forms.CharField(max_length=300, required=False, label="Acta de reunion (referencia)")
    observacion = forms.CharField(
        max_length=1000,
        required=False,
        label="Observacion",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_observacion(self):
        return _normalize_optional_text(self.cleaned_data.get("observacion"))


class AsignacionResponsableForm(forms.Form):
    area = forms.CharField(max_length=200, label="Area")
    director_jefe = forms.CharField(max_length=200, label="Director o jefe")
    subordinado_responsable = forms.CharField(max_length=200, label="Subordinado responsable")
    indicador = forms.CharField(max_length=200, label="Indicador")
    elemento = forms.CharField(max_length=200, label="Elemento")
    fecha_asignacion = forms.DateField(
        label="Fecha de asignacion",
        widget=forms.DateInput(attrs={"type": "date"}),
    )


class CargaInformacionForm(forms.Form):
    responsable = forms.CharField(max_length=200, label="Responsable de carga")
    indicador = forms.CharField(max_length=200, label="Indicador")
    elemento = forms.CharField(max_length=200, label="Elemento")
    nombre_evidencia = forms.CharField(max_length=250, label="Nombre de evidencia")
    descripcion = forms.CharField(
        max_length=1000,
        required=False,
        label="Descripcion",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    metadatos = forms.CharField(
        max_length=1000,
        required=False,
        label="Metadatos",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    fecha_carga = forms.DateField(
        label="Fecha de carga",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean_descripcion(self):
        return _normalize_optional_text(self.cleaned_data.get("descripcion"))

    def clean_metadatos(self):
        return _normalize_optional_text(self.cleaned_data.get("metadatos"))


class RevisionJefaturaForm(forms.Form):
    DECISION_CHOICES = (
        ("APROBADA", "Aprobada"),
        ("OBSERVADA", "Observada / Requiere correccion"),
    )

    jefe_revisor = forms.CharField(max_length=200, label="Jefe revisor")
    decision = forms.ChoiceField(choices=DECISION_CHOICES, label="Decision")
    comentario = forms.CharField(
        max_length=1000,
        label="Comentario de revision",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    fecha_revision = forms.DateField(
        label="Fecha de revision",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean_comentario(self):
        normalized = _normalize_optional_text(self.cleaned_data.get("comentario"))
        if not normalized:
            raise forms.ValidationError("Debes registrar un comentario de revision.")
        return normalized


class EnvioFormalForm(forms.Form):
    director_area = forms.CharField(max_length=200, label="Director de area")
    fecha_envio = forms.DateField(
        label="Fecha de envio formal",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    aprobado = forms.BooleanField(required=True, label="Confirmo la aprobacion formal")
    comentario = forms.CharField(
        max_length=1000,
        required=False,
        label="Comentario",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_comentario(self):
        return _normalize_optional_text(self.cleaned_data.get("comentario"))


class RecepcionEvaluadorForm(forms.Form):
    ESTADO_CHOICES = (
        ("RECIBIDO", "Recibido"),
        ("EN_REVISION", "En revision"),
        ("OBSERVADO", "Observado"),
    )

    evaluador_responsable = forms.CharField(max_length=200, label="Responsable evaluador")
    fecha_recepcion = forms.DateField(
        label="Fecha de recepcion",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    estado_inicial = forms.ChoiceField(choices=ESTADO_CHOICES, label="Estado inicial")
    observacion = forms.CharField(
        max_length=1000,
        required=False,
        label="Observacion",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_observacion(self):
        return _normalize_optional_text(self.cleaned_data.get("observacion"))
