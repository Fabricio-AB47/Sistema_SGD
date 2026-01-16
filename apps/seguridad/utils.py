from django.utils import timezone

from apps.core.models import Auditoria


def audit_log(
    usuario_id,
    accion,
    tabla,
    id_registro=None,
    descripcion="",
    valores_nuevos=None,
    valores_anteriores=None,
    request=None,
):
    """
    Registra una auditoría simple en la tabla auditoria.
    - usuario_id: id_user del actor
    - accion: texto corto (CREATE, UPDATE, DELETE, LOGIN, LOGOUT, VERIFY_MAIL, etc.)
    - tabla: nombre lógico de la tabla o entidad
    - id_registro: PK afectado
    - descripcion: detalle breve
    - valores_nuevos / valores_anteriores: dict/obj convertible a str (truncado a 500)
    - request: opcional, para tomar ip y user_agent
    """
    try:
        Auditoria.objects.create(
            usuario_id=usuario_id,
            accion=accion,
            tabla_afectada=tabla,
            id_registro=id_registro,
            descripcion=str(descripcion)[:500],
            valores_nuevos=str(valores_nuevos)[:500] if valores_nuevos else None,
            valores_anteriores=str(valores_anteriores)[:500] if valores_anteriores else None,
            fecha_evento=timezone.now(),
            ip=(request.META.get("REMOTE_ADDR") if request else None),
            user_agent=(request.META.get("HTTP_USER_AGENT") if request else None),
        )
    except Exception:
        # No romper el flujo principal si la auditoría falla
        pass
