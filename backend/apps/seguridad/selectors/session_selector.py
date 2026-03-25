from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone

from apps.seguridad.models import HistorialLogin, UserSession


SESSION_ONLY_FIELDS = (
    "id_sesion",
    "usuario_id",
    "token_sesion_hash",
    "fecha_inicio",
    "fecha_expiracion",
    "fecha_renovacion",
    "activa",
    "ip",
    "user_agent",
    "ultima_actividad",
    "usuario__id_user",
    "usuario__primer_nombre",
    "usuario__segundo_nombre",
    "usuario__primer_apellido",
    "usuario__segundo_apellido",
    "usuario__correo",
)


def get_session_dashboard_data(
    *,
    filters,
    current_user=None,
    current_session_hash=None,
    current_session_id=None,
    page_number=1,
    per_page=12,
):
    now = timezone.now()
    queryset = (
        UserSession.objects.select_related("usuario")
        .only(*SESSION_ONLY_FIELDS)
        .order_by("-fecha_inicio", "-id_sesion")
    )

    search = filters.get("q") or ""
    estado = filters.get("estado") or ""
    alcance = filters.get("alcance") or "all"

    if search:
        queryset = queryset.filter(
            Q(usuario__primer_nombre__icontains=search)
            | Q(usuario__primer_apellido__icontains=search)
            | Q(usuario__correo__icontains=search)
            | Q(ip__icontains=search)
            | Q(token_sesion_hash__icontains=search)
            | Q(user_agent__icontains=search)
        )

    # Estas ramas aprovechan el índice por usuario/activa/fecha_expiracion.
    if alcance == "mine" and current_user:
        queryset = queryset.filter(usuario=current_user)

    if estado == "active":
        queryset = queryset.filter(activa=True, fecha_expiracion__gt=now)
    elif estado == "expired":
        queryset = queryset.filter(fecha_expiracion__lte=now)
    elif estado == "inactive":
        queryset = queryset.filter(activa=False)

    paginator = Paginator(queryset, per_page)
    sessions_page = paginator.get_page(page_number)

    current_count = 0
    for session in sessions_page.object_list:
        session.es_actual = bool(
            (current_session_id and session.id_sesion == current_session_id)
            or (current_session_hash and session.token_sesion_hash == current_session_hash)
        )
        session.esta_expirada = bool(session.fecha_expiracion and session.fecha_expiracion <= now)
        if session.es_actual:
            current_count += 1

    metrics = UserSession.objects.aggregate(
        total=Count("id_sesion"),
        activas=Count(
            "id_sesion",
            filter=Q(activa=True, fecha_expiracion__gt=now),
        ),
        expiradas=Count(
            "id_sesion",
            filter=Q(fecha_expiracion__lte=now),
        ),
        usuarios=Count("usuario", distinct=True),
    )
    metrics["mias"] = (
        UserSession.objects.filter(
            usuario=current_user,
            activa=True,
            fecha_expiracion__gt=now,
        ).count()
        if current_user
        else 0
    )
    metrics["actuales_en_pagina"] = current_count

    return {
        "metrics": metrics,
        "sessions_page": sessions_page,
        "filters": {
            "q": search,
            "estado": estado,
            "alcance": alcance,
        },
    }


def get_recent_login_attempts(limit=12):
    return (
        HistorialLogin.objects.select_related("usuario")
        .only(
            "id_login",
            "usuario_id",
            "correo_intento",
            "fecha_intento",
            "exito",
            "motivo",
            "ip",
            "user_agent",
            "usuario__id_user",
            "usuario__primer_nombre",
            "usuario__segundo_nombre",
            "usuario__primer_apellido",
            "usuario__segundo_apellido",
        )
        .order_by("-fecha_intento")[:limit]
    )
