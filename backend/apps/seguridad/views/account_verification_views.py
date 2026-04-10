from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import FormView

from apps.seguridad.forms import EmailVerificationConfirmForm, EmailVerificationRequestForm
from apps.seguridad.services.account_verification_service import (
    create_verification_token,
    verify_email_with_token,
)


class EmailVerificationRequestView(FormView):
    template_name = "seguridad/solicitar_verificacion.html"
    form_class = EmailVerificationRequestForm

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("correo"):
            initial["correo"] = self.request.GET.get("correo")
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Verificar correo",
                "page_description": "Genera un token temporal en token_verificacion para confirmar la cuenta.",
            }
        )
        return context

    def form_valid(self, form):
        actor = None
        actor_id = self.request.session.get("sig_user_id")
        if actor_id:
            from apps.usuarios.models import Usuario

            actor = Usuario.objects.filter(pk=actor_id).first()

        result = create_verification_token(
            correo=form.cleaned_data["correo"],
            actor=actor,
            request=self.request,
        )

        if result["already_verified"]:
            messages.info(self.request, "El correo ya se encuentra verificado.")
            return redirect("seguridad-solicitar-verificacion")

        if result["usuario"] and result["token"]:
            if result.get("email_sent"):
                messages.success(self.request, "Se envio un correo de verificacion a la cuenta registrada.")
            else:
                messages.warning(self.request, "Se genero el token, pero el correo no pudo enviarse.")
            if settings.DEBUG:
                self.request.session["sig_debug_verification_token"] = result["token"]
                return redirect("seguridad-verificar-cuenta")

        messages.success(self.request, "Si la cuenta existe, se genero un flujo de verificacion.")
        return redirect("seguridad-solicitar-verificacion")


class EmailVerificationConfirmView(FormView):
    template_name = "seguridad/verificar_cuenta.html"
    form_class = EmailVerificationConfirmForm

    def get_initial(self):
        initial = super().get_initial()
        debug_token = self.request.session.pop("sig_debug_verification_token", None)
        if debug_token:
            initial["token"] = debug_token
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Confirmacion de correo",
                "page_description": "Validacion del token de verificacion.",
            }
        )
        return context

    def form_valid(self, form):
        result = verify_email_with_token(
            token_plain=form.cleaned_data["token"],
            request=self.request,
        )
        if result.get("success"):
            messages.success(
                self.request,
                f"Correo verificado correctamente para {result['usuario'].correo}.",
            )
        else:
            messages.error(self.request, "El token no es valido o ya expiro.")
        return redirect("seguridad-verificar-cuenta")
