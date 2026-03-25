from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from apps.auditoria.services import registrar_evento
from apps.core.mixins import SigLoginRequiredMixin
from apps.integraciones.forms import CredencialForm
from apps.integraciones.models import ApiCredencial
from apps.integraciones.services import api_service
from apps.usuarios.models import Usuario


def _get_current_usuario(request):
    user_id = request.session.get("sig_user_id")
    if not user_id:
        return None
    return Usuario.objects.filter(pk=user_id).first()


class CredencialListView(SigLoginRequiredMixin, ListView):
    model = ApiCredencial
    template_name = "integraciones/credencial_list.html"
    context_object_name = "credenciales"
    paginate_by = 20

    def get_queryset(self):
        queryset = ApiCredencial.objects.select_related("api_servicio", "creado_por").order_by(
            "-fecha_creacion"
        )
        servicio_id = self.request.GET.get("servicio")
        if servicio_id:
            queryset = queryset.filter(api_servicio_id=servicio_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["servicios"] = api_service.obtener_servicios_activos()
        return context


class CredencialCreateView(SigLoginRequiredMixin, CreateView):
    model = ApiCredencial
    form_class = CredencialForm
    template_name = "integraciones/credencial_form.html"
    success_url = reverse_lazy("integraciones-credenciales-lista")

    def form_valid(self, form):
        self.object = form.save(current_user=_get_current_usuario(self.request))
        registrar_evento(
            usuario=_get_current_usuario(self.request),
            accion="CREAR CREDENCIAL API",
            tipo_evento="INTEGRACIONES",
            tabla_afectada="api_credencial",
            id_registro=self.object.pk,
            descripcion=f"Se creó la credencial API {self.object.nombre_aplicacion}.",
            valores_nuevos={
                "api_servicio": self.object.api_servicio.nombre_servicio,
                "nombre_aplicacion": self.object.nombre_aplicacion,
                "client_id": "PROTEGIDO" if self.object.client_id else None,
                "tenant_id": "PROTEGIDO" if self.object.tenant_id else None,
                "secret": "PROTEGIDO",
                "activo": self.object.activo,
            },
            criticidad="ALTA",
            request=self.request,
        )
        messages.success(self.request, "Credencial registrada y cifrada correctamente.")
        return redirect(self.get_success_url())
