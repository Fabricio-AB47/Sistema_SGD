from django.db import transaction
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.core.models import EstadoEvidencia, EstadoTareaEvidencia
from apps.documentos.services import upload_structured_document
from apps.evaluacion.models import TareaEvidencia
from apps.evaluacion.services.notification_service import queue_evidence_uploaded_email
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
    actor_area_ids = _get_actor_level_one_area_ids(actor)
    if not actor_id or not actor_area_ids:
        return False

    if tarea is None:
        return True

    if tarea.usuario_responsable_id == actor_id or tarea.asignado_por_id == actor_id:
        return True

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
    requires_director_check = not _actor_can_mark_evidence_uploaded(
        actor=actor,
        tarea=related_task,
    )
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
    }
