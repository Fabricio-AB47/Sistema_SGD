from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.core.mixins import SigLoginRequiredMixin
from apps.mejora.forms import (
    AsignacionResponsableForm,
    CargaInformacionForm,
    CicloAprobacionForm,
    EnvioFormalForm,
    RecepcionEvaluadorForm,
    RevisionJefaturaForm,
)


MODULE_TITLE = "Mejora"
MODULE_DESCRIPTION = "Guia operativa para ejecutar y cerrar el proceso de autoevaluacion."
WORKFLOW_SESSION_KEY = "mejora_proceso_workflow"


def _empty_workflow_data() -> dict:
    return {
        "ciclo_aprobacion": None,
        "asignaciones": [],
        "cargas": [],
        "revision_jefatura": None,
        "envio_formal": None,
        "recepcion_evaluador": None,
    }


def _to_serializable(cleaned_data: dict) -> dict:
    payload = {}
    for key, value in cleaned_data.items():
        if hasattr(value, "isoformat"):
            payload[key] = value.isoformat()
        else:
            payload[key] = value
    return payload


class MejoraBaseView(SigLoginRequiredMixin, TemplateView):
    template_name = ""
    page_title = ""
    page_description = ""
    page_status = "Operacion real"
    page_actions = []
    module_tabs = [
        {
            "label": "Resumen",
            "url_name": "mejora-lista",
            "active_names": ("mejora-lista",),
        },
        {
            "label": "1. Aprobacion ciclo",
            "url_name": "mejora-ciclo-aprobacion",
            "active_names": ("mejora-ciclo-aprobacion", "mejora-crear"),
        },
        {
            "label": "2. Asignacion",
            "url_name": "mejora-asignacion-responsables",
            "active_names": ("mejora-asignacion-responsables",),
        },
        {
            "label": "3. Carga informacion",
            "url_name": "mejora-carga-informacion",
            "active_names": ("mejora-carga-informacion",),
        },
        {
            "label": "4. Revision jefatura",
            "url_name": "mejora-revision-jefatura",
            "active_names": ("mejora-revision-jefatura", "mejora-detalle"),
        },
        {
            "label": "5. Envio formal",
            "url_name": "mejora-envio-formal",
            "active_names": ("mejora-envio-formal",),
        },
        {
            "label": "6. Recepcion evaluador",
            "url_name": "mejora-recepcion-evaluador",
            "active_names": ("mejora-recepcion-evaluador",),
        },
        {
            "label": "Seguimiento",
            "url_name": "mejora-seguimiento",
            "active_names": ("mejora-seguimiento",),
        },
    ]

    def _get_workflow_data(self) -> dict:
        data = self.request.session.get(WORKFLOW_SESSION_KEY) or _empty_workflow_data()
        for key, value in _empty_workflow_data().items():
            data.setdefault(key, value)
        return data

    def _save_workflow_data(self, data: dict):
        self.request.session[WORKFLOW_SESSION_KEY] = data
        self.request.session.modified = True

    @staticmethod
    def _completion(data: dict) -> dict:
        steps = {
            "ciclo_aprobacion": bool(data.get("ciclo_aprobacion")),
            "asignaciones": len(data.get("asignaciones", [])) > 0,
            "cargas": len(data.get("cargas", [])) > 0,
            "revision_jefatura": bool(data.get("revision_jefatura")),
            "envio_formal": bool(data.get("envio_formal")),
            "recepcion_evaluador": bool(data.get("recepcion_evaluador")),
        }
        completed = sum(1 for value in steps.values() if value)
        return {
            "steps": steps,
            "completed": completed,
            "total": len(steps),
            "percentage": round((completed / len(steps)) * 100, 2),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        workflow_data = kwargs.get("workflow_data") or self._get_workflow_data()
        context.update(
            {
                "module_title": MODULE_TITLE,
                "module_description": MODULE_DESCRIPTION,
                "module_tabs": self.module_tabs,
                "page_title": self.page_title,
                "page_description": self.page_description,
                "page_status": self.page_status,
                "page_actions": self.page_actions,
                "current_url_name": self.request.resolver_match.url_name if self.request.resolver_match else "",
                "workflow_data": workflow_data,
                "completion": self._completion(workflow_data),
            }
        )
        return context


class ProcesoDashboardView(MejoraBaseView):
    template_name = "mejora/proceso_dashboard.html"
    page_title = "Panel del proceso"
    page_description = "Controla el avance de las 6 etapas del proceso de autoevaluacion."


class ProcesoCicloAprobacionView(MejoraBaseView):
    template_name = "mejora/ciclo_aprobacion.html"
    page_title = "Paso 1: Aprobacion del ciclo"
    page_description = "Registra la aprobacion del ciclo de autoevaluacion."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = context["workflow_data"].get("ciclo_aprobacion") or {}
        context["form"] = kwargs.get("form") or CicloAprobacionForm(initial=data)
        return context

    def post(self, request, *args, **kwargs):
        form = CicloAprobacionForm(request.POST)
        if form.is_valid():
            data = self._get_workflow_data()
            data["ciclo_aprobacion"] = _to_serializable(form.cleaned_data)
            self._save_workflow_data(data)
            messages.success(request, "Aprobacion de ciclo registrada correctamente.")
            return redirect("mejora-asignacion-responsables")
        return self.render_to_response(self.get_context_data(form=form))


class ProcesoAsignacionResponsablesView(MejoraBaseView):
    template_name = "mejora/asignacion_responsables.html"
    page_title = "Paso 2: Asignacion de responsables"
    page_description = "Registra responsables por area, indicador y elemento."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or AsignacionResponsableForm()
        return context

    def post(self, request, *args, **kwargs):
        data = self._get_workflow_data()
        action = (request.POST.get("action") or "").strip().lower()

        if action == "clear":
            data["asignaciones"] = []
            self._save_workflow_data(data)
            messages.info(request, "Asignaciones limpiadas.")
            return redirect("mejora-asignacion-responsables")

        form = AsignacionResponsableForm(request.POST)
        if form.is_valid():
            data["asignaciones"].append(_to_serializable(form.cleaned_data))
            self._save_workflow_data(data)
            messages.success(request, "Responsable asignado correctamente.")
            return redirect("mejora-asignacion-responsables")

        return self.render_to_response(self.get_context_data(form=form, workflow_data=data))


class ProcesoCargaInformacionView(MejoraBaseView):
    template_name = "mejora/carga_informacion.html"
    page_title = "Paso 3: Carga de informacion"
    page_description = "Registra las cargas de evidencia y metadatos."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or CargaInformacionForm()
        return context

    def post(self, request, *args, **kwargs):
        data = self._get_workflow_data()
        action = (request.POST.get("action") or "").strip().lower()

        if action == "clear":
            data["cargas"] = []
            self._save_workflow_data(data)
            messages.info(request, "Cargas de informacion limpiadas.")
            return redirect("mejora-carga-informacion")

        form = CargaInformacionForm(request.POST)
        if form.is_valid():
            data["cargas"].append(_to_serializable(form.cleaned_data))
            self._save_workflow_data(data)
            messages.success(request, "Carga registrada correctamente.")
            return redirect("mejora-carga-informacion")

        return self.render_to_response(self.get_context_data(form=form, workflow_data=data))


class ProcesoRevisionJefaturaView(MejoraBaseView):
    template_name = "mejora/revision_jefatura.html"
    page_title = "Paso 4: Revision de jefatura"
    page_description = "Registra la revision y visto de avance del jefe."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = context["workflow_data"].get("revision_jefatura") or {}
        context["form"] = kwargs.get("form") or RevisionJefaturaForm(initial=data)
        return context

    def post(self, request, *args, **kwargs):
        form = RevisionJefaturaForm(request.POST)
        if form.is_valid():
            data = self._get_workflow_data()
            data["revision_jefatura"] = _to_serializable(form.cleaned_data)
            self._save_workflow_data(data)
            messages.success(request, "Revision de jefatura registrada.")
            return redirect("mejora-envio-formal")
        return self.render_to_response(self.get_context_data(form=form))


class ProcesoEnvioFormalView(MejoraBaseView):
    template_name = "mejora/envio_formal.html"
    page_title = "Paso 5: Envio formal"
    page_description = "Registra la aprobacion y envio formal por el director de area."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = context["workflow_data"].get("envio_formal") or {}
        context["form"] = kwargs.get("form") or EnvioFormalForm(initial=data)
        return context

    def post(self, request, *args, **kwargs):
        form = EnvioFormalForm(request.POST)
        if form.is_valid():
            data = self._get_workflow_data()
            data["envio_formal"] = _to_serializable(form.cleaned_data)
            self._save_workflow_data(data)
            messages.success(request, "Envio formal registrado correctamente.")
            return redirect("mejora-recepcion-evaluador")
        return self.render_to_response(self.get_context_data(form=form))


class ProcesoRecepcionEvaluadorView(MejoraBaseView):
    template_name = "mejora/recepcion_evaluador.html"
    page_title = "Paso 6: Recepcion evaluador"
    page_description = "Registra la recepcion formal por el responsable evaluador."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = context["workflow_data"].get("recepcion_evaluador") or {}
        context["form"] = kwargs.get("form") or RecepcionEvaluadorForm(initial=data)
        return context

    def post(self, request, *args, **kwargs):
        form = RecepcionEvaluadorForm(request.POST)
        if form.is_valid():
            data = self._get_workflow_data()
            data["recepcion_evaluador"] = _to_serializable(form.cleaned_data)
            self._save_workflow_data(data)
            messages.success(request, "Recepcion de evaluador registrada. Proceso completo.")
            return redirect("mejora-seguimiento")
        return self.render_to_response(self.get_context_data(form=form))


class ProcesoSeguimientoView(MejoraBaseView):
    template_name = "mejora/seguimiento.html"
    page_title = "Seguimiento integral"
    page_description = "Consolida estado, avances y registros cargados en cada etapa."
