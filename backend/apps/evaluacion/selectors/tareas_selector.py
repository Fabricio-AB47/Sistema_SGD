from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.core.models import EstadoTareaEvidencia
from apps.evaluacion.models import TareaEvidencia
from apps.usuarios.models import UsuarioAreaCargo


def _task_responsable_assignments_prefetch():
    return Prefetch(
        "usuario_responsable__areas_cargos",
        queryset=UsuarioAreaCargo.objects.select_related("area", "cargo")
        .filter(activo=True, area__activo=True, cargo__activo=True)
        .order_by("cargo__nivel_jerarquico", "area__nombre_area", "cargo__nombre_cargo"),
        to_attr="task_area_assignments",
    )


def get_tareas_evidencia_queryset(
    *,
    q: str = "",
    estado_id=None,
    ciclo_id=None,
    responsable_id=None,
    responsable_ids=None,
    area_id=None,
    assigned_by_id=None,
    order_by_hierarchy=False,
):
    queryset = (
        TareaEvidencia.objects.select_related(
            "ciclo",
            "indicador__subcriterio__criterio",
            "elemento_fundamental",
            "usuario_responsable",
            "estado",
            "asignado_por",
        )
        .prefetch_related(_task_responsable_assignments_prefetch())
        .filter(activo=True)
    )
    if order_by_hierarchy:
        queryset = queryset.order_by(
            "indicador__subcriterio__criterio__codigo_criterio",
            "indicador__subcriterio__codigo_subcriterio",
            "indicador__codigo_indicador",
            "elemento_fundamental__codigo_elemento",
            "-fecha_asignacion",
            "-id_tarea_evidencia",
        )
    else:
        queryset = queryset.order_by("-fecha_asignacion", "-id_tarea_evidencia")

    q = (q or "").strip()
    if q:
        queryset = queryset.filter(
            Q(ciclo__nombre__icontains=q)
            | Q(indicador__subcriterio__criterio__codigo_criterio__icontains=q)
            | Q(indicador__subcriterio__criterio__nombre_criterio__icontains=q)
            | Q(indicador__subcriterio__codigo_subcriterio__icontains=q)
            | Q(indicador__subcriterio__nombre_subcriterio__icontains=q)
            | Q(indicador__codigo_indicador__icontains=q)
            | Q(indicador__nombre_indicador__icontains=q)
            | Q(elemento_fundamental__codigo_elemento__icontains=q)
            | Q(elemento_fundamental__nombre_elemento__icontains=q)
            | Q(usuario_responsable__primer_nombre__icontains=q)
            | Q(usuario_responsable__primer_apellido__icontains=q)
            | Q(usuario_responsable__correo__icontains=q)
        )
    if estado_id:
        queryset = queryset.filter(estado_id=estado_id)
    if ciclo_id:
        queryset = queryset.filter(ciclo_id=ciclo_id)
    if responsable_ids is not None and assigned_by_id:
        responsable_ids = [item for item in responsable_ids if item]
        if responsable_ids:
            queryset = queryset.filter(
                Q(usuario_responsable_id__in=responsable_ids)
                | Q(asignado_por_id=assigned_by_id)
            )
        else:
            queryset = queryset.filter(asignado_por_id=assigned_by_id)
    elif responsable_ids is not None:
        responsable_ids = [item for item in responsable_ids if item]
        if responsable_ids:
            queryset = queryset.filter(usuario_responsable_id__in=responsable_ids)
        else:
            queryset = queryset.none()
    elif responsable_id and assigned_by_id:
        queryset = queryset.filter(
            Q(usuario_responsable_id=responsable_id) | Q(asignado_por_id=assigned_by_id)
        )
    elif responsable_id:
        queryset = queryset.filter(usuario_responsable_id=responsable_id)
    elif assigned_by_id:
        queryset = queryset.filter(asignado_por_id=assigned_by_id)
    if area_id:
        queryset = queryset.filter(
            usuario_responsable__areas_cargos__area_id=area_id,
            usuario_responsable__areas_cargos__activo=True,
            usuario_responsable__areas_cargos__area__activo=True,
            usuario_responsable__areas_cargos__cargo__activo=True,
        ).distinct()
    return queryset


def get_tarea_evidencia_detail(tarea_id):
    if not tarea_id:
        return None
    return (
        TareaEvidencia.objects.select_related(
            "ciclo",
            "indicador",
            "elemento_fundamental",
            "usuario_responsable",
            "estado",
            "asignado_por",
        )
        .prefetch_related(_task_responsable_assignments_prefetch())
        .filter(pk=tarea_id, activo=True)
        .first()
    )


def get_tarea_evidencia_metrics(*, responsable_id=None):
    now = timezone.now()
    base = TareaEvidencia.objects.filter(activo=True)
    if responsable_id:
        base = base.filter(usuario_responsable_id=responsable_id)
    total = base.count()
    cerradas = base.filter(fecha_cierre__isnull=False).count()
    vencidas = base.filter(fecha_cierre__isnull=True, fecha_limite__lt=now).count()
    pendientes = max(total - cerradas, 0)
    return {
        "total": total,
        "cerradas": cerradas,
        "pendientes": pendientes,
        "vencidas": vencidas,
        "avance": round((cerradas / total) * 100, 2) if total else 0,
    }


def get_estado_tarea_options():
    return EstadoTareaEvidencia.objects.filter(activo=True).order_by("descripcion")
