from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.informes.models import InformeAutoevaluacion


class InformeWorkflowError(Exception):
    pass


@transaction.atomic
def generar_informe(*, form, actor=None, request=None):
    if actor is None:
        raise InformeWorkflowError("No fue posible identificar al usuario que genera el informe.")

    informe = form.save(commit=False)
    informe.elaborado_por = actor
    informe.fecha_generacion = timezone.now()
    informe.save()
    registrar_evento(
        accion="GENERAR_INFORME_AUTOEVALUACION",
        descripcion=f"Se registró el informe del ciclo {informe.ciclo.nombre}.",
        usuario=actor,
        tipo_evento="INFORMES",
        tabla_afectada="informe_autoevaluacion",
        id_registro=informe.pk,
        valores_nuevos={
            "ciclo_id": informe.ciclo_id,
            "estado": informe.estado.descripcion,
            "documento_id": informe.documento_id,
        },
        criticidad="MEDIA",
        request=request,
    )
    return informe


@transaction.atomic
def aprobar_informe(*, informe: InformeAutoevaluacion, estado, observacion_aprobacion=None, actor=None, request=None):
    if actor is None:
        raise InformeWorkflowError("No fue posible identificar al usuario aprobador.")

    informe.estado = estado
    informe.observacion_aprobacion = observacion_aprobacion
    update_fields = ["estado", "observacion_aprobacion"]
    estado_desc = (estado.descripcion or "").strip().upper()
    if estado_desc == "APROBADO":
        informe.aprobado_por = actor
        informe.fecha_aprobacion = timezone.now()
        update_fields.extend(["aprobado_por", "fecha_aprobacion"])
    informe.save(update_fields=update_fields)
    registrar_evento(
        accion="ACTUALIZAR_ESTADO_INFORME",
        descripcion=f"Se actualizó el informe {informe.pk} a {estado.descripcion}.",
        usuario=actor,
        tipo_evento="INFORMES",
        tabla_afectada="informe_autoevaluacion",
        id_registro=informe.pk,
        valores_nuevos={
            "estado": estado.descripcion,
            "aprobado_por": getattr(informe.aprobado_por, "pk", None),
            "fecha_aprobacion": informe.fecha_aprobacion.isoformat() if informe.fecha_aprobacion else None,
            "observacion_aprobacion": informe.observacion_aprobacion,
        },
        criticidad="MEDIA",
        request=request,
    )
    return informe
