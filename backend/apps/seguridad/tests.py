from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import DatabaseError
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.seguridad.middleware import TokenSessionMiddleware
from apps.usuarios.services.auth_service import _requires_otp_for_login


class LoginOtpPolicyTests(SimpleTestCase):
    @override_settings(DEBUG=True, SIG_REQUIRE_OTP_EVERY_LOGIN=False)
    def test_debug_login_does_not_force_otp_when_mfa_is_disabled(self):
        credencial = SimpleNamespace(mfa_activo=False)

        self.assertFalse(_requires_otp_for_login(credencial))

    @override_settings(DEBUG=True, SIG_REQUIRE_OTP_EVERY_LOGIN=False)
    def test_mfa_enabled_still_requires_otp(self):
        credencial = SimpleNamespace(mfa_activo=True)

        self.assertTrue(_requires_otp_for_login(credencial))

    @override_settings(DEBUG=False, SIG_REQUIRE_OTP_EVERY_LOGIN=True)
    def test_production_policy_can_require_otp_every_login(self):
        credencial = SimpleNamespace(mfa_activo=False)

        self.assertTrue(_requires_otp_for_login(credencial))


class TokenSessionMiddlewareTests(SimpleTestCase):
    def test_api_token_expired_session_is_not_attached_to_request(self):
        expired_session = SimpleNamespace(
            usuario=SimpleNamespace(id_user=1),
            fecha_expiracion=timezone.now() - timezone.timedelta(minutes=1),
        )
        queryset = Mock()
        queryset.filter.return_value.first.return_value = expired_session
        session_model = Mock()
        session_model.objects.select_related.return_value = queryset
        request = SimpleNamespace(
            session={},
            META={"HTTP_AUTHORIZATION": "Bearer token-vencido"},
            COOKIES={},
        )

        with patch("apps.seguridad.middleware.UserSession", session_model):
            TokenSessionMiddleware(lambda req: None).process_request(request)

        self.assertIsNone(request.sig_actor)
        self.assertFalse(hasattr(request, "user"))


class AuditServiceTests(SimpleTestCase):
    def test_audit_database_error_does_not_break_caller(self):
        with patch(
            "apps.auditoria.services.auditoria_service.Auditoria.objects.create",
            side_effect=DatabaseError("tabla no disponible"),
        ), self.assertLogs("apps.auditoria.services.auditoria_service", level="ERROR"):
            result = registrar_evento(
                accion="LOGIN_EXITOSO",
                descripcion="Evento de prueba",
                tipo_evento="SEGURIDAD",
            )

        self.assertIsNone(result)
