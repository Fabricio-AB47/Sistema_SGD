"""
Middleware para validar el token de sesión custom (user_session).
Si se envía Authorization: Bearer <token> y es válido, se asocia request.user.
Si no hay token, se deja que la autenticación estándar (session) actúe.
"""

import hashlib
from django.utils.deprecation import MiddlewareMixin
from apps.seguridad.models import UserSession
from apps.usuarios.models import Usuario
from apps.usuarios.services.session_service import ensure_request_session_active
from apps.usuarios.services.user_context_service import hydrate_request_session_context


class TokenSessionMiddleware(MiddlewareMixin):
    """
    Middleware muy ligero para soportar token plano emitido por LoginApiView.
    No sustituye la auth de Django; la complementa para llamadas AJAX.
    """

    def process_request(self, request):
        request.sig_actor = None
        request.sig_active_assignment_id = request.session.get("sig_active_assignment_id")
        request.sig_active_area_id = request.session.get("sig_active_area_id")
        request.sig_active_cargo_id = request.session.get("sig_active_cargo_id")

        user_id = request.session.get("sig_user_id")
        if user_id:
            session_status = ensure_request_session_active(request=request, touch=True)
            if session_status.get("valid"):
                request.sig_actor = session_status.get("usuario")
                if request.session.get("sig_active_assignment_id") is None:
                    hydrate_request_session_context(request, usuario_id=user_id)
                request.sig_active_assignment_id = request.session.get("sig_active_assignment_id")
                request.sig_active_area_id = request.session.get("sig_active_area_id")
                request.sig_active_cargo_id = request.session.get("sig_active_cargo_id")
            else:
                request.sig_actor = None

        auth = request.META.get("HTTP_AUTHORIZATION", "")
        cookie_token = (request.COOKIES.get("sig_api_token") or "").strip()
        if not auth.startswith("Bearer ") and not cookie_token:
            if request.sig_actor is None and request.session.get("sig_user_id"):
                request.sig_actor = Usuario.objects.filter(pk=user_id, activo=True).first()
            return None
        token_plain = auth.split(" ", 1)[1].strip() if auth.startswith("Bearer ") else cookie_token
        if not token_plain:
            return None
        token_hash = hashlib.sha256(token_plain.encode()).hexdigest()
        session = (
            UserSession.objects.select_related("usuario")
            .filter(token_sesion_hash=token_hash, activa=True)
            .first()
        )
        if session and session.fecha_expiracion and session.fecha_expiracion >= session.fecha_inicio:
            request.user = session.usuario  # asocia usuario autenticado
            request.sig_actor = session.usuario
        return None
