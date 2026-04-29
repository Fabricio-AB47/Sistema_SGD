from django.db import transaction
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.acreditacion.models import ElementoFundamental, RolIndicador, RolIndicadorElemento
from apps.core.models import EstadoEvidencia, EstadoTareaEvidencia
from apps.evaluacion.models import TareaEvidencia
from apps.evaluacion.services.notification_service import (
    queue_correction_requested_email,
    queue_director_signoff_email,
    queue_task_reassigned_notification,
)
from apps.evidencias.models import RegistroEvidencia
from apps.usuarios.models import UsuarioRol


class TareaEvidenciaWorkflowError(Exception):
    pass


DIRECTOR_SIGNOFF_TOKEN = "VISTO_BUENO_DIRECTOR"
DIRECTOR_REJECTION_TOKEN = "CORRECCION_DIRECTOR"


def tarea_tiene_visto_bueno_director(tarea) -> bool:
    observacion = (getattr(tarea, "observacion", "") or "").upper()
    return DIRECTOR_SIGNOFF_TOKEN in observacion or "VISTO BUENO DEL DIRECTOR" in observacion


def _resolve_task_state(*descriptions: str):
    for description in descriptions:
        estado = EstadoTareaEvidencia.objects.filter(
            activo=True,
            descripcion__iexact=description,
        ).first()
        if estado is not None:
            return estado
    return None


def _resolve_evidence_state(*descriptions: str):
    for description in descriptions:
        estado = EstadoEvidencia.objects.filter(
            activo=True,
            descripcion__iexact=description,
        ).first()
        if estado is not None:
            return estado
    return None


def _latest_evidence_record_for_task(tarea):
    return (
        RegistroEvidencia.objects.select_related("documento", "estado")
        .filter(
            ciclo=tarea.ciclo,
            indicador=tarea.indicador,
            elemento_fundamental=tarea.elemento_fundamental,
        )
        .order_by("-fecha_registro", "-id_registro")
        .first()
    )


def _active_role_ids_for_user(user_id):
    if not user_id:
        return []
    return list(
        UsuarioRol.objects.filter(
            usuario_id=user_id,
            activo=True,
            rol__activo=True,
        ).values_list("rol_id", flat=True)
    )


def _assigned_elements_for_actor(*, ciclo, actor, include_all=False):
    base_elements = ElementoFundamental.objects.select_related(
        "indicador__subcriterio__criterio"
    ).filter(
        activo=True,
        indicador__activo=True,
        indicador__subcriterio__activo=True,
        indicador__subcriterio__criterio__activo=True,
    )
    if include_all:
        return base_elements

    role_ids = _active_role_ids_for_user(getattr(actor, "pk", None))
    if not role_ids:
        return ElementoFundamental.objects.none()

    role_access = list(
        RolIndicador.objects.filter(
            ciclo=ciclo,
            rol_id__in=role_ids,
            activo=True,
            rol__activo=True,
            indicador__activo=True,
        ).select_related("indicador")
    )
    if not role_access:
        return base_elements

    full_indicator_ids = [
        access.indicador_id
        for access in role_access
        if access.acceso_total
    ]
    partial_access_ids = [
        access.pk
        for access in role_access
        if not access.acceso_total
    ]

    element_ids = set()
    if full_indicator_ids:
        element_ids.update(
            base_elements.filter(indicador_id__in=full_indicator_ids).values_list("pk", flat=True)
        )
    if partial_access_ids:
        element_ids.update(
            RolIndicadorElemento.objects.filter(
                rol_indicador_id__in=partial_access_ids,
                elemento_fundamental__activo=True,
                elemento_fundamental__indicador__activo=True,
            ).values_list("elemento_fundamental_id", flat=True)
        )

    if not element_ids:
        return ElementoFundamental.objects.none()
    return base_elements.filter(pk__in=element_ids)


