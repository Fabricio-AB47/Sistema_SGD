from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.db import connections
from django.db.utils import OperationalError
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.seguridad.views import _send_reset_email
from apps.seguridad.models import (
    Rol,
    TipoIdentificacion,
    TipoUsuario,
    Usuario,
    UsuarioCredencial,
    UsuarioRol,
)
from apps.core.models import (
    Criterio,
    Subcriterio,
    TipoIndicador,
    Indicador,
)


def home(request):
    if not request.session.get("usuario_id"):
        return redirect("login")

    db_conf = settings.DATABASES["default"]
    status = {"ok": False, "message": ""}
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        status["ok"] = True
        status["message"] = "Conexion exitosa a la base de datos."
    except OperationalError as exc:
        status["ok"] = False
        status["message"] = f"Error de conexion: {exc}"

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "create_tipo_usuario":
                descripcion = request.POST.get("descripcion_tp_user", "").strip()
                if not descripcion:
                    messages.error(request, "Ingrese la descripcion del tipo de usuario.")
                    return redirect("home")
                TipoUsuario.objects.get_or_create(
                    descripcion_tp_user=descripcion, defaults={"activo_tp_user": True}
                )
                messages.success(request, "Tipo de usuario guardado.")

            elif action == "assign_role":
                id_user = request.POST.get("id_user")
                id_rol = request.POST.get("id_rol")
                if not id_user or not id_rol:
                    messages.error(request, "Seleccione usuario y rol.")
                    return redirect("home")
                usuario = Usuario.objects.get(id_user=id_user)
                rol = Rol.objects.get(id_rol=id_rol)
                UsuarioRol.objects.get_or_create(
                    usuario=usuario,
                    rol=rol,
                    defaults={"fecha_asignacion": timezone.now(), "asignado_por": None},
                )
                messages.success(request, "Rol asignado al usuario.")
        except Exception as exc:
            messages.error(request, f"Error: {exc}")
        return redirect("home")

    usuarios_qs = Usuario.objects.all().prefetch_related("roles_asignados__rol", "roles_asignados")
    context = {
        "db_status": status,
        "db_info": {
            "engine": db_conf.get("ENGINE"),
            "name": db_conf.get("NAME"),
            "host": db_conf.get("HOST"),
            "port": db_conf.get("PORT"),
            "user": db_conf.get("USER"),
            "driver": db_conf.get("OPTIONS", {}).get("driver"),
        },
        "usuario": request.session.get("usuario_nombre"),
        "tipos_ident": TipoIdentificacion.objects.all(),
        "tipos_usuario": TipoUsuario.objects.filter(activo_tp_user=True),
        "roles": Rol.objects.filter(activo=True),
        "usuarios": usuarios_qs,
        "usuarios_activos": usuarios_qs.filter(activo=True).count(),
        "usuarios_inactivos": usuarios_qs.filter(activo=False).count(),
    }
    return render(request, "admin/home.html", context)


def create_user_view(request):
    if not request.session.get("usuario_id"):
        return redirect("login")

    if request.method == "POST":
        primer_nombre = request.POST.get("primer_nombre", "").strip()
        segundo_nombre = request.POST.get("segundo_nombre", "").strip()
        primer_apellido = request.POST.get("primer_apellido", "").strip()
        segundo_apellido = request.POST.get("segundo_apellido", "").strip()
        identificacion = request.POST.get("identificacion", "").strip()
        correo = request.POST.get("correo", "").strip()
        tipo_ident_id = request.POST.get("id_tipo_identificacion")
        tipo_usuario_id = request.POST.get("id_tipo_usuario")
        password = request.POST.get("password", "")
        role_ids = request.POST.getlist("roles")

        if not all(
            [
                primer_nombre,
                primer_apellido,
                identificacion,
                correo,
                tipo_ident_id,
                tipo_usuario_id,
                password,
            ]
        ):
            messages.error(request, "Complete los campos obligatorios.")
            return redirect("admin_create_user")
        if not role_ids:
            messages.error(request, "Seleccione al menos un rol.")
            return redirect("admin_create_user")

        try:
            usuario, created = Usuario.objects.get_or_create(
                correo=correo,
                defaults={
                    "primer_nombre": primer_nombre,
                    "segundo_nombre": segundo_nombre,
                    "primer_apellido": primer_apellido,
                    "segundo_apellido": segundo_apellido,
                    "identificacion": identificacion,
                    "id_tipo_identificacion": tipo_ident_id,
                    "correo_verificado": False,
                    "activo": True,
                },
            )
            if not created:
                messages.error(request, "El correo ya existe.")
                return redirect("admin_create_user")

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

            role_ids_int = [int(r) for r in role_ids]
            roles_asignar = Rol.objects.filter(id_rol__in=role_ids_int, activo=True)
            for rol in roles_asignar:
                if rol.tipo_usuario_id and str(rol.tipo_usuario_id) != str(tipo_usuario_id):
                    continue
                UsuarioRol.objects.get_or_create(
                    usuario=usuario,
                    rol=rol,
                    defaults={"fecha_asignacion": timezone.now(), "asignado_por": None},
                )

            messages.success(request, "Usuario creado con credencial y roles.")
            return redirect("home")
        except Exception as exc:
            messages.error(request, f"Error creando usuario: {exc}")
            return redirect("admin_create_user")

    context = {
        "tipos_ident": TipoIdentificacion.objects.all(),
        "tipos_usuario": TipoUsuario.objects.filter(activo_tp_user=True),
        "roles": Rol.objects.filter(activo=True),
        "usuarios": Usuario.objects.filter(activo=True),
        "usuario": request.session.get("usuario_nombre"),
    }
    return render(request, "admin/user_create.html", context)


