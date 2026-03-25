from django import forms


class SessionFilterForm(forms.Form):
    ESTADO_CHOICES = (
        ("", "Todas"),
        ("active", "Activas"),
        ("expired", "Expiradas"),
        ("inactive", "Inactivas"),
    )
    ALCANCE_CHOICES = (
        ("all", "Todas las sesiones"),
        ("mine", "Solo mis sesiones"),
    )

    q = forms.CharField(
        required=False,
        label="Busqueda",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Usuario, correo, IP o token",
            }
        ),
    )
    estado = forms.ChoiceField(
        required=False,
        choices=ESTADO_CHOICES,
        label="Estado",
    )
    alcance = forms.ChoiceField(
        required=False,
        choices=ALCANCE_CHOICES,
        initial="all",
        label="Alcance",
    )

    def clean_q(self):
        return (self.cleaned_data.get("q") or "").strip()
