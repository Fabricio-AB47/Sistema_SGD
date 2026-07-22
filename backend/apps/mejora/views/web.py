from __future__ import annotations

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.acreditacion.models import CicloEvaluacion, RolIndicador
from apps.core.mixins import SigRoleOrPermissionRequiredMixin
from apps.core.services.navigation_service import (
    PERM_CONSULTA_VER,
    PERM_MEJORA_GESTIONAR,
    ROLE_ADMIN,
    ROLE_CONSULTA,
    ROLE_QUALITY,
    ROLE_RECTOR,
)
from apps.mejora.forms import (
    AsignacionResponsableForm,
    CargaInformacionForm,
    CicloAprobacionForm,
    EnvioFormalForm,
    RecepcionEvaluadorForm,
    RevisionJefaturaForm,
)
from apps.evaluacion.models import Evaluacion, RevisionInternaEvidencia, TareaEvidencia
from apps.evidencias.models import RegistroEvidencia


MODULE_TITLE = "Mejora"
MODULE_DESCRIPTION = "Guia operativa para ejecutar y cerrar el proceso de autoevaluacion."
WORKFLOW_SESSION_KEY = "mejora_proceso_workflow"
WORKFLOW_MANAGEMENT_ROLES = {ROLE_ADMIN, ROLE_QUALITY}
EVALUATOR_RECEPTION_ROLES = {ROLE_ADMIN, ROLE_QUALITY}
READ_ONLY_TAB_URLS = {"mejora-lista", "mejora-seguimiento"}
WORKFLOW_STEP_DEFINITIONS = (
    {
        "key": "ciclo_aprobacion",
        "number": 1,
        "label": "Aprobacion del ciclo",
        "capture": "Ciclo, fecha, aprobador, acta y observacion.",
        "url_name": "mejora-ciclo-aprobacion",
        "manage_label": "Iniciar proceso",
    },
    {
        "key": "asignaciones",
        "number": 2,
        "label": "Asignacion de responsables",
        "capture": "Area, jefe, responsable, indicador, elemento y fecha.",
        "url_name": "mejora-asignacion-responsables",
        "manage_label": "Continuar asignacion",
    },
    {
        "key": "cargas",
        "number": 3,
        "label": "Carga de informacion",
        "capture": "Evidencia, descripcion, metadatos, indicador, elemento y fecha.",
        "url_name": "mejora-carga-informacion",
        "manage_label": "Continuar carga",
    },
    {
        "key": "revision_jefatura",
        "number": 4,
        "label": "Revision de jefatura",
        "capture": "Revisor, decision, comentario y fecha.",
        "url_name": "mejora-revision-jefatura",
        "manage_label": "Continuar revision",
    },
    {
        "key": "envio_formal",
        "number": 5,
        "label": "Envio formal",
        "capture": "Director, fecha de envio, confirmacion y comentario.",
        "url_name": "mejora-envio-formal",
        "manage_label": "Continuar envio",
    },
    {
        "key": "recepcion_evaluador",
        "number": 6,
        "label": "Recepcion del evaluador",
        "capture": "Evaluador, fecha de recepcion, estado inicial y observacion.",
        "url_name": "mejora-recepcion-evaluador",
        "manage_label": "Continuar recepcion",
    },
)


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


def _invalidate_after(data: dict, step_key: str):
    ordered_keys = [step["key"] for step in WORKFLOW_STEP_DEFINITIONS]
    if step_key not in ordered_keys:
        return
    for key in ordered_keys[ordered_keys.index(step_key) + 1 :]:
        data[key] = [] if key in {"asignaciones", "cargas"} else None


def _full_name(user) -> str:
    if user is None:
        return ""
    return getattr(user, "nombre_completo", None) or str(user)


def _latest_real_cycle():
    queryset = CicloEvaluacion.objects.select_related(
        "estado",
        "aprobado_por",
        "documento_autorizacion",
    ).order_by("-fecha_inicio", "-id_ciclo")
    approved = queryset.filter(
        Q(fecha_aprobacion__isnull=False)
        | Q(estado__descripcion__icontains="APROB")
        | Q(estado__descripcion__icontains="ACTIV")
    ).first()
    return approved or queryset.first()


