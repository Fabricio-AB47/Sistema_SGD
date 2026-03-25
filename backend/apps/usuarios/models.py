from django.db import models


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

    class Meta:
        db_table = "usuario"
        managed = False
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        ordering = ("primer_apellido", "primer_nombre")
        indexes = [
            models.Index(fields=["correo"], name="uq_usuario_correo"),
            models.Index(fields=["identificacion"], name="uq_usuario_identificacion"),
        ]

    def __str__(self):
        return f"{self.primer_nombre} {self.primer_apellido}".strip()

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
    fecha_creacion = models.DateTimeField(null=True, blank=True)

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
