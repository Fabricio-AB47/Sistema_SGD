from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_protect

from apps.seguridad.forms.login import LoginForm
from apps.seguridad.services.auth import AuthError, autenticar, cerrar_sesion


def _json_error(message, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)


@method_decorator(csrf_protect, name="dispatch")
class LoginApiView(View):
    def post(self, request, *args, **kwargs):
        form = LoginForm(request.POST)
        if not form.is_valid():
            return _json_error(form.errors.as_json(), status=400)

        data = form.cleaned_data
        try:
            result = autenticar(
                correo=data["correo"],
                password=data["password"],
                remember=data.get("remember", False),
                ip=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
            )
        except AuthError as exc:
            return _json_error(str(exc), status=exc.status)

        user = result["usuario"]
        response = JsonResponse(
            {
                "ok": True,
                "token": result["token"],
                "expira": result["expira"].isoformat() if result.get("expira") else None,
                "user": {
                    "id": user.id_user,
                    "nombre": user.nombre_completo,
                    "correo": user.correo,
                },
                "session_id": result["session_id"],
            }
        )
        expira = result.get("expira")
        max_age = None
        if expira:
            max_age = max(1, int((expira - timezone.now()).total_seconds()))
        response.set_cookie(
            "sig_api_token",
            result["token"],
            max_age=max_age,
            httponly=True,
            secure=getattr(settings, "SESSION_COOKIE_SECURE", True),
            samesite=getattr(settings, "SESSION_COOKIE_SAMESITE", "Lax"),
        )
        return response


@method_decorator(csrf_protect, name="dispatch")
class LogoutApiView(View):
    def post(self, request, *args, **kwargs):
        token = request.POST.get("token") or request.COOKIES.get("sig_api_token")
        if not token:
            return _json_error("Token requerido")
        updated = cerrar_sesion(token)
        response = JsonResponse({"ok": updated > 0})
        response.delete_cookie(
            "sig_api_token",
            samesite=getattr(settings, "SESSION_COOKIE_SAMESITE", "Lax"),
        )
        return response


def login_page(request):
    return render(request, "auth/login.html")