def _real_workflow_data() -> dict:
    data = _empty_workflow_data()
    ciclo = _latest_real_cycle()
    if ciclo is None:
        return data

    ciclo_estado = (getattr(getattr(ciclo, "estado", None), "descripcion", "") or "").strip()
    ciclo_aprobado = bool(getattr(ciclo, "fecha_aprobacion", None)) or any(
        token in ciclo_estado.upper() for token in ("APROB", "ACTIV", "EJECUC")
    )
    if ciclo_aprobado:
        data["ciclo_aprobacion"] = {
            "id_ciclo": ciclo.pk,
            "ciclo_nombre": ciclo.nombre,
            "fecha_aprobacion": getattr(ciclo, "fecha_aprobacion", None),
            "aprobado_por": _full_name(getattr(ciclo, "aprobado_por", None)) or ciclo_estado,
            "acta_reunion": getattr(getattr(ciclo, "documento_autorizacion", None), "nombre_archivo", ""),
            "observacion": getattr(ciclo, "observacion_aprobacion", "") or ciclo_estado,
            "source": "real",
        }

    tareas = list(
        TareaEvidencia.objects.select_related(
            "ciclo",
            "indicador",
            "elemento_fundamental",
            "usuario_responsable",
            "asignado_por",
        )
        .filter(ciclo=ciclo, activo=True)
        .order_by("-fecha_asignacion", "-id_tarea_evidencia")[:200]
    )
    data["asignaciones"] = [
        {
            "area": "",
            "director_jefe": _full_name(tarea.asignado_por),
            "subordinado_responsable": _full_name(tarea.usuario_responsable),
            "indicador": str(tarea.indicador),
            "elemento": str(tarea.elemento_fundamental),
            "fecha_asignacion": getattr(tarea, "fecha_asignacion", None),
            "source": "real",
        }
        for tarea in tareas
    ]
    if not data["asignaciones"]:
        role_assignments = list(
            RolIndicador.objects.select_related("rol", "indicador", "asignado_por")
            .filter(ciclo=ciclo, activo=True)
            .order_by("-fecha_asignacion", "-id_rol_indicador")[:200]
        )
        data["asignaciones"] = [
            {
                "area": "",
                "director_jefe": _full_name(access.asignado_por),
                "subordinado_responsable": getattr(access.rol, "nombre_rol", str(access.rol)),
                "indicador": str(access.indicador),
                "elemento": "Acceso total" if access.acceso_total else "Acceso parcial",
                "fecha_asignacion": getattr(access, "fecha_asignacion", None),
                "source": "real",
            }
            for access in role_assignments
        ]

    registros = list(
        RegistroEvidencia.objects.select_related(
            "documento",
            "indicador",
            "elemento_fundamental",
            "registrado_por",
            "enviado_revision_por",
            "estado",
        )
        .filter(ciclo=ciclo)
        .order_by("-fecha_registro", "-id_registro")[:200]
    )
    data["cargas"] = [
        {
            "responsable": _full_name(registro.registrado_por),
            "indicador": str(registro.indicador),
            "elemento": str(registro.elemento_fundamental),
            "nombre_evidencia": getattr(registro.documento, "nombre_archivo", ""),
            "descripcion": getattr(registro, "comentario", "") or "",
            "metadatos": getattr(getattr(registro, "estado", None), "descripcion", ""),
            "fecha_carga": getattr(registro, "fecha_registro", None),
            "source": "real",
        }
        for registro in registros
    ]

    registro_ids = [registro.pk for registro in registros]
    revision = None
    if registro_ids:
        revision_interna = (
            RevisionInternaEvidencia.objects.select_related("usuario_revisor")
            .filter(registro_id__in=registro_ids)
            .order_by("-fecha_revision", "-id_revision_interna")
            .first()
        )
        released = next((registro for registro in registros if registro.fecha_envio_revision), None)
        if revision_interna is not None:
            decision = "APROBADA" if revision_interna.resultado == RevisionInternaEvidencia.RESULTADO_APROBADA else "OBSERVADA"
            revision = {
                "jefe_revisor": _full_name(revision_interna.usuario_revisor),
                "decision": decision,
                "comentario": revision_interna.comentario or "",
                "fecha_revision": revision_interna.fecha_revision,
                "source": "real",
            }
        elif released is not None:
            revision = {
                "jefe_revisor": _full_name(released.enviado_revision_por),
                "decision": "APROBADA",
                "comentario": "Evidencia liberada al evaluador.",
                "fecha_revision": released.fecha_envio_revision,
                "source": "real",
            }
        data["revision_jefatura"] = revision

        latest_release = next((registro for registro in registros if registro.fecha_envio_revision), None)
        if latest_release is not None:
            data["envio_formal"] = {
                "director_area": _full_name(latest_release.enviado_revision_por),
                "fecha_envio": latest_release.fecha_envio_revision,
                "aprobado": True,
                "comentario": "Evidencias enviadas formalmente al evaluador.",
                "source": "real",
            }

        latest_evaluation = (
            Evaluacion.objects.select_related("usuario_evaluador", "estado", "registro")
            .filter(registro_id__in=registro_ids)
            .order_by("-fecha_evaluacion", "-id_evaluacion")
            .first()
        )
        if latest_evaluation is not None:
            data["recepcion_evaluador"] = {
                "evaluador_responsable": _full_name(latest_evaluation.usuario_evaluador),
                "fecha_recepcion": latest_evaluation.fecha_evaluacion,
                "estado_inicial": getattr(latest_evaluation.estado, "descripcion", "Evaluado"),
                "observacion": latest_evaluation.comentario or "",
                "source": "real",
            }
    return data