@transaction.atomic
def materializar_tareas_principales_desde_acceso(
    *,
    ciclo,
    actor,
    include_all=False,
    request=None,
):
    if ciclo is None or actor is None:
        return {"created": 0, "total": 0}

    estado = _resolve_task_state("PENDIENTE", "ASIGNADA", "EN_PROCESO")
    if estado is None:
        raise TareaEvidenciaWorkflowError("No existe un estado activo para materializar tareas.")

    elementos = list(_assigned_elements_for_actor(ciclo=ciclo, actor=actor, include_all=include_all))
    if not elementos:
        return {"created": 0, "total": 0}

    element_ids = [elemento.pk for elemento in elementos]
    existing_element_ids = set(
        TareaEvidencia.objects.filter(
            ciclo=ciclo,
            elemento_fundamental_id__in=element_ids,
            activo=True,
        ).values_list("elemento_fundamental_id", flat=True)
    )

    created_tasks = []
    timestamp = timezone.now()
    for elemento in elementos:
        if elemento.pk in existing_element_ids:
            continue
        created_tasks.append(
            TareaEvidencia.objects.create(
                ciclo=ciclo,
                indicador=elemento.indicador,
                elemento_fundamental=elemento,
                usuario_responsable=actor,
                estado=estado,
                fecha_asignacion=timestamp,
                fecha_limite=None,
                fecha_cierre=None,
                prioridad=None,
                observacion="Tarea habilitada desde la estructura del ciclo aprobado.",
                resultado_tarea=None,
                asignado_por=actor,
                activo=True,
            )
        )

    if created_tasks:
        registrar_evento(
            accion="MATERIALIZAR_TAREAS_PRINCIPAL",
            descripcion=(
                f"Se habilitaron {len(created_tasks)} tarea(s) de evidencia "
                f"para el ciclo {ciclo.nombre}."
            ),
            usuario=actor,
            tipo_evento="EVALUACION",
            tabla_afectada="tarea_evidencia",
            valores_nuevos={
                "ciclo_id": ciclo.pk,
                "tareas": [tarea.pk for tarea in created_tasks],
                "include_all": include_all,
            },
            criticidad="MEDIA",
            request=request,
        )

    return {"created": len(created_tasks), "total": len(elementos)}


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


@transaction.atomic
def redireccionar_tarea_subordinado(
    *,
    tarea,
    nuevo_responsable,
    actor=None,
    comentario=None,
    request=None,
):
    if actor is None:
        raise TareaEvidenciaWorkflowError("No fue posible identificar al director que desglosa la tarea.")

    if tarea.usuario_responsable_id == getattr(nuevo_responsable, "pk", None):
        raise TareaEvidenciaWorkflowError("La tarea ya esta asignada al usuario seleccionado.")

    previous_payload = {
        "responsable_id": tarea.usuario_responsable_id,
        "asignado_por_id": tarea.asignado_por_id,
        "fecha_asignacion": tarea.fecha_asignacion.isoformat() if tarea.fecha_asignacion else None,
        "observacion": tarea.observacion,
    }

    timestamp = timezone.now()
    actor_name = getattr(actor, "nombre_completo", None) or getattr(actor, "correo", "Director")
    note = f"Desglosada por {actor_name} el {timestamp.strftime('%Y-%m-%d %H:%M')}"
    extra_note = " ".join((comentario or "").strip().split())
    if extra_note:
        note = f"{note}. Nota: {extra_note}"

    merged_observacion = "\n".join(
        part for part in [tarea.observacion, note] if part
    )

    tarea.usuario_responsable = nuevo_responsable
    tarea.asignado_por = actor
    tarea.fecha_asignacion = timestamp
    tarea.fecha_cierre = None
    tarea.resultado_tarea = None
    tarea.observacion = merged_observacion
    tarea.save(
        update_fields=[
            "usuario_responsable",
            "asignado_por",
            "fecha_asignacion",
            "fecha_cierre",
            "resultado_tarea",
            "observacion",
        ]
    )

    registrar_evento(
        accion="DESGLOSAR_TAREA_DIRECTOR",
        descripcion=f"El director desgloso la tarea de evidencia {tarea.pk} a un usuario de su rol.",
        usuario=actor,
        tipo_evento="EVALUACION",
        tabla_afectada="tarea_evidencia",
        id_registro=tarea.pk,
        valores_anteriores=previous_payload,
        valores_nuevos={
            "responsable_id": tarea.usuario_responsable_id,
            "asignado_por_id": tarea.asignado_por_id,
            "fecha_asignacion": tarea.fecha_asignacion.isoformat() if tarea.fecha_asignacion else None,
            "observacion": tarea.observacion,
        },
        criticidad="MEDIA",
        request=request,
    )
    queue_task_reassigned_notification(
        tarea=tarea,
        nuevo_responsable=nuevo_responsable,
        actor=actor,
        comentario=comentario,
        request=request,
    )
    return tarea


