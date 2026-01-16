from django.urls import path
from .views import (
    verify_request_view,
    resend_verification_view,
    verify_token_view,
)

urlpatterns = [
    path("seguridad/solicitar-verificacion/", verify_request_view, name="verify_request"),
    path("seguridad/reenviar-verificacion/", resend_verification_view, name="resend_verification"),
    path("seguridad/verificar-correo/<str:token>/", verify_token_view, name="verify_token"),
]