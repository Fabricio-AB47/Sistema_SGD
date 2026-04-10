from django import forms


class PasswordChangeForm(forms.Form):
    current_password = forms.CharField(
        label="Contrasena actual",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    new_password = forms.CharField(
        label="Nueva contrasena",
        strip=False,
        min_length=8,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    confirm_password = forms.CharField(
        label="Confirmar contrasena",
        strip=False,
        min_length=8,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")
        if new_password and confirm_password and new_password != confirm_password:
            self.add_error("confirm_password", "Las contrasenas no coinciden.")
        return cleaned_data


class PasswordRecoveryForm(forms.Form):
    correo = forms.EmailField(
        label="Correo",
        widget=forms.EmailInput(attrs={"placeholder": "correo@dominio.com"}),
    )


class PasswordResetForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput())
    password = forms.CharField(
        label="Nueva contrasena",
        strip=False,
        min_length=8,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password_confirm = forms.CharField(
        label="Confirmar contrasena",
        strip=False,
        min_length=8,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Las contrasenas no coinciden.")
        return cleaned_data
