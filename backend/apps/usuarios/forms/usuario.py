"""
Formularios para gestión de usuarios y asignación de roles.
Incluyen validaciones básicas alineadas al esquema de la base de datos.
"""

from django import forms

from apps.usuarios.models import Usuario, UsuarioRol, Rol, TipoIdentificacion
from apps.seguridad.models import UsuarioCredencial
from apps.seguridad.services import password_service
from apps.seguridad.models import UsuarioOTP, TokenVerificacion


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
        self.fields["rol"].empty_label = "Seleccione el rol de usuario"

    def save(self, commit=True):
        """
        Crea el usuario, su credencial y asigna (si se indicó) un rol.
        """
        usuario = super().save(commit=False)
        if commit:
            usuario.save()

            # Credencial
            raw_pwd = self.cleaned_data["password"]
            UsuarioCredencial.objects.create(
                usuario=usuario,
                password_hash=password_service.hash_password(raw_pwd),
                algoritmo_hash="argon2",
            )

            # Rol (opcional)
            rol = self.cleaned_data.get("rol")
            if rol:
                UsuarioRol.objects.create(usuario=usuario, rol=rol, activo=True)

        return usuario


class UsuarioEditarForm(forms.ModelForm):
    """
    Formulario para editar datos de un usuario existente.
    Controla colisiones de correo e identificación excluyendo el propio registro.
    """

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