def _merge_workflow_data(session_data: dict, real_data: dict) -> dict:
    merged = _empty_workflow_data()
    for key in merged:
        real_value = real_data.get(key)
        session_value = session_data.get(key)
        if isinstance(merged[key], list):
            merged[key] = real_value if real_value else (session_value or [])
        else:
            merged[key] = real_value or session_value
    return merged


class MejoraBaseView(SigRoleOrPermissionRequiredMixin, TemplateView):
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY, ROLE_RECTOR, ROLE_CONSULTA)
    allowed_permissions = (PERM_MEJORA_GESTIONAR, PERM_CONSULTA_VER)
    access_denied_message = "No tienes acceso al proceso de mejora."
    template_name = ""
    page_title = ""
    page_description = ""
    page_status = "Operacion real"
    page_actions = []
    workflow_step_key = ""
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

    def _get_session_workflow_data(self) -> dict:
        data = self.request.session.get(WORKFLOW_SESSION_KEY) or _empty_workflow_data()
        for key, value in _empty_workflow_data().items():
            data.setdefault(key, value)
        return data

    def _get_workflow_data(self) -> dict:
        return _merge_workflow_data(self._get_session_workflow_data(), _real_workflow_data())

    def _save_workflow_data(self, data: dict):
        self.request.session[WORKFLOW_SESSION_KEY] = data
        self.request.session.modified = True

    def _role_tokens(self) -> set[str]:
        role_names = [
            *(self.request.session.get("sig_roles", []) or []),
            *(self.request.session.get("sig_operational_roles", []) or []),
        ]
        return {str(role).strip().upper() for role in role_names if str(role).strip()}

    def _permission_tokens(self) -> set[str]:
        return {
            str(permission).strip().lower()
            for permission in (self.request.session.get("sig_permissions", []) or [])
            if str(permission).strip()
        }

    def _can_manage_workflow(self) -> bool:
        role_tokens = self._role_tokens()
        permission_tokens = self._permission_tokens()
        return bool(
            role_tokens.intersection(WORKFLOW_MANAGEMENT_ROLES)
            or PERM_MEJORA_GESTIONAR in permission_tokens
        )

    def _can_access_evaluator_reception(self) -> bool:
        role_tokens = self._role_tokens()
        permission_tokens = self._permission_tokens()
        return bool(
            role_tokens.intersection(EVALUATOR_RECEPTION_ROLES)
            or PERM_MEJORA_GESTIONAR in permission_tokens
        )

    def _module_tabs(self):
        if self._can_manage_workflow():
            return self.module_tabs

        return [tab for tab in self.module_tabs if tab["url_name"] in READ_ONLY_TAB_URLS]

    @staticmethod
    def _completion(data: dict) -> dict:
        revision = data.get("revision_jefatura") or {}
        envio = data.get("envio_formal") or {}
        steps = {}
        steps["ciclo_aprobacion"] = bool(data.get("ciclo_aprobacion"))
        steps["asignaciones"] = steps["ciclo_aprobacion"] and len(data.get("asignaciones", [])) > 0
        steps["cargas"] = steps["asignaciones"] and len(data.get("cargas", [])) > 0
        steps["revision_jefatura"] = steps["cargas"] and revision.get("decision") == "APROBADA"
        steps["envio_formal"] = steps["revision_jefatura"] and bool(envio) and bool(envio.get("aprobado"))
        steps["recepcion_evaluador"] = steps["envio_formal"] and bool(data.get("recepcion_evaluador"))
        completed = sum(1 for value in steps.values() if value)
        return {
            "steps": steps,
            "completed": completed,
            "total": len(steps),
            "percentage": round((completed / len(steps)) * 100, 2),
        }

    @classmethod
    def _workflow_steps(cls, data: dict) -> list[dict]:
        completion = cls._completion(data)
        previous_complete = True
        current_assigned = False
        rows = []
        for definition in WORKFLOW_STEP_DEFINITIONS:
            key = definition["key"]
            complete = completion["steps"][key]
            status = "locked"
            status_label = "Bloqueada"
            status_class = "muted"
            can_manage = previous_complete
            detail = ""

            if complete:
                status = "completed"
                status_label = "Aprobada"
                status_class = "success"
            elif key == "revision_jefatura" and previous_complete and data.get("revision_jefatura"):
                status = "blocked"
                status_label = "Observada"
                status_class = "danger"
                detail = "La jefatura solicito correcciones antes del envio formal."
                can_manage = True
            elif previous_complete and not current_assigned:
                status = "current"
                status_label = "En proceso"
                status_class = "warning"
                current_assigned = True
            elif previous_complete:
                status = "pending"
                status_label = "Pendiente"
                status_class = "warning"
            else:
                detail = "Completa y aprueba la etapa anterior para habilitar este paso."

            rows.append(
                {
                    **definition,
                    "complete": complete,
                    "status": status,
                    "status_label": status_label,
                    "status_class": status_class,
                    "can_manage": can_manage,
                    "detail": detail,
                }
            )
            previous_complete = previous_complete and complete
        return rows

    @classmethod
    def _next_workflow_step(cls, data: dict) -> dict | None:
        for step in cls._workflow_steps(data):
            if step["status"] in {"current", "blocked"}:
                return step
        return None

    def dispatch(self, request, *args, **kwargs):
        if self.workflow_step_key:
            workflow_data = self._get_workflow_data()
            selected_step = next(
                (
                    step
                    for step in self._workflow_steps(workflow_data)
                    if step["key"] == self.workflow_step_key
                ),
                None,
            )
            if selected_step and selected_step["status"] == "locked":
                messages.warning(
                    request,
                    "Completa y aprueba las etapas anteriores antes de continuar con este paso.",
                )
                return redirect("mejora-lista")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        workflow_data = kwargs.get("workflow_data") or self._get_workflow_data()
        workflow_steps = self._workflow_steps(workflow_data)
        next_workflow_step = self._next_workflow_step(workflow_data)
        context.update(
            {
                "module_title": MODULE_TITLE,
                "module_description": MODULE_DESCRIPTION,
                "module_tabs": self._module_tabs(),
                "page_title": self.page_title,
                "page_description": self.page_description,
                "page_status": self.page_status,
                "page_actions": self.page_actions,
                "current_url_name": self.request.resolver_match.url_name if self.request.resolver_match else "",
                "workflow_data": workflow_data,
                "completion": self._completion(workflow_data),
                "workflow_steps": workflow_steps,
                "next_workflow_step": next_workflow_step,
                "can_manage_mejora_workflow": self._can_manage_workflow(),
                "can_access_evaluator_reception": self._can_access_evaluator_reception(),
            }
        )
        return context


