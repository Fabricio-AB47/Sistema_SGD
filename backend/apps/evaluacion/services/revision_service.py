from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.core.models import EstadoEvidencia
from apps.evaluacion.models import (
    Evaluacion,
    ObservacionEvaluacion,
    RevisionInternaEvidencia,
    TareaEvidencia,
)
from apps.evaluacion.services.notification_service import queue_evaluator_release_notification
from apps.evaluacion.services.tareas_service import tarea_tiene_visto_bueno_director
from apps.usuarios.models import UsuarioAreaCargo, UsuarioRol


class EvaluacionWorkflowError(Exception):
    pass


def _resolve_evidence_status(description: str):
    return EstadoEvidencia.objects.filter(
        activo=True,
        descripcion__iexact=description,
    ).first()


def _resolve_first_available_evidence_status(*descriptions: str):
    for description in descriptions:
        estado = _resolve_evidence_status(description)
        if estado is not None:
            return estado
    return None


def _sync_registro_estado(*, registro, evaluation_state_description: str):
    normalized = (evaluation_state_description or "").strip().upper()
    status_map = {
        "EN_ANALISIS": "EN_REVISION_EVALUADOR",
        "APROBADA": "APROBADA",
        "OBSERVADA": "OBSERVADA",
        "RECHAZADA": "RECHAZADA",
    }
    target = status_map.get(normalized)
    if not target:
        return
    estado = _resolve_evidence_status(target)
    if estado is None:
        return
    registro.estado = estado
    if normalized == "EN_ANALISIS":
        registro.fecha_envio_revision = registro.fecha_envio_revision or timezone.now()
    registro.save(update_fields=["estado", "fecha_envio_revision"])


def _sync_registro_estado_directo(*, registro, estado_objetivo, set_release_metadata: bool = False, actor=None):
    if estado_objetivo is None:
        return False

    registro.estado = estado_objetivo
    update_fields = ["estado"]
    if set_release_metadata:
        if registro.fecha_envio_revision is None:
            registro.fecha_envio_revision = timezone.now()
            update_fields.append("fecha_envio_revision")
        if actor is not None and getattr(registro, "enviado_revision_por_id", None) is None:
            registro.enviado_revision_por = actor
            update_fields.append("enviado_revision_por")

    registro.save(update_fields=update_fields)
    return True


def _is_first_rank_approver_for_task(tarea) -> bool:
    approver_id = getattr(tarea, "asignado_por_id", None)
    if not approver_id:
        return False
    if UsuarioRol.objects.filter(
        usuario_id=approver_id,
        activo=True,
        rol__activo=True,
        rol__nombre_rol__iexact="Administrador",
    ).exists():
        return True

    responsible_area_ids = list(
        UsuarioAreaCargo.objects.filter(
            usuario_id=tarea.usuario_responsable_id,
            activo=True,
            area__activo=True,
            cargo__activo=True,
        ).values_list("area_id", flat=True)
    )
    if not responsible_area_ids:
        return False

    return UsuarioAreaCargo.objects.filter(
        usuario_id=approver_id,
        activo=True,
        area_id__in=responsible_area_ids,
        area__activo=True,
        cargo__activo=True,
        cargo__nivel_jerarquico=1,
        cargo__aprueba_interno=True,
    ).exists()


def obtener_aprobacion_principal_registro(registro):
    if registro is None:
        return {
            "approved": False,
            "status": "sin_registro",
            "message": "No fue posible identificar la evidencia.",
            "task": None,
        }

    tareas = list(
        TareaEvidencia.objects.select_related(
            "usuario_responsable",
            "asignado_por",
            "estado",
        )
        .filter(
            ciclo_id=registro.ciclo_id,
            indicador_id=registro.indicador_id,
            elemento_fundamental_id=registro.elemento_fundamental_id,
            activo=True,
        )
        .order_by("-fecha_asignacion", "-id_tarea_evidencia")
    )
    if not tareas:
        return {
            "approved": False,
            "status": "sin_tarea",
            "message": (
                "Primero debe existir una tarea operativa para esta evidencia y su responsable debe cerrarla."
            ),
            "task": None,
        }

    closed_without_signoff = None
    pending_task = None
    invalid_approver_task = None
    for tarea in tareas:
        if not tarea.fecha_cierre:
            pending_task = pending_task or tarea
            continue
        if not tarea_tiene_visto_bueno_director(tarea):
            closed_without_signoff = closed_without_signoff or tarea
            continue
        if not _is_first_rank_approver_for_task(tarea):
            invalid_approver_task = invalid_approver_task or tarea
            continue

        return {
            "approved": True,
            "status": "aprobada",
            "message": "La evidencia cuenta con aprobacion de la cabeza principal.",
            "task": tarea,
        }

    if closed_without_signoff is not None:
        return {
            "approved": False,
            "status": "pendiente_visto_bueno",
            "message": (
                "La tarea ya fue cerrada por el responsable, pero falta el check de revision de la cabeza de rango 1."
            ),
            "task": closed_without_signoff,
        }
    if invalid_approver_task is not None:
        return {
            "approved": False,
            "status": "aprobador_no_principal",
            "message": (
                "El check registrado no corresponde a una cabeza de rango 1 del area responsable."
            ),
            "task": invalid_approver_task,
        }

    return {
        "approved": False,
        "status": "pendiente_cierre",
        "message": "La tarea operativa debe cerrarse antes del check de revision de la cabeza de rango 1.",
        "task": pending_task or tareas[0],
    }


