import logging

from django.contrib import messages
from django.db import DatabaseError, IntegrityError, OperationalError, transaction
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import RedirectView, TemplateView

from apps.core.mixins import SigLoginRequiredMixin
from apps.acreditacion.forms import (
    CicloEstadoAutorizacionForm,
    ESTADOS_FLUJO_CICLO,
    ESTADOS_RECTOR_DECISION,
    CicloAuthorizationRevisionForm,
    CicloEstadoUpdateForm,
    CicloEvaluacionForm,
    CriterioForm,
    ElementoFundamentalForm,
    IndicadorElementoForm,
    IndicadorForm,
    SubcriterioForm,
)
from apps.core.models import EstadoCiclo
from apps.acreditacion.selectors import (
    get_acreditacion_metrics,
    get_ciclo_detail,
    get_ciclos_queryset,
    get_criterios_queryset,
    get_elementos_queryset,
    get_indicator_detail,
    get_indicadores_queryset,
    get_matrix_rows,
    get_subcriterios_queryset,
)
from apps.acreditacion.services import (
    actualizar_estado_ciclo,
    crear_ciclo,
    crear_criterio,
    crear_elemento,
    crear_indicador,
    crear_subcriterio,
    vincular_indicador_elemento,
)
from apps.acreditacion.models import CicloEvaluacion
from apps.documentos.services import (
    AuthorizationServiceError,
    StructuredDocumentUploadError,
    upload_cycle_authorization_revision,
)
from apps.documentos.selectors import attach_cycle_authorization_status
from apps.evaluacion.forms import MatrixEvidenceRegistrationForm
from apps.evaluacion.selectors import get_matrix_registration_dashboard
from apps.evaluacion.services import (
    MatrixEvidenceRegistrationError,
    register_matrix_evidence,
)
from apps.integraciones.services.graph_service import GraphServiceError
from apps.usuarios.models import Usuario


logger = logging.getLogger(__name__)

MODULE_TITLE = "Acreditacion"
MODULE_DESCRIPTION = "Gestiona la estructura CACES real del sistema y su relacion con ciclos y evidencia."
MODULE_TABS = [
    {"label": "Criterios", "url_name": "acreditacion-criterios-lista", "active_names": ["acreditacion-criterios-lista"]},
    {"label": "Subcriterios", "url_name": "acreditacion-subcriterios-lista", "active_names": ["acreditacion-subcriterios-lista"]},
    {"label": "Indicadores", "url_name": "acreditacion-indicadores-lista", "active_names": ["acreditacion-indicadores-lista", "acreditacion-indicadores-detalle"]},
    {"label": "Elementos fundamentales", "url_name": "acreditacion-elementos-lista", "active_names": ["acreditacion-elementos-lista"]},
    {
        "label": "Matriz de registro",
        "url_name": "acreditacion-matriz-registro",
        "active_names": ["acreditacion-matriz-registro", "acreditacion-matriz-evidencias"],
    },
    {"label": "Matriz de acreditacion", "url_name": "acreditacion-matriz", "active_names": ["acreditacion-matriz"]},
    {"label": "Ciclos y autorizacion", "url_name": "acreditacion-ciclos-lista", "active_names": ["acreditacion-ciclos-lista", "acreditacion-ciclos-crear", "acreditacion-ciclos-detalle"]},
]


def _report_operation_error(*, request, exc: Exception, form=None, user_message: str):
    logger.exception("Operacion de acreditacion fallida", exc_info=exc)
    messages.error(request, user_message)
    if form is not None:
        form.add_error(None, user_message)


class AcreditacionBaseView(SigLoginRequiredMixin, TemplateView):
    template_name = ""
    page_title = ""
    page_description = ""
    page_status = "Operacion real"
    page_actions = []
    show_acreditacion_overview = True

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
                "show_acreditacion_overview": self.show_acreditacion_overview,
                "current_url_name": self.request.resolver_match.url_name if self.request.resolver_match else "",
                "acreditacion_metrics": get_acreditacion_metrics(),
            }
        )
        context.update(kwargs)
        return context


class CriterioListView(AcreditacionBaseView):
    template_name = "acreditacion/criterio_list.html"
    page_title = "Criterios"
    page_description = "Carga y administra la estructura principal de criterios de acreditacion."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or CriterioForm()
        context["criterios"] = get_criterios_queryset()
        return context

    def post(self, request, *args, **kwargs):
        form = CriterioForm(request.POST)
        if form.is_valid():
            try:
                crear_criterio(form=form, actor=self._actor(), request=request)
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible registrar el criterio. Revisa la informacion y vuelve a intentar.",
                )
            else:
                messages.success(request, "Criterio registrado correctamente.")
                return redirect("acreditacion-criterios-lista")
        return self.render_to_response(self.get_context_data(form=form))


