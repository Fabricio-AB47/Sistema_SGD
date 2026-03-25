from django import forms
from django.utils import timezone

from apps.integraciones.models import ApiCredencial
from apps.integraciones.services import credential_service


class CredencialForm(forms.ModelForm):
    secret = forms.CharField(
        label="Secret",
        widget=forms.PasswordInput(render_value=True),
        help_text="El valor se cifra antes de guardarse.",
    )

    class Meta:
        model = ApiCredencial
        fields = [
            "api_servicio",
            "nombre_aplicacion",
            "client_id",
            "tenant_id",
            "fecha_expiracion",
            "activo",
        ]
        widgets = {
            "fecha_expiracion": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client_id"].help_text = "Se cifra antes de guardarse."
        self.fields["tenant_id"].help_text = "Se cifra antes de guardarse."
        if self.instance and self.instance.pk:
            self.initial["client_id"] = credential_service.decrypt_text_value(
                self.instance.client_id
            )
            self.initial["tenant_id"] = credential_service.decrypt_text_value(
                self.instance.tenant_id
            )

    def save(self, commit=True, current_user=None):
        credencial = super().save(commit=False)
        secret_encriptado, iv_secret, referencia = credential_service.encrypt_secret(
            self.cleaned_data["secret"]
        )
        credencial.client_id = credential_service.encrypt_text_value(
            self.cleaned_data.get("client_id")
        )
        credencial.tenant_id = credential_service.encrypt_text_value(
            self.cleaned_data.get("tenant_id")
        )
        credencial.secret_encriptado = secret_encriptado
        credencial.iv_secret = iv_secret
        credencial.referencia_clave_cifrado = referencia
        if not credencial.pk:
            credencial.fecha_creacion = timezone.now()
        if current_user is not None:
            credencial.creado_por = current_user
        if commit:
            credencial.save()
        return credencial
