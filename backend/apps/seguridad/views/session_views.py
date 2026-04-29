from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView

from apps.core.mixins import SigAdminRoleRequiredMixin
from apps.seguridad.forms import SessionFilterForm
from apps.seguridad.selectors import (
    get_recent_login_attempts,
    get_session_dashboard_data,
)
from apps.seguridad.models import UserSession
from apps.seguridad.services.session_service import (
    get_token_hash,
    revoke_other_sessions_for_user,
    revoke_session,
)
from apps.usuarios.models import Usuario


class SessionManagementView(SigAdminRoleRequiredMixin, TemplateView):
    template_name = "seguridad/sesiones.html"

    def _current_usuario(self):
        user_id = self.request.session.get("sig_user_id")
        if not user_id:
            return None
        return Usuario.objects.filter(pk=user_id).only(
            "id_user",
            "primer_nombre",
            "primer_apellido",
            "correo",
        ).first()

    def _current_session_hash(self):
        return get_token_hash(self.request.session.get("sig_session_token"))

    def _current_session_id(self):
        session_id = self.request.session.get("sig_session_id")
        if session_id:
            return session_id

        session_hash = self._current_session_hash()
        if not session_hash:
            return None

        session = UserSession.objects.only("id_sesion").filter(
            token_sesion_hash=session_hash,
            activa=True,
        ).first()
        if not session:
            return None

        self.request.session["sig_session_id"] = session.id_sesion
        return session.id_sesion

    def _build_redirect_url(self):
        query_string = self.request.GET.urlencode()
        base_url = reverse("seguridad-sesiones")
        return f"{base_url}?{query_string}" if query_string else base_url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = kwargs.get("filter_form") or SessionFilterForm(self.request.GET or None)
        current_user = self._current_usuario()
        cleaned_filters = {"q": "", "estado": "", "alcance": "all"}
        if form.is_valid():
            cleaned_filters.update(form.cleaned_data)

        dashboard = get_session_dashboard_data(
            filters=cleaned_filters,
            current_user=current_user,
            current_session_hash=self._current_session_hash(),
            current_session_id=self._current_session_id(),
            page_number=self.request.GET.get("page") or 1,
        )

        context.update(
            {
                "page_title": "Sesiones activas",
                "page_description": "Gestiona sesiones, valida actividad y revoca accesos vigentes desde la base real.",
                "filter_form": form,
                "session_metrics": dashboard["metrics"],
                "sessions_page": dashboard["sessions_page"],
                "recent_logins": get_recent_login_attempts(),
                "current_user_session": current_user,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        current_user = self._current_usuario()
        current_session_hash = self._current_session_hash()
        current_session_id = self._current_session_id()
        action = request.POST.get("action")

        if action == "revoke_session":
            result = revoke_session(
                session_id=request.POST.get("session_id"),
                actor=current_user,
                request=request,
                current_session_hash=current_session_hash,
                current_session_id=current_session_id,
            )
            if not result["updated"]:
                messages.error(request, "No fue posible revocar la sesion seleccionada.")
                return redirect(self._build_redirect_url())

            if result["is_current"]:
                request.session.flush()
                messages.info(request, "La sesion actual fue cerrada.")
                return redirect("seguridad-login")

            messages.success(request, "Sesion revocada correctamente.")
            return redirect(self._build_redirect_url())

        if action == "revoke_other_sessions":
            revoked = revoke_other_sessions_for_user(
                usuario=current_user,
                actor=current_user,
                request=request,
                current_session_hash=current_session_hash,
                current_session_id=current_session_id,
            )
            if revoked:
                messages.success(request, f"Se revocaron {revoked} sesiones adicionales.")
            else:
                messages.info(request, "No existen otras sesiones activas para revocar.")
            return redirect(self._build_redirect_url())

        messages.error(request, "Accion no reconocida.")
        return redirect(self._build_redirect_url())