class SubcriterioListView(AcreditacionBaseView):
    template_name = "acreditacion/subcriterio_list.html"
    page_title = "Subcriterios"
    page_description = "Carga subcriterios asociados a cada criterio real del sistema."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or SubcriterioForm()
        context["subcriterios"] = get_subcriterios_queryset()
        context["criterios"] = get_criterios_queryset()
        return context

    def post(self, request, *args, **kwargs):
        form = SubcriterioForm(request.POST)
        if form.is_valid():
            try:
                crear_subcriterio(form=form, actor=self._actor(), request=request)
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible registrar el subcriterio. Revisa la informacion y vuelve a intentar.",
                )
            else:
                messages.success(request, "Subcriterio registrado correctamente.")
                return redirect("acreditacion-subcriterios-lista")
        return self.render_to_response(self.get_context_data(form=form))


class IndicadorListView(AcreditacionBaseView):
    template_name = "acreditacion/indicador_list.html"
    page_title = "Indicadores"
    page_description = "Carga indicadores y vincula su tipo, subcriterio y peso de evaluacion."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or IndicadorForm()
        context["indicadores"] = get_indicadores_queryset()
        return context

    def post(self, request, *args, **kwargs):
        form = IndicadorForm(request.POST)
        if form.is_valid():
            try:
                indicador = crear_indicador(form=form, actor=self._actor(), request=request)
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible registrar el indicador. Revisa la informacion y vuelve a intentar.",
                )
            else:
                messages.success(request, "Indicador registrado correctamente.")
                return redirect(f"{reverse('acreditacion-indicadores-detalle')}?indicador={indicador.pk}")
        return self.render_to_response(self.get_context_data(form=form))


class IndicadorDetailView(AcreditacionBaseView):
    template_name = "acreditacion/indicador_detail.html"
    page_title = "Detalle de indicador"
    page_description = "Gestiona la ficha operativa del indicador y su relacion con elementos fundamentales."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_indicator = kwargs.get("selected_indicator") or get_indicator_detail(
            self.request.GET.get("indicador")
        )
        context["selected_indicator"] = selected_indicator
        context["indicadores"] = get_indicadores_queryset()
        context["relation_form"] = kwargs.get("relation_form") or IndicadorElementoForm(
            initial={"indicador": selected_indicator} if selected_indicator else None,
            fixed_indicador=selected_indicator,
        )
        return context

    def post(self, request, *args, **kwargs):
        form = IndicadorElementoForm(request.POST)
        selected_indicator = get_indicator_detail(request.POST.get("indicador"))
        if selected_indicator is not None:
            form = IndicadorElementoForm(
                request.POST,
                fixed_indicador=selected_indicator,
            )
        if form.is_valid():
            try:
                vincular_indicador_elemento(
                    indicador=form.cleaned_data["indicador"],
                    elemento_fundamental=form.cleaned_data["elemento_fundamental"],
                    actor=self._actor(),
                    request=request,
                )
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible vincular el elemento al indicador.",
                )
            else:
                messages.success(request, "Elemento vinculado al indicador.")
                return redirect(f"{reverse('acreditacion-indicadores-detalle')}?indicador={form.cleaned_data['indicador'].pk}")
        return self.render_to_response(
            self.get_context_data(relation_form=form, selected_indicator=selected_indicator)
        )


class ElementoListView(AcreditacionBaseView):
    template_name = "acreditacion/elemento_list.html"
    page_title = "Elementos fundamentales"
    page_description = "Carga los elementos fundamentales que alimentan la evidencia documental."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or ElementoFundamentalForm()
        context["elementos"] = get_elementos_queryset()
        return context

    def post(self, request, *args, **kwargs):
        form = ElementoFundamentalForm(request.POST)
        if form.is_valid():
            try:
                crear_elemento(form=form, actor=self._actor(), request=request)
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message="No fue posible registrar el elemento fundamental.",
                )
            else:
                messages.success(request, "Elemento fundamental registrado correctamente.")
                return redirect("acreditacion-elementos-lista")
        return self.render_to_response(self.get_context_data(form=form))


class MatrizView(AcreditacionBaseView):
    template_name = "acreditacion/matriz.html"
    page_title = "Matriz de acreditacion"
    page_description = "Lectura real de la jerarquia criterio > subcriterio > indicador > elemento."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["matrix_rows"] = get_matrix_rows()
        return context


