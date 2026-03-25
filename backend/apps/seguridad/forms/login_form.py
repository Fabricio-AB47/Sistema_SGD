"""
Formulario de login básico (solo valida campos, no autentica).
"""

from django import forms


class LoginForm(forms.Form):
    """Formulario para login con correo y contraseña."""

    correo = forms.EmailField(
        label="Correo",
        widget=forms.EmailInput(attrs={"placeholder": "correo@dominio.com"}),
    )
    password = forms.CharField(
        label="Contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "********"}),
    )
    remember = forms.BooleanField(
        label="Mantener sesión",
        required=False,
        initial=False,
    )
