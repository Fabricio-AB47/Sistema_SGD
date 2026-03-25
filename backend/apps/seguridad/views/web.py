"""
Vista de login HTML.
No requiere autenticación; el resto de vistas deben estar protegidas.
"""

from django.views.generic import TemplateView


class LoginPageView(TemplateView):
    """Página de acceso al sistema."""

    # Usa el template unificado de frontend para login.
    template_name = "auth/login.html"