def update_credential_view(request, user_id):
    """
    Actualiza la credencial (intentos, bloqueo, requiere cambio) de un usuario.
    Tras guardar, redirige a crear usuario con mensaje de exito o error.
    """
    if not request.session.get("usuario_id"):
        return redirect("login")

    if request.method != "POST":
        messages.error(request, "Metodo no permitido.")
        return redirect("admin_create_user")

    try:
        usuario = Usuario.objects.get(pk=user_id)
    except Usuario.DoesNotExist:
        messages.error(request, "Usuario no encontrado.")
        return redirect("admin_create_user")

    intentos = request.POST.get("intentos_fallidos") or "0"
    bloqueado_hasta_raw = request.POST.get("bloqueado_hasta", "")
    requiere_cambio = bool(request.POST.get("requiere_cambio"))

    bloqueado_dt = None
    if bloqueado_hasta_raw:
        try:
            bloqueado_dt = timezone.make_aware(
                timezone.datetime.fromisoformat(bloqueado_hasta_raw)
            )
        except Exception:
            bloqueado_dt = None

    try:
        cred, _ = UsuarioCredencial.objects.update_or_create(
            usuario=usuario,
            defaults={
                "intentos_fallidos": int(intentos or 0),
                "bloqueado_hasta": bloqueado_dt,
                "requiere_cambio": requiere_cambio,
            },
        )
        # Si requiere cambio, opcionalmente reiniciar ultimo_login
        if requiere_cambio:
            cred.ultimo_login = None
            cred.save(update_fields=["ultimo_login"])
            # Enviar enlace de restablecimiento inmediato
            try:
                _send_reset_email(usuario, request)
                messages.success(
                    request,
                    "Credencial actualizada. Se ha enviado enlace de cambio de contrasena y no podra iniciar sesion hasta cambiarla.",
                )
            except Exception as exc:
                messages.warning(request, f"Credencial actualizada pero no se pudo enviar el correo: {exc}")
        else:
            messages.success(request, "Credencial actualizada correctamente.")
    except Exception as exc:
        messages.error(request, f"No se pudo actualizar la credencial: {exc}")

    return redirect("admin_create_user")


def user_role_view(request):
    if not request.session.get("usuario_id"):
        return redirect("login")

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "create_tipo_usuario":
                descripcion = request.POST.get("descripcion_tp_user", "").strip()
                if not descripcion:
                    messages.error(request, "Ingrese la descripcion del tipo de usuario.")
                    return redirect("admin_user_role")
                TipoUsuario.objects.get_or_create(
                    descripcion_tp_user=descripcion, defaults={"activo_tp_user": True}
                )
                messages.success(request, "Tipo de usuario guardado.")

            elif action == "create_rol":
                nombre = request.POST.get("nombre_rol", "").strip()
                descripcion = request.POST.get("descripcion", "").strip()
                tipo_id = request.POST.get("id_tp_user")
                if not all([nombre, descripcion, tipo_id]):
                    messages.error(request, "Complete nombre, descripcion y tipo de usuario.")
                    return redirect("admin_user_role")
                Rol.objects.create(
                    nombre_rol=nombre,
                    descripcion=descripcion,
                    activo=True,
                    tipo_usuario_id=tipo_id,
                )
                messages.success(request, "Rol creado.")

            elif action == "assign_role":
                id_user = request.POST.get("id_user")
                id_rol = request.POST.get("id_rol")
                asignado_por = request.session.get("usuario_id")
                if not id_user or not id_rol:
                    messages.error(request, "Seleccione usuario y rol.")
                    return redirect("admin_user_role")
                usuario = Usuario.objects.get(id_user=id_user)
                rol = Rol.objects.get(id_rol=id_rol)
                UsuarioRol.objects.get_or_create(
                    usuario=usuario,
                    rol=rol,
                    defaults={
                        "fecha_asignacion": timezone.now(),
                        "asignado_por": asignado_por,
                    },
                )
                messages.success(request, "Rol asignado al usuario.")
        except Exception as exc:
            messages.error(request, f"Error: {exc}")
        return redirect("admin_user_role")

    context = {
        "tipos_usuario": TipoUsuario.objects.filter(activo_tp_user=True),
        "roles": Rol.objects.filter(activo=True),
        "usuarios": Usuario.objects.filter(activo=True),
        "usuario_roles": UsuarioRol.objects.select_related("usuario", "rol"),
        "usuario": request.session.get("usuario_nombre"),
    }
    return render(request, "admin/user_role.html", context)