class MatrizRegistroView(AcreditacionBaseView):
    template_name = "acreditacion/matriz_registro.html"
    page_title = "Matriz de registro"
    page_description = (
        "Unifica la carga documental con el registro de evidencia sobre la misma matriz "
        "operativa de criterio, subcriterio, indicador y elemento."
    )
    page_actions = [
        {"label": "Ver matriz", "url_name": "acreditacion-matriz", "variant": "secondary"},
        {"label": "Gestion documental", "url_name": "documentos-lista", "variant": "secondary"},
    ]
    show_acreditacion_overview = False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dashboard = get_matrix_registration_dashboard(
            ciclo_id=kwargs.get("selected_cycle_id") or self.request.GET.get("ciclo")
        )
        selected_cycle = dashboard.get("selected_cycle")
        summary = dashboard.get("matrix_registration_summary", {})
        context.update(dashboard)
        context["page_highlights"] = [
            {
                "label": "Ciclo activo",
                "value": getattr(selected_cycle, "nombre", "Sin ciclo habilitado"),
            },
            {"label": "Subidas", "value": summary.get("uploaded", 0)},
            {"label": "Faltantes", "value": summary.get("pending", 0)},
            {"label": "Cobertura", "value": f"{summary.get('completion_percent', 0)}%"},
        ]
        allowed_cycle_ids = [ciclo.pk for ciclo in dashboard.get("available_cycles", [])]
        context["registration_form"] = kwargs.get("registration_form") or MatrixEvidenceRegistrationForm(
            ciclo_initial=selected_cycle,
            allowed_cycle_ids=allowed_cycle_ids,
        )
        return context

    def post(self, request, *args, **kwargs):
        dashboard = get_matrix_registration_dashboard(ciclo_id=request.POST.get("ciclo"))
        allowed_cycle_ids = [ciclo.pk for ciclo in dashboard.get("available_cycles", [])]
        form = MatrixEvidenceRegistrationForm(
            request.POST,
            request.FILES,
            allowed_cycle_ids=allowed_cycle_ids,
        )
        if form.is_valid():
            try:
                register_matrix_evidence(
                    ciclo=form.cleaned_data["ciclo"],
                    indicador=form.cleaned_data["indicador"],
                    elemento_fundamental=form.cleaned_data["elemento_fundamental"],
                    clasificacion=form.cleaned_data["clasificacion"],
                    uploaded_file=form.cleaned_data["archivo"],
                    descripcion_documento=form.cleaned_data.get("descripcion_documento"),
                    comentario=form.cleaned_data.get("comentario"),
                    actor=self._actor(),
                    request=request,
                )
            except (
                MatrixEvidenceRegistrationError,
                StructuredDocumentUploadError,
                GraphServiceError,
                AuthorizationServiceError,
                OSError,
                ValueError,
                IntegrityError,
                OperationalError,
                DatabaseError,
            ) as exc:
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message=(
                        "No fue posible registrar la evidencia. "
                        "Verifica el ciclo, el archivo y la conexion con Microsoft Graph."
                    ),
                )
            else:
                messages.success(
                    request,
                    "Documento y evidencia registrados correctamente en la matriz de registro.",
                )
                return redirect(
                    f"{reverse('acreditacion-matriz-registro')}?ciclo={form.cleaned_data['ciclo'].pk}"
                )

        return self.render_to_response(
            self.get_context_data(
                registration_form=form,
                selected_cycle_id=request.POST.get("ciclo"),
            )
        )


