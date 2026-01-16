from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.seguridad.models import UserActivity, UserSession
from apps.seguridad.audit_trail import reset_request_context, set_request_context


class SessionActivityMiddleware:
    """
    - Actualiza last_seen_at en user_activity.
    - Renueva fecha_expiracion y fecha_renovacion en user_session (sesion deslizante).
    - Si la sesion expiro, limpia la sesion de Django.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_request_context(request)
        try:
            # Procesa la peticion y luego actualiza tracking de actividad/sesion.
            response = self.get_response(request)

            usuario_id = request.session.get("usuario_id")
            if not usuario_id:
                return response

            now = timezone.localtime(timezone.now())
            idle_minutes = getattr(settings, "SESSION_IDLE_MINUTES", 15)

            # Actualizar actividad (preferimos la creada al hacer login)
            try:
                act_id = request.session.get("user_activity_id")
                queryset = (
                    UserActivity.objects.filter(pk=act_id)
                    if act_id
                    else UserActivity.objects.filter(usuario_id=usuario_id).order_by("-login_at")
                )
                act = queryset.first()
                if act:
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
                        # Sesion expirada: limpia la sesion de Django
                        request.session.flush()
                        return response
                    # Sesion activa: extiende expiracion (idle timeout)
                    us.fecha_renovacion = now
                    us.fecha_expiracion = now + timedelta(minutes=idle_minutes)
                    us.save(update_fields=["fecha_renovacion", "fecha_expiracion"])
                except UserSession.DoesNotExist:
                    # Si no existe el registro, retira el id de la sesion
                    request.session.pop("user_session_id", None)
                except Exception:
                    pass

            return response
        finally:
            reset_request_context(token)
