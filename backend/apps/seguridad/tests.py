from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import unittest
from django.db import connection
from django.db import DatabaseError
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.seguridad.middleware import TokenSessionMiddleware
from apps.seguridad.services.notification_service import _render_email as render_security_email
from apps.seguridad.services.otp_service import _hash_code, create_login_otp, verify_login_otp
from apps.usuarios.models import Usuario, UsuarioOTP
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


class SecurityEmailTemplateTests(SimpleTestCase):
    def test_transactional_email_templates_render_text_and_html(self):
        usuario = SimpleNamespace(
            nombre_completo="Ada Lovelace",
            correo="ada@example.com",
        )
        cases = [
            (
                "login_otp",
                {
                    "usuario": usuario,
                    "codigo": "123456",
                    "fecha_expiracion": timezone.now() + timedelta(minutes=10),
                    "otp_minutes": 10,
                },
                "123456",
            ),
            (
                "verification_email",
                {
                    "usuario": usuario,
                    "verification_url": "https://sig.local/verificar?token=abc",
                },
                "https://sig.local/verificar?token=abc",
            ),
            (
                "password_recovery",
                {
                    "usuario": usuario,
                    "reset_url": "https://sig.local/password?token=abc",
                },
                "https://sig.local/password?token=abc",
            ),
        ]

        for template_name, context, expected_text in cases:
            with self.subTest(template_name=template_name):
                body, html_body = render_security_email(template_name, context)

                self.assertIn(expected_text, body)
                self.assertTrue(html_body.strip())


@override_settings(USE_TZ=True)
class LoginOtpSingleUseTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        if connection.vendor != "sqlite":
            raise unittest.SkipTest("Estas pruebas crean tablas minimas solo para SQLite.")
        super().setUpClass()
        cls._created_tables = []
        existing_tables = set(connection.introspection.table_names())
        with connection.cursor() as cursor:
            if "usuario" not in existing_tables:
                cursor.execute(
                    """
                    CREATE TABLE usuario (
                        id_user integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                        primer_nombre varchar(150) NOT NULL,
                        segundo_nombre varchar(150) NULL,
                        primer_apellido varchar(150) NOT NULL,
                        segundo_apellido varchar(150) NULL,
                        identificacion varchar(20) NOT NULL UNIQUE,
                        correo varchar(254) NOT NULL UNIQUE,
                        telefono varchar(20) NULL,
                        correo_verificado bool NOT NULL,
                        activo bool NOT NULL,
                        fecha_creacion datetime NULL,
                        fecha_actualizacion datetime NULL,
                        id_tipo_identificacion integer NOT NULL,
                        version_fila blob NULL
                    )
                    """
                )
                cls._created_tables.append("usuario")
            if "usuario_otp" not in existing_tables:
                cursor.execute(
                    """
                    CREATE TABLE usuario_otp (
                        id_otp integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                        id_user integer NOT NULL REFERENCES usuario(id_user),
                        codigo_otp_hash varchar(64) NOT NULL,
                        tipo_otp varchar(50) NOT NULL,
                        fecha_generacion datetime NULL,
                        fecha_expiracion datetime NOT NULL,
                        usado bool NOT NULL,
                        intentos integer unsigned NOT NULL CHECK (intentos >= 0),
                        ip varchar(45) NULL
                    )
                    """
                )
                cls._created_tables.append("usuario_otp")

    @classmethod
    def tearDownClass(cls):
        with connection.cursor() as cursor:
            for table_name in reversed(getattr(cls, "_created_tables", [])):
                cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        super().tearDownClass()

    def setUp(self):
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM usuario_otp")
            cursor.execute("DELETE FROM usuario")

    def _usuario(self):
        return Usuario.objects.create(
            primer_nombre="Ada",
            primer_apellido="Lovelace",
            identificacion="ID-OTP-1",
            correo="ada.otp@example.com",
            correo_verificado=True,
            activo=True,
            id_tipo_identificacion=1,
        )

    def _patch_delivery_and_audit(self):
        return patch.multiple(
            "apps.seguridad.services.otp_service",
            send_login_otp_email=Mock(return_value={"sent": True, "error": None}),
            registrar_evento=Mock(return_value=None),
        )

    def test_generating_new_login_otp_invalidates_previous_pending_codes(self):
        usuario = self._usuario()

        with self._patch_delivery_and_audit():
            first = create_login_otp(usuario=usuario)
            second = create_login_otp(usuario=usuario)

        self.assertTrue(UsuarioOTP.objects.get(pk=first["otp"].pk).usado)
        self.assertFalse(UsuarioOTP.objects.get(pk=second["otp"].pk).usado)

    def test_login_otp_can_only_be_validated_once(self):
        usuario = self._usuario()
        with self._patch_delivery_and_audit():
            otp_result = create_login_otp(usuario=usuario)
            first_validation = verify_login_otp(
                usuario=usuario,
                codigo=otp_result["codigo"],
                otp_id=otp_result["otp"].pk,
            )
            second_validation = verify_login_otp(
                usuario=usuario,
                codigo=otp_result["codigo"],
                otp_id=otp_result["otp"].pk,
            )

        stored_otp = UsuarioOTP.objects.get(pk=otp_result["otp"].pk)
        self.assertTrue(first_validation["success"])
        self.assertEqual(first_validation["status"], "valid")
        self.assertFalse(second_validation["success"])
        self.assertEqual(second_validation["status"], "missing")
        self.assertTrue(stored_otp.usado)
        self.assertEqual(stored_otp.intentos, 1)

    def test_validating_one_otp_consumes_any_other_pending_login_otp_for_user(self):
        usuario = self._usuario()
        now = timezone.now()
        otp_a = UsuarioOTP.objects.create(
            usuario=usuario,
            codigo_otp_hash=_hash_code("111111"),
            tipo_otp="LOGIN",
            fecha_generacion=now,
            fecha_expiracion=now + timedelta(minutes=10),
            usado=False,
            intentos=0,
        )
        otp_b = UsuarioOTP.objects.create(
            usuario=usuario,
            codigo_otp_hash=_hash_code("222222"),
            tipo_otp="LOGIN",
            fecha_generacion=now + timedelta(seconds=1),
            fecha_expiracion=now + timedelta(minutes=10),
            usado=False,
            intentos=0,
        )

        with patch("apps.seguridad.services.otp_service.registrar_evento", return_value=None):
            result = verify_login_otp(usuario=usuario, codigo="111111", otp_id=otp_a.pk)

        self.assertTrue(result["success"])
        self.assertTrue(UsuarioOTP.objects.get(pk=otp_a.pk).usado)
        self.assertTrue(UsuarioOTP.objects.get(pk=otp_b.pk).usado)


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