class CicloListView(AcreditacionBaseView):
    template_name = "acreditacion/ciclo_list.html"
    page_title = "Ciclos y documento de autorizacion"
    page_description = "En una sola pantalla registras el ciclo, cargas su autorizacion y consultas el documento asociado."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session_roles = tuple(self.request.session.get("sig_roles", []) or [])
        operational_roles = tuple(self.request.session.get("sig_operational_roles", []) or [])
        effective_roles = tuple(dict.fromkeys([*session_roles, *operational_roles]))
        context["can_create_cycles"] = not any(
            str(role).strip().upper() == "RECTOR" for role in effective_roles
        )
        context["form"] = kwargs.get("form") or CicloEvaluacionForm(
            usuario_id=self.request.session.get("sig_user_id"),
            assignment_id=self.request.session.get("sig_active_assignment_id"),
        )
        ciclos = attach_cycle_authorization_status(get_ciclos_queryset())
        context["ciclos"] = ciclos
        context["ciclos_summary"] = {
            "total": len(ciclos),
            "con_autorizacion": sum(1 for ciclo in ciclos if getattr(ciclo, "has_authorization_document", False)),
            "aprobados": sum(
                1
                for ciclo in ciclos
                if (getattr(getattr(ciclo, "estado", None), "descripcion", "") or "").strip().upper() == "APROBADO"
            ),
            "habilitados": sum(1 for ciclo in ciclos if getattr(ciclo, "document_upload_enabled", False)),
        }
        return context

    def post(self, request, *args, **kwargs):
        session_roles = tuple(request.session.get("sig_roles", []) or [])
        operational_roles = tuple(request.session.get("sig_operational_roles", []) or [])
        effective_roles = tuple(dict.fromkeys([*session_roles, *operational_roles]))
        if any(str(role).strip().upper() == "RECTOR" for role in effective_roles):
            messages.warning(request, "El rol RECTOR solo puede revisar, aprobar o rechazar ciclos.")
            return redirect("acreditacion-ciclos-lista")

        form = CicloEvaluacionForm(
            request.POST,
            request.FILES,
            usuario_id=request.session.get("sig_user_id"),
            assignment_id=request.session.get("sig_active_assignment_id"),
        )
        if form.is_valid():
            try:
                crear_ciclo(form=form, actor=self._actor(), request=request)
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                user_message = str(exc).strip() or (
                    "No fue posible registrar el ciclo y su documento. Verifica los datos, la conexion a SQL Server y Microsoft Graph."
                )
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message=user_message,
                )
            else:
                messages.success(request, "Ciclo y documento de autorizacion registrados correctamente.")
                return redirect("acreditacion-ciclos-lista")
        else:
            messages.error(
                request,
                "No fue posible registrar el ciclo. Revisa los campos obligatorios y vuelve a adjuntar el documento de autorizacion.",
            )
        return self.render_to_response(self.get_context_data(form=form))


class CicloCreateView(RedirectView):
    pattern_name = "acreditacion-ciclos-lista"
    permanent = False


