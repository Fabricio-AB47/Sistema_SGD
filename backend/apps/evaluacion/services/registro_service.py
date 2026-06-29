from django.db import transaction
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.core.models import EstadoEvidencia, EstadoTareaEvidencia
from apps.documentos.services import upload_structured_document
from apps.evaluacion.models import TareaEvidencia
from apps.evaluacion.services.notification_service import queue_evidence_uploaded_email
from apps.evaluacion.services.revision_service import EvaluacionWorkflowError, habilitar_salida_evaluador
from apps.evaluacion.services.tareas_service import DIRECTOR_SIGNOFF_TOKEN
from apps.evidencias.models import RegistroEvidencia
from apps.usuarios.models import UsuarioAreaCargo, UsuarioRol


class MatrixEvidenceRegistrationError(Exception):
    pass


def _resolve_evidence_status(*descriptions: str):
    for description in descriptions:
        estado = EstadoEvidencia.objects.filter(
            activo=True,
            descripcion__iexact=description,
        ).first()
        if estado is not None:
            return estado
    return None


def _resolve_task_state(*descriptions: str):
    for description in descriptions:
        estado = EstadoTareaEvidencia.objects.filter(
            activo=True,
            descripcion__iexact=description,
        ).first()
        if estado is not None:
            return estado
    return None


def _get_default_evidence_status():
    return (
        _resolve_evidence_status("CARGADA", "REGISTRADA", "VALIDADA")
        or EstadoEvidencia.objects.filter(activo=True).order_by("id_estado_evidencia").first()
    )


def _get_internal_review_status():
    return (
        _resolve_evidence_status("EN_REVISION_INTERNA", "BORRADOR", "REENVIADA")
        or _get_default_evidence_status()
    )


def _actor_has_admin_role(actor) -> bool:
    actor_id = getattr(actor, "pk", None)
    if not actor_id:
        return False
    return UsuarioRol.objects.filter(
        usuario_id=actor_id,
        activo=True,
        rol__activo=True,
        rol__nombre_rol__iexact="Administrador",
    ).exists()


def _get_actor_level_one_area_ids(actor):
    actor_id = getattr(actor, "pk", None)
    if not actor_id:
        return set()
    return set(
        UsuarioAreaCargo.objects.filter(
            usuario_id=actor_id,
            activo=True,
            area__activo=True,
            cargo__activo=True,
            cargo__nivel_jerarquico=1,
            cargo__aprueba_interno=True,
        ).values_list("area_id", flat=True)
    )


def _find_related_task(*, ciclo, indicador, elemento_fundamental, actor):
    queryset = TareaEvidencia.objects.select_related(
        "usuario_responsable",
        "asignado_por",
        "estado",
    ).filter(
        ciclo=ciclo,
        indicador=indicador,
        elemento_fundamental=elemento_fundamental,
        activo=True,
    ).order_by("-fecha_asignacion", "-id_tarea_evidencia")

    actor_id = getattr(actor, "pk", None)
    if actor_id:
        actor_task = queryset.filter(usuario_responsable_id=actor_id).first()
        if actor_task is not None:
            return actor_task

        assigned_by_task = queryset.filter(asignado_por_id=actor_id).first()
        if assigned_by_task is not None:
            return assigned_by_task

    return queryset.first()


def _actor_can_mark_evidence_uploaded(*, actor, tarea) -> bool:
    if _actor_has_admin_role(actor):
        return True

    actor_id = getattr(actor, "pk", None)
    if not actor_id:
        return False

    if tarea is None:
        return bool(_get_actor_level_one_area_ids(actor))

    if tarea.usuario_responsable_id == actor_id or tarea.asignado_por_id == actor_id:
        return True

    actor_area_ids = _get_actor_level_one_area_ids(actor)
    if not actor_area_ids:
        return False

    task_area_ids = set(
        UsuarioAreaCargo.objects.filter(
            usuario_id=tarea.usuario_responsable_id,
            activo=True,
            area__activo=True,
            cargo__activo=True,
        ).values_list("area_id", flat=True)
    )
    return bool(actor_area_ids.intersection(task_area_ids))


def _latest_evidence_record_for_task(tarea):
    if tarea is None:
        return None
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


def _actor_can_auto_signoff_task(*, actor, tarea) -> bool:
    if _actor_has_admin_role(actor):
        return True

    actor_id = getattr(actor, "pk", None)
    actor_area_ids = _get_actor_level_one_area_ids(actor)
    if not actor_id or not actor_area_ids:
        return False

    if tarea is None:
        return True

    if tarea.usuario_responsable_id == actor_id:
        return False

    task_area_ids = set(
        UsuarioAreaCargo.objects.filter(
            usuario_id=tarea.usuario_responsable_id,
            activo=True,
            area__activo=True,
            cargo__activo=True,
        ).values_list("area_id", flat=True)
    )
    return bool(actor_area_ids.intersection(task_area_ids))


