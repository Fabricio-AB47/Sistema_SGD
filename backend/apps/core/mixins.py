from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.cache import add_never_cache_headers

from apps.core.services.redirect_security import build_login_redirect_url


class SigLoginRequiredMixin:
    """
    Mixin simple que valida la sesión custom (sig_user_id) creada por LoginView.
    Si no existe, redirige al login con parámetro next.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.session.get("sig_user_id"):
            login_url = settings.LOGIN_URL or "/login/"
            return redirect(build_login_redirect_url(request, login_url))
        response = super().dispatch(request, *args, **kwargs)
        add_never_cache_headers(response)
        return response


class SigAdminRoleRequiredMixin(SigLoginRequiredMixin):
    """
    Restringe el acceso a usuarios con rol ADMINISTRADOR en la sesión SIG.
    """

    admin_role_name = "administrador"

    def dispatch(self, request, *args, **kwargs):
        if not request.session.get("sig_user_id"):
            return super().dispatch(request, *args, **kwargs)

        session_roles = tuple(request.session.get("sig_roles", []) or [])
        has_admin_role = any(str(role).strip().lower() == self.admin_role_name for role in session_roles)
        if not has_admin_role:
            messages.error(request, "Solo los usuarios con rol ADMINISTRADOR pueden acceder a esta opcion.")
            return redirect("core-dashboard")

        return super().dispatch(request, *args, **kwargs)
