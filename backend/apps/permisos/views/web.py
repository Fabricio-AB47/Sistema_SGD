from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView

from apps.core.mixins import SigLoginRequiredMixin
from apps.permisos.forms import (
    PermisoGestionForm,
    RolGestionForm,
    RolIndicadorElementoGestionForm,
    RolIndicadorGestionForm,
    RolPermisoForm,
    UsuarioRolGestionForm,
)
from apps.permisos.models import RolIndicador, RolIndicadorElemento, UsuarioRol
from apps.permisos.selectors import (
    get_permission_metrics,
    get_role_detail,
    get_role_indicator_assignments,
    get_role_indicator_element_assignments,
    get_role_permissions,
    get_roles_queryset,
    get_user_role_assignments,
)
from apps.permisos.services import (
    actualizar_rol,
    asignar_rol_indicador,
    asignar_rol_indicador_elemento,
    asignar_usuario_rol,
    crear_permiso,
    crear_rol,
    desactivar_rol_indicador,
    eliminar_rol_indicador_elemento,
    revocar_usuario_rol,
    sincronizar_permisos_rol,
)
from apps.usuarios.models import Usuario


PERMISSION_TABS = [
    {"label": "Roles", "url_name": "permisos-roles-lista"},
    {"label": "Detalle de rol", "url_name": "permisos-roles-detalle"},
    {"label": "Permisos por rol", "url_name": "permisos-roles-permisos"},
    {"label": "Asignacion usuario-rol", "url_name": "permisos-usuario-rol"},
    {"label": "Acceso por indicador", "url_name": "permisos-acceso-indicador"},
    {"label": "Acceso por elemento", "url_name": "permisos-acceso-elemento"},
]


def _current_usuario(request):
    user_id = request.session.get("sig_user_id")
    if not user_id:
        return None
    return Usuario.objects.filter(pk=user_id).first()


def _url(name, **params):
    base = reverse(name)
    clean_params = {key: value for key, value in params.items() if value not in (None, "", [])}
    if not clean_params:
        return base
    return f"{base}?{urlencode(clean_params)}"


class PermisosBaseView(SigLoginRequiredMixin, TemplateView):
    module_title = "Permisos"
    page_title = ""
    page_description = ""
    template_name = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "module_title": self.module_title,
                "page_title": self.page_title,
                "page_description": self.page_description,
                "permission_tabs": PERMISSION_TABS,
                "permission_metrics": get_permission_metrics(),
            }
        )
        context.update(kwargs)
        return context


class RoleListView(PermisosBaseView):
    template_name = "permisos/rol_list.html"
    page_title = "Roles"
    page_description = "Consulta los roles existentes y su relacion con permisos, usuarios e indicadores."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["roles"] = get_roles_queryset()
        return context


class RoleDetailView(PermisosBaseView):
    template_name = "permisos/rol_detail.html"
    page_title = "Detalle de rol"
    page_description = "Consulta y actualiza el rol, sus permisos y sus accesos relacionados."

    def _selected_role(self):
        role_id = self.request.GET.get("rol") or self.request.POST.get("rol_id")
        if role_id:
            selected = get_role_detail(role_id)
            if selected:
                return selected
        first_role = get_roles_queryset().first()
        return get_role_detail(first_role.pk) if first_role else None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_role = kwargs.get("selected_role") or self._selected_role()
        context["roles"] = get_roles_queryset()
        context["selected_role"] = selected_role
        context["form"] = kwargs.get("form") or (
            RolGestionForm(instance=selected_role) if selected_role else None
        )
        return context

    def post(self, request, *args, **kwargs):
        selected_role = self._selected_role()
        if not selected_role:
            messages.error(request, "No existe un rol disponible para editar.")
            return redirect("permisos-roles-lista")

        form = RolGestionForm(request.POST, instance=selected_role)
        if form.is_valid():
            actualizar_rol(form, actor=_current_usuario(request), request=request)
            messages.success(request, "Rol actualizado correctamente.")
            return redirect(_url("permisos-roles-detalle", rol=selected_role.pk))
        return self.render_to_response(
            self.get_context_data(form=form, selected_role=selected_role)
        )


