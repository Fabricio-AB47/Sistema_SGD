from django.db import models
from django.utils import timezone


class Usuario(models.Model):
    id_user = models.AutoField(primary_key=True)
    primer_nombre = models.CharField(max_length=150)
    segundo_nombre = models.CharField(max_length=150, null=True, blank=True)
    primer_apellido = models.CharField(max_length=150)
    segundo_apellido = models.CharField(max_length=150, null=True, blank=True)
    identificacion = models.CharField(max_length=20, unique=True)
    correo = models.EmailField(max_length=254, unique=True)
    telefono = models.CharField(max_length=20, null=True, blank=True)
    correo_verificado = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(null=True, blank=True)
    fecha_actualizacion = models.DateTimeField(null=True, blank=True)
    id_tipo_identificacion = models.IntegerField()
    version_fila = models.BinaryField(null=True, blank=True)

    class Meta:
        db_table = "usuario"
        managed = False
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        ordering = ("primer_apellido", "primer_nombre")

    def __str__(self):
        return self.nombre_completo or self.correo

    @property
    def tipo_identificacion(self):
        return TipoIdentificacion.objects.filter(
            id_tipo_identificacion=self.id_tipo_identificacion
        ).first()

    @property
    def nombre_completo(self) -> str:
        parts = [
            self.primer_nombre,
            self.segundo_nombre,
            self.primer_apellido,
            self.segundo_apellido,
        ]
        return " ".join(part for part in parts if part)


class TipoIdentificacion(models.Model):
    id_tipo_identificacion = models.AutoField(primary_key=True)
    descripcion = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "tipo_identificacion"
        managed = False
        verbose_name = "Tipo de identificacion"
        verbose_name_plural = "Tipos de identificacion"
        ordering = ("descripcion",)

    def __str__(self):
        return self.descripcion


class Rol(models.Model):
    id_rol = models.AutoField(primary_key=True)
    nombre_rol = models.CharField(max_length=100, unique=True)
    descripcion = models.CharField(max_length=250, null=True, blank=True)
    acceso_global = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "rol"
        managed = False
        verbose_name = "Rol"
        verbose_name_plural = "Roles"
        ordering = ("nombre_rol",)

    def __str__(self):
        return self.nombre_rol


class Permiso(models.Model):
    id_permiso = models.AutoField(primary_key=True)
    codigo_permiso = models.CharField(max_length=100, unique=True)
    descripcion = models.CharField(max_length=250)
    modulo = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "permiso"
        managed = False
        verbose_name = "Permiso"
        verbose_name_plural = "Permisos"
        ordering = ("modulo", "codigo_permiso")

    def __str__(self):
        return self.codigo_permiso


class RolPermiso(models.Model):
    pk = models.CompositePrimaryKey("rol", "permiso")
    rol = models.ForeignKey(
        Rol,
        on_delete=models.CASCADE,
        related_name="permisos_asignados",
        db_column="id_rol",
    )
    permiso = models.ForeignKey(
        Permiso,
        on_delete=models.CASCADE,
        related_name="roles_asignados",
        db_column="id_permiso",
    )

    class Meta:
        db_table = "rol_permiso"
        managed = False
        verbose_name = "Rol - Permiso"
        verbose_name_plural = "Roles - Permisos"
        ordering = ("rol", "permiso")


class UsuarioRol(models.Model):
    id_user_rol = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="roles_asignados",
        db_column="id_user",
    )
    rol = models.ForeignKey(
        Rol,
        on_delete=models.CASCADE,
        related_name="usuarios",
        db_column="id_rol",
    )
    fecha_asignacion = models.DateTimeField(null=True, blank=True)
    fecha_revocacion = models.DateTimeField(null=True, blank=True)
    asignado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roles_asignados_por",
        db_column="asignado_por",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "usuario_rol"
        managed = False
        verbose_name = "Usuario - Rol"
        verbose_name_plural = "Usuarios - Roles"
        ordering = ("-fecha_asignacion",)
        constraints = [
            models.UniqueConstraint(fields=["usuario", "rol"], name="uq_usuario_rol")
        ]

    def __str__(self):
        return f"{self.usuario} -> {self.rol}"


