from django.urls import path

from apps.core.views.auth_page import AuthPageView
from apps.seguridad.views.login_view import LoginView, logout_view
from apps.seguridad.views.password_views import PasswordChangeView, PasswordRecoveryView
from apps.seguridad.views.session_views import SessionManagementView

urlpatterns = [
    path("login/", LoginView.as_view(), name="seguridad-login"),
    path("logout/", logout_view, name="seguridad-logout"),
    path("recuperar-password/", PasswordRecoveryView.as_view(), name="seguridad-recuperar-password"),
    path("cambiar-password/", PasswordChangeView.as_view(), name="seguridad-cambiar-password"),
    path(
        "otp/",
        AuthPageView.as_view(
            template_name="seguridad/otp.html",
            page_title="Validacion OTP",
            page_description="Segundo factor de autenticacion para accesos sensibles.",
            page_sections=[
                {
                    "title": "Objetivo",
                    "description": "Completar el acceso con un codigo temporal.",
                    "items": [
                        "Control de intentos.",
                        "Expiracion del codigo.",
                        "Registro del evento de validacion.",
                    ],
                }
            ],
        ),
        name="seguridad-otp",
    ),
    path("seguridad/sesiones/", SessionManagementView.as_view(), name="seguridad-sesiones"),
]
