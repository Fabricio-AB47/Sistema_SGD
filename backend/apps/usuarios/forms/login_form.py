from django import forms


class LoginForm(forms.Form):
    correo = forms.EmailField(
        label="Correo",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "correo@dominio.com",
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        label="Contrasena",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "********",
                "autocomplete": "current-password",
            }
        ),
    )
    remember = forms.BooleanField(
        label="Mantener sesion",
        required=False,
        initial=False,
    )

    def clean_correo(self):
        return (self.cleaned_data["correo"] or "").strip().lower()
