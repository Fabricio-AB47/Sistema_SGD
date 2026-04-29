from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import ListView
from urllib.parse import urlencode

from apps.auditoria.services import registrar_evento
from apps.core.mixins import SigAdminRoleRequiredMixin
from apps.core.services.redirect_security import build_login_redirect_url
from apps.integraciones.models import ApiCredencial, ApiToken
from apps.integraciones.services import api_service, token_service
from apps.usuarios.models import Usuario


def _get_current_usuario(request):
    user_id = request.session.get("sig_user_id")
    if not user_id:
        return None
    return Usuario.objects.filter(pk=user_id).first()


def _build_token_list_url(*, credencial_id: int | None = None) -> str:
    base_url = str(reverse_lazy("integraciones-tokens-lista"))
    if not credencial_id:
        return base_url
    return f"{base_url}?{urlencode({'credencial': credencial_id})}"


class TokenListView(SigAdminRoleRequiredMixin, ListView):
    model = ApiToken
    template_name = "integraciones/token_list.html"
    context_object_name = "tokens"
    paginate_by = 20

    def get_queryset(self):
        queryset = ApiToken.objects.select_related(
            "api_credencial",
            "api_credencial__api_servicio",
        ).order_by("-fecha_generacion")
        credencial_id = self.request.GET.get("credencial")
        servicio_id = self.request.GET.get("servicio")
        if credencial_id:
            queryset = queryset.filter(api_credencial_id=credencial_id)
        if servicio_id:
            queryset = queryset.filter(api_credencial__api_servicio_id=servicio_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["credenciales"] = ApiCredencial.objects.select_related("api_servicio").filter(activo=True)
        context["servicios"] = api_service.obtener_servicios_activos()
        context["token_service"] = token_service
        return context


@require_POST
def generar_token_view(request, credencial_id):
    if not request.session.get("sig_user_id"):
        return redirect(build_login_redirect_url(request, settings.LOGIN_URL or "/login/"))

    session_roles = tuple(request.session.get("sig_roles", []) or [])
    has_admin_role = any(str(role).strip().lower() == "administrador" for role in session_roles)
    if not has_admin_role:
        messages.error(request, "Solo los usuarios con rol ADMINISTRADOR pueden acceder a esta opcion.")
        return redirect("core-dashboard")

    credencial = get_object_or_404(
        ApiCredencial.objects.select_related("api_servicio"),
        pk=credencial_id,
        activo=True,
    )
    token = token_service.generar_token(credencial)
    registrar_evento(
        usuario=_get_current_usuario(request),
        accion="GENERAR TOKEN API",
        tipo_evento="INTEGRACIONES",
        tabla_afectada="api_token",
        id_registro=token.pk,
        descripcion=f"Se generó un token para la credencial {credencial.nombre_aplicacion}.",
        valores_nuevos={
            "credencial": credencial.nombre_aplicacion,
            "servicio": credencial.api_servicio.nombre_servicio,
            "token": "PROTEGIDO",
            "refresh_token": "PROTEGIDO",
            "fecha_expiracion": token.fecha_expiracion,
            "activo": token.activo,
        },
        criticidad="ALTA",
        request=request,
    )
    messages.success(request, f"Token generado para {credencial.nombre_aplicacion}.")
    return redirect(_build_token_list_url(credencial_id=credencial.pk))
