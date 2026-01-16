import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.seguridad.models import (
    EmailVerificationToken,
    Rol,
    TipoIdentificacion,
    TipoUsuario,
    Usuario,
    UsuarioCredencial,
    UsuarioRol,
    UserSession,
)
from apps.seguridad.email_service import send_verification_email


def _normalize_password_hash(raw_value):
    if raw_value is None:
        return None
    if hasattr(raw_value, "tobytes"):
        raw_value = raw_value.tobytes()
    if isinstance(raw_value, bytes):
        try:
            return raw_value.decode("utf-8")
        except UnicodeDecodeError:
            return raw_value.decode("latin-1", errors="ignore")
    return str(raw_value)


def _password_matches(plain, stored_hash):
    """
    Compara una contraseña en texto plano con un hash robusto (pbkdf2/bcrypt/argon2).
    Para hashes pbkdf2_sha256 (default de Django) se usa check_password, que incluye sal y muchas iteraciones.
    """
    if not stored_hash:
        return False
    if stored_hash.startswith(("pbkdf2_", "argon2", "bcrypt")):
        try:
            return check_password(plain, stored_hash)
        except Exception:
            return False
    return plain == stored_hash


def login_view(request):
    if request.session.get("usuario_id"):
        return redirect("home")

    if request.method == "POST":
        correo = request.POST.get("correo", "").strip()
        password = request.POST.get("password", "").strip()

        if not correo or not password:
            messages.error(request, "Ingrese correo y contrasena.")
            return render(request, "auth/login.html")

        try:
            usuario = Usuario.objects.get(correo=correo)
            credencial = usuario.credencial
        except (Usuario.DoesNotExist, UsuarioCredencial.DoesNotExist):
            messages.error(request, "Usuario o contrasena incorrectos.")
            return render(request, "auth/login.html")

        stored_hash = _normalize_password_hash(credencial.password_hash)
        # Valida contra hash PBKDF2 (robusto, con sal e iteraciones)
        if not _password_matches(password, stored_hash):
            messages.error(request, "Usuario o contrasena incorrectos.")
            return render(request, "auth/login.html")

        now = timezone.localtime(timezone.now())
        idle_minutes = getattr(settings, "SESSION_IDLE_MINUTES", 15)
        fecha_exp = now + timezone.timedelta(minutes=idle_minutes)
        try:
            session_obj = UserSession.objects.create(
                usuario=usuario,
                fecha_inicio=now,
                fecha_expiracion=fecha_exp,
                fecha_renovacion=now,
                ip=request.META.get("REMOTE_ADDR", ""),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
            )
            UsuarioCredencial.objects.filter(usuario=usuario).update(ultimo_login=now)
            request.session["user_session_id"] = session_obj.id_sesion
        except Exception:
            # No bloquear el login si falla el registro de sesion
            pass

        request.session["usuario_id"] = usuario.id_user
        request.session["usuario_nombre"] = f"{usuario.primer_nombre} {usuario.primer_apellido}"
        messages.success(request, "Ingreso exitoso.")
        return redirect("home")

    return render(request, "auth/login.html")


def logout_view(request):
    request.session.flush()
    return redirect("login")


