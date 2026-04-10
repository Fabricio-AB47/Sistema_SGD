from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView, FormView, TemplateView
from django.db import models

from apps.core.mixins import SigLoginRequiredMixin
from apps.usuarios.forms.estructura import (
    AreaInstitucionalForm,
    CargoAreaForm,
    UsuarioAreaCargoForm,
    UsuarioSupervisorForm,
)
from apps.usuarios.forms.usuario import UsuarioCrearForm, UsuarioEditarForm, AsignarRolForm
from apps.usuarios.forms.rol import RolCrearForm
from apps.usuarios.models import Usuario, Rol, UsuarioRol
from apps.usuarios.selectors import (
    get_areas_queryset,
    get_cargos_queryset,
    get_usuario_area_cargos,
    get_usuario_supervisores,
)
from apps.usuarios.services import (
    UserStructureError,
    asignar_supervisor_usuario,
    asignar_usuario_area_cargo,
    crear_area,
    crear_cargo,
)


class UsuarioListView(SigLoginRequiredMixin, ListView):
    model = Usuario
    template_name = "usuarios/lista.html"
    context_object_name = "usuarios"
    paginate_by = 15

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .order_by("primer_apellido", "primer_nombre")
            .prefetch_related("roles_asignados__rol")
        )
        q = self.request.GET.get("q")
        rol_id = self.request.GET.get("rol")
        activo = self.request.GET.get("activo")

        if q:
            qs = qs.filter(
                models.Q(primer_nombre__icontains=q)
                | models.Q(segundo_nombre__icontains=q)
                | models.Q(primer_apellido__icontains=q)
                | models.Q(segundo_apellido__icontains=q)
                | models.Q(correo__icontains=q)
            )
        if rol_id:
            qs = qs.filter(roles_asignados__rol_id=rol_id, roles_asignados__activo=True)
        if activo in ("0", "1"):
            qs = qs.filter(activo=bool(int(activo)))
        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["roles"] = Rol.objects.filter(activo=True).order_by("nombre_rol")
        return ctx


class UsuarioCreateView(SigLoginRequiredMixin, CreateView):
    model = Usuario
    form_class = UsuarioCrearForm
    template_name = "usuarios/crear.html"
    success_url = reverse_lazy("usuarios-lista")

    def form_valid(self, form):
        messages.success(self.request, "Usuario creado exitosamente.")
        return super().form_valid(form)


class UsuarioUpdateView(SigLoginRequiredMixin, UpdateView):
    model = Usuario
    form_class = UsuarioEditarForm
    template_name = "usuarios/editar.html"
    success_url = reverse_lazy("usuarios-lista")

    def form_valid(self, form):
        messages.success(self.request, "Usuario actualizado exitosamente.")
        return super().form_valid(form)


class UsuarioDetailView(SigLoginRequiredMixin, DetailView):
    model = Usuario
    template_name = "usuarios/detalle.html"
    context_object_name = "usuario"


