"""
Vistas base del núcleo del SIG.
Se protegen con el mixin custom que valida la sesión propia (sig_user_id).
"""

from django.views.generic import TemplateView

from apps.core.mixins import SigLoginRequiredMixin

class InicioView(SigLoginRequiredMixin, TemplateView):
    """Página de inicio simple."""

    template_name = "core/inicio.html"


class DashboardView(SigLoginRequiredMixin, TemplateView):
    """Dashboard principal."""

    template_name = "core/dashboard.html"
