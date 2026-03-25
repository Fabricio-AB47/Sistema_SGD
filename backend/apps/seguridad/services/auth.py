import uuid
import hashlib
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from django.db import transaction

from apps.usuarios.models import (
    Usuario,
    UsuarioCredencial,
    HistorialLogin,
    UserSession,
)
from apps.seguridad.selectors.usuarios import (
    get_usuario_activo_por_correo,
    get_credencial_con_lock,
)

ph = PasswordHasher()


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@transaction.atomic
def autenticar(correo: str, password: str, remember: bool, ip: str, user_agent: str):
    now = datetime.now(timezone.utc)
    usuario = get_usuario_activo_por_correo(correo)
    if not usuario:
        HistorialLogin.objects.create(
            usuario=None,
            correo_intento=correo,
            fecha_intento=now,
            exito=False,
            motivo="usuario_inexistente",
            ip=ip,
            user_agent=user_agent,
        )
        raise AuthError("Credenciales inválidas", status=401)

    cred = get_credencial_con_lock(usuario.id)
    if not cred:
        HistorialLogin.objects.create(
            usuario=usuario,
            correo_intento=correo,
            fecha_intento=now,
            exito=False,
            motivo="credencial_inexistente",
            ip=ip,
            user_agent=user_agent,
        )
        raise AuthError("Credenciales inválidas", status=401)

    if cred.bloqueado_hasta and cred.bloqueado_hasta > now:
        raise AuthError("Cuenta bloqueada temporalmente. Intente más tarde.", status=423)

    # Validar hash Argon2
    try:
        ph.verify(cred.password_hash, password)
        password_ok = True
    except Exception:
        password_ok = False

    if not password_ok:
        cred.intentos_fallidos += 1
        cred.ultimo_intento_fallido = now
        if cred.intentos_fallidos >= 5:
            cred.bloqueado_hasta = now + timedelta(minutes=10)
        cred.save(update_fields=["intentos_fallidos", "ultimo_intento_fallido", "bloqueado_hasta"])
        HistorialLogin.objects.create(
            usuario=usuario,
            correo_intento=correo,
            fecha_intento=now,
            exito=False,
            motivo="password_incorrecto",
            ip=ip,
            user_agent=user_agent,
        )
        raise AuthError("Credenciales inválidas", status=401)

    # Reset intentos
    cred.intentos_fallidos = 0
    cred.bloqueado_hasta = None
    cred.ultimo_login = now
    cred.save(update_fields=["intentos_fallidos", "bloqueado_hasta", "ultimo_login"])

    # Crear sesión
    token_plain = uuid.uuid4().hex
    token_hash = hashlib.sha256(token_plain.encode()).hexdigest()
    exp = now + (timedelta(days=7) if remember else timedelta(hours=8))

    session = UserSession.objects.create(
        usuario=usuario,
        token_sesion_hash=token_hash,
        fecha_inicio=now,
        fecha_expiracion=exp,
        ip=ip,
        user_agent=user_agent[:300],
        activa=True,
    )

    HistorialLogin.objects.create(
        usuario=usuario,
        correo_intento=correo,
        fecha_intento=now,
        exito=True,
        motivo="login_ok",
        ip=ip,
        user_agent=user_agent,
    )

    return {
        "token": token_plain,
        "expira": exp,
        "usuario": usuario,
        "session_id": session.id_sesion,
    }


def cerrar_sesion(token_plain: str):
    token_hash = hashlib.sha256(token_plain.encode()).hexdigest()
    return UserSession.objects.filter(token_sesion_hash=token_hash, activa=True).update(activa=False)
