from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.cache import add_never_cache_headers

from apps.core.services.navigation_service import (
    ROLE_ADMIN,
    ROLE_CONSULTA,
    ROLE_EVALUATOR,
    ROLE_QUALITY,
    ROLE_RECTOR,
    _has_matching_permission,
    _has_matching_role,
    _normalize_permissions,
    _normalize_roles,
)
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
        operational_roles = tuple(request.session.get("sig_operational_roles", []) or [])
        effective_roles = tuple(dict.fromkeys([*session_roles, *operational_roles]))
        has_admin_role = any(
            str(role).strip().lower() == self.admin_role_name
            for role in effective_roles
        )
        if not has_admin_role:
            messages.error(request, "Solo los usuarios con rol ADMINISTRADOR pueden acceder a esta opcion.")
            return redirect("core-dashboard")

        return super().dispatch(request, *args, **kwargs)


class SigRoleOrPermissionRequiredMixin(SigLoginRequiredMixin):
    """
    Restriccion reusable para vistas que usan la sesion SIG.
    Permite acceso por rol efectivo o por codigo de permiso.
    """

    allowed_roles = ()
    allowed_permissions = ()
    include_operational_roles = True
    access_denied_message = "No tienes permisos para acceder a esta opcion."
    access_denied_redirect = "core-dashboard"
    read_only_roles = (ROLE_CONSULTA,)
    read_only_bypass_roles = (ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_EVALUATOR)
    read_only_methods = ("GET", "HEAD", "OPTIONS")
    read_only_denied_message = "El rol CONSULTA solo tiene acceso de lectura."

    def _session_roles(self, request):
        session_roles = tuple(request.session.get("sig_roles", []) or [])
        if not self.include_operational_roles:
            return session_roles
        operational_roles = tuple(request.session.get("sig_operational_roles", []) or [])
        return tuple(dict.fromkeys([*session_roles, *operational_roles]))

    def has_sig_access(self, request) -> bool:
        normalized_roles = _normalize_roles(self._session_roles(request))
        normalized_permissions = _normalize_permissions(
            tuple(request.session.get("sig_permissions", []) or [])
        )

        if ROLE_ADMIN in normalized_roles:
            return True
        if not self.allowed_roles and not self.allowed_permissions:
            return True

        role_ok = bool(self.allowed_roles) and _has_matching_role(
            normalized_roles,
            tuple(self.allowed_roles),
        )
        permission_ok = _has_matching_permission(
            normalized_permissions,
            tuple(self.allowed_permissions),
        ) if self.allowed_permissions else False
        return role_ok or permission_ok

    def is_read_only_denied(self, request) -> bool:
        if request.method.upper() in self.read_only_methods:
            return False

        normalized_roles = _normalize_roles(self._session_roles(request))
        if ROLE_ADMIN in normalized_roles:
            return False
        if not any(role in normalized_roles for role in self.read_only_roles):
            return False
        if any(role in normalized_roles for role in self.read_only_bypass_roles):
            return False
        return True

    def dispatch(self, request, *args, **kwargs):
        if not request.session.get("sig_user_id"):
            return super().dispatch(request, *args, **kwargs)

        if self.is_read_only_denied(request):
            messages.error(request, self.read_only_denied_message)
            return redirect(self.access_denied_redirect)

        if not self.has_sig_access(request):
            messages.error(request, self.access_denied_message)
            return redirect(self.access_denied_redirect)

        return super().dispatch(request, *args, **kwargs)
