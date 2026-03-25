"""
Vista de login basada en formularios y el servicio de autenticación custom.
"""

import hashlib

from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import FormView
from django.conf import settings
from django.utils.cache import add_never_cache_headers

from apps.seguridad.forms import LoginForm
from apps.seguridad.models import UserSession
from apps.seguridad.services import auth_service


class LoginView(FormView):
    """Renderiza y procesa el login usando el modelo de seguridad propio."""

    template_name = "seguridad/login.html"
    form_class = LoginForm
    success_url = getattr(settings, "LOGIN_REDIRECT_URL", "/dashboard/")

    def form_valid(self, form):
        data = form.cleaned_data
        result = auth_service.authenticate(
            correo=data["correo"],
            password=data["password"],
            remember=data.get("remember", False),
            ip=self.request.META.get("REMOTE_ADDR", ""),
            user_agent=self.request.META.get("HTTP_USER_AGENT", "")[:300],
        )

        status = result.status

        if status == "success":
            # Guarda referencias mínimas en la sesión de Django.
            self.request.session["sig_user_id"] = result.usuario.id_user
            self.request.session["sig_session_token"] = result.session_token
            self.request.session["sig_session_id"] = result.session_id
            self.request.session["sig_session_exp"] = result.session_expires_at.isoformat()
            messages.success(self.request, "Inicio de sesión exitoso.")

            # Si el usuario tiene rol Administrador activo, envía al dashboard admin.
            admin_url = getattr(settings, "ADMIN_DASHBOARD_URL", "/dashboard/")
            if result.usuario.roles_asignados.filter(
                activo=True, rol__nombre_rol__iexact="administrador"
            ).exists():
                return redirect(admin_url)

            # Caso general: redirige a LOGIN_REDIRECT_URL
            return redirect(self.get_success_url())

        if status == "requires_otp":
            # Preparar redirección a flujo OTP (pendiente de implementación).
            self.request.session["pending_otp_user"] = result.usuario.id_user
            messages.info(self.request, "Ingresa tu OTP para completar el acceso.")
            otp_url = getattr(settings, "OTP_URL", "/otp/")  # Ruta futura configurable.
            return redirect(otp_url)

        if status == "blocked":
            form.add_error(None, "Cuenta bloqueada temporalmente. Intente más tarde.")
        else:
            form.add_error(None, "Correo o contraseña inválidos.")

        return self.form_invalid(form)

    def form_invalid(self, form):
        messages.error(self.request, "No se pudo iniciar sesión. Verifique sus datos.")
        return super().form_invalid(form)


def logout_view(request):
    """
    Cierra la sesión custom (limpia la sesión de Django y tokens guardados).
    """
    session_token = request.session.get("sig_session_token")
    if session_token:
        session_hash = hashlib.sha256(session_token.encode()).hexdigest()
        UserSession.objects.filter(token_sesion_hash=session_hash, activa=True).update(activa=False)

    request.session.flush()
    messages.info(request, "Sesión cerrada.")
    response = redirect(settings.LOGIN_URL or "/login/")
    add_never_cache_headers(response)
    return response
