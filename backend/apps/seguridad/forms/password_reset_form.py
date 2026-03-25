from django import forms


class PasswordResetForm(forms.Form):
    token = forms.CharField(
        widget=forms.HiddenInput(),
    )
    password = forms.CharField(
        label="Nueva contrasena",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Nueva contrasena",
            }
        ),
    )
    password_confirm = forms.CharField(
        label="Confirmar contrasena",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Confirmar contrasena",
            }
        ),
    )

    def clean_password(self):
        password = self.cleaned_data["password"]
        if len(password) < 8:
            raise forms.ValidationError("La contrasena debe tener al menos 8 caracteres.")
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Las contrasenas no coinciden.")
        return cleaned_data
