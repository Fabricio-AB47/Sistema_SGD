"""
Formularios para gestión de usuarios y asignación de roles.
Incluyen validaciones básicas alineadas al esquema de la base de datos.
"""

import unicodedata

from django import forms
from django.utils import timezone

from apps.usuarios.models import (
    AreaInstitucional,
    CargoArea,
    TipoIdentificacion,
    Rol,
    Usuario,
    UsuarioCredencial,
    UsuarioRol,
)
from apps.usuarios.services import password_service
from apps.usuarios.services.structure_service import asignar_usuario_area_cargo


ROLE_AREA_TOKEN_MAP = {
    "ACADEMICO": "ACADEMICO",
    "ADMISIONES": "ADMISIONES",
    "BIENESTAR": "BIENESTAR",
    "FINANCIERO": "FINANCIERO",
    "TECNOLOGIA": "TECNOLOGIA",
    "RECTOR": "RECTORADO",
    "CONSULTA": "ACADEMICO",
    "CALIDAD ACADEMICA": "ACADEMICO",
}


def _normalize_token(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", (value or "").strip())
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(ascii_only.upper().split())


def _normalize_area_token(value: str | None) -> str:
    return _normalize_token(value).replace(" ", "")


def _get_allowed_area_ids(rol: Rol | None) -> list[int]:
    if rol is None:
        return []

    role_token = _normalize_token(getattr(rol, "nombre_rol", ""))
    mapped_token = ROLE_AREA_TOKEN_MAP.get(role_token, role_token)
    if not mapped_token:
        return []

    target_token = _normalize_area_token(mapped_token)
    allowed_area_ids: list[int] = []
    for area in AreaInstitucional.objects.filter(activo=True).only("id_area", "codigo_area", "nombre_area"):
        area_tokens = {
            _normalize_area_token(area.nombre_area),
            _normalize_area_token(area.codigo_area),
        }
        if target_token in area_tokens or any(target_token in token for token in area_tokens):
            allowed_area_ids.append(area.id_area)
    return allowed_area_ids


def _get_allowed_areas_queryset(rol: Rol | None):
    allowed_ids = _get_allowed_area_ids(rol)
    if not allowed_ids:
        return AreaInstitucional.objects.none()
    return AreaInstitucional.objects.filter(activo=True, pk__in=allowed_ids).order_by("nombre_area")


def _build_area_catalog():
    return [
        {
            "id": str(area.id_area),
            "label": f"{_normalize_token(area.codigo_area)} - {_normalize_token(area.nombre_area)}",
        }
        for area in AreaInstitucional.objects.filter(activo=True).order_by("nombre_area")
    ]


def _build_role_area_map(area_catalog):
    role_area_map = {"__all__": []}
    for rol in Rol.objects.filter(activo=True).only("id_rol", "nombre_rol"):
        allowed_ids = [
            str(area.id_area)
            for area in _get_allowed_areas_queryset(rol).only("id_area")
        ]
        role_area_map[str(rol.id_rol)] = allowed_ids
    return role_area_map


def _build_area_cargo_map():
    area_cargo_map = {}
    cargos = (
        CargoArea.objects.filter(activo=True, area__activo=True)
        .select_related("area")
        .order_by("area__nombre_area", "nombre_cargo")
    )
    for cargo in cargos:
        key = str(cargo.area_id)
        area_cargo_map.setdefault(key, []).append(
            {
                "id": str(cargo.id_cargo),
                "label": f"{_normalize_token(cargo.codigo_cargo)} - {_normalize_token(cargo.nombre_cargo)}",
            }
        )
    return area_cargo_map


def _get_selected_model_choice(raw_value, queryset):
    try:
        if raw_value in (None, ""):
            return None
        return queryset.filter(pk=raw_value).first()
    except (TypeError, ValueError):
        return None


class UsuarioCrearForm(forms.ModelForm):
    """
    Formulario para crear un usuario.
    Se validan unicidad de correo e identificación a nivel de modelo.
    """

    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput,
        min_length=8,
        help_text="Mínimo 8 caracteres.",
    )
    password_confirm = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput,
        min_length=8,
    )
    rol = forms.ModelChoiceField(
        queryset=Rol.objects.filter(activo=True),
        label="Rol",
        required=False,
        help_text="Rol principal a asignar (opcional).",
    )
    area = forms.ModelChoiceField(
        queryset=AreaInstitucional.objects.filter(activo=True).order_by("nombre_area"),
        label="Area",
        required=False,
        empty_label="SELECCIONE AREA",
    )
    cargo = forms.ModelChoiceField(
        queryset=CargoArea.objects.filter(activo=True).select_related("area").order_by("area__nombre_area", "nombre_cargo"),
        label="Cargo",
        required=False,
        empty_label="SELECCIONE CARGO",
    )

    class Meta:
        model = Usuario
        fields = [
            "primer_nombre",
            "segundo_nombre",
            "primer_apellido",
            "segundo_apellido",
            "identificacion",
            "correo",
            "telefono",
            "id_tipo_identificacion",
            "activo",
        ]
        widgets = {
            "id_tipo_identificacion": forms.Select(),
        }

    def clean_correo(self):
        """
        Normaliza el correo a minúsculas para evitar duplicados por casing.
        """
        correo = self.cleaned_data["correo"].lower()
        if Usuario.objects.filter(correo__iexact=correo).exists():
            raise forms.ValidationError("Ya existe un usuario con este correo.")
        return correo

    def clean_identificacion(self):
        """
        Verifica unicidad de la identificación.
        """
        identificacion = self.cleaned_data["identificacion"]
        if Usuario.objects.filter(identificacion=identificacion).exists():
            raise forms.ValidationError("Ya existe un usuario con esta identificación.")
        return identificacion

    def clean_id_tipo_identificacion(self):
        tipo = self.cleaned_data["id_tipo_identificacion"]
        return tipo.id_tipo_identificacion if tipo else None

    def clean(self):
        data = super().clean()
        pwd = data.get("password")
        pwd2 = data.get("password_confirm")
        if pwd and pwd2 and pwd != pwd2:
            self.add_error("password_confirm", "Las contraseñas no coinciden.")

        rol = data.get("rol")
        area = data.get("area")
        cargo = data.get("cargo")

        if (area or cargo) and not rol:
            self.add_error("rol", "Debes seleccionar un rol antes de elegir area o cargo.")
            return data

        if rol and area and area.pk not in _get_allowed_area_ids(rol):
            self.add_error("area", "El area seleccionada no corresponde al rol indicado.")

        if area and cargo and cargo.area_id != area.id_area:
            self.add_error("cargo", "El cargo seleccionado no corresponde al area elegida.")
        elif bool(area) != bool(cargo):
            self.add_error("cargo", "Debes seleccionar area y cargo para registrar la asignacion.")
        return data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Reemplaza el integer field por un select basado en el catálogo.
        self.fields["id_tipo_identificacion"] = forms.ModelChoiceField(
            queryset=TipoIdentificacion.objects.filter(activo=True).order_by("descripcion"),
            to_field_name="id_tipo_identificacion",
            empty_label="Seleccione...",
            label="Tipo de identificación",
        )
        # Texto del rol y placeholder
        self.fields["rol"].label = "Rol"
        self.fields["rol"].empty_label = "SELECCIONE EL ROL DE USUARIO"
        self.fields["rol"].label_from_instance = lambda value: (value.nombre_rol or "").upper()
        self.fields["area"].label_from_instance = lambda value: f"{_normalize_token(value.codigo_area)} - {_normalize_token(value.nombre_area)}"
        self.fields["cargo"].label_from_instance = lambda value: f"{_normalize_token(value.codigo_cargo)} - {_normalize_token(value.nombre_cargo)}"

        selected_rol = _get_selected_model_choice(
            (self.data.get("rol") if self.is_bound else None) or self.initial.get("rol"),
            Rol.objects.filter(activo=True),
        )
        self.fields["area"].queryset = _get_allowed_areas_queryset(selected_rol)

        area_id = (self.data.get("area") if self.is_bound else None) or self.initial.get("area")
        cargos = CargoArea.objects.none()
        if area_id:
            cargos = CargoArea.objects.filter(activo=True).select_related("area").order_by("area__nombre_area", "nombre_cargo")
            cargos = cargos.filter(area_id=area_id)
        self.fields["cargo"].queryset = cargos

        self.area_catalog = _build_area_catalog()
        self.role_area_map = _build_role_area_map(self.area_catalog)
        self.area_cargo_map = _build_area_cargo_map()

    def save(self, commit=True):
        """
        Crea el usuario, su credencial y asigna (si se indicó) un rol.
        """
        usuario = super().save(commit=False)
        now = timezone.now()
        if not usuario.fecha_creacion:
            usuario.fecha_creacion = now
        usuario.fecha_actualizacion = now
        if commit:
            usuario.save()

            # Credencial
            raw_pwd = self.cleaned_data["password"]
            UsuarioCredencial.objects.create(
                usuario=usuario,
                password_hash=password_service.hash_password_argon2(raw_pwd),
                algoritmo_hash="argon2",
            )

            # Rol (opcional)
            rol = self.cleaned_data.get("rol")
            if rol:
                UsuarioRol.objects.create(usuario=usuario, rol=rol, activo=True)

            area = self.cleaned_data.get("area")
            cargo = self.cleaned_data.get("cargo")
            if area and cargo:
                asignar_usuario_area_cargo(usuario=usuario, area=area, cargo=cargo)

        return usuario