class RolePermissionView(PermisosBaseView):
    template_name = "permisos/rol_permiso.html"
    page_title = "Permisos por rol"
    page_description = "Gestiona el catalogo de permisos y la matriz rol-permiso."

    def _selected_role_id(self):
        return self.request.GET.get("rol") or self.request.POST.get("rol")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = get_role_permissions(self._selected_role_id())
        selected_role = data["selected_role"]
        context.update(
            {
                "roles": data["roles"],
                "selected_role": selected_role,
                "permissions_grouped": data["permissions_grouped"],
                "assigned_ids": data["assigned_ids"],
                "sync_form": kwargs.get("sync_form")
                or RolPermisoForm(role=selected_role, initial={"rol": selected_role} if selected_role else None),
                "permission_form": kwargs.get("permission_form")
                or PermisoGestionForm(prefix="permission"),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        actor = _current_usuario(request)
        action = request.POST.get("action")
        selected_role_id = request.POST.get("rol")

        if action == "create_permission":
            permission_form = PermisoGestionForm(request.POST, prefix="permission")
            if permission_form.is_valid():
                permiso = crear_permiso(permission_form, actor=actor, request=request)
                messages.success(request, f"Permiso {permiso.codigo_permiso} creado correctamente.")
                return redirect(_url("permisos-roles-permisos", rol=selected_role_id))
            return self.render_to_response(
                self.get_context_data(permission_form=permission_form)
            )

        sync_form = RolPermisoForm(request.POST)
        if sync_form.is_valid():
            rol = sync_form.cleaned_data["rol"]
            permisos = sync_form.cleaned_data["permisos"]
            sincronizar_permisos_rol(
                rol=rol,
                permisos=permisos,
                actor=actor,
                request=request,
            )
            messages.success(request, "Permisos del rol actualizados correctamente.")
            return redirect(_url("permisos-roles-permisos", rol=rol.pk))

        return self.render_to_response(self.get_context_data(sync_form=sync_form))


class UserRoleAssignmentView(PermisosBaseView):
    template_name = "permisos/usuario_rol.html"
    page_title = "Asignacion usuario-rol"
    page_description = "Registra y revoca asignaciones activas de roles por usuario."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or UsuarioRolGestionForm()
        context["assignments"] = get_user_role_assignments()
        return context

    def post(self, request, *args, **kwargs):
        actor = _current_usuario(request)
        action = request.POST.get("action")

        if action == "revoke":
            assignment = UsuarioRol.objects.filter(pk=request.POST.get("assignment_id")).select_related(
                "usuario", "rol"
            ).first()
            if assignment:
                revocar_usuario_rol(asignacion=assignment, actor=actor, request=request)
                messages.success(request, "Asignacion revocada correctamente.")
            return redirect("permisos-usuario-rol")

        form = UsuarioRolGestionForm(request.POST)
        if form.is_valid():
            asignar_usuario_rol(
                usuario=form.cleaned_data["usuario"],
                rol=form.cleaned_data["rol"],
                activo=form.cleaned_data["activo"],
                actor=actor,
                request=request,
            )
            messages.success(request, "Asignacion usuario-rol registrada correctamente.")
            return redirect("permisos-usuario-rol")
        return self.render_to_response(self.get_context_data(form=form))


class RoleIndicatorAccessView(PermisosBaseView):
    template_name = "permisos/rol_indicador.html"
    page_title = "Acceso por indicador"
    page_description = "Gestiona el acceso por rol sobre cada indicador dentro de un ciclo."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or RolIndicadorGestionForm()
        context["assignments"] = get_role_indicator_assignments()
        return context

    def post(self, request, *args, **kwargs):
        actor = _current_usuario(request)
        action = request.POST.get("action")

        if action == "deactivate":
            access = RolIndicador.objects.filter(pk=request.POST.get("access_id")).select_related(
                "rol", "indicador"
            ).first()
            if access:
                desactivar_rol_indicador(acceso=access, actor=actor, request=request)
                messages.success(request, "Acceso por indicador desactivado.")
            return redirect("permisos-acceso-indicador")

        form = RolIndicadorGestionForm(request.POST)
        if form.is_valid():
            asignar_rol_indicador(
                rol=form.cleaned_data["rol"],
                indicador=form.cleaned_data["indicador"],
                ciclo=form.cleaned_data["ciclo"],
                acceso_total=form.cleaned_data["acceso_total"],
                actor=actor,
                request=request,
            )
            messages.success(request, "Acceso por indicador registrado correctamente.")
            return redirect("permisos-acceso-indicador")
        return self.render_to_response(self.get_context_data(form=form))


class RoleIndicatorElementAccessView(PermisosBaseView):
    template_name = "permisos/rol_indicador_elemento.html"
    page_title = "Acceso por elemento"
    page_description = "Relaciona elementos fundamentales con accesos ya creados por indicador."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or RolIndicadorElementoGestionForm()
        context["assignments"] = get_role_indicator_element_assignments()
        return context

    def post(self, request, *args, **kwargs):
        actor = _current_usuario(request)
        action = request.POST.get("action")

        if action == "delete":
            access = RolIndicadorElemento.objects.filter(
                rol_indicador_id=request.POST.get("rol_indicador_id"),
                elemento_fundamental_id=request.POST.get("elemento_id"),
            ).select_related("rol_indicador", "elemento_fundamental").first()
            if access:
                eliminar_rol_indicador_elemento(acceso=access, actor=actor, request=request)
                messages.success(request, "Acceso por elemento eliminado.")
            return redirect("permisos-acceso-elemento")

        form = RolIndicadorElementoGestionForm(request.POST)
        if form.is_valid():
            asignar_rol_indicador_elemento(
                rol_indicador=form.cleaned_data["rol_indicador"],
                elemento_fundamental=form.cleaned_data["elemento_fundamental"],
                actor=actor,
                request=request,
            )
            messages.success(request, "Acceso por elemento registrado correctamente.")
            return redirect("permisos-acceso-elemento")
        return self.render_to_response(self.get_context_data(form=form))
