from django import forms


class OTPVerificationForm(forms.Form):
    codigo = forms.CharField(
        label="Codigo temporal",
        max_length=12,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ingresa el codigo enviado al correo",
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
            }
        ),
    )

    def clean_codigo(self):
        return "".join(char for char in (self.cleaned_data["codigo"] or "").strip() if char.isdigit())