class UsuarioCredencial(models.Model):
    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="credencial",
        db_column="id_user",
    )
    password_hash = models.CharField(max_length=255)
    algoritmo_hash = models.CharField(max_length=30, default="argon2")
    requiere_cambio = models.BooleanField(default=False)
    mfa_activo = models.BooleanField(default=False)
    intentos_fallidos = models.PositiveIntegerField(default=0)
    ultimo_intento_fallido = models.DateTimeField(null=True, blank=True)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    ultimo_login = models.DateTimeField(null=True, blank=True)
    fecha_cambio = models.DateTimeField(default=timezone.now, null=True, blank=True)
    salt_referencia = models.CharField(max_length=100, null=True, blank=True)
    password_version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "usuario_credencial"
        managed = False
        verbose_name = "Credencial de usuario"
        verbose_name_plural = "Credenciales de usuario"


class HistorialPassword(models.Model):
    id_historial_password = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="historial_passwords",
        db_column="id_user",
    )
    password_hash = models.CharField(max_length=255)
    fecha_cambio = models.DateTimeField(default=timezone.now, null=True, blank=True)

    class Meta:
        db_table = "historial_password"
        managed = False
        verbose_name = "Historial de password"
        verbose_name_plural = "Historial de passwords"
        ordering = ("-fecha_cambio",)


class TokenVerificacion(models.Model):
    id_token_verificacion = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="tokens_verificacion",
        db_column="id_user",
    )
    token_hash = models.CharField(max_length=255, unique=True)
    fecha_creacion = models.DateTimeField(default=timezone.now, null=True, blank=True)
    fecha_expiracion = models.DateTimeField()
    verificado = models.BooleanField(default=False)
    ip_solicitud = models.CharField(max_length=45, null=True, blank=True)

    class Meta:
        db_table = "token_verificacion"
        managed = False
        verbose_name = "Token de verificacion"
        verbose_name_plural = "Tokens de verificacion"
        ordering = ("-fecha_creacion",)


class TokenRecuperacion(models.Model):
    id_token_recuperacion = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="tokens_recuperacion",
        db_column="id_user",
    )
    token_hash = models.CharField(max_length=255, unique=True)
    fecha_creacion = models.DateTimeField(default=timezone.now, null=True, blank=True)
    fecha_expiracion = models.DateTimeField()
    usado = models.BooleanField(default=False)
    ip_solicitud = models.CharField(max_length=45, null=True, blank=True)

    class Meta:
        db_table = "token_recuperacion"
        managed = False
        verbose_name = "Token de recuperacion"
        verbose_name_plural = "Tokens de recuperacion"
        ordering = ("-fecha_creacion",)


class UsuarioOTP(models.Model):
    id_otp = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="otps",
        db_column="id_user",
    )
    codigo_otp_hash = models.CharField(max_length=255)
    tipo_otp = models.CharField(max_length=50)
    fecha_generacion = models.DateTimeField(default=timezone.now, null=True, blank=True)
    fecha_expiracion = models.DateTimeField()
    usado = models.BooleanField(default=False)
    intentos = models.PositiveIntegerField(default=0)
    ip = models.CharField(max_length=45, null=True, blank=True)

    class Meta:
        db_table = "usuario_otp"
        managed = False
        verbose_name = "OTP de usuario"
        verbose_name_plural = "OTPs de usuario"
        ordering = ("-fecha_generacion",)


class UserSession(models.Model):
    id_sesion = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="sesiones",
        db_column="id_user",
    )
    token_sesion_hash = models.CharField(max_length=255, unique=True)
    fecha_inicio = models.DateTimeField(default=timezone.now, null=True, blank=True)
    fecha_expiracion = models.DateTimeField()
    fecha_renovacion = models.DateTimeField(null=True, blank=True)
    activa = models.BooleanField(default=True)
    ip = models.CharField(max_length=45, null=True, blank=True)
    user_agent = models.CharField(max_length=300, null=True, blank=True)
    ultima_actividad = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_session"
        managed = False
        verbose_name = "Sesion de usuario"
        verbose_name_plural = "Sesiones de usuario"
        ordering = ("-fecha_inicio",)
        indexes = [
            models.Index(
                fields=["usuario", "activa", "fecha_expiracion"],
                name="ix_user_session_usuario_activa_exp",
            ),
        ]