def register_view(request):
    if request.session.get("usuario_id"):
        return redirect("home")

    tipos_ident = TipoIdentificacion.objects.all()
    tipos_usuario = TipoUsuario.objects.filter(activo_tp_user=True)
    roles = Rol.objects.filter(activo=True)
    form_data = {}
    selected_roles = []

    if request.method == "POST":
        data = {
            "primer_nombre": request.POST.get("primer_nombre", "").strip(),
            "segundo_nombre": request.POST.get("segundo_nombre", "").strip(),
            "primer_apellido": request.POST.get("primer_apellido", "").strip(),
            "segundo_apellido": request.POST.get("segundo_apellido", "").strip(),
            "identificacion": request.POST.get("identificacion", "").strip(),
            "correo": request.POST.get("correo", "").strip(),
            "id_tipo_identificacion": request.POST.get("id_tipo_identificacion"),
            "id_tipo_usuario": request.POST.get("id_tipo_usuario"),
            "password": request.POST.get("password", ""),
            "password2": request.POST.get("password2", ""),
        }
        role_ids = request.POST.getlist("roles")
        form_data = data
        selected_roles = role_ids

        if not all(
            [
                data["primer_nombre"],
                data["primer_apellido"],
                data["identificacion"],
                data["correo"],
                data["id_tipo_identificacion"],
                data["id_tipo_usuario"],
                data["password"],
            ]
        ):
            messages.error(request, "Complete todos los campos obligatorios.")
            return render(
                request,
                "auth/register.html",
                {
                    "tipos_ident": tipos_ident,
                    "roles": roles,
                    "tipos_usuario": tipos_usuario,
                    "form_data": form_data,
                    "selected_roles": selected_roles,
                },
            )

        if data["password"] != data["password2"]:
            messages.error(request, "Las contrasenas no coinciden.")
            return render(
                request,
                "auth/register.html",
                {
                    "tipos_ident": tipos_ident,
                    "roles": roles,
                    "tipos_usuario": tipos_usuario,
                    "form_data": form_data,
                    "selected_roles": selected_roles,
                },
            )

        if not role_ids:
            messages.error(request, "Seleccione al menos un rol.")
            return render(
                request,
                "auth/register.html",
                {
                    "tipos_ident": tipos_ident,
                    "roles": roles,
                    "tipos_usuario": tipos_usuario,
                    "form_data": form_data,
                    "selected_roles": selected_roles,
                },
            )

        try:
            tipo_usuario_sel = TipoUsuario.objects.get(id_tp_user=data["id_tipo_usuario"])
        except TipoUsuario.DoesNotExist:
            messages.error(request, "Tipo de usuario no valido.")
            return render(
                request,
                "auth/register.html",
                {
                    "tipos_ident": tipos_ident,
                    "roles": roles,
                    "tipos_usuario": tipos_usuario,
                    "form_data": form_data,
                    "selected_roles": selected_roles,
                },
            )

        try:
            usuario, created = Usuario.objects.get_or_create(
                correo=data["correo"],
                defaults={
                    "primer_nombre": data["primer_nombre"],
                    "segundo_nombre": data["segundo_nombre"],
                    "primer_apellido": data["primer_apellido"],
                    "segundo_apellido": data["segundo_apellido"],
                    "identificacion": data["identificacion"],
                    "id_tipo_identificacion": data["id_tipo_identificacion"],
                    "correo_verificado": False,
                    "activo": True,
                },
            )
            if not created:
                messages.error(request, "El correo ya esta registrado.")
                return render(
                    request,
                    "auth/register.html",
                    {
                        "tipos_ident": tipos_ident,
                        "roles": roles,
                        "tipos_usuario": tipos_usuario,
                        "form_data": form_data,
                        "selected_roles": selected_roles,
                    },
                )
        except Exception as exc:
            messages.error(request, f"Error creando usuario: {exc}")
            return render(
                request,
                "auth/register.html",
                {"tipos_ident": tipos_ident, "roles": roles, "tipos_usuario": tipos_usuario},
            )

        try:
            UsuarioCredencial.objects.update_or_create(
                usuario=usuario,
                defaults={
                    "password_hash": make_password(data["password"]).encode(),
                    "algoritmo_hash": "pbkdf2_sha256",
                    "fecha_cambio": timezone.now(),
                    "requiere_cambio": False,
                    "intentos_fallidos": 0,
                    "bloqueado_hasta": None,
                    "ultimo_login": None,
                },
            )
        except Exception as exc:
            usuario.delete()
            messages.error(request, f"Error creando credencial: {exc}")
            return render(
                request,
                "auth/register.html",
                {
                    "tipos_ident": tipos_ident,
                    "roles": roles,
                    "tipos_usuario": tipos_usuario,
                    "form_data": form_data,
                    "selected_roles": selected_roles,
                },
            )

        try:
            role_ids_int = [int(r) for r in role_ids]
            roles_asignar = Rol.objects.filter(id_rol__in=role_ids_int, activo=True)
            if roles_asignar.count() != len(role_ids_int):
                raise ValueError("Algun rol seleccionado no existe o esta inactivo.")
            if any(r.tipo_usuario_id != tipo_usuario_sel.id_tp_user for r in roles_asignar):
                raise ValueError("Los roles no corresponden al tipo de usuario seleccionado.")

            for rol in roles_asignar:
                UsuarioRol.objects.get_or_create(
                    usuario=usuario,
                    rol=rol,
                    defaults={"fecha_asignacion": timezone.now(), "asignado_por": None},
                )
        except Exception as exc:
            messages.warning(request, f"Usuario creado pero no se pudo asignar rol: {exc}")
            return redirect("login")

        messages.success(request, "Registro exitoso. Ahora puede iniciar sesion.")
        return redirect("login")

    return render(
        request,
        "auth/register.html",
        {
            "tipos_ident": tipos_ident,
            "roles": roles,
            "tipos_usuario": tipos_usuario,
            "form_data": form_data,
            "selected_roles": selected_roles,
        },
    )


