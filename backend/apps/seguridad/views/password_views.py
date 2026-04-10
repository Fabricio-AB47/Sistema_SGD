from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import FormView

from apps.seguridad.forms import PasswordRecoveryForm, PasswordResetForm
from apps.seguridad.services.password_reset_service import (
    create_recovery_token,
    get_valid_reset_token,
    reset_password_with_token,
)

SESSION_RESET_TOKEN_KEY = "password_reset_token"


class PasswordRecoveryView(FormView):
    template_name = "seguridad/recuperar_password.html"
    form_class = PasswordRecoveryForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Recuperar contrasena",
                "page_description": "Genera un token temporal en `token_recuperacion` para reiniciar la credencial del usuario.",
            }
        )
        return context

    def form_valid(self, form):
        actor = None
        actor_id = self.request.session.get("sig_user_id")
        if actor_id:
            from apps.usuarios.models import Usuario
            actor = Usuario.objects.filter(pk=actor_id).first()

        result = create_recovery_token(
            correo=form.cleaned_data["correo"],
            actor=actor,
            request=self.request,
        )

        if result["usuario"] and result["token"]:
            if result.get("email_sent"):
                messages.success(self.request, "Se envio un correo con el enlace de recuperacion.")
            else:
                messages.warning(self.request, "Se genero el token, pero el correo no pudo enviarse.")

            # Solo para pruebas locales, sin exponer el token en la URL
            if settings.DEBUG:
                self.request.session[SESSION_RESET_TOKEN_KEY] = result["token"]
                self.request.session.modified = True
                return redirect("seguridad-cambiar-password")

        messages.success(
            self.request,
            "Si el usuario existe, se genero un flujo de recuperacion.",
        )
        return redirect("seguridad-recuperar-password")


class PasswordChangeView(FormView):
    template_name = "seguridad/cambiar_password.html"
    form_class = PasswordResetForm

    def dispatch(self, request, *args, **kwargs):
        token = (kwargs.get("token") or "").strip()

        # Si el token viene en la URL del correo, lo movemos a session
        # y limpiamos la URL con un redirect seguro.
        if token:
            request.session[SESSION_RESET_TOKEN_KEY] = token
            request.session.modified = True
            return redirect("seguridad-cambiar-password")

        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        token = (self.request.session.get(SESSION_RESET_TOKEN_KEY) or "").strip()
        if token:
            initial["token"] = token
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        token_plain = (
            self.request.POST.get("token")
            or self.request.session.get(SESSION_RESET_TOKEN_KEY)
            or ""
        ).strip()

        token_record = get_valid_reset_token(token_plain) if token_plain else None

        context.update(
            {
                "page_title": "Cambiar contrasena",
                "page_description": "Actualiza la credencial del usuario y revoca sus sesiones activas.",
                "token_valido": bool(token_record),
                "usuario_token": token_record.usuario if token_record else None,
            }
        )
        return context

    def form_valid(self, form):
        actor = None
        actor_id = self.request.session.get("sig_user_id")
        if actor_id:
            from apps.usuarios.models import Usuario
            actor = Usuario.objects.filter(pk=actor_id).first()

        token_plain = (
            form.cleaned_data.get("token")
            or self.request.session.get(SESSION_RESET_TOKEN_KEY)
            or ""
        ).strip()

        result = reset_password_with_token(
            token_plain=token_plain,
            new_password=form.cleaned_data["password"],
            actor=actor,
            request=self.request,
        )

        if not result["success"]:
            self.request.session.pop(SESSION_RESET_TOKEN_KEY, None)
            form.add_error(None, "El token no es valido o ya expiro.")
            return self.form_invalid(form)

        self.request.session.pop(SESSION_RESET_TOKEN_KEY, None)

        messages.success(
            self.request,
            "Contrasena actualizada correctamente. Las sesiones anteriores fueron revocadas.",
        )
        return redirect("seguridad-login")