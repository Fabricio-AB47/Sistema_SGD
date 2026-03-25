from django.db import models
from django.utils import timezone

from apps.usuarios.models import Usuario


class UsuarioCredencial(models.Model):
    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="credencial",
        db_column="id_user",
    )
    password_hash = models.CharField(max_length=255)
    algoritmo_hash = models.CharField(max_length=30, default="ARGON2ID")
    requiere_cambio = models.BooleanField(default=False)
    mfa_activo = models.BooleanField(default=False)
    intentos_fallidos = models.PositiveIntegerField(default=0)
    ultimo_intento_fallido = models.DateTimeField(null=True, blank=True)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    ultimo_login = models.DateTimeField(null=True, blank=True)
    fecha_cambio = models.DateTimeField(default=timezone.now, null=True, blank=True)
    salt_referencia = models.CharField(max_length=120, null=True, blank=True)
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
    algoritmo_hash = models.CharField(max_length=30)
    fecha_cambio = models.DateTimeField(default=timezone.now, null=True, blank=True)

    class Meta:
        db_table = "historial_password"
        managed = False
        verbose_name = "Historial de password"
        verbose_name_plural = "Historial de passwords"
        ordering = ("-fecha_cambio",)


class UsuarioOTP(models.Model):
    id_otp = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="otps",
        db_column="id_user",
    )
    codigo_otp_hash = models.BinaryField()
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


class TokenVerificacion(models.Model):
    id_token_verificacion = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="tokens_verificacion",
        db_column="id_user",
    )
    token_hash = models.CharField(max_length=64, unique=True)
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
    token_hash = models.CharField(max_length=64, unique=True)
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


class UserSession(models.Model):
    id_sesion = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="sesiones",
        db_column="id_user",
    )
    token_sesion_hash = models.CharField(max_length=64, unique=True)
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
                name="ix_user_session_user_activa",
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
                name="ix_historial_login_user_fecha",
            ),
        ]