@transaction.atomic
def aprobar_tarea_visto_bueno_director(*, tarea, actor=None, comentario=None, request=None):
    if actor is None:
        raise TareaEvidenciaWorkflowError("No fue posible identificar al director que aprueba la tarea.")

    if not tarea.fecha_cierre:
        raise TareaEvidenciaWorkflowError(
            "La tarea debe estar cerrada por el usuario asignado antes del visto bueno del director."
        )

    previous_payload = {
        "observacion": tarea.observacion,
        "asignado_por_id": tarea.asignado_por_id,
        "estado": getattr(getattr(tarea, "estado", None), "descripcion", None),
    }
    latest_record = _latest_evidence_record_for_task(tarea)
    if latest_record is None or getattr(latest_record, "documento_id", None) is None:
        raise TareaEvidenciaWorkflowError(
            "No existe un documento de evidencia cargado para registrar el check de subida."
        )

    timestamp = timezone.now()
    actor_name = getattr(actor, "nombre_completo", None) or getattr(actor, "correo", "Director")
    note = (
        f"[{DIRECTOR_SIGNOFF_TOKEN}] Visto bueno del director {actor_name} "
        f"el {timestamp.strftime('%Y-%m-%d %H:%M')}"
    )
    extra_note = " ".join((comentario or "").strip().split())
    if extra_note:
        note = f"{note}. Comentario: {extra_note}"

    tarea.observacion = "\n".join(part for part in [tarea.observacion, note] if part)
    tarea.asignado_por = actor
    update_fields = ["observacion", "asignado_por"]
    estado_revision = _resolve_task_state("REVISADA", "APROBADA", "CERRADA")
    if estado_revision is not None:
        tarea.estado = estado_revision
        update_fields.append("estado")
    tarea.save(update_fields=update_fields)

    estado_evidencia = _resolve_evidence_state("CARGADA", "VALIDADA", "REGISTRADA")
    registros_actualizados = 0
    if estado_evidencia is not None:
        if latest_record.estado_id != estado_evidencia.pk:
            latest_record.estado = estado_evidencia
            latest_record.save(update_fields=["estado"])
            registros_actualizados = 1

    registrar_evento(
        accion="VISTO_BUENO_DIRECTOR_TAREA",
        descripcion=f"Se registro visto bueno del director para la tarea de evidencia {tarea.pk}.",
        usuario=actor,
        tipo_evento="EVALUACION",
        tabla_afectada="tarea_evidencia",
        id_registro=tarea.pk,
        valores_anteriores=previous_payload,
        valores_nuevos={
            "observacion": tarea.observacion,
            "asignado_por_id": tarea.asignado_por_id,
            "estado": getattr(getattr(tarea, "estado", None), "descripcion", None),
            "estado_evidencia_id": getattr(estado_evidencia, "pk", None),
            "registro_evidencia_id": latest_record.pk,
            "documento_id": latest_record.documento_id,
            "registros_actualizados": registros_actualizados,
        },
        criticidad="MEDIA",
        request=request,
    )
    queue_director_signoff_email(
        tarea=tarea,
        registro=latest_record,
        actor=actor,
        comentario=comentario,
        request=request,
    )
    return tarea


