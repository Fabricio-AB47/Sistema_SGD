from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from apps.seguridad.forms.login import LoginForm
from apps.seguridad.services.auth import autenticar, cerrar_sesion, AuthError


def _json_error(message, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)


@method_decorator(csrf_exempt, name="dispatch")
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
        except AuthError as e:
            return _json_error(str(e), status=e.status)

        user = result["usuario"]
        return JsonResponse(
            {
                "ok": True,
                "token": result["token"],
                "expira": result["expira"].isoformat(),
                "user": {
                    "id": user.id,
                    "nombre": f"{user.primer_nombre} {user.primer_apellido}".strip(),
                    "correo": user.correo,
                },
                "session_id": result["session_id"],
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class LogoutApiView(View):
    def post(self, request, *args, **kwargs):
        token = request.POST.get("token")
        if not token:
            return _json_error("Token requerido")
        updated = cerrar_sesion(token)
        return JsonResponse({"ok": updated > 0})
