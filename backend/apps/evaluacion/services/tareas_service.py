from django.db import transaction
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.core.models import EstadoTareaEvidencia
from apps.evaluacion.models import TareaEvidencia


class TareaEvidenciaWorkflowError(Exception):
    pass


def _resolve_task_state(*descriptions: str):
    for description in descriptions:
        estado = EstadoTareaEvidencia.objects.filter(
            activo=True,
            descripcion__iexact=description,
        ).first()
        if estado is not None:
            return estado
    return None


@transaction.atomic
def registrar_tarea_evidencia(
    *,
    ciclo,
    indicador,
    elemento_fundamental,
    usuario_responsable,
    estado,
    fecha_limite=None,
    prioridad=None,
    observacion=None,
    actor=None,
    request=None,
):
    if actor is None:
        raise TareaEvidenciaWorkflowError("No fue posible identificar al usuario que asigna la tarea.")
    if elemento_fundamental.indicador_id != indicador.pk:
        raise TareaEvidenciaWorkflowError("El elemento no pertenece al indicador seleccionado.")

    matching_tasks = list(
        TareaEvidencia.objects.filter(
            ciclo=ciclo,
            indicador=indicador,
            elemento_fundamental=elemento_fundamental,
            activo=True,
        ).order_by("-fecha_asignacion", "-id_tarea_evidencia")
    )
    tarea = next(
        (
            item
            for item in matching_tasks
            if item.usuario_responsable_id == getattr(usuario_responsable, "pk", None)
        ),
        None,
    )
    if tarea is None and matching_tasks:
        tarea = matching_tasks[0]
    duplicate_tasks = [item for item in matching_tasks if tarea is not None and item.pk != tarea.pk]

    created = tarea is None
    previous_payload = None
    reassigned = False

    if created:
        tarea = TareaEvidencia.objects.create(
            ciclo=ciclo,
            indicador=indicador,
            elemento_fundamental=elemento_fundamental,
            usuario_responsable=usuario_responsable,
            estado=estado,
            fecha_asignacion=timezone.now(),
            fecha_limite=fecha_limite,
            fecha_cierre=None,
            prioridad=prioridad or None,
            observacion=observacion,
            resultado_tarea=None,
            asignado_por=actor,
            activo=True,
        )
    else:
        previous_payload = {
            "responsable_id": tarea.usuario_responsable_id,
            "estado": getattr(getattr(tarea, "estado", None), "descripcion", None),
            "fecha_asignacion": tarea.fecha_asignacion.isoformat() if tarea.fecha_asignacion else None,
            "fecha_limite": tarea.fecha_limite.isoformat() if tarea.fecha_limite else None,
            "prioridad": tarea.prioridad,
            "observacion": tarea.observacion,
            "fecha_cierre": tarea.fecha_cierre.isoformat() if tarea.fecha_cierre else None,
        }
        reassigned = tarea.usuario_responsable_id != getattr(usuario_responsable, "pk", None)
        tarea.usuario_responsable = usuario_responsable
        tarea.estado = estado
        tarea.fecha_limite = fecha_limite
        tarea.fecha_cierre = None
        tarea.prioridad = prioridad or None
        tarea.observacion = observacion
        tarea.resultado_tarea = None
        tarea.asignado_por = actor
        update_fields = [
            "usuario_responsable",
            "estado",
            "fecha_limite",
            "fecha_cierre",
            "prioridad",
            "observacion",
            "resultado_tarea",
            "asignado_por",
        ]
        if reassigned:
            tarea.fecha_asignacion = timezone.now()
            update_fields.append("fecha_asignacion")
        tarea.save(update_fields=update_fields)

    deactivated_duplicate_ids = []
    for duplicate in duplicate_tasks:
        duplicate.activo = False
        duplicate.save(update_fields=["activo"])
        deactivated_duplicate_ids.append(duplicate.pk)

    registrar_evento(
        accion=(
            "CREAR_TAREA_EVIDENCIA"
            if created
            else "REASIGNAR_TAREA_EVIDENCIA"
            if reassigned
            else "ACTUALIZAR_TAREA_EVIDENCIA"
        ),
        descripcion=(
            f"Se registro la tarea de evidencia {tarea.pk} "
            f"para el elemento {elemento_fundamental.codigo_elemento}."
            if created
            else f"Se actualizo la tarea de evidencia {tarea.pk} "
            f"para el elemento {elemento_fundamental.codigo_elemento}."
            if not reassigned
            else f"Se reasigno la tarea de evidencia {tarea.pk} "
            f"para el elemento {elemento_fundamental.codigo_elemento}."
        ),
        usuario=actor,
        tipo_evento="EVALUACION",
        tabla_afectada="tarea_evidencia",
        id_registro=tarea.pk,
        valores_anteriores=previous_payload,
        valores_nuevos={
            "tarea_id": tarea.pk,
            "ciclo_id": ciclo.pk,
            "indicador_id": indicador.pk,
            "elemento_id": elemento_fundamental.pk,
            "responsable_id": usuario_responsable.pk,
            "estado": estado.descripcion,
            "fecha_limite": fecha_limite.isoformat() if fecha_limite else None,
            "prioridad": prioridad or None,
            "observacion": observacion,
            "reasignada": reassigned,
            "duplicados_desactivados": deactivated_duplicate_ids,
        },
        criticidad="MEDIA",
        request=request,
    )
    return {"tarea": tarea, "created": created}