class ProcesoDashboardView(MejoraBaseView):
    template_name = "mejora/proceso_dashboard.html"
    page_title = "Panel del proceso"
    page_description = "Controla el avance de las 6 etapas del proceso de autoevaluacion."


class ProcesoCicloAprobacionView(MejoraBaseView):
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY)
    allowed_permissions = (PERM_MEJORA_GESTIONAR,)
    access_denied_message = "No tienes acceso para iniciar procesos de mejora."
    template_name = "mejora/ciclo_aprobacion.html"
    page_title = "Paso 1: Aprobacion del ciclo"
    page_description = "Registra la aprobacion del ciclo de autoevaluacion."
    workflow_step_key = "ciclo_aprobacion"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = context["workflow_data"].get("ciclo_aprobacion") or {}
        context["form"] = kwargs.get("form") or CicloAprobacionForm(initial=data)
        return context

    def post(self, request, *args, **kwargs):
        form = CicloAprobacionForm(request.POST)
        if form.is_valid():
            data = self._get_session_workflow_data()
            data["ciclo_aprobacion"] = _to_serializable(form.cleaned_data)
            _invalidate_after(data, "ciclo_aprobacion")
            self._save_workflow_data(data)
            messages.success(request, "Aprobacion de ciclo registrada correctamente.")
            return redirect("mejora-asignacion-responsables")
        return self.render_to_response(self.get_context_data(form=form))


