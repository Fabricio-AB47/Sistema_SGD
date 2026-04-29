from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.auditoria.services import registrar_evento
from apps.core.mixins import SigAdminRoleRequiredMixin
from apps.integraciones.forms import ServicioForm
from apps.integraciones.models import ApiServicio
from apps.usuarios.models import Usuario


def _get_current_usuario(request):
    user_id = request.session.get("sig_user_id")
    if not user_id:
        return None
    return Usuario.objects.filter(pk=user_id).first()


class ServicioListView(SigAdminRoleRequiredMixin, ListView):
    model = ApiServicio
    template_name = "integraciones/servicio_list.html"
    context_object_name = "servicios"
    paginate_by = 20

    def get_queryset(self):
        return ApiServicio.objects.prefetch_related("credenciales").order_by("nombre_servicio", "proveedor")


class ServicioCreateView(SigAdminRoleRequiredMixin, CreateView):
    model = ApiServicio
    form_class = ServicioForm
    template_name = "integraciones/servicio_form.html"
    success_url = reverse_lazy("integraciones-servicios-lista")

    def form_valid(self, form):
        response = super().form_valid(form)
        registrar_evento(
            usuario=_get_current_usuario(self.request),
            accion="CREAR SERVICIO API",
            tipo_evento="INTEGRACIONES",
            tabla_afectada="api_servicio",
            id_registro=self.object.pk,
            descripcion=f"Se creó el servicio API {self.object.nombre_servicio}.",
            valores_nuevos={
                "nombre_servicio": self.object.nombre_servicio,
                "proveedor": self.object.proveedor,
                "url_base": self.object.url_base,
                "activo": self.object.activo,
            },
            criticidad="MEDIA",
            request=self.request,
        )
        messages.success(self.request, "Servicio API creado exitosamente.")
        return response


class ServicioUpdateView(SigAdminRoleRequiredMixin, UpdateView):
    model = ApiServicio
    form_class = ServicioForm
    template_name = "integraciones/servicio_form.html"
    success_url = reverse_lazy("integraciones-servicios-lista")

    def form_valid(self, form):
        original = ApiServicio.objects.filter(pk=self.get_object().pk).values(
            "nombre_servicio",
            "proveedor",
            "descripcion",
            "url_base",
            "activo",
        ).first()
        response = super().form_valid(form)
        registrar_evento(
            usuario=_get_current_usuario(self.request),
            accion="ACTUALIZAR SERVICIO API",
            tipo_evento="INTEGRACIONES",
            tabla_afectada="api_servicio",
            id_registro=self.object.pk,
            descripcion=f"Se actualizó el servicio API {self.object.nombre_servicio}.",
            valores_anteriores=original,
            valores_nuevos={
                "nombre_servicio": self.object.nombre_servicio,
                "proveedor": self.object.proveedor,
                "descripcion": self.object.descripcion,
                "url_base": self.object.url_base,
                "activo": self.object.activo,
            },
            criticidad="MEDIA",
            request=self.request,
        )
        messages.success(self.request, "Servicio API actualizado exitosamente.")
        return response