class UsuarioEditarForm(forms.ModelForm):
    """
    Formulario para editar datos de un usuario existente.
    Controla colisiones de correo e identificación excluyendo el propio registro.
    """

    rol = forms.ModelChoiceField(
        queryset=Rol.objects.filter(activo=True),
        label="Rol",
        required=False,
        help_text="Rol principal a asignar (opcional).",
    )
    area = forms.ModelChoiceField(
        queryset=AreaInstitucional.objects.filter(activo=True).order_by("nombre_area"),
        label="Area",
        required=False,
        empty_label="SELECCIONE AREA",
    )
    cargo = forms.ModelChoiceField(
        queryset=CargoArea.objects.filter(activo=True).select_related("area").order_by("area__nombre_area", "nombre_cargo"),
        label="Cargo",
        required=False,
        empty_label="SELECCIONE CARGO",
    )

    class Meta:
        model = Usuario
        fields = [
            "primer_nombre",
            "segundo_nombre",
            "primer_apellido",
            "segundo_apellido",
            "identificacion",
            "correo",
            "telefono",
            "id_tipo_identificacion",
            "activo",
        ]

    def __init__(self, *args, **kwargs):
        """
        Recibe la instancia de usuario para excluirla en las validaciones.
        """
        super().__init__(*args, **kwargs)
        self.instance_id = self.instance.id_user if self.instance and self.instance.pk else None
        self.fields["id_tipo_identificacion"] = forms.ModelChoiceField(
            queryset=TipoIdentificacion.objects.filter(activo=True).order_by("descripcion"),
            to_field_name="id_tipo_identificacion",
            empty_label="Seleccione...",
            label="Tipo de identificación",
        )
        self.fields["rol"].empty_label = "SELECCIONE EL ROL DE USUARIO"
        self.fields["rol"].label_from_instance = lambda value: (value.nombre_rol or "").upper()
        self.fields["area"].label_from_instance = lambda value: f"{value.codigo_area} - {value.nombre_area}".upper()
        self.fields["cargo"].label_from_instance = lambda value: f"{value.codigo_cargo} - {value.nombre_cargo}".upper()

        current_assignment = (
            self.instance.areas_cargos.select_related("area", "cargo")
            .filter(activo=True, area__activo=True, cargo__activo=True)
            .order_by("-fecha_asignacion")
            .first()
            if self.instance_id
            else None
        )
        if current_assignment and not self.is_bound:
            self.initial.setdefault("area", current_assignment.area_id)
            self.initial.setdefault("cargo", current_assignment.cargo_id)

        current_role = (
            self.instance.roles_asignados.select_related("rol")
            .filter(activo=True, rol__activo=True)
            .order_by("-fecha_asignacion")
            .first()
            if self.instance_id
            else None
        )
        if current_role and not self.is_bound:
            self.initial.setdefault("rol", current_role.rol_id)

        selected_rol = _get_selected_model_choice(
            (self.data.get("rol") if self.is_bound else None) or self.initial.get("rol"),
            Rol.objects.filter(activo=True),
        )
        self.fields["area"].queryset = _get_allowed_areas_queryset(selected_rol)

        area_id = (self.data.get("area") if self.is_bound else None) or self.initial.get("area")
        cargos = CargoArea.objects.none()
        if area_id:
            cargos = CargoArea.objects.filter(activo=True).select_related("area").order_by("area__nombre_area", "nombre_cargo")
            cargos = cargos.filter(area_id=area_id)
        self.fields["cargo"].queryset = cargos

        self.area_catalog = _build_area_catalog()
        self.role_area_map = _build_role_area_map(self.area_catalog)
        self.area_cargo_map = _build_area_cargo_map()

    def clean_correo(self):
        """
        Normaliza y valida que el correo no esté usado por otro usuario.
        """
        correo = self.cleaned_data["correo"].lower()
        qs = Usuario.objects.filter(correo__iexact=correo)
        if self.instance_id:
            qs = qs.exclude(pk=self.instance_id)
        if qs.exists():
            raise forms.ValidationError("Ya existe un usuario con este correo.")
        return correo

    def clean_identificacion(self):
        """
        Evita duplicar identificación en otros usuarios.
        """
        identificacion = self.cleaned_data["identificacion"]
        qs = Usuario.objects.filter(identificacion=identificacion)
        if self.instance_id:
            qs = qs.exclude(pk=self.instance_id)
        if qs.exists():
            raise forms.ValidationError("Ya existe un usuario con esta identificación.")
        return identificacion

    def clean_id_tipo_identificacion(self):
        tipo = self.cleaned_data["id_tipo_identificacion"]
        return tipo.id_tipo_identificacion if tipo else None

    def clean(self):
        cleaned = super().clean()
        rol = cleaned.get("rol")
        area = cleaned.get("area")
        cargo = cleaned.get("cargo")
        if (area or cargo) and not rol:
            self.add_error("rol", "Debes seleccionar un rol antes de elegir area o cargo.")
            return cleaned
        if rol and area and not _get_allowed_areas_queryset(rol).filter(pk=area.pk).exists():
            self.add_error("area", "El area seleccionada no corresponde al rol indicado.")
        if area and cargo and cargo.area_id != area.id_area:
            self.add_error("cargo", "El cargo seleccionado no corresponde al area elegida.")
        elif bool(area) != bool(cargo):
            self.add_error("cargo", "Debes seleccionar area y cargo para registrar la asignacion.")
        return cleaned

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.fecha_actualizacion = timezone.now()
        if commit:
            usuario.save()
            rol = self.cleaned_data.get("rol")
            if rol and not UsuarioRol.objects.filter(usuario=usuario, rol=rol, activo=True).exists():
                UsuarioRol.objects.create(usuario=usuario, rol=rol, activo=True)
            area = self.cleaned_data.get("area")
            cargo = self.cleaned_data.get("cargo")
            if area and cargo:
                asignar_usuario_area_cargo(usuario=usuario, area=area, cargo=cargo)
        return usuario


class AsignarRolForm(forms.Form):
    """
    Formulario simple para asignar roles a un usuario.
    """

    rol = forms.ModelChoiceField(
        queryset=Rol.objects.filter(activo=True),
        label="Rol",
        help_text="Selecciona un rol activo para el usuario.",
    )
    activo = forms.BooleanField(
        required=False,
        initial=True,
        label="Activo",
        help_text="Marca si la asignación debe quedar activa.",
    )

    def __init__(self, usuario, *args, **kwargs):
        """
        Recibe el usuario destino para validar asignaciones duplicadas.
        """
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def clean_rol(self):
        """
        Evita asignar dos veces el mismo rol al usuario.
        """
        rol = self.cleaned_data["rol"]
        if UsuarioRol.objects.filter(usuario=self.usuario, rol=rol).exists():
            raise forms.ValidationError("El usuario ya tiene este rol asignado.")
        return rol