@transaction.atomic
def registrar_evaluacion(*, registro, estado, calificacion=None, comentario=None, actor=None, request=None):
    if actor is None:
        raise EvaluacionWorkflowError("No fue posible identificar al usuario evaluador.")
    if registro.fecha_envio_revision is None:
        raise EvaluacionWorkflowError(
            "La evidencia aun no esta habilitada para evaluacion. Primero habilita la salida al evaluador."
        )
    approval = obtener_aprobacion_principal_registro(registro)
    if not approval["approved"]:
        raise EvaluacionWorkflowError(approval["message"])

    evaluacion = (
        Evaluacion.objects.filter(registro=registro)
        .order_by("-fecha_evaluacion", "-id_evaluacion")
        .first()
    )
    created = evaluacion is None
    if created:
        evaluacion = Evaluacion.objects.create(
            registro=registro,
            usuario_evaluador=actor,
            estado=estado,
            fecha_evaluacion=timezone.now(),
            calificacion=calificacion,
            comentario=comentario,
            aprobado=(estado.descripcion or "").strip().upper() == "APROBADA",
        )
    else:
        evaluacion.usuario_evaluador = actor
        evaluacion.estado = estado
        evaluacion.fecha_evaluacion = timezone.now()
        evaluacion.calificacion = calificacion
        evaluacion.comentario = comentario
        evaluacion.aprobado = (estado.descripcion or "").strip().upper() == "APROBADA"
        evaluacion.save(
            update_fields=[
                "usuario_evaluador",
                "estado",
                "fecha_evaluacion",
                "calificacion",
                "comentario",
                "aprobado",
            ]
        )

    _sync_registro_estado(registro=registro, evaluation_state_description=estado.descripcion)
    registrar_evento(
        accion="REGISTRAR_EVALUACION",
        descripcion=f"Se registró la evaluacion de la evidencia {registro.id_registro}.",
        usuario=actor,
        tipo_evento="EVALUACION",
        tabla_afectada="evaluacion",
        id_registro=evaluacion.pk,
        valores_nuevos={
            "registro_id": registro.pk,
            "estado": estado.descripcion,
            "calificacion": str(calificacion) if calificacion is not None else None,
            "comentario": comentario,
            "aprobado": evaluacion.aprobado,
        },
        criticidad="MEDIA",
        request=request,
    )
    return {"evaluacion": evaluacion, "created": created}


@transaction.atomic
def registrar_observacion(*, evaluacion, observacion: str, actor=None, request=None):
    if actor is None:
        raise EvaluacionWorkflowError("No fue posible identificar al usuario emisor.")

    observation = ObservacionEvaluacion.objects.create(
        evaluacion=evaluacion,
        observacion=observacion,
        fecha_observacion=timezone.now(),
        usuario_emisor=actor,
        atendida=False,
        fecha_atendida=None,
    )

    estado_observada = (
        evaluacion.estado.__class__.objects.filter(
            activo=True,
            descripcion__iexact="OBSERVADA",
        ).first()
    )
    if estado_observada is not None:
        evaluacion.estado = estado_observada
        evaluacion.aprobado = False
        evaluacion.save(update_fields=["estado", "aprobado"])
        _sync_registro_estado(
            registro=evaluacion.registro,
            evaluation_state_description=estado_observada.descripcion,
        )

    registrar_evento(
        accion="REGISTRAR_OBSERVACION_EVALUACION",
        descripcion=f"Se registró una observacion para la evaluacion {evaluacion.id_evaluacion}.",
        usuario=actor,
        tipo_evento="EVALUACION",
        tabla_afectada="observacion_evaluacion",
        id_registro=observation.pk,
        valores_nuevos={
            "evaluacion_id": evaluacion.pk,
            "registro_id": evaluacion.registro_id,
            "observacion": observacion,
        },
        criticidad="MEDIA",
        request=request,
    )
    return observation