class ProcesoAsignacionResponsablesView(MejoraBaseView):
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY)
    allowed_permissions = (PERM_MEJORA_GESTIONAR,)
    access_denied_message = "No tienes acceso para asignar responsables de mejora."
    template_name = "mejora/asignacion_responsables.html"
    page_title = "Paso 2: Asignacion de responsables"
    page_description = "Registra responsables por area, indicador y elemento."
    workflow_step_key = "asignaciones"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or AsignacionResponsableForm()
        return context

    def post(self, request, *args, **kwargs):
        data = self._get_session_workflow_data()
        action = (request.POST.get("action") or "").strip().lower()

        if action == "clear":
            data["asignaciones"] = []
            _invalidate_after(data, "asignaciones")
            self._save_workflow_data(data)
            messages.info(request, "Asignaciones limpiadas.")
            return redirect("mejora-asignacion-responsables")

        form = AsignacionResponsableForm(request.POST)
        if form.is_valid():
            data["asignaciones"].append(_to_serializable(form.cleaned_data))
            _invalidate_after(data, "asignaciones")
            self._save_workflow_data(data)
            messages.success(request, "Responsable asignado correctamente.")
            return redirect("mejora-asignacion-responsables")

        return self.render_to_response(self.get_context_data(form=form, workflow_data=data))


class ProcesoCargaInformacionView(MejoraBaseView):
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY)
    allowed_permissions = (PERM_MEJORA_GESTIONAR,)
    access_denied_message = "No tienes acceso para cargar informacion de mejora."
    template_name = "mejora/carga_informacion.html"
    page_title = "Paso 3: Carga de informacion"
    page_description = "Registra las cargas de evidencia y metadatos."
    workflow_step_key = "cargas"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or CargaInformacionForm()
        return context

    def post(self, request, *args, **kwargs):
        data = self._get_session_workflow_data()
        action = (request.POST.get("action") or "").strip().lower()

        if action == "clear":
            data["cargas"] = []
            _invalidate_after(data, "cargas")
            self._save_workflow_data(data)
            messages.info(request, "Cargas de informacion limpiadas.")
            return redirect("mejora-carga-informacion")

        form = CargaInformacionForm(request.POST)
        if form.is_valid():
            data["cargas"].append(_to_serializable(form.cleaned_data))
            _invalidate_after(data, "cargas")
            self._save_workflow_data(data)
            messages.success(request, "Carga registrada correctamente.")
            return redirect("mejora-carga-informacion")

        return self.render_to_response(self.get_context_data(form=form, workflow_data=data))


