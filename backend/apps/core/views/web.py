"""
Vistas base del núcleo del SIG.
Se protegen con el mixin custom que valida la sesión propia (sig_user_id).
"""

from django.views.generic import TemplateView

from apps.core.mixins import SigLoginRequiredMixin
from apps.core.selectors.dashboard_selector import (
    get_dashboard_metrics,
    get_dashboard_quick_links,
)

class InicioView(SigLoginRequiredMixin, TemplateView):
    """Página de inicio simple."""

    template_name = "core/inicio.html"


class DashboardView(SigLoginRequiredMixin, TemplateView):
    """Dashboard principal."""

    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        roles = tuple(self.request.session.get("sig_roles", []) or [])
        operational_roles = tuple(self.request.session.get("sig_operational_roles", []) or [])
        effective_roles = tuple(dict.fromkeys([*roles, *operational_roles]))
        permissions = tuple(self.request.session.get("sig_permissions", []) or [])
        context["dashboard_metrics"] = get_dashboard_metrics()
        context["quick_links"] = get_dashboard_quick_links(
            role_names=effective_roles,
            permission_codes=permissions,
        )
        return context