def request_reset_view(request):
    if request.method == "POST":
        correo = request.POST.get("correo", "").strip()
        if not correo:
            messages.error(request, "Ingrese su correo.")
            return render(request, "auth/password_reset_request.html")
        try:
            usuario = Usuario.objects.get(correo=correo, activo=True)
        except Usuario.DoesNotExist:
            messages.success(request, "Si el correo existe, recibira instrucciones.")
            return redirect("login")

        import secrets

        token = secrets.token_urlsafe(32)
        reset_link = request.build_absolute_uri(f"/reset-password/confirm/?token={token}&correo={correo}")

        request.session["reset_token"] = token
        request.session["reset_correo"] = correo
        request.session["reset_created_at"] = timezone.now().isoformat()

        subject = "Restablecimiento de contrasena"
        body = (
            f"Hola {usuario.primer_nombre},\n\n"
            f"Usa este enlace para restablecer tu contrasena:\n{reset_link}\n\n"
            "Si no solicitaste esto, ignora el correo."
        )
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER,
            to=[correo],
            cc=[settings.MAIL_CC] if getattr(settings, "MAIL_CC", "") else [],
        )
        try:
            msg.send()
            messages.success(request, "Revisa tu correo para restablecer la contrasena.")
        except Exception as exc:
            messages.error(request, f"No se pudo enviar el correo: {exc}")
        return redirect("login")

    return render(request, "auth/password_reset_request.html")


def confirm_reset_view(request):
    session_token = request.session.get("reset_token")
    session_correo = request.session.get("reset_correo")
    session_created_at = request.session.get("reset_created_at")
    token = request.GET.get("token")
    correo = request.GET.get("correo")

    def _clear_token(sess):
        sess.pop("reset_token", None)
        sess.pop("reset_correo", None)
        sess.pop("reset_created_at", None)

    if not session_token or not session_correo or session_token != token or session_correo != correo:
        messages.error(request, "Enlace invalido o expirado.")
        return redirect("login")

    if session_created_at:
        try:
            created_dt = timezone.datetime.fromisoformat(session_created_at)
            if timezone.is_naive(created_dt):
                created_dt = timezone.make_aware(created_dt, timezone.get_default_timezone())
            if (timezone.now() - created_dt).total_seconds() > 900:
                _clear_token(request.session)
                messages.error(request, "El enlace expiro. Solicita uno nuevo.")
                return redirect("login")
        except Exception:
            _clear_token(request.session)
            messages.error(request, "El enlace expiro. Solicita uno nuevo.")
            return redirect("login")

    if request.method == "POST":
        password = request.POST.get("password", "")
        password2 = request.POST.get("password2", "")
        if not password or password != password2:
            messages.error(request, "Las contrasenas no coinciden.")
            return render(request, "auth/password_reset_confirm.html")
        try:
            usuario = Usuario.objects.get(correo=correo, activo=True)
            UsuarioCredencial.objects.update_or_create(
                usuario=usuario,
                defaults={
                    "password_hash": make_password(password).encode(),
                    "algoritmo_hash": "pbkdf2_sha256",
                    "fecha_cambio": timezone.now(),
                    "requiere_cambio": False,
                    "intentos_fallidos": 0,
                    "bloqueado_hasta": None,
                    "ultimo_login": None,
                },
            )
            messages.success(request, "Contrasena restablecida. Inicie sesion.")
            _clear_token(request.session)
            return redirect("login")
        except Exception as exc:
            messages.error(request, f"No se pudo restablecer la contrasena: {exc}")
            return render(request, "auth/password_reset_confirm.html")

    return render(request, "auth/password_reset_confirm.html")


# -------------------------------
# Verificacion de correo
# -------------------------------