@transaction.atomic
def registrar_tareas_evidencia_lote(
    *,
    ciclo,
    elementos_fundamentales,
    usuario_responsable,
    estado,
    fecha_limite=None,
    prioridad=None,
    observacion=None,
    actor=None,
    request=None,
):
    if actor is None:
        raise TareaEvidenciaWorkflowError("No fue posible identificar al usuario que asigna la tarea.")

    elementos = list(elementos_fundamentales or [])
    if not elementos:
        raise TareaEvidenciaWorkflowError(
            "Debes seleccionar al menos un elemento fundamental para la asignacion parcial."
        )

    unique_elements = []
    seen_ids = set()
    for elemento in elementos:
        elemento_id = getattr(elemento, "pk", None)
        if elemento_id is None or elemento_id in seen_ids:
            continue
        seen_ids.add(elemento_id)
        unique_elements.append(elemento)

    if not unique_elements:
        raise TareaEvidenciaWorkflowError(
            "No fue posible identificar elementos validos para la asignacion parcial."
        )

    processed = []
    created_count = 0
    updated_count = 0

    for elemento in unique_elements:
        result = registrar_tarea_evidencia(
            ciclo=ciclo,
            indicador=elemento.indicador,
            elemento_fundamental=elemento,
            usuario_responsable=usuario_responsable,
            estado=estado,
            fecha_limite=fecha_limite,
            prioridad=prioridad,
            observacion=observacion,
            actor=actor,
            request=request,
        )
        processed.append(result["tarea"])
        if result["created"]:
            created_count += 1
        else:
            updated_count += 1

    return {
        "tareas": processed,
        "created": created_count,
        "updated": updated_count,
        "total": len(processed),
    }


@transaction.atomic
def cerrar_tarea_evidencia(*, tarea, resultado_tarea: str, actor=None, request=None):
    if actor is None:
        raise TareaEvidenciaWorkflowError("No fue posible identificar al usuario que cierra la tarea.")

    resultado = " ".join((resultado_tarea or "").strip().split())
    if not resultado:
        raise TareaEvidenciaWorkflowError("Debes registrar el resultado de cierre.")

    estado_cierre = _resolve_task_state("CERRADA", "COMPLETADA", "FINALIZADA")
    previous_payload = {
        "estado": getattr(getattr(tarea, "estado", None), "descripcion", None),
        "fecha_cierre": tarea.fecha_cierre.isoformat() if tarea.fecha_cierre else None,
        "resultado_tarea": tarea.resultado_tarea,
    }

    tarea.resultado_tarea = resultado
    tarea.fecha_cierre = timezone.now()
    update_fields = ["resultado_tarea", "fecha_cierre"]
    if estado_cierre is not None:
        tarea.estado = estado_cierre
        update_fields.append("estado")
    tarea.save(update_fields=update_fields)

    registrar_evento(
        accion="CERRAR_TAREA_EVIDENCIA",
        descripcion=f"Se cerro la tarea de evidencia {tarea.pk}.",
        usuario=actor,
        tipo_evento="EVALUACION",
        tabla_afectada="tarea_evidencia",
        id_registro=tarea.pk,
        valores_anteriores=previous_payload,
        valores_nuevos={
            "estado": getattr(getattr(tarea, "estado", None), "descripcion", None),
            "fecha_cierre": tarea.fecha_cierre.isoformat() if tarea.fecha_cierre else None,
            "resultado_tarea": tarea.resultado_tarea,
        },
        criticidad="MEDIA",
        request=request,
    )
    return tarea