class UsuarioAsignarRolesView(SigLoginRequiredMixin, FormView):
    template_name = "usuarios/asignar_roles.html"
    form_class = AsignarRolForm

    def dispatch(self, request, *args, **kwargs):
        self.usuario = get_object_or_404(Usuario, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.usuario
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["usuario"] = self.usuario
        context["asignaciones"] = self.usuario.roles_asignados.select_related("rol", "asignado_por")
        return context

    def form_valid(self, form):
        UsuarioRol.objects.create(
            usuario=self.usuario,
            rol=form.cleaned_data["rol"],
            activo=form.cleaned_data.get("activo", True),
        )
        messages.success(self.request, "Rol asignado exitosamente.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("usuarios-asignar-roles", args=[self.usuario.pk])


class RolListView(SigLoginRequiredMixin, ListView):
    model = Rol
    template_name = "roles/lista.html"
    context_object_name = "roles"
    paginate_by = 20

    def get_queryset(self):
        return Rol.objects.order_by("nombre_rol")


class RolCreateView(SigLoginRequiredMixin, CreateView):
    model = Rol
    form_class = RolCrearForm
    template_name = "roles/crear.html"

    def form_valid(self, form):
        messages.success(self.request, "Rol creado exitosamente.")
        return super().form_valid(form)

    def get_success_url(self):
        return f"{reverse('permisos-roles-detalle')}?rol={self.object.pk}"


class AreaInstitucionalListView(SigLoginRequiredMixin, TemplateView):
    template_name = "usuarios/areas.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["area_form"] = kwargs.get("area_form") or AreaInstitucionalForm()
        context["areas"] = get_areas_queryset()
        return context

    def post(self, request, *args, **kwargs):
        form = AreaInstitucionalForm(request.POST)
        if form.is_valid():
            try:
                crear_area(form=form)
            except IntegrityError:
                form.add_error("codigo_area", "No fue posible crear el area. Verifica que el codigo sea unico.")
            else:
                messages.success(request, "Area institucional creada correctamente.")
                return redirect("usuarios-areas")
        return self.render_to_response(self.get_context_data(area_form=form))


class CargoAreaListView(SigLoginRequiredMixin, TemplateView):
    template_name = "usuarios/cargos.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_area_id = self.request.GET.get("area")
        context["cargo_form"] = kwargs.get("cargo_form") or CargoAreaForm()
        context["areas"] = get_areas_queryset()
        context["selected_area_id"] = selected_area_id
        context["cargos"] = get_cargos_queryset(area_id=selected_area_id)
        return context

    def post(self, request, *args, **kwargs):
        form = CargoAreaForm(request.POST)
        if form.is_valid():
            try:
                crear_cargo(form=form)
            except IntegrityError:
                form.add_error("codigo_cargo", "No fue posible crear el cargo. Verifica area y codigo.")
            else:
                messages.success(request, "Cargo por area creado correctamente.")
                return redirect("usuarios-cargos")
        return self.render_to_response(self.get_context_data(cargo_form=form))


class UsuarioEstructuraView(SigLoginRequiredMixin, TemplateView):
    template_name = "usuarios/estructura.html"

    def dispatch(self, request, *args, **kwargs):
        self.usuario = get_object_or_404(Usuario, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["usuario"] = self.usuario
        context["area_cargo_form"] = kwargs.get("area_cargo_form") or UsuarioAreaCargoForm(usuario=self.usuario)
        context["supervisor_form"] = kwargs.get("supervisor_form") or UsuarioSupervisorForm(usuario=self.usuario)
        context["area_cargos"] = get_usuario_area_cargos(self.usuario)
        context["supervisores"] = get_usuario_supervisores(self.usuario)
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        area_cargo_form = UsuarioAreaCargoForm(usuario=self.usuario)
        supervisor_form = UsuarioSupervisorForm(usuario=self.usuario)

        if action == "asignar_area_cargo":
            area_cargo_form = UsuarioAreaCargoForm(request.POST, usuario=self.usuario)
            if area_cargo_form.is_valid():
                try:
                    asignar_usuario_area_cargo(
                        usuario=self.usuario,
                        area=area_cargo_form.cleaned_data["area"],
                        cargo=area_cargo_form.cleaned_data["cargo"],
                    )
                except (UserStructureError, IntegrityError) as exc:
                    area_cargo_form.add_error(None, str(exc))
                else:
                    messages.success(request, "Area y cargo asignados al usuario.")
                    return redirect("usuarios-estructura", pk=self.usuario.pk)

        elif action == "asignar_supervisor":
            supervisor_form = UsuarioSupervisorForm(request.POST, usuario=self.usuario)
            if supervisor_form.is_valid():
                try:
                    asignar_supervisor_usuario(
                        usuario=self.usuario,
                        supervisor=supervisor_form.cleaned_data["supervisor"],
                    )
                except (UserStructureError, IntegrityError) as exc:
                    supervisor_form.add_error(None, str(exc))
                else:
                    messages.success(request, "Supervisor asignado correctamente.")
                    return redirect("usuarios-estructura", pk=self.usuario.pk)
        else:
            messages.error(request, "Accion no reconocida.")

        return self.render_to_response(
            self.get_context_data(
                area_cargo_form=area_cargo_form,
                supervisor_form=supervisor_form,
            )
        )
