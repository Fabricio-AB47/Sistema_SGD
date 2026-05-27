from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import FormView

from apps.core.services.redirect_security import build_login_redirect_url
from apps.seguridad.forms import OTPVerificationForm
from apps.seguridad.services import (
    complete_login_after_otp,
    create_login_otp,
    invalidate_login_otp,
    verify_login_otp,
)
from apps.usuarios.models import Usuario
from apps.usuarios.services.user_context_service import hydrate_request_session_context


def _pending_user(request):
    user_id = request.session.get("pending_otp_user")
    if not user_id:
        return None
    return Usuario.objects.filter(pk=user_id, activo=True).first()


def _clear_pending_otp_session(request):
    for key in (
        "pending_otp_user",
        "pending_otp_roles",
        "pending_otp_permissions",
        "pending_requires_password_change",
        "pending_otp_remember",
        "pending_otp_redirect",
        "pending_otp_debug_code",
        "pending_otp_id",
        "pending_otp_issued_at",
    ):
        request.session.pop(key, None)


def _pending_otp_id(request):
    try:
        otp_id = int(request.session.get("pending_otp_id") or 0)
    except (TypeError, ValueError):
        return None
    return otp_id or None


def _store_authenticated_session(
    request,
    *,
    usuario,
    session_data,
    roles,
    permissions,
    requires_password_change,
):
    request.session["sig_user_id"] = usuario.id_user
    request.session["sig_session_token"] = session_data["token"]
    request.session["sig_session_id"] = session_data["session_id"]
    request.session["sig_session_exp"] = session_data["expires_at"].isoformat()
    request.session["sig_roles"] = list(roles)
    request.session["sig_permissions"] = list(permissions)
    request.session["sig_requires_password_change"] = bool(requires_password_change)
    hydrate_request_session_context(request, usuario_id=usuario.id_user)

    expires_at = session_data.get("expires_at")
    if expires_at:
        seconds = max(1, int((expires_at - timezone.now()).total_seconds()))
        request.session.set_expiry(seconds)


class OTPVerificationView(FormView):
    template_name = "seguridad/otp.html"
    form_class = OTPVerificationForm

    def dispatch(self, request, *args, **kwargs):
        usuario = _pending_user(request)
        if usuario is None:
            if request.session.get("pending_otp_user") or _pending_otp_id(request):
                invalidate_login_otp(
                    usuario_id=request.session.get("pending_otp_user"),
                    otp_id=_pending_otp_id(request),
                    request=request,
                    reason="usuario_pendiente_no_valido",
                )
                _clear_pending_otp_session(request)
            if request.session.get("sig_user_id"):
                return redirect(getattr(settings, "LOGIN_REDIRECT_URL", "/dashboard/") or "/dashboard/")
            messages.info(request, "Primero debes iniciar sesion para generar un OTP.")
            return redirect(build_login_redirect_url(request, settings.LOGIN_URL or "/login/"))
        if _pending_otp_id(request) is None:
            invalidate_login_otp(
                usuario=usuario,
                request=request,
                reason="otp_id_ausente_en_sesion",
            )
            _clear_pending_otp_session(request)
            messages.error(request, "El OTP pendiente no esta ligado a un intento valido. Inicia sesion nuevamente.")
            return redirect(settings.LOGIN_URL or "/login/")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Validacion OTP",
                "page_description": "Ingresa el codigo temporal enviado a tu correo para completar el acceso.",
                "pending_user": _pending_user(self.request),
                "debug_otp_code": (
                    self.request.session.get("pending_otp_debug_code")
                    if getattr(settings, "SIG_EXPOSE_DEBUG_OTP", False)
                    else None
                ),
            }
        )
        return context

    def form_valid(self, form):
        usuario = _pending_user(self.request)
        if usuario is None:
            messages.error(self.request, "La solicitud OTP ya no es valida. Inicia sesion nuevamente.")
            return redirect(settings.LOGIN_URL or "/login/")

        result = verify_login_otp(
            usuario=usuario,
            codigo=form.cleaned_data["codigo"],
            otp_id=_pending_otp_id(self.request),
            actor=usuario,
            request=self.request,
        )
        if not result["success"]:
            if result["status"] == "expired":
                form.add_error(None, "El codigo expiro. Genera uno nuevo.")
            elif result["status"] == "blocked":
                _clear_pending_otp_session(self.request)
                messages.error(self.request, "Se agotaron los intentos del OTP. Inicia sesion nuevamente.")
                return redirect(settings.LOGIN_URL or "/login/")
            elif result["status"] == "missing":
                _clear_pending_otp_session(self.request)
                messages.error(
                    self.request,
                    "El OTP pendiente ya no corresponde a este acceso. Inicia sesion nuevamente.",
                )
                return redirect(settings.LOGIN_URL or "/login/")
            else:
                form.add_error(None, "El codigo OTP no corresponde a este acceso o usuario.")
            return self.form_invalid(form)

        completion = complete_login_after_otp(
            usuario=usuario,
            remember=bool(self.request.session.get("pending_otp_remember", False)),
            roles=(),
            permissions=(),
            requires_password_change=bool(self.request.session.get("pending_requires_password_change", False)),
            ip=self.request.META.get("REMOTE_ADDR", ""),
            user_agent=self.request.META.get("HTTP_USER_AGENT", "")[:300],
            request=self.request,
        )
        _store_authenticated_session(
            self.request,
            usuario=completion["usuario"],
            session_data=completion["session_data"],
            roles=completion["roles"],
            permissions=completion["permissions"],
            requires_password_change=completion["requires_password_change"],
        )
        redirect_target = self.request.session.get("pending_otp_redirect") or (
            getattr(settings, "LOGIN_REDIRECT_URL", "/dashboard/") or "/dashboard/"
        )
        _clear_pending_otp_session(self.request)

        if completion["requires_password_change"]:
            messages.warning(self.request, "La credencial exige cambio de contrasena en el siguiente paso seguro.")
        messages.success(self.request, "OTP validado. Sesion iniciada correctamente.")

        if any(role.strip().lower() == "administrador" for role in completion["roles"]):
            return redirect(getattr(settings, "ADMIN_DASHBOARD_URL", redirect_target) or redirect_target)
        return redirect(redirect_target)


@require_POST
def resend_login_otp_view(request):
    usuario = _pending_user(request)
    if usuario is None:
        messages.info(request, "Debes iniciar sesion nuevamente para generar un OTP.")
        return redirect(settings.LOGIN_URL or "/login/")

    otp_result = create_login_otp(
        usuario=usuario,
        actor=usuario,
        request=request,
    )
    request.session["pending_otp_id"] = otp_result["otp"].pk
    request.session["pending_otp_issued_at"] = timezone.now().isoformat()
    if getattr(settings, "SIG_EXPOSE_DEBUG_OTP", False):
        request.session["pending_otp_debug_code"] = otp_result["codigo"]
    if otp_result["email_sent"]:
        messages.info(request, "Se envio un nuevo codigo OTP al correo registrado.")
    else:
        messages.warning(request, "Se genero un nuevo OTP, pero el correo no pudo enviarse.")
    return redirect(getattr(settings, "OTP_URL", "/otp/") or "/otp/")
