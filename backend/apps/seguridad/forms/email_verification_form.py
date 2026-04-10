from django import forms


class EmailVerificationRequestForm(forms.Form):
    correo = forms.EmailField(
        label="Correo",
        widget=forms.EmailInput(attrs={"placeholder": "correo@dominio.com"}),
    )


class EmailVerificationConfirmForm(forms.Form):
    token = forms.CharField(
        label="Token de verificacion",
        widget=forms.TextInput(attrs={"placeholder": "Pega aqui el token recibido"}),
    )