class CicloDetailView(AcreditacionBaseView):
    template_name = "acreditacion/ciclo_detail.html"
    page_title = "Informacion del ciclo"
    page_description = "Consulta el estado del ciclo y el documento de autorizacion asociado en una subpantalla dedicada."
    page_actions = [
        {"label": "Volver a ciclos", "url_name": "acreditacion-ciclos-lista", "variant": "secondary"},
    ]
    show_acreditacion_overview = False

    def _effective_roles(self, request):
        session_roles = tuple(request.session.get("sig_roles", []) or [])
        operational_roles = tuple(request.session.get("sig_operational_roles", []) or [])
        return tuple(dict.fromkeys([*session_roles, *operational_roles]))

    def _is_rector(self, request) -> bool:
        return any(str(role).strip().upper() == "RECTOR" for role in self._effective_roles(request))

    def _allowed_states_for_actor(self, request) -> tuple[str, ...]:
        if self._is_rector(request):
            return ESTADOS_RECTOR_DECISION
        return ESTADOS_FLUJO_CICLO

    def _get_estado_by_normalized_name(self, normalized_name: str):
        for estado in EstadoCiclo.objects.filter(activo=True).only("id_estado_ciclo", "descripcion"):
            current_name = (getattr(estado, "descripcion", "") or "").strip().upper().replace(" ", "_")
            if current_name == normalized_name:
                return estado
        return None

    def _ensure_rector_review_state(self, request, ciclo):
        if not self._is_rector(request):
            return ciclo

        estado_actual = (getattr(getattr(ciclo, "estado", None), "descripcion", "") or "").strip().upper().replace(" ", "_")
        if estado_actual != "ENVIADO":
            return ciclo

        estado_en_ejecucion = self._get_estado_by_normalized_name("EN_EJECUCION")
        if estado_en_ejecucion is None:
            return ciclo

        try:
            actualizar_estado_ciclo(
                ciclo=ciclo,
                estado=estado_en_ejecucion,
                observacion_aprobacion=None,
                actor=self._actor(),
                request=request,
            )
            messages.info(request, "El ciclo cambio a EN_EJECUCION para revision del Rector.")
        except (ValueError, IntegrityError, OperationalError, DatabaseError):
            return ciclo

        return get_ciclo_detail(ciclo.pk) or ciclo

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ciclo = kwargs.get("ciclo")
        allowed_states = self._allowed_states_for_actor(self.request)
        context["ciclo"] = ciclo
        context["is_rector_actor"] = self._is_rector(self.request)
        context["ciclo_form"] = kwargs.get("ciclo_form") or CicloEstadoAutorizacionForm(
            initial={
                "ciclo_id": ciclo.pk,
                "estado": ciclo.estado,
                "observacion_aprobacion": ciclo.observacion_aprobacion,
                "descripcion_documento": "",
            },
            allowed_states=allowed_states,
        )
        return context

    def get(self, request, ciclo_id, *args, **kwargs):
        ciclo = get_ciclo_detail(ciclo_id)
        if ciclo is None:
            raise Http404("El ciclo no existe.")
        ciclo = self._ensure_rector_review_state(request, ciclo)
        return self.render_to_response(self.get_context_data(ciclo=ciclo))

    def post(self, request, ciclo_id, *args, **kwargs):
        ciclo = get_ciclo_detail(ciclo_id)
        if ciclo is None:
            raise Http404("El ciclo no existe.")

        form = CicloEstadoAutorizacionForm(
            request.POST,
            request.FILES,
            allowed_states=self._allowed_states_for_actor(request),
        )
        if form.is_valid():
            if form.cleaned_data["ciclo_id"] != ciclo.pk:
                form.add_error(None, "El ciclo enviado no coincide con la solicitud.")
                return self.render_to_response(self.get_context_data(ciclo=ciclo, ciclo_form=form))

            try:
                with transaction.atomic():
                    actualizar_estado_ciclo(
                        ciclo=ciclo,
                        estado=form.cleaned_data["estado"],
                        observacion_aprobacion=form.cleaned_data.get("observacion_aprobacion"),
                        actor=self._actor(),
                        request=request,
                    )

                    uploaded_file = form.cleaned_data.get("archivo")
                    if uploaded_file:
                        revision_result = upload_cycle_authorization_revision(
                            ciclo=ciclo,
                            descripcion_documento=form.cleaned_data.get("descripcion_documento"),
                            uploaded_file=uploaded_file,
                            actor=self._actor(),
                            request=request,
                        )
                        if revision_result["documento"].pk != ciclo.documento_autorizacion_id:
                            ciclo.documento_autorizacion = revision_result["documento"]
                            ciclo.save(update_fields=["documento_autorizacion"])
                        messages.success(request, "Estado del ciclo y nueva version del documento registrados correctamente.")
                    else:
                        messages.success(request, f"Estado actualizado a {form.cleaned_data['estado'].descripcion}.")
                return redirect("acreditacion-ciclos-lista")
            except (GraphServiceError, AuthorizationServiceError, OSError, ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                user_message = str(exc).strip() or "No fue posible guardar el estado y la version del documento."
                _report_operation_error(
                    request=request,
                    exc=exc,
                    form=form,
                    user_message=user_message,
                )

        ciclo = get_ciclo_detail(ciclo_id)
        return self.render_to_response(
            self.get_context_data(
                ciclo=ciclo,
                ciclo_form=form,
            )
        )


class CicloEstadoUpdateView(SigLoginRequiredMixin, View):
    def _actor(self):
        user_id = self.request.session.get("sig_user_id")
        if not user_id:
            return None
        return Usuario.objects.filter(pk=user_id).only("id_user", "primer_nombre", "primer_apellido").first()

    def _is_rector(self, request) -> bool:
        session_roles = tuple(request.session.get("sig_roles", []) or [])
        operational_roles = tuple(request.session.get("sig_operational_roles", []) or [])
        effective_roles = tuple(dict.fromkeys([*session_roles, *operational_roles]))
        return any(str(role).strip().upper() == "RECTOR" for role in effective_roles)

    def post(self, request, ciclo_id, *args, **kwargs):
        ciclo = CicloEvaluacion.objects.select_related("estado").filter(pk=ciclo_id).first()
        if ciclo is None:
            raise Http404("El ciclo no existe.")

        form = CicloEstadoUpdateForm(
            request.POST,
            allowed_states=ESTADOS_RECTOR_DECISION if self._is_rector(request) else ESTADOS_FLUJO_CICLO,
        )
        if form.is_valid():
            if form.cleaned_data["ciclo_id"] != ciclo.pk:
                form.add_error(None, "El ciclo enviado no coincide con la solicitud.")
            else:
                try:
                    actualizar_estado_ciclo(
                        ciclo=ciclo,
                        estado=form.cleaned_data["estado"],
                        observacion_aprobacion=form.cleaned_data.get("observacion_aprobacion"),
                        actor=self._actor(),
                        request=request,
                    )
                except (ValueError, IntegrityError, OperationalError, DatabaseError) as exc:
                    _report_operation_error(
                        request=request,
                        exc=exc,
                        user_message="No fue posible actualizar el estado del ciclo.",
                    )
                else:
                    messages.success(request, f"Estado actualizado a {form.cleaned_data['estado'].descripcion}.")
                return redirect("acreditacion-ciclos-lista")

        messages.error(request, "No fue posible actualizar el estado del ciclo.")
        return redirect("acreditacion-ciclos-lista")
