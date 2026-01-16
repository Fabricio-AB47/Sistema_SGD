from django.db import models


class TipoUsuario(models.Model):
    # Catálogo de clasificación institucional de usuario
    id_tp_user = models.AutoField(primary_key=True, db_column="id_tp_user")
    descripcion_tp_user = models.CharField(max_length=150)
    activo_tp_user = models.BooleanField(default=True)

    class Meta:
        db_table = "tipo_usuario"

    def __str__(self) -> str:
        return self.descripcion_tp_user


class Permiso(models.Model):
    # Permisos atómicos por módulo (código único)
    id_permiso = models.AutoField(primary_key=True, db_column="id_permiso")
    codigo_permiso = models.CharField(max_length=100, unique=True)
    descripcion = models.CharField(max_length=250)
    modulo = models.CharField(max_length=100)

    class Meta:
        db_table = "permiso"

    def __str__(self) -> str:
        return self.codigo_permiso


class Rol(models.Model):
    # Rol funcional ligado a un tipo de usuario
    id_rol = models.AutoField(primary_key=True, db_column="id_rol")
    nombre_rol = models.CharField(max_length=150, unique=True)
    descripcion = models.CharField(max_length=250)
    activo = models.BooleanField(default=True)
    tipo_usuario = models.ForeignKey(
        "TipoUsuario",
        on_delete=models.PROTECT,
        db_column="id_tp_user",
        related_name="roles",
    )

    class Meta:
        db_table = "rol"

    def __str__(self) -> str:
        return self.nombre_rol


class RolPermiso(models.Model):
    # N:M entre rol y permiso
    rol = models.ForeignKey(
        Rol, on_delete=models.CASCADE, db_column="id_rol", related_name="rol_permisos"
    )
    permiso = models.ForeignKey(
        Permiso,
        on_delete=models.CASCADE,
        db_column="id_permiso",
        related_name="rol_permisos",
    )

    class Meta:
        db_table = "rol_permiso"
        constraints = [
            models.UniqueConstraint(
                fields=["rol", "permiso"], name="rol_permiso_pk"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.rol} - {self.permiso}"


class TipoIdentificacion(models.Model):
    # Catálogo de documentos (cédula, pasaporte, etc.)
    id_tipo_identificacion = models.AutoField(
        primary_key=True, db_column="id_tipo_identificacion"
    )
    descripcion_tp_identificacion = models.CharField(max_length=150)

    class Meta:
        db_table = "tipo_identificacion"

    def __str__(self) -> str:
        return self.descripcion_tp_identificacion


class Usuario(models.Model):
    # Tabla principal de usuarios (login por correo)
    id_user = models.AutoField(primary_key=True, db_column="id_user")
    primer_nombre = models.CharField(max_length=150)
    segundo_nombre = models.CharField(max_length=150)
    primer_apellido = models.CharField(max_length=150)
    segundo_apellido = models.CharField(max_length=150)
    identificacion = models.CharField(max_length=15, unique=True)
    correo = models.EmailField(max_length=254, unique=True)
    correo_verificado = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    tipo_identificacion = models.ForeignKey(
        TipoIdentificacion,
        on_delete=models.PROTECT,
        db_column="id_tipo_identificacion",
        related_name="usuarios",
    )

    class Meta:
        db_table = "usuario"

    def __str__(self) -> str:
        return f"{self.primer_nombre} {self.primer_apellido}"


class UsuarioCredencial(models.Model):
    # Credenciales separadas: hash PBKDF2 (robusto) guardado en VARBINARY
    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column="id_user",
        related_name="credencial",
    )
    password_hash = models.BinaryField(max_length=255)  # guardar make_password().encode()
    algoritmo_hash = models.CharField(max_length=30)
    fecha_cambio = models.DateTimeField()
    requiere_cambio = models.BooleanField(default=False)
    intentos_fallidos = models.IntegerField(default=0)  # control de fuerza bruta
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)  # lock temporal
    ultimo_login = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "usuario_credencial"

    def __str__(self) -> str:
        return f"Credencial {self.usuario_id}"


class UsuarioRol(models.Model):
    # Relación N:M usuario-rol, con trazabilidad de asignación
    id_user_rol = models.AutoField(primary_key=True, db_column="id_user_rol")
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        db_column="id_user",
        related_name="roles_asignados",
    )
    rol = models.ForeignKey(
        Rol,
        on_delete=models.PROTECT,
        db_column="id_rol",
        related_name="usuarios",
    )
    fecha_asignacion = models.DateTimeField()
    asignado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        db_column="asignado_por",
        related_name="roles_otorgados",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "usuario_rol"
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "rol"], name="usuario_rol_uq"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.usuario} - {self.rol}"


class UserSession(models.Model):
    # Registro de sesión (inicio, expiración deslizante, IP, user-agent)
    id_sesion = models.AutoField(primary_key=True, db_column="id_sesion")
    fecha_inicio = models.DateTimeField()
    fecha_expiracion = models.DateTimeField()
    fecha_renovacion = models.DateTimeField()
    ip = models.CharField(max_length=45)
    user_agent = models.CharField(max_length=300)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        db_column="id_user",
        related_name="sesiones",
    )

    class Meta:
        db_table = "user_session"

    def __str__(self) -> str:
        return f"Sesion {self.id_sesion} de {self.usuario}"


class UserActivity(models.Model):
    # Trazabilidad de actividad de usuario (login, último visto, logout)
    id_user_act = models.AutoField(primary_key=True, db_column="id_user_act")
    login_at = models.DateTimeField()
    last_seen_at = models.DateTimeField(null=True, blank=True)
    logout_at = models.DateTimeField(null=True, blank=True)
    ip = models.CharField(max_length=45)
    user_agent = models.CharField(max_length=300)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        db_column="id_user",
        related_name="actividades",
    )

    class Meta:
        db_table = "user_activity"

    def __str__(self) -> str:
        return f"Actividad {self.id_user_act} de {self.usuario}"


class EmailVerificationToken(models.Model):
    # Token de verificación de correo: hash + prefijo (sin guardar el token en claro)
    id_token = models.AutoField(primary_key=True, db_column="id_token")
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        db_column="id_user",
        related_name="tokens_verificacion",
    )
    token_hash = models.BinaryField(max_length=255)
    token_prefix = models.CharField(max_length=12)
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    ip = models.CharField(max_length=45, null=True, blank=True)
    user_agent = models.CharField(max_length=300, null=True, blank=True)
    resend_count = models.IntegerField(default=0)
    last_resend_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "email_verification_token"
        managed = False
        indexes = [
            models.Index(fields=["usuario", "expires_at"], name="ix_evt_user_expires_py"),
            models.Index(fields=["token_prefix"], name="ix_evt_prefix_py"),
        ]

    def __str__(self) -> str:
        return f"Token verificacion user {self.usuario_id}"
