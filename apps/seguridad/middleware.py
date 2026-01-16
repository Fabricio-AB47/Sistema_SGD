from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

from apps.seguridad.models import UserActivity, UserSession


class SessionActivityMiddleware:
    """
    - Actualiza last_seen_at en user_activity.
    - Renueva fecha_expiracion y fecha_renovacion en user_session (sesion deslizante).
    - Si la sesion expiro, limpia la sesion de Django.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Procesa la petición y luego actualiza tracking de actividad/sesión.
        response = self.get_response(request)

        usuario_id = request.session.get("usuario_id")
        if not usuario_id:
            return response

        now = timezone.localtime(timezone.now())
        idle_minutes = getattr(settings, "SESSION_IDLE_MINUTES", 15)

        # Actualizar actividad
        try:
            act = UserActivity.objects.filter(usuario_id=usuario_id).order_by("-login_at").first()
            if act:
                # Marca el último visto
                act.last_seen_at = now
                act.save(update_fields=["last_seen_at"])
        except Exception:
            pass

        # Renovar sesion deslizante
        session_id = request.session.get("user_session_id")
        if session_id:
            try:
                us = UserSession.objects.get(pk=session_id)
                if us.fecha_expiracion and us.fecha_expiracion < now:
                    # Sesión expirada: limpia la sesión de Django
                    request.session.flush()
                    return response
                # Sesión activa: extiende expiración (idle timeout)
                us.fecha_renovacion = now
                us.fecha_expiracion = now + timedelta(minutes=idle_minutes)
                us.save(update_fields=["fecha_renovacion", "fecha_expiracion"])
            except UserSession.DoesNotExist:
                # Si no existe el registro, retira el id de la sesión
                request.session.pop("user_session_id", None)
            except Exception:
                pass

        return response
