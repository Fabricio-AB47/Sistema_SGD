from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.usuarios.models import Usuario, UsuarioCredencial, TipoIdentificacion
from argon2 import PasswordHasher


class LoginApiTests(TestCase):
    def setUp(self):
        self.ph = PasswordHasher()
        self.tipo = TipoIdentificacion.objects.create(descripcion="CEDULA")
        self.user = Usuario.objects.create(
            primer_nombre="Test",
            primer_apellido="User",
            identificacion="1234567890",
            correo="test@example.com",
            tipo_identificacion=self.tipo,
        )
        UsuarioCredencial.objects.create(
            usuario=self.user,
            password_hash=self.ph.hash("Secret123"),
        )

    def test_login_ok(self):
        url = reverse("seguridad-api-login")
        resp = self.client.post(url, {"correo": "test@example.com", "password": "Secret123"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("token", data)

    def test_login_bad_password(self):
        url = reverse("seguridad-api-login")
        resp = self.client.post(url, {"correo": "test@example.com", "password": "bad"})
        self.assertEqual(resp.status_code, 401)
        data = resp.json()
        self.assertFalse(data["ok"])