@transaction.atomic
def resolver_observacion(*, observacion, solucion: str, actor=None, marcar_atendida: bool = True, request=None):
    if actor is None:
        raise EvaluacionWorkflowError("No fue posible identificar al usuario que atiende la observacion.")

    solucion_normalizada = " ".join((solucion or "").strip().split())
    if not solucion_normalizada:
        raise EvaluacionWorkflowError("Debes ingresar la solucion de la recomendacion.")

    valores_anteriores = {
        "observacion": observacion.observacion,
        "atendida": bool(observacion.atendida),
        "fecha_atendida": observacion.fecha_atendida.isoformat() if observacion.fecha_atendida else None,
    }

    now = timezone.now()
    observacion.observacion = solucion_normalizada
    observacion.atendida = bool(marcar_atendida)
    observacion.fecha_atendida = now if marcar_atendida else None
    observacion.save(update_fields=["observacion", "atendida", "fecha_atendida"])

    if observacion.atendida:
        estado_reenviada = _resolve_first_available_evidence_status(
            "REENVIADA",
            "ENVIADA_EVALUADOR",
            "EN_REVISION_EVALUADOR",
        )
        _sync_registro_estado_directo(
            registro=observacion.evaluacion.registro,
            estado_objetivo=estado_reenviada,
            set_release_metadata=True,
            actor=actor,
        )

    registrar_evento(
        accion="RESOLVER_OBSERVACION_EVALUACION",
        descripcion=f"Se actualizo la observacion {observacion.id_observacion} para la evaluacion {observacion.evaluacion_id}.",
        usuario=actor,
        tipo_evento="EVALUACION",
        tabla_afectada="observacion_evaluacion",
        id_registro=observacion.pk,
        valores_anteriores=valores_anteriores,
        valores_nuevos={
            "observacion": observacion.observacion,
            "atendida": bool(observacion.atendida),
            "fecha_atendida": observacion.fecha_atendida.isoformat() if observacion.fecha_atendida else None,
        },
        criticidad="MEDIA",
        request=request,
    )
    return observacion


@transaction.atomic
def habilitar_salida_evaluador(
    *,
    registro,
    actor=None,
    allow_reassign: bool = False,
    require_actor_approver: bool = True,
    request=None,
):
    if actor is None:
        raise EvaluacionWorkflowError("No fue posible identificar al usuario responsable de la salida.")

    approval = obtener_aprobacion_principal_registro(registro)
    if not approval["approved"]:
        raise EvaluacionWorkflowError(approval["message"])
    if require_actor_approver and getattr(approval["task"], "asignado_por_id", None) != getattr(actor, "pk", None):
        raise EvaluacionWorkflowError(
            "Solo la cabeza de rango 1 que registro el check de revision puede habilitar la salida al evaluador."
        )

    already_released = registro.fecha_envio_revision is not None
    previous_sender_id = getattr(registro, "enviado_revision_por_id", None)
    actor_id = getattr(actor, "pk", None)

    if already_released and not allow_reassign:
        return {
            "status": "already_released",
            "released_at": registro.fecha_envio_revision,
            "sender_id": previous_sender_id,
        }

    if already_released and allow_reassign and previous_sender_id == actor_id:
        return {
            "status": "already_released",
            "released_at": registro.fecha_envio_revision,
            "sender_id": previous_sender_id,
        }

    now = timezone.now()
    previous_payload = {
        "enviado_revision_por": previous_sender_id,
        "fecha_envio_revision": registro.fecha_envio_revision.isoformat() if registro.fecha_envio_revision else None,
    }

    registro.enviado_revision_por = actor
    registro.fecha_envio_revision = now
    estado_salida = _resolve_first_available_evidence_status(
        "ENVIADA_EVALUADOR",
        "EN_REVISION_EVALUADOR",
        "EN_REVISION_INTERNA",
    )
    if estado_salida is not None:
        registro.estado = estado_salida
        registro.save(update_fields=["enviado_revision_por", "fecha_envio_revision", "estado"])
    else:
        registro.save(update_fields=["enviado_revision_por", "fecha_envio_revision"])

    revision_interna = (
        RevisionInternaEvidencia.objects.filter(
            registro=registro,
            resultado=RevisionInternaEvidencia.RESULTADO_APROBADA,
        )
        .order_by("-fecha_revision", "-id_revision_interna")
        .first()
    )
    if revision_interna is not None and not revision_interna.enviado_a_evaluador:
        revision_interna.enviado_a_evaluador = True
        revision_interna.save(update_fields=["enviado_a_evaluador"])

    was_reassigned = already_released and allow_reassign
    registrar_evento(
        accion="REASIGNAR_SALIDA_EVALUADOR" if was_reassigned else "HABILITAR_SALIDA_EVALUADOR",
        descripcion=(
            f"Se reasigno la salida a evaluador para la evidencia {registro.id_registro}."
            if was_reassigned
            else f"Se habilito la salida a evaluador para la evidencia {registro.id_registro}."
        ),
        usuario=actor,
        tipo_evento="EVALUACION",
        tabla_afectada="registro_evidencia",
        id_registro=registro.pk,
        valores_anteriores=previous_payload,
        valores_nuevos={
            "enviado_revision_por": actor_id,
            "fecha_envio_revision": now.isoformat(),
            "estado": getattr(getattr(registro, "estado", None), "descripcion", None),
            "revision_interna_id": getattr(revision_interna, "pk", None),
        },
        criticidad="MEDIA",
        request=request,
    )
    queue_evaluator_release_notification(registro=registro, actor=actor, request=request)

    return {
        "status": "reassigned" if was_reassigned else "released",
        "released_at": now,
        "sender_id": actor_id,
    }