class HistorialLogin(models.Model):
    id_login = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logins",
        db_column="id_user",
    )
    correo_intento = models.EmailField(max_length=254, null=True, blank=True)
    fecha_intento = models.DateTimeField(default=timezone.now, null=True, blank=True)
    exito = models.BooleanField()
    motivo = models.CharField(max_length=150, null=True, blank=True)
    ip = models.CharField(max_length=45, null=True, blank=True)
    user_agent = models.CharField(max_length=300, null=True, blank=True)

    class Meta:
        db_table = "historial_login"
        managed = False
        verbose_name = "Historial de login"
        verbose_name_plural = "Historial de login"
        ordering = ("-fecha_intento",)
        indexes = [
            models.Index(
                fields=["usuario", "-fecha_intento"],
                name="ix_historial_login_usuario_fecha",
            ),
        ]


class AreaInstitucional(models.Model):
    id_area = models.AutoField(primary_key=True)
    codigo_area = models.CharField(max_length=20, unique=True)
    nombre_area = models.CharField(max_length=150)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "area_institucional"
        managed = False
        verbose_name = "Area institucional"
        verbose_name_plural = "Areas institucionales"
        ordering = ("nombre_area",)

    def __str__(self):
        return f"{self.codigo_area} - {self.nombre_area}"


class CargoArea(models.Model):
    id_cargo = models.AutoField(primary_key=True)
    area = models.ForeignKey(
        AreaInstitucional,
        on_delete=models.CASCADE,
        related_name="cargos",
        db_column="id_area",
    )
    codigo_cargo = models.CharField(max_length=30)
    nombre_cargo = models.CharField(max_length=150)
    nivel_jerarquico = models.PositiveIntegerField()
    aprueba_interno = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "cargo_area"
        managed = False
        verbose_name = "Cargo por area"
        verbose_name_plural = "Cargos por area"
        ordering = ("area__nombre_area", "nivel_jerarquico", "nombre_cargo")
        constraints = [
            models.UniqueConstraint(fields=["area", "codigo_cargo"], name="uq_cargo_area"),
            models.CheckConstraint(condition=models.Q(nivel_jerarquico__gt=0), name="ck_cargo_area_nivel"),
        ]

    def __str__(self):
        return f"{self.area.codigo_area} / {self.codigo_cargo} - {self.nombre_cargo}"


class UsuarioAreaCargo(models.Model):
    id_usuario_area_cargo = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="areas_cargos",
        db_column="id_user",
    )
    area = models.ForeignKey(
        AreaInstitucional,
        on_delete=models.CASCADE,
        related_name="usuarios_asignados",
        db_column="id_area",
    )
    cargo = models.ForeignKey(
        CargoArea,
        on_delete=models.CASCADE,
        related_name="usuarios_asignados",
        db_column="id_cargo",
    )
    fecha_asignacion = models.DateTimeField(default=timezone.now, null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "usuario_area_cargo"
        managed = False
        verbose_name = "Usuario area cargo"
        verbose_name_plural = "Usuarios area cargo"
        ordering = ("-fecha_asignacion",)
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "area", "cargo", "activo"],
                name="uq_usuario_area_cargo",
            )
        ]

    def __str__(self):
        return f"{self.usuario} -> {self.area.codigo_area} / {self.cargo.codigo_cargo}"


class UsuarioSupervisor(models.Model):
    id_usuario_supervisor = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="supervisores_asignados",
        db_column="id_user",
    )
    supervisor = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="colaboradores_asignados",
        db_column="id_supervisor",
    )
    fecha_asignacion = models.DateTimeField(default=timezone.now, null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "usuario_supervisor"
        managed = False
        verbose_name = "Usuario supervisor"
        verbose_name_plural = "Usuarios supervisor"
        ordering = ("-fecha_asignacion",)
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "supervisor", "activo"],
                name="uq_usuario_supervisor",
            ),
            models.CheckConstraint(condition=~models.Q(usuario=models.F("supervisor")), name="ck_usuario_supervisor_distinto"),
        ]

    def __str__(self):
        return f"{self.usuario} -> supervisor {self.supervisor}"