def _close_task_after_upload(*, tarea, actor, comentario, request=None):
    actor_id = getattr(actor, "pk", None)
    if tarea is None or tarea.usuario_responsable_id != actor_id or tarea.fecha_cierre:
        return False

    estado_cierre = _resolve_task_state("CERRADA", "COMPLETADA", "FINALIZADA")
    previous_payload = {
        "estado": getattr(getattr(tarea, "estado", None), "descripcion", None),
        "fecha_cierre": tarea.fecha_cierre.isoformat() if tarea.fecha_cierre else None,
        "resultado_tarea": tarea.resultado_tarea,
    }

    resultado = " ".join((comentario or "Evidencia cargada en la matriz de registro.").split())
    tarea.resultado_tarea = resultado[:1000]
    tarea.fecha_cierre = timezone.now()
    update_fields = ["resultado_tarea", "fecha_cierre"]
    if estado_cierre is not None:
        tarea.estado = estado_cierre
        update_fields.append("estado")
    tarea.save(update_fields=update_fields)

    registrar_evento(
        accion="CERRAR_TAREA_EVIDENCIA_POR_CARGA",
        descripcion=f"Se cerro la tarea de evidencia {tarea.pk} por carga documental.",
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
    return True


def _signoff_task_after_director_upload(*, tarea, actor, comentario, request=None):
    if tarea is None:
        return False

    timestamp = timezone.now()
    previous_payload = {
        "estado": getattr(getattr(tarea, "estado", None), "descripcion", None),
        "fecha_cierre": tarea.fecha_cierre.isoformat() if tarea.fecha_cierre else None,
        "resultado_tarea": tarea.resultado_tarea,
        "observacion": tarea.observacion,
        "asignado_por_id": tarea.asignado_por_id,
    }

    actor_name = getattr(actor, "nombre_completo", None) or getattr(actor, "correo", "Director")
    note = (
        f"[{DIRECTOR_SIGNOFF_TOKEN}] Aprobacion interna por carga directa del director "
        f"{actor_name} el {timestamp.strftime('%Y-%m-%d %H:%M')}"
    )
    extra_note = " ".join((comentario or "").strip().split())
    if extra_note:
        note = f"{note}. Comentario: {extra_note}"

    update_fields = ["observacion", "asignado_por"]
    if not tarea.fecha_cierre:
        tarea.fecha_cierre = timestamp
        tarea.resultado_tarea = (extra_note or "Evidencia cargada y aprobada internamente por el director.")[:1000]
        update_fields.extend(["fecha_cierre", "resultado_tarea"])

    tarea.observacion = "\n".join(part for part in [tarea.observacion, note] if part)
    tarea.asignado_por = actor

    estado_revision = _resolve_task_state("REVISADA", "APROBADA", "CERRADA")
    if estado_revision is not None:
        tarea.estado = estado_revision
        update_fields.append("estado")
    tarea.save(update_fields=list(dict.fromkeys(update_fields)))

    registrar_evento(
        accion="APROBACION_INTERNA_DIRECTOR_CARGA",
        descripcion=f"Se aprobo internamente la tarea {tarea.pk} por carga directa del director.",
        usuario=actor,
        tipo_evento="EVALUACION",
        tabla_afectada="tarea_evidencia",
        id_registro=tarea.pk,
        valores_anteriores=previous_payload,
        valores_nuevos={
            "estado": getattr(getattr(tarea, "estado", None), "descripcion", None),
            "fecha_cierre": tarea.fecha_cierre.isoformat() if tarea.fecha_cierre else None,
            "resultado_tarea": tarea.resultado_tarea,
            "observacion": tarea.observacion,
            "asignado_por_id": tarea.asignado_por_id,
        },
        criticidad="MEDIA",
        request=request,
    )
    return True


@transaction.atomic
def register_matrix_evidence(
    *,
    ciclo,
    indicador,
    elemento_fundamental,
    clasificacion,
    uploaded_file,
    descripcion_documento: str | None = None,
    comentario: str | None = None,
    actor=None,
    request=None,
):
    if actor is None:
        raise MatrixEvidenceRegistrationError("No fue posible identificar al usuario activo.")
    if elemento_fundamental.indicador_id != indicador.pk:
        raise MatrixEvidenceRegistrationError(
            "El elemento fundamental no pertenece al indicador seleccionado."
        )

    related_task = _find_related_task(
        ciclo=ciclo,
        indicador=indicador,
        elemento_fundamental=elemento_fundamental,
        actor=actor,
    )
    can_mark_uploaded = _actor_can_mark_evidence_uploaded(
        actor=actor,
        tarea=related_task,
    )
    can_auto_signoff = _actor_can_auto_signoff_task(
        actor=actor,
        tarea=related_task,
    )
    if not can_mark_uploaded:
        raise MatrixEvidenceRegistrationError(
            "Solo el responsable asignado, quien reasigno la tarea o una cabeza de rango 1 puede registrar esta evidencia."
        )
    if related_task is not None and getattr(related_task, "fecha_cierre", None) and not can_auto_signoff:
        latest_record = _latest_evidence_record_for_task(related_task)
        if latest_record is not None:
            raise MatrixEvidenceRegistrationError(
                "La evidencia ya fue subida y esta pendiente de revision. Solo podras modificarla si la persona que reasigno solicita correcciones."
            )
    requires_director_check = not can_auto_signoff
    estado = _get_internal_review_status() if requires_director_check else _get_default_evidence_status()
    if estado is None:
        raise MatrixEvidenceRegistrationError(
            "No existe un estado de evidencia activo para registrar la carga."
        )

    upload_result = upload_structured_document(
        ciclo=ciclo,
        indicador=indicador,
        elemento_fundamental=elemento_fundamental,
        clasificacion=clasificacion,
        uploaded_file=uploaded_file,
        descripcion_documento=descripcion_documento,
        actor=actor,
        request=request,
    )

    registro = (
        RegistroEvidencia.objects.filter(
            documento=upload_result["documento"],
            elemento_fundamental=elemento_fundamental,
            ciclo=ciclo,
        )
        .order_by("-id_registro")
        .first()
    )
    created = registro is None
    if created:
        registro = RegistroEvidencia.objects.create(
            documento=upload_result["documento"],
            elemento_fundamental=elemento_fundamental,
            indicador=indicador,
            ciclo=ciclo,
            estado=estado,
            fecha_registro=timezone.now(),
            registrado_por=actor,
            enviado_revision_por=None,
            fecha_envio_revision=None,
            comentario=comentario,
        )
    else:
        registro.indicador = indicador
        registro.estado = estado
        registro.fecha_registro = timezone.now()
        registro.registrado_por = actor
        registro.enviado_revision_por = None
        registro.fecha_envio_revision = None
        registro.comentario = comentario
        registro.save(
            update_fields=[
                "indicador",
                "estado",
                "fecha_registro",
                "registrado_por",
                "enviado_revision_por",
                "fecha_envio_revision",
                "comentario",
            ]
        )

    task_closed = _close_task_after_upload(
        tarea=related_task,
        actor=actor,
        comentario=comentario or descripcion_documento,
        request=request,
    )
    auto_approved_by_director = False
    auto_release_result = None
    auto_release_error = None
    if can_auto_signoff and related_task is not None:
        auto_approved_by_director = _signoff_task_after_director_upload(
            tarea=related_task,
            actor=actor,
            comentario=comentario or descripcion_documento,
            request=request,
        )
        if auto_approved_by_director:
            try:
                auto_release_result = habilitar_salida_evaluador(
                    registro=registro,
                    actor=actor,
                    allow_reassign=True,
                    require_actor_approver=not _actor_has_admin_role(actor),
                    request=request,
                )
            except (EvaluacionWorkflowError, ValueError) as exc:
                auto_release_error = str(exc)
                registrar_evento(
                    accion="SALIDA_EVALUADOR_AUTOMATICA_PENDIENTE",
                    descripcion=(
                        "La evidencia se registro correctamente, pero quedo pendiente "
                        "la salida automatica al evaluador."
                    ),
                    usuario=actor,
                    tipo_evento="EVALUACION",
                    tabla_afectada="registro_evidencia",
                    id_registro=registro.pk,
                    valores_nuevos={
                        "registro_id": registro.pk,
                        "tarea_id": getattr(related_task, "pk", None),
                        "detalle_error": auto_release_error[:500],
                    },
                    criticidad="MEDIA",
                    request=request,
                )

    registrar_evento(
        accion="REGISTRAR_EVIDENCIA_MATRIZ",
        descripcion=(
            f"Se registro la evidencia del elemento {elemento_fundamental.codigo_elemento} "
            f"en el ciclo {ciclo.nombre}."
        ),
        usuario=actor,
        tipo_evento="EVIDENCIAS",
        tabla_afectada="registro_evidencia",
        id_registro=registro.pk,
        valores_nuevos={
            "registro_id": registro.pk,
            "documento_id": upload_result["documento"].pk,
            "version_id": upload_result["version"].pk,
            "ciclo_id": ciclo.pk,
            "indicador_id": indicador.pk,
            "elemento_id": elemento_fundamental.pk,
            "estado_id": estado.pk,
            "comentario": comentario,
            "requiere_visto_bueno_director": requires_director_check,
            "tarea_id": getattr(related_task, "pk", None),
            "tarea_cerrada": task_closed,
            "aprobacion_interna_director": auto_approved_by_director,
            "salida_evaluador_automatica": bool(auto_release_result),
            "salida_evaluador_estado": auto_release_result["status"] if auto_release_result else None,
            "salida_evaluador_error": auto_release_error,
        },
        criticidad="ALTA",
        request=request,
    )
    queue_evidence_uploaded_email(
        registro=registro,
        documento=upload_result["documento"],
        tarea=related_task,
        actor=actor,
        requires_director_check=requires_director_check,
        request=request,
    )
    return {
        "registro": registro,
        "documento": upload_result["documento"],
        "version": upload_result["version"],
        "created": created,
        "auto_approved_by_director": auto_approved_by_director,
        "auto_sent_to_evaluator": bool(auto_release_result),
        "auto_release_error": auto_release_error,
        "requires_director_check": requires_director_check,
    }
