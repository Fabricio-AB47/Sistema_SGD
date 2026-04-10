from django.db import transaction
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.core.models import EstadoEvidencia
from apps.documentos.services import upload_structured_document
from apps.evidencias.models import RegistroEvidencia


class MatrixEvidenceRegistrationError(Exception):
    pass


def _get_default_evidence_status():
    return (
        EstadoEvidencia.objects.filter(activo=True, descripcion__iexact="CARGADA").first()
        or EstadoEvidencia.objects.filter(activo=True, descripcion__iexact="REGISTRADA").first()
        or EstadoEvidencia.objects.filter(activo=True).order_by("id_estado_evidencia").first()
    )


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

    estado = _get_default_evidence_status()
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
        },
        criticidad="ALTA",
        request=request,
    )
    return {
        "registro": registro,
        "documento": upload_result["documento"],
        "version": upload_result["version"],
        "created": created,
    }
