from django.db import transaction
from django.core.cache import cache

from application.services.storage_path_service import (
    build_criterio_drive_path,
    build_elemento_drive_path,
    build_indicador_drive_path,
    build_subcriterio_drive_path,
)
from apps.auditoria.services.auditoria_service import registrar_evento
from apps.acreditacion.models import IndicadorElementoFundamental
from apps.documentos.selectors import authorization_document_exists
from apps.documentos.services import upload_cycle_authorization_document
from apps.integraciones.services.graph_service import (
    ensure_drive_folder,
    require_graph_configuration,
)


def _invalidate_acreditacion_metrics_cache():
    cache.delete("sig:acreditacion:metrics")


def _registrar_evento_catalogo(*, actor, request, accion, descripcion, tabla, registro):
    registrar_evento(
        accion=accion,
        descripcion=descripcion,
        usuario=actor,
        tipo_evento="ACREDITACION",
        tabla_afectada=tabla,
        id_registro=registro.pk,
        valores_nuevos={"id": registro.pk},
        criticidad="MEDIA",
        request=request,
    )


def _provision_storage(*, drive_path):
    require_graph_configuration()
    graph_item = ensure_drive_folder(drive_path)
    return {
        "drive_path": drive_path,
        "graph_item": graph_item,
    }


@transaction.atomic
def crear_criterio(*, form, actor=None, request=None):
    criterio = form.save()
    _invalidate_acreditacion_metrics_cache()
    storage = _provision_storage(
        drive_path=build_criterio_drive_path(criterio),
    )
    _registrar_evento_catalogo(
        actor=actor,
        request=request,
        accion="CREAR_CRITERIO",
        descripcion=f"Se registro el criterio {criterio.codigo_criterio}.",
        tabla="criterio",
        registro=criterio,
    )
    registrar_evento(
        accion="CREAR_CARPETA_CRITERIO",
        descripcion=f"Se creo la carpeta Graph del criterio {criterio.codigo_criterio}.",
        usuario=actor,
        tipo_evento="ALMACENAMIENTO",
        tabla_afectada="criterio",
        id_registro=criterio.pk,
        valores_nuevos={
            "ruta_drive": storage["drive_path"].as_posix(),
            "graph_web_url": (storage["graph_item"] or {}).get("webUrl"),
        },
        criticidad="MEDIA",
        request=request,
    )
    return criterio


@transaction.atomic
def crear_subcriterio(*, form, actor=None, request=None):
    subcriterio = form.save()
    _invalidate_acreditacion_metrics_cache()
    storage = _provision_storage(
        drive_path=build_subcriterio_drive_path(subcriterio),
    )
    _registrar_evento_catalogo(
        actor=actor,
        request=request,
        accion="CREAR_SUBCRITERIO",
        descripcion=f"Se registro el subcriterio {subcriterio.codigo_subcriterio}.",
        tabla="subcriterio",
        registro=subcriterio,
    )
    registrar_evento(
        accion="CREAR_CARPETA_SUBCRITERIO",
        descripcion=f"Se creo la carpeta Graph del subcriterio {subcriterio.codigo_subcriterio}.",
        usuario=actor,
        tipo_evento="ALMACENAMIENTO",
        tabla_afectada="subcriterio",
        id_registro=subcriterio.pk,
        valores_nuevos={
            "ruta_drive": storage["drive_path"].as_posix(),
            "graph_web_url": (storage["graph_item"] or {}).get("webUrl"),
        },
        criticidad="MEDIA",
        request=request,
    )
    return subcriterio


@transaction.atomic
def crear_indicador(*, form, actor=None, request=None):
    indicador = form.save()
    _invalidate_acreditacion_metrics_cache()
    storage = _provision_storage(
        drive_path=build_indicador_drive_path(indicador),
    )
    _registrar_evento_catalogo(
        actor=actor,
        request=request,
        accion="CREAR_INDICADOR",
        descripcion=f"Se registro el indicador {indicador.codigo_indicador}.",
        tabla="indicador",
        registro=indicador,
    )
    registrar_evento(
        accion="CREAR_CARPETA_INDICADOR",
        descripcion=f"Se creo la carpeta Graph del indicador {indicador.codigo_indicador}.",
        usuario=actor,
        tipo_evento="ALMACENAMIENTO",
        tabla_afectada="indicador",
        id_registro=indicador.pk,
        valores_nuevos={
            "ruta_drive": storage["drive_path"].as_posix(),
            "graph_web_url": (storage["graph_item"] or {}).get("webUrl"),
        },
        criticidad="MEDIA",
        request=request,
    )
    return indicador