TOKEN_EXP_HOURS = 24
RESEND_LIMIT_PER_HOUR = 3


def _require_auth(request):
    uid = request.session.get("usuario_id")
    if not uid:
        return None
    try:
        return Usuario.objects.get(pk=uid, activo=True)
    except Usuario.DoesNotExist:
        return None


def _hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def _create_token(usuario, request, is_resend=False):
    now = timezone.now()
    if is_resend:
        hace_una_hora = now - timedelta(hours=1)
        recientes = EmailVerificationToken.objects.filter(usuario=usuario, created_at__gte=hace_una_hora).count()
        if recientes >= RESEND_LIMIT_PER_HOUR:
            raise ValueError("Has superado el maximo de reenvios por hora.")
    # invalidar tokens vigentes
    EmailVerificationToken.objects.filter(
        usuario=usuario, used_at__isnull=True, expires_at__gt=now
    ).update(used_at=now)

    raw_token = secrets.token_urlsafe(32)
    prefix = raw_token[:12]
    digest = _hash_token(raw_token)
    expires = now + timedelta(hours=TOKEN_EXP_HOURS)

    EmailVerificationToken.objects.create(
        usuario=usuario,
        token_hash=digest,
        token_prefix=prefix,
        created_at=now,
        expires_at=expires,
        used_at=None,
        ip=request.META.get("REMOTE_ADDR", ""),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
        resend_count=0 if not is_resend else 1,
        last_resend_at=now if is_resend else None,
    )
    return raw_token


def verify_request_view(request):
    usuario = _require_auth(request)
    if not usuario:
        return redirect("login")
    if usuario.correo_verificado:
        messages.info(request, "Tu correo ya esta verificado.")
        return redirect("home")

    if request.method == "POST":
        try:
            raw_token = _create_token(usuario, request, is_resend=False)
            verification_url = request.build_absolute_uri(f"/seguridad/verificar-correo/{raw_token}/")
            send_verification_email(usuario.correo, verification_url, {"usuario": usuario})
            messages.success(request, "Te enviamos un correo de verificacion (24h).")
        except Exception as exc:
            messages.error(request, f"No se pudo generar el token: {exc}")
        return redirect("verify_request")

    return render(request, "seguridad/verify_request.html", {"usuario": usuario})


def resend_verification_view(request):
    usuario = _require_auth(request)
    if not usuario:
        return redirect("login")
    if usuario.correo_verificado:
        messages.info(request, "Tu correo ya esta verificado.")
        return redirect("home")

    if request.method == "POST":
        try:
            raw_token = _create_token(usuario, request, is_resend=True)
            verification_url = request.build_absolute_uri(f"/seguridad/verificar-correo/{raw_token}/")
            send_verification_email(usuario.correo, verification_url, {"usuario": usuario})
            messages.success(request, "Reenvio enviado. Revisa tu correo.")
        except Exception as exc:
            messages.error(request, f"No se pudo reenviar: {exc}")
        return redirect("verify_request")

    return redirect("verify_request")


def verify_token_view(request, token: str):
    prefix = token[:12]
    now = timezone.now()
    try:
        evt = EmailVerificationToken.objects.select_related("usuario").get(token_prefix=prefix)
    except EmailVerificationToken.DoesNotExist:
        return render(request, "seguridad/verify_result.html", {"status": "invalid"})

    if evt.used_at:
        return render(request, "seguridad/verify_result.html", {"status": "used"})
    if evt.expires_at < now:
        return render(request, "seguridad/verify_result.html", {"status": "expired"})
    if not hmac.compare_digest(evt.token_hash, _hash_token(token)):
        return render(request, "seguridad/verify_result.html", {"status": "invalid"})

    usuario = evt.usuario
    if not usuario.activo:
        return render(request, "seguridad/verify_result.html", {"status": "inactive"})

    with transaction.atomic():
        usuario.correo_verificado = True
        usuario.save(update_fields=["correo_verificado"])
        evt.used_at = now
        evt.ip = request.META.get("REMOTE_ADDR", "")
        evt.user_agent = request.META.get("HTTP_USER_AGENT", "")[:300]
        evt.save(update_fields=["used_at", "ip", "user_agent"])

    return render(request, "seguridad/verify_result.html", {"status": "ok"})
