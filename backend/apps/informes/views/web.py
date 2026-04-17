import logging

from django.contrib import messages
from django.db import DatabaseError, IntegrityError, OperationalError
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView

from apps.core.mixins import SigLoginRequiredMixin
from apps.informes.forms import InformeAprobacionForm, InformeGeneracionForm
from apps.informes.selectors import (
    get_informe_detail,
    get_informe_metrics,
    get_informes_queryset,
)
from apps.informes.services import InformeWorkflowError, aprobar_informe, generar_informe
from apps.usuarios.models import Usuario


logger = logging.getLogger(__name__)

MODULE_TITLE = "Informes"
MODULE_DESCRIPTION = "Gestiona informes de autoevaluacion y su flujo de aprobacion."
MODULE_TABS = [
    {"label": "Informes", "url_name": "informes-lista", "active_names": ("informes-lista", "informes-detalle")},
    {"label": "Generar informe", "url_name": "informes-generar", "active_names": ("informes-generar",)},
    {"label": "Aprobar informe", "url_name": "informes-aprobar", "active_names": ("informes-aprobar",)},
]


def _report_operation_error(*, request, exc: Exception, user_message: str, form=None):
    logger.exception("Operacion de informes fallida", exc_info=exc)
    messages.error(request, user_message)
    if form is not None:
        form.add_error(None, user_message)


class InformesBaseView(SigLoginRequiredMixin, TemplateView):
    template_name = ""
    page_title = ""
    page_description = ""
    page_status = "Operacion real"
    page_actions = []

    def _actor(self):
        user_id = self.request.session.get("sig_user_id")
        if not user_id:
            return None
        return Usuario.objects.filter(pk=user_id).only("id_user", "primer_nombre", "primer_apellido").first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "module_title": MODULE_TITLE,
                "module_description": MODULE_DESCRIPTION,
                "module_tabs": MODULE_TABS,
                "page_title": self.page_title,
                "page_description": self.page_description,
                "page_status": self.page_status,
                "page_actions": self.page_actions,
                "current_url_name": self.request.resolver_match.url_name if self.request.resolver_match else "",
                "informe_metrics": get_informe_metrics(),
            }
        )
        context.update(kwargs)
        return context


class InformeListView(InformesBaseView):
    template_name = "informes/informe_list.html"
    page_title = "Informes"
    page_description = "Consulta informes registrados, su ciclo asociado y el estado actual de aprobación."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["informes"] = get_informes_queryset()[:100]
        return context


class InformeGenerateView(InformesBaseView):
    template_name = "informes/informe_generate.html"
    page_title = "Generar informe"
    page_description = "Registra un informe de autoevaluacion para un ciclo y deja trazabilidad desde su creación."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or InformeGeneracionForm()
        context["recent_informes"] = get_informes_queryset()[:15]
        return context

    def post(self, request, *args, **kwargs):
        form = InformeGeneracionForm(request.POST)
        if form.is_valid():
            try:
                informe = generar_informe(form=form, actor=self._actor(), request=request)
            except (
                InformeWorkflowError,
                ValueError,
                IntegrityError,
                OperationalError,
                DatabaseError,
            ) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible registrar el informe.",
                )
            else:
                messages.success(request, "Informe registrado correctamente.")
                return redirect(f"{reverse('informes-detalle')}?informe={informe.pk}")
        return self.render_to_response(self.get_context_data(form=form))


class InformeDetailView(InformesBaseView):
    template_name = "informes/informe_detail.html"
    page_title = "Detalle de informe"
    page_description = "Consulta resumen, conclusiones, documento vinculado y trazabilidad de aprobación."

    def get(self, request, *args, **kwargs):
        informe = get_informe_detail(request.GET.get("informe"))
        if informe is None:
            raise Http404("El informe solicitado no existe.")
        return self.render_to_response(self.get_context_data(informe=informe))


class InformeApproveView(InformesBaseView):
    template_name = "informes/informe_approve.html"
    page_title = "Aprobar informe"
    page_description = "Actualiza el estado del informe y registra la observación de aprobación o rechazo."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        informe = kwargs.get("informe") or get_informe_detail(
            self.request.GET.get("informe") or self.request.POST.get("informe")
        )
        context["informe"] = informe
        context["form"] = kwargs.get("form") or InformeAprobacionForm(informe_initial=informe)
        context["pending_informes"] = get_informes_queryset(estado="EN_REVISION")[:20]
        return context

    def post(self, request, *args, **kwargs):
        form = InformeAprobacionForm(request.POST)
        if form.is_valid():
            try:
                aprobar_informe(
                    informe=form.cleaned_data["informe"],
                    estado=form.cleaned_data["estado"],
                    observacion_aprobacion=form.cleaned_data.get("observacion_aprobacion"),
                    actor=self._actor(),
                    request=request,
                )
            except (
                InformeWorkflowError,
                ValueError,
                IntegrityError,
                OperationalError,
                DatabaseError,
            ) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible actualizar el estado del informe.",
                )
            else:
                messages.success(request, "Estado del informe actualizado correctamente.")
                return redirect(f"{reverse('informes-detalle')}?informe={form.cleaned_data['informe'].pk}")
        return self.render_to_response(
            self.get_context_data(
                form=form,
                informe=get_informe_detail(request.POST.get("informe")),
            )
        )
