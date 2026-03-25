import uuid
import hashlib
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction

from apps.usuarios.models import Usuario
from apps.seguridad.models import UsuarioCredencial, HistorialLogin, UserSession


ph = PasswordHasher()


def _json_error(message, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)


@csrf_exempt
@transaction.atomic
def login_view(request):
    """
    POST /api/auth/login
    Body: { "correo": "...", "password": "...", "remember": false }
    - Verifica credenciales en usuario/usuario_credencial.
    - Registra historial de login.
    - Crea sesión en user_session y retorna token (plain) + expiración.
    """
    if request.method != "POST":
        return _json_error("Método no permitido", status=405)

    data = request.POST or getattr(request, "data", None) or {}
    correo = (data.get("correo") or "").strip().lower()
    password = data.get("password") or ""
    remember = data.get("remember") in (True, "true", "1", 1)
    ip = request.META.get("REMOTE_ADDR")
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:300]

    if not correo or not password:
        return _json_error("Correo y contraseña son obligatorios")

    try:
        usuario = Usuario.objects.get(correo__iexact=correo, activo=True)
    except Usuario.DoesNotExist:
        HistorialLogin.objects.create(
            usuario=None, correo_intento=correo, exito=False, motivo="usuario_inexistente", ip=ip, user_agent=user_agent
        )
        return _json_error("Credenciales inválidas")

    try:
        cred = UsuarioCredencial.objects.select_for_update().get(usuario=usuario)
    except UsuarioCredencial.DoesNotExist:
        HistorialLogin.objects.create(
            usuario=usuario, correo_intento=correo, exito=False, motivo="credencial_inexistente", ip=ip, user_agent=user_agent
        )
        return _json_error("Credenciales inválidas")

    # Verificar bloqueo temporal
    now = datetime.now(timezone.utc)
    if cred.bloqueado_hasta and cred.bloqueado_hasta > now:
        return _json_error("Cuenta bloqueada temporalmente. Intente más tarde.", status=423)

    # Validar hash Argon2
    try:
        ph.verify(cred.password_hash, password)
        password_ok = True
    except Exception:
        password_ok = False

    if not password_ok:
        cred.intentos_fallidos += 1
        cred.ultimo_intento_fallido = now
        # Bloqueo simple después de 5 intentos: 10 minutos
        if cred.intentos_fallidos >= 5:
            cred.bloqueado_hasta = now + timedelta(minutes=10)
        cred.save(update_fields=["intentos_fallidos", "ultimo_intento_fallido", "bloqueado_hasta"])
        HistorialLogin.objects.create(
            usuario=usuario, correo_intento=correo, exito=False, motivo="password_incorrecto", ip=ip, user_agent=user_agent
        )
        return _json_error("Credenciales inválidas")

    # Reset de intentos al éxito
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
        fecha_expiracion=exp,
        ip=ip,
        user_agent=user_agent,
        activa=True,
    )

    HistorialLogin.objects.create(
        usuario=usuario, correo_intento=correo, exito=True, motivo="login_ok", ip=ip, user_agent=user_agent
    )

    return JsonResponse(
        {
            "ok": True,
            "token": token_plain,
            "expira": exp.isoformat(),
            "user": {
                "id": usuario.id_user,
                "nombre": f"{usuario.primer_nombre} {usuario.primer_apellido}".strip(),
                "correo": usuario.correo,
            },
            "session_id": session.id_sesion,
        }
    )


def login_page(request):
    """
    GET /login – página HTML de acceso.
    """
    return render(request, "auth/login.html")


@csrf_exempt
@transaction.atomic
def logout_view(request):
    """
    POST /api/auth/logout
    Body: { "token": "<plain_token>" }
    Marca la sesión como inactiva.
    """
    if request.method != "POST":
        return _json_error("Método no permitido", status=405)

    data = request.POST or getattr(request, "data", None) or {}
    token = data.get("token")
    if not token:
        return _json_error("Token requerido")

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    updated = UserSession.objects.filter(token_sesion_hash=token_hash, activa=True).update(activa=False)

    return JsonResponse({"ok": updated > 0})