def criterio_view(request):
    if not request.session.get("usuario_id"):
        return redirect("login")

    if request.method == "POST":
        nombre = request.POST.get("nombre_criterio", "").strip()
        if not nombre:
            messages.error(request, "Ingrese el nombre del criterio.")
            return redirect("admin_criterio")
        try:
            Criterio.objects.create(nombre_criterio=nombre)
            messages.success(request, "Criterio creado.")
        except Exception as exc:
            messages.error(request, f"Error creando criterio: {exc}")
        return redirect("admin_criterio")

    context = {
        "criterios": Criterio.objects.all().order_by("id_criterio"),
        "usuario": request.session.get("usuario_nombre"),
    }
    return render(request, "admin/criterio.html", context)


def subcriterio_view(request):
    if not request.session.get("usuario_id"):
        return redirect("login")

    if request.method == "POST":
        nombre = request.POST.get("nombre_subcriterio", "").strip()
        criterio_id = request.POST.get("id_criterio")
        if not nombre or not criterio_id:
            messages.error(request, "Seleccione criterio e ingrese el subcriterio.")
            return redirect("admin_subcriterio")
        try:
            Subcriterio.objects.create(
                nombre_subcriterio=nombre,
                criterio_id=criterio_id,
            )
            messages.success(request, "Subcriterio creado.")
        except Exception as exc:
            messages.error(request, f"Error creando subcriterio: {exc}")
        return redirect("admin_subcriterio")

    context = {
        "criterios": Criterio.objects.all().order_by("nombre_criterio"),
        "subcriterios": Subcriterio.objects.select_related("criterio").all().order_by("id_subcriterio"),
        "usuario": request.session.get("usuario_nombre"),
    }
    return render(request, "admin/subcriterio.html", context)


def tipo_indicador_view(request):
    if not request.session.get("usuario_id"):
        return redirect("login")

    if request.method == "POST":
        desc = request.POST.get("descripcion_tipo_ind", "").strip()
        if not desc:
            messages.error(request, "Ingrese la descripcion del tipo de indicador.")
            return redirect("admin_tipo_indicador")
        try:
            TipoIndicador.objects.create(descripcion_tipo_ind=desc)
            messages.success(request, "Tipo de indicador creado.")
        except Exception as exc:
            messages.error(request, f"Error creando tipo de indicador: {exc}")
        return redirect("admin_tipo_indicador")

    context = {
        "tipos": TipoIndicador.objects.all().order_by("id_tipo_ind"),
        "usuario": request.session.get("usuario_nombre"),
    }
    return render(request, "admin/tipo_indicador.html", context)


def indicador_view(request):
    if not request.session.get("usuario_id"):
        return redirect("login")

    if request.method == "POST":
        nombre = request.POST.get("nombre_indicador", "").strip()
        subcriterio_id = request.POST.get("id_subcriterio")
        tipo_ind_id = request.POST.get("id_tipo_ind")
        if not all([nombre, subcriterio_id, tipo_ind_id]):
            messages.error(request, "Complete nombre, subcriterio y tipo de indicador.")
            return redirect("admin_indicador")
        try:
            Indicador.objects.create(
                nombre_indicador=nombre,
                subcriterio_id=subcriterio_id,
                tipo_ind_id=tipo_ind_id,
            )
            messages.success(request, "Indicador creado.")
        except Exception as exc:
            messages.error(request, f"Error creando indicador: {exc}")
        return redirect("admin_indicador")

    context = {
        "subcriterios": Subcriterio.objects.select_related("criterio").all().order_by("id_subcriterio"),
        "tipos_ind": TipoIndicador.objects.all().order_by("id_tipo_ind"),
        "indicadores": Indicador.objects.select_related("subcriterio", "tipo_ind").all().order_by("id_indicador"),
        "usuario": request.session.get("usuario_nombre"),
    }
    return render(request, "admin/indicador.html", context)
