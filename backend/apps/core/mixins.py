from django.conf import settings
from django.shortcuts import redirect
from django.utils.cache import add_never_cache_headers


class SigLoginRequiredMixin:
    """
    Mixin simple que valida la sesión custom (sig_user_id) creada por LoginView.
    Si no existe, redirige al login con parámetro next.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.session.get("sig_user_id"):
            login_url = settings.LOGIN_URL or "/login/"
            return redirect(f"{login_url}?next={request.get_full_path()}")
        response = super().dispatch(request, *args, **kwargs)
        add_never_cache_headers(response)
        return response