@transaction.atomic
def crear_elemento(*, form, actor=None, request=None):
    elemento = form.save()
    _invalidate_acreditacion_metrics_cache()
    _registrar_evento_catalogo(
        actor=actor,
        request=request,
        accion="CREAR_ELEMENTO_FUNDAMENTAL",
        descripcion=f"Se registro el elemento {elemento.codigo_elemento}.",
        tabla="elemento_fundamental",
        registro=elemento,
    )
    return elemento


@transaction.atomic
def vincular_indicador_elemento(*, indicador, elemento_fundamental, actor=None, request=None):
    relacion = IndicadorElementoFundamental.objects.create(
        indicador=indicador,
        elemento_fundamental=elemento_fundamental,
    )
    storage = _provision_storage(
        drive_path=build_elemento_drive_path(indicador, elemento_fundamental),
    )
    registrar_evento(
        accion="VINCULAR_INDICADOR_ELEMENTO",
        descripcion=f"Se vinculo el elemento {elemento_fundamental.codigo_elemento} al indicador {indicador.codigo_indicador}.",
        usuario=actor,
        tipo_evento="ACREDITACION",
        tabla_afectada="indicador_elemento_fundamental",
        id_registro=indicador.pk,
        valores_nuevos={
            "indicador_id": indicador.pk,
            "elemento_id": elemento_fundamental.pk,
            "ruta_drive": storage["drive_path"].as_posix(),
            "graph_web_url": (storage["graph_item"] or {}).get("webUrl"),
        },
        criticidad="MEDIA",
        request=request,
    )
    return relacion


@transaction.atomic
def crear_ciclo(*, form, actor=None, request=None):
    if not hasattr(form, "cleaned_data"):
        if not form.is_valid():
            raise ValueError(
                "No fue posible registrar el ciclo. Revisa los datos del formulario y adjunta el documento de autorizacion."
            )

    authorization_result = upload_cycle_authorization_document(
        nombre_ciclo=form.cleaned_data["nombre"],
        anio=form.cleaned_data.get("anio"),
        clasificacion=form.cleaned_data["clasificacion"],
        descripcion_documento=form.cleaned_data.get("descripcion_documento"),
        uploaded_file=form.cleaned_data["archivo"],
        actor=actor,
        request=request,
    )
    ciclo = form.save()
    _invalidate_acreditacion_metrics_cache()
    _registrar_evento_catalogo(
        actor=actor,
        request=request,
        accion="CREAR_CICLO",
        descripcion=f"Se registro el ciclo {ciclo.nombre}.",
        tabla="ciclo_evaluacion",
        registro=ciclo,
    )
    registrar_evento(
        accion="CREAR_CICLO_CON_AUTORIZACION",
        descripcion=f"Se registro el ciclo {ciclo.nombre} con su documento de autorizacion.",
        usuario=actor,
        tipo_evento="ACREDITACION",
        tabla_afectada="ciclo_evaluacion",
        id_registro=ciclo.pk,
        valores_nuevos={
            "documento_id": authorization_result["documento"].pk,
            "version_id": authorization_result["version"].pk,
            "ruta_drive": authorization_result["drive_path"].as_posix(),
            "graph_web_url": (authorization_result["graph_item"] or {}).get("webUrl"),
        },
        criticidad="ALTA",
        request=request,
    )
    return ciclo


@transaction.atomic
def actualizar_estado_ciclo(*, ciclo, estado, actor=None, request=None):
    if (
        (getattr(estado, "descripcion", "") or "").strip().upper() == "APROBADO"
        and not authorization_document_exists(ciclo.nombre, ciclo.anio)
    ):
        raise ValueError(
            "No puedes aprobar el ciclo si no existe su documento de autorizacion."
        )

    estado_anterior = getattr(ciclo.estado, "descripcion", None)
    ciclo.estado = estado
    ciclo.save(update_fields=["estado"])
    registrar_evento(
        accion="ACTUALIZAR_ESTADO_CICLO",
        descripcion=f"Se actualizo el estado del ciclo {ciclo.nombre} a {estado.descripcion}.",
        usuario=actor,
        tipo_evento="ACREDITACION",
        tabla_afectada="ciclo_evaluacion",
        id_registro=ciclo.pk,
        valores_anteriores={"estado": estado_anterior},
        valores_nuevos={"estado": estado.descripcion},
        criticidad="MEDIA",
        request=request,
    )
    return ciclo
