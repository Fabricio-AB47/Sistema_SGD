from django import forms


class PasswordRecoveryForm(forms.Form):
    correo = forms.EmailField(
        label="Correo",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "correo@dominio.com",
            }
        ),
    )
