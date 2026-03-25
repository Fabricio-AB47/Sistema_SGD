import json

from django.views.generic import DetailView, ListView

from apps.auditoria.models import Auditoria
from apps.auditoria.selectors.auditoria_selector import (
    obtener_auditorias_filtradas,
    obtener_opciones_filtro,
    obtener_resumen_auditoria,
)
from apps.core.mixins import SigLoginRequiredMixin


def _pretty_payload(value):
    if not value:
        return "--"
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return value
    return json.dumps(parsed, ensure_ascii=False, indent=2)


class AuditoriaListView(SigLoginRequiredMixin, ListView):
    model = Auditoria
    template_name = "auditoria/lista.html"
    context_object_name = "auditorias"
    paginate_by = 20

    def get_queryset(self):
        return obtener_auditorias_filtradas(self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(obtener_opciones_filtro())
        context["resumen"] = obtener_resumen_auditoria(self.object_list)
        return context


class AuditoriaDetailView(SigLoginRequiredMixin, DetailView):
    model = Auditoria
    template_name = "auditoria/detalle.html"
    context_object_name = "auditoria"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["valores_anteriores_pretty"] = _pretty_payload(self.object.valores_anteriores)
        context["valores_nuevos_pretty"] = _pretty_payload(self.object.valores_nuevos)
        return context
