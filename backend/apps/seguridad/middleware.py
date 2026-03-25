"""
Middleware para validar el token de sesión custom (user_session).
Si se envía Authorization: Bearer <token> y es válido, se asocia request.user.
Si no hay token, se deja que la autenticación estándar (session) actúe.
"""

import hashlib
from django.utils.deprecation import MiddlewareMixin
from apps.seguridad.models import UserSession


class TokenSessionMiddleware(MiddlewareMixin):
    """
    Middleware muy ligero para soportar token plano emitido por LoginApiView.
    No sustituye la auth de Django; la complementa para llamadas AJAX.
    """

    def process_request(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return None
        token_plain = auth.split(" ", 1)[1].strip()
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
        return None