class ProcesoRevisionJefaturaView(MejoraBaseView):
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY)
    allowed_permissions = (PERM_MEJORA_GESTIONAR,)
    access_denied_message = "No tienes acceso para revisar el proceso de mejora."
    template_name = "mejora/revision_jefatura.html"
    page_title = "Paso 4: Revision de jefatura"
    page_description = "Registra la revision y visto de avance del jefe."
    workflow_step_key = "revision_jefatura"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = context["workflow_data"].get("revision_jefatura") or {}
        context["form"] = kwargs.get("form") or RevisionJefaturaForm(initial=data)
        return context

    def post(self, request, *args, **kwargs):
        form = RevisionJefaturaForm(request.POST)
        if form.is_valid():
            data = self._get_session_workflow_data()
            data["revision_jefatura"] = _to_serializable(form.cleaned_data)
            _invalidate_after(data, "revision_jefatura")
            self._save_workflow_data(data)
            if form.cleaned_data["decision"] == "APROBADA":
                messages.success(request, "Revision de jefatura aprobada. Puedes continuar con el envio formal.")
                return redirect("mejora-envio-formal")
            messages.warning(
                request,
                "Revision observada. Corrige la carga de informacion antes de solicitar el envio formal.",
            )
            return redirect("mejora-carga-informacion")
        return self.render_to_response(self.get_context_data(form=form))


class ProcesoEnvioFormalView(MejoraBaseView):
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY)
    allowed_permissions = (PERM_MEJORA_GESTIONAR,)
    access_denied_message = "No tienes acceso para enviar formalmente el proceso de mejora."
    template_name = "mejora/envio_formal.html"
    page_title = "Paso 5: Envio formal"
    page_description = "Registra la aprobacion y envio formal por el director de area."
    workflow_step_key = "envio_formal"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = context["workflow_data"].get("envio_formal") or {}
        context["form"] = kwargs.get("form") or EnvioFormalForm(initial=data)
        return context

    def post(self, request, *args, **kwargs):
        form = EnvioFormalForm(request.POST)
        if form.is_valid():
            data = self._get_session_workflow_data()
            data["envio_formal"] = _to_serializable(form.cleaned_data)
            _invalidate_after(data, "envio_formal")
            self._save_workflow_data(data)
            messages.success(request, "Envio formal registrado correctamente.")
            return redirect("mejora-recepcion-evaluador")
        return self.render_to_response(self.get_context_data(form=form))


class ProcesoRecepcionEvaluadorView(MejoraBaseView):
    allowed_roles = (ROLE_ADMIN, ROLE_QUALITY)
    allowed_permissions = (PERM_MEJORA_GESTIONAR,)
    access_denied_message = "No tienes acceso para registrar la recepcion del proceso de mejora."
    template_name = "mejora/recepcion_evaluador.html"
    page_title = "Paso 6: Recepcion evaluador"
    page_description = "Registra la recepcion formal por el responsable evaluador."
    workflow_step_key = "recepcion_evaluador"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = context["workflow_data"].get("recepcion_evaluador") or {}
        context["form"] = kwargs.get("form") or RecepcionEvaluadorForm(initial=data)
        return context

    def post(self, request, *args, **kwargs):
        form = RecepcionEvaluadorForm(request.POST)
        if form.is_valid():
            data = self._get_session_workflow_data()
            data["recepcion_evaluador"] = _to_serializable(form.cleaned_data)
            self._save_workflow_data(data)
            messages.success(request, "Recepcion de evaluador registrada. Proceso completo.")
            return redirect("mejora-seguimiento")
        return self.render_to_response(self.get_context_data(form=form))


class ProcesoSeguimientoView(MejoraBaseView):
    template_name = "mejora/seguimiento.html"
    page_title = "Seguimiento integral"
    page_description = "Consolida estado, avances y registros cargados en cada etapa."
