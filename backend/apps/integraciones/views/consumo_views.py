from django.views.generic import ListView

from apps.core.mixins import SigAdminRoleRequiredMixin
from apps.integraciones.models import ApiConsumoLog
from apps.integraciones.services import api_service


class ConsumoLogView(SigAdminRoleRequiredMixin, ListView):
    model = ApiConsumoLog
    template_name = "integraciones/consumo_log.html"
    context_object_name = "logs"
    paginate_by = 30

    def get_queryset(self):
        queryset = ApiConsumoLog.objects.select_related("api_servicio", "usuario_sistema").order_by(
            "-fecha_consumo"
        )
        servicio_id = self.request.GET.get("servicio")
        if servicio_id:
            queryset = queryset.filter(api_servicio_id=servicio_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["servicios"] = api_service.obtener_servicios_activos()
        return context
