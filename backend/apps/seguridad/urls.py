from django.urls import path

from apps.seguridad.views.account_verification_views import (
    EmailVerificationConfirmView,
    EmailVerificationRequestView,
)
from apps.seguridad.views.login_view import LoginView, logout_view
from apps.seguridad.views.otp_views import OTPVerificationView, resend_login_otp_view
from apps.seguridad.views.password_views import PasswordChangeView, PasswordRecoveryView
from apps.seguridad.views.session_views import SessionManagementView

urlpatterns = [
    path("login/", LoginView.as_view(), name="seguridad-login"),
    path("logout/", logout_view, name="seguridad-logout"),
    path(
        "verificacion/solicitar/",
        EmailVerificationRequestView.as_view(),
        name="seguridad-solicitar-verificacion",
    ),
    path(
        "verificacion/confirmar/",
        EmailVerificationConfirmView.as_view(),
        name="seguridad-verificar-cuenta",
    ),
    path("recuperar-password/", PasswordRecoveryView.as_view(), name="seguridad-recuperar-password"),
    path("cambiar-password/", PasswordChangeView.as_view(), name="seguridad-cambiar-password"),
    path("otp/", OTPVerificationView.as_view(), name="seguridad-otp"),
    path("otp/reenviar/", resend_login_otp_view, name="seguridad-otp-reenviar"),
    path("seguridad/sesiones/", SessionManagementView.as_view(), name="seguridad-sesiones"),
]
