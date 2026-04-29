from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.html import format_html
from django.views.generic import FormView

from apps.core.services.redirect_security import get_auth_flow_redirect_blocklist, get_safe_redirect_target
from apps.seguridad.services import create_login_otp
from apps.usuarios.forms import LoginForm
from apps.usuarios.services import auth_service, session_service
from apps.usuarios.services.user_context_service import hydrate_request_session_context


class LoginView(FormView):
    template_name = "seguridad/login.html"
    form_class = LoginForm
    success_url = getattr(settings, "LOGIN_REDIRECT_URL", "/dashboard/") or "/dashboard/"

    def dispatch(self, request, *args, **kwargs):
        if request.session.get("sig_user_id"):
            redirect_target = get_safe_redirect_target(
                request,
                fallback=self.get_success_url(),
                disallowed_paths=get_auth_flow_redirect_blocklist(),
            )
            return redirect(redirect_target)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next"] = self.request.GET.get("next") or self.request.POST.get("next") or ""
        return context

    def form_valid(self, form):
        redirect_target = get_safe_redirect_target(
            self.request,
            fallback=self.get_success_url(),
            disallowed_paths=get_auth_flow_redirect_blocklist(),
        )
        result = auth_service.authenticate_user(
            correo=form.cleaned_data["correo"],
            password=form.cleaned_data["password"],
            remember=form.cleaned_data.get("remember", False),
            ip=self.request.META.get("REMOTE_ADDR", ""),
            user_agent=self.request.META.get("HTTP_USER_AGENT", "")[:300],
            request=self.request,
        )

        if result.status == "success":
            self.request.session["sig_user_id"] = result.usuario.id_user
            self.request.session["sig_session_token"] = result.session_token
            self.request.session["sig_session_id"] = result.session_id
            self.request.session["sig_session_exp"] = result.session_expires_at.isoformat()
            self.request.session["sig_roles"] = list(result.roles)
            self.request.session["sig_permissions"] = list(result.permissions)
            self.request.session["sig_requires_password_change"] = result.requires_password_change
            hydrate_request_session_context(self.request, usuario_id=result.usuario.id_user)

            if result.session_expires_at:
                seconds = max(1, int((result.session_expires_at - timezone.now()).total_seconds()))
                self.request.session.set_expiry(seconds)

            if result.requires_password_change:
                messages.warning(self.request, "La credencial exige cambio de contrasena en el siguiente paso seguro.")

            if any(role.strip().lower() == "administrador" for role in result.roles):
                return redirect(getattr(settings, "ADMIN_DASHBOARD_URL", self.success_url) or self.success_url)

            return redirect(redirect_target)

        if result.status == "requires_otp":
            otp_result = create_login_otp(
                usuario=result.usuario,
                actor=result.usuario,
                request=self.request,
            )
            self.request.session["pending_otp_user"] = result.usuario.id_user
            # Keep OTP pending session minimal because signed-cookie sessions have size limits.
            # Roles/permissions are resolved again after OTP validation.
            self.request.session["pending_requires_password_change"] = result.requires_password_change
            self.request.session["pending_otp_remember"] = bool(form.cleaned_data.get("remember", False))
            self.request.session["pending_otp_redirect"] = redirect_target
            if getattr(settings, "SIG_EXPOSE_DEBUG_OTP", False):
                self.request.session["pending_otp_debug_code"] = otp_result["codigo"]
            messages.info(self.request, "Se requiere un segundo factor para completar el acceso.")
            if otp_result["email_sent"]:
                messages.info(self.request, f"Se envio un codigo temporal al correo {result.usuario.correo}.")
            else:
                messages.warning(self.request, "Se genero el OTP, pero el correo no pudo enviarse.")
            if getattr(settings, "SIG_EXPOSE_DEBUG_OTP", False):
                messages.info(
                    self.request,
                    format_html("DEBUG: codigo OTP generado para este acceso: <strong>{}</strong>", otp_result["codigo"]),
                )
            return redirect(getattr(settings, "OTP_URL", "/otp/") or "/otp/")

        if result.status == "blocked":
            form.add_error(None, "Cuenta bloqueada temporalmente. Intenta mas tarde.")
        elif result.status == "email_not_verified":
            verify_url = reverse("seguridad-solicitar-verificacion")
            form.add_error(
                None,
                f"Debes verificar tu correo antes de iniciar sesion. Solicita token en {verify_url}.",
            )
        else:
            form.add_error(None, "Correo o contrasena invalidos.")

        return self.form_invalid(form)

    def form_invalid(self, form):
        messages.error(self.request, "No fue posible iniciar sesion.")
        return super().form_invalid(form)


def logout_view(request):
    actor = getattr(request, "sig_actor", None)
    session_service.close_session(
        request=request,
        actor=actor,
        reason="manual",
        flush_request=True,
    )
    messages.info(request, "Sesion cerrada.")
    response = redirect(settings.LOGOUT_REDIRECT_URL or settings.LOGIN_URL or "/login/")
    add_never_cache_headers(response)
    return response