@transaction.atomic
def rechazar_tarea_revision_director(*, tarea, actor=None, comentario=None, request=None):
    if actor is None:
        raise TareaEvidenciaWorkflowError("No fue posible identificar al director que revisa la tarea.")

    if not tarea.fecha_cierre:
        raise TareaEvidenciaWorkflowError(
            "La tarea debe estar cerrada por el usuario asignado antes de solicitar correcciones."
        )

    correction_note = " ".join((comentario or "").strip().split())
    if not correction_note:
        raise TareaEvidenciaWorkflowError(
            "Debes registrar el comentario con las correcciones solicitadas."
        )

    latest_record = _latest_evidence_record_for_task(tarea)
    if latest_record is None or getattr(latest_record, "documento_id", None) is None:
        raise TareaEvidenciaWorkflowError(
            "No existe un documento de evidencia cargado para solicitar correcciones."
        )

    previous_payload = {
        "observacion": tarea.observacion,
        "asignado_por_id": tarea.asignado_por_id,
        "estado": getattr(getattr(tarea, "estado", None), "descripcion", None),
        "fecha_cierre": tarea.fecha_cierre.isoformat() if tarea.fecha_cierre else None,
        "resultado_tarea": tarea.resultado_tarea,
        "registro_estado": getattr(getattr(latest_record, "estado", None), "descripcion", None),
        "registro_comentario": latest_record.comentario,
    }

    timestamp = timezone.now()
    actor_name = getattr(actor, "nombre_completo", None) or getattr(actor, "correo", "Director")
    note = (
        f"[{DIRECTOR_REJECTION_TOKEN}] Correcciones solicitadas por {actor_name} "
        f"el {timestamp.strftime('%Y-%m-%d %H:%M')}. Comentario: {correction_note}"
    )

    tarea.observacion = "\n".join(part for part in [tarea.observacion, note] if part)
    tarea.asignado_por = actor
    tarea.fecha_cierre = None
    tarea.resultado_tarea = None
    update_fields = [
        "observacion",
        "asignado_por",
        "fecha_cierre",
        "resultado_tarea",
    ]
    estado_rechazo = _resolve_task_state("RECHAZADA", "PENDIENTE", "EN_PROCESO")
    if estado_rechazo is not None:
        tarea.estado = estado_rechazo
        update_fields.append("estado")
    tarea.save(update_fields=update_fields)

    estado_evidencia = _resolve_evidence_state(
        "DEVUELTA_INTERNA",
        "OBSERVADA",
        "RECHAZADA",
        "BORRADOR",
    )
    registros_actualizados = 0
    latest_record.comentario = correction_note[:500]
    update_record_fields = ["comentario"]
    if estado_evidencia is not None and latest_record.estado_id != estado_evidencia.pk:
        latest_record.estado = estado_evidencia
        update_record_fields.append("estado")
        registros_actualizados = 1
    latest_record.save(update_fields=update_record_fields)

    registrar_evento(
        accion="SOLICITAR_CORRECCION_DIRECTOR_TAREA",
        descripcion=(
            f"Se solicitaron correcciones para la tarea de evidencia {tarea.pk} "
            "y se reabrio la carga documental."
        ),
        usuario=actor,
        tipo_evento="EVALUACION",
        tabla_afectada="tarea_evidencia",
        id_registro=tarea.pk,
        valores_anteriores=previous_payload,
        valores_nuevos={
            "observacion": tarea.observacion,
            "asignado_por_id": tarea.asignado_por_id,
            "estado": getattr(getattr(tarea, "estado", None), "descripcion", None),
            "fecha_cierre": tarea.fecha_cierre.isoformat() if tarea.fecha_cierre else None,
            "resultado_tarea": tarea.resultado_tarea,
            "estado_evidencia_id": getattr(estado_evidencia, "pk", None),
            "registro_evidencia_id": latest_record.pk,
            "documento_id": latest_record.documento_id,
            "comentario_correccion": correction_note,
            "registros_actualizados": registros_actualizados,
        },
        criticidad="MEDIA",
        request=request,
    )
    queue_correction_requested_email(
        tarea=tarea,
        registro=latest_record,
        actor=actor,
        comentario=correction_note,
        request=request,
    )
    return tarea
