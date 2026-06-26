from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone

from application.services.storage_path_service import (
    build_criterio_drive_path,
    build_elemento_drive_path,
    build_indicador_drive_path,
    build_subcriterio_drive_path,
    ensure_local_mirror_folder,
)
from apps.acreditacion.models import Criterio, Indicador, RolIndicador, Subcriterio
from apps.auditoria.services.auditoria_service import registrar_evento
from apps.core.models import TipoIndicador
from apps.documentos.selectors import (
    authorization_document_exists,
    authorization_document_exists_for_cycle,
)
from apps.documentos.services import upload_cycle_authorization_document
from apps.evidencias.models import Documento, RegistroEvidencia
from apps.integraciones.services.graph_service import (
    clear_graph_cache,
    ensure_drive_folder,
    get_item_by_relative_path,
    GraphServiceError,
    get_graph_session,
    require_graph_configuration,
)
from apps.usuarios.models import UsuarioRol


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


def _registrar_evento_carpeta(*, actor, request, accion, descripcion, tabla, registro, storage, extra=None):
    local_path = storage.get("local_path")
    registrar_evento(
        accion=accion,
        descripcion=descripcion,
        usuario=actor,
        tipo_evento="ALMACENAMIENTO",
        tabla_afectada=tabla,
        id_registro=registro.pk,
        valores_nuevos={
            "ruta_drive": storage["drive_path"].as_posix(),
            "ruta_espejo_local": str(local_path) if local_path else None,
            "graph_web_url": (storage["graph_item"] or {}).get("webUrl"),
            **(extra or {}),
        },
        criticidad="MEDIA",
        request=request,
    )


def _registrar_evento_carpeta_pendiente(
    *,
    actor,
    request,
    accion,
    descripcion,
    tabla,
    registro,
    drive_path,
    error,
    local_path=None,
    extra=None,
):
    registrar_evento(
        accion=accion,
        descripcion=descripcion,
        usuario=actor,
        tipo_evento="ALMACENAMIENTO",
        tabla_afectada=tabla,
        id_registro=registro.pk,
        valores_nuevos={
            "ruta_drive": drive_path.as_posix(),
            "ruta_espejo_local": str(local_path) if local_path else None,
            "estado_carpeta": "PENDIENTE_VALIDACION",
            "detalle_error": str(error)[:500],
            **(extra or {}),
        },
        criticidad="MEDIA",
        request=request,
    )


def _try_provision_storage(
    *,
    drive_path,
    actor,
    request,
    accion,
    descripcion,
    tabla,
    registro,
    extra=None,
    storage_context=None,
):
    local_path = ensure_local_mirror_folder(drive_path)
    graph_error = (storage_context or {}).get("graph_error")
    if graph_error is not None:
        _registrar_evento_carpeta_pendiente(
            actor=actor,
            request=request,
            accion=f"{accion}_PENDIENTE",
            descripcion=f"{descripcion} Quedo pendiente de validacion Graph.",
            tabla=tabla,
            registro=registro,
            drive_path=drive_path,
            error=graph_error,
            local_path=local_path,
            extra=extra,
        )
        return None

    try:
        storage = _provision_storage(
            drive_path=drive_path,
            local_path=local_path,
            **(storage_context or {}),
        )
    except (GraphServiceError, OSError, ValueError) as exc:
        _registrar_evento_carpeta_pendiente(
            actor=actor,
            request=request,
            accion=f"{accion}_PENDIENTE",
            descripcion=f"{descripcion} Quedo pendiente de validacion Graph.",
            tabla=tabla,
            registro=registro,
            drive_path=drive_path,
            error=exc,
            local_path=local_path,
            extra=extra,
        )
        return None

    _registrar_evento_carpeta(
        actor=actor,
        request=request,
        accion=accion,
        descripcion=descripcion,
        tabla=tabla,
        registro=registro,
        storage=storage,
        extra=extra,
    )
    return storage


def _provision_storage(
    *,
    drive_path,
    graph_payload=None,
    graph_access_token=None,
    refresh=False,
    local_path=None,
):
    local_path = local_path or ensure_local_mirror_folder(drive_path)
    if graph_payload is None or graph_access_token is None:
        require_graph_configuration()
    if refresh:
        clear_graph_cache(drive_path)
    graph_item = ensure_drive_folder(
        drive_path,
        payload=graph_payload,
        access_token=graph_access_token,
        refresh=refresh,
    )
    if not graph_item or "folder" not in graph_item:
        validated_item = get_item_by_relative_path(
            drive_path,
            payload=graph_payload,
            access_token=graph_access_token,
            refresh=refresh,
        )
        if validated_item is None or "folder" not in validated_item:
            raise GraphServiceError(
                f"No fue posible validar la carpeta Graph esperada para la ruta {drive_path.as_posix()}."
            )
        graph_item = validated_item
    return {
        "drive_path": drive_path,
        "graph_item": graph_item,
        "local_path": local_path,
    }


def _element_has_linked_content(*, elemento_fundamental) -> bool:
    previous_path = build_elemento_drive_path(
        elemento_fundamental.indicador,
        elemento_fundamental,
    ).as_posix()
    has_documents = Documento.objects.filter(
        ruta_local__startswith=previous_path,
        activo=True,
    ).exists()
    if has_documents:
        return True
    return RegistroEvidencia.objects.filter(
        elemento_fundamental=elemento_fundamental
    ).exists()


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _next_visual_order(model, field_name: str, **filters) -> int:
    current = model.objects.filter(**filters).aggregate(max_order=Max(field_name)).get("max_order")
    return int(current or 0) + 1


def _unique_code(model, field_name: str, base_code: str) -> str:
    base = "-".join(_normalize_text(base_code).upper().split())[:20] or "CACES"
    code = base
    suffix = 1
    while model.objects.filter(**{field_name: code}).exists():
        suffix += 1
        trailer = f"-{suffix}"
        code = f"{base[:20 - len(trailer)]}{trailer}"
    return code


def _ensure_tipo_indicador(tipo_evaluacion: str):
    tipo = _normalize_text(tipo_evaluacion).upper() or "CUALITATIVO"
    existing = TipoIndicador.objects.filter(descripcion__iexact=tipo).first()
    if existing:
        return existing
    return TipoIndicador.objects.create(descripcion=tipo, activo=True)


def _ensure_caces_criterio(
    *,
    nombre: str,
    order: int,
    actor=None,
    request=None,
    ensure_existing_storage=False,
    storage_context=None,
):
    nombre = _normalize_text(nombre)
    base_code = f"CACES-C{order:02d}"
    criterio = Criterio.objects.filter(
        Q(nombre_criterio__iexact=nombre) | Q(codigo_criterio__iexact=base_code)
    ).first()
    created = criterio is None
    if created:
        try:
            with transaction.atomic():
                criterio = Criterio.objects.create(
                    codigo_criterio=_unique_code(Criterio, "codigo_criterio", base_code),
                    nombre_criterio=nombre,
                    descripcion=f"Criterio importado desde modelo_indicador_caces: {nombre}",
                    ponderacion=None,
                    orden_visual=_next_visual_order(Criterio, "orden_visual"),
                    activo=True,
                )
        except IntegrityError:
            criterio = Criterio.objects.filter(
                Q(nombre_criterio__iexact=nombre) | Q(codigo_criterio__iexact=base_code)
            ).first()
            created = False
        if criterio is None:
            raise ValueError(f"No fue posible reutilizar o crear el criterio {base_code}.")

    if created:
        _registrar_evento_catalogo(
            actor=actor,
            request=request,
            accion="CREAR_CRITERIO_CACES_MASIVO",
            descripcion=f"Se registro el criterio {criterio.codigo_criterio} desde modelo CACES.",
            tabla="criterio",
            registro=criterio,
        )

    if created or ensure_existing_storage:
        _try_provision_storage(
            drive_path=build_criterio_drive_path(criterio),
            actor=actor,
            request=request,
            accion="CREAR_CARPETA_CRITERIO_CACES_MASIVO",
            descripcion=f"Se valido la carpeta Graph del criterio {criterio.codigo_criterio}.",
            tabla="criterio",
            registro=criterio,
            storage_context=storage_context,
        )
    return criterio, created


def _ensure_caces_subcriterio(
    *,
    criterio,
    nombre: str,
    criterion_order: int,
    subcriterion_order: int,
    actor=None,
    request=None,
    ensure_existing_storage=False,
    storage_context=None,
):
    nombre = _normalize_text(nombre)
    base_code = f"C{criterion_order:02d}-S{subcriterion_order:02d}"
    subcriterio = Subcriterio.objects.filter(
        Q(criterio=criterio, nombre_subcriterio__iexact=nombre)
        | Q(codigo_subcriterio__iexact=base_code)
    ).first()
    created = subcriterio is None
    if created:
        try:
            with transaction.atomic():
                subcriterio = Subcriterio.objects.create(
                    criterio=criterio,
                    codigo_subcriterio=_unique_code(
                        Subcriterio,
                        "codigo_subcriterio",
                        base_code,
                    ),
                    nombre_subcriterio=nombre,
                    descripcion=f"Subcriterio importado desde modelo_indicador_caces: {nombre}",
                    ponderacion=None,
                    orden_visual=_next_visual_order(Subcriterio, "orden_visual", criterio=criterio),
                    activo=True,
                )
        except IntegrityError:
            subcriterio = Subcriterio.objects.filter(
                Q(criterio=criterio, nombre_subcriterio__iexact=nombre)
                | Q(codigo_subcriterio__iexact=base_code)
            ).first()
            created = False
        if subcriterio is None:
            raise ValueError(f"No fue posible reutilizar o crear el subcriterio {base_code}.")

    if created:
        _registrar_evento_catalogo(
            actor=actor,
            request=request,
            accion="CREAR_SUBCRITERIO_CACES_MASIVO",
            descripcion=f"Se registro el subcriterio {subcriterio.codigo_subcriterio} desde modelo CACES.",
            tabla="subcriterio",
            registro=subcriterio,
        )

    if created or ensure_existing_storage:
        _try_provision_storage(
            drive_path=build_subcriterio_drive_path(subcriterio),
            actor=actor,
            request=request,
            accion="CREAR_CARPETA_SUBCRITERIO_CACES_MASIVO",
            descripcion=f"Se valido la carpeta Graph del subcriterio {subcriterio.codigo_subcriterio}.",
            tabla="subcriterio",
            registro=subcriterio,
            storage_context=storage_context,
        )
    return subcriterio, created


def _ensure_caces_indicador(
    *,
    modelo,
    subcriterio,
    actor=None,
    request=None,
    ensure_existing_storage=False,
    storage_context=None,
):
    codigo = _normalize_text(getattr(modelo, "codigo_modelo", "")).upper()
    nombre = _normalize_text(getattr(modelo, "nombre_indicador", ""))
    indicador = Indicador.objects.filter(codigo_indicador__iexact=codigo).first()
    if indicador is None:
        indicador = Indicador.objects.filter(
            subcriterio=subcriterio,
            nombre_indicador__iexact=nombre,
        ).first()
    created = indicador is None
    if created:
        tipo_indicador = _ensure_tipo_indicador(modelo.tipo_evaluacion)
        try:
            with transaction.atomic():
                indicador = Indicador.objects.create(
                    subcriterio=subcriterio,
                    tipo_indicador=tipo_indicador,
                    codigo_indicador=_unique_code(Indicador, "codigo_indicador", codigo),
                    nombre_indicador=nombre,
                    descripcion=f"Indicador importado desde modelo_indicador_caces numero {modelo.numero_modelo}.",
                    medio_verificacion=None,
                    ponderacion=modelo.ponderacion_a,
                    orden_visual=_next_visual_order(Indicador, "orden_visual", subcriterio=subcriterio),
                    activo=True,
                )
        except IntegrityError:
            indicador = Indicador.objects.filter(codigo_indicador__iexact=codigo).first()
            if indicador is None:
                indicador = Indicador.objects.filter(
                    subcriterio=subcriterio,
                    nombre_indicador__iexact=nombre,
                ).first()
            created = False
        if indicador is None:
            raise ValueError(f"No fue posible reutilizar o crear el indicador {codigo}.")

    if created:
        _registrar_evento_catalogo(
            actor=actor,
            request=request,
            accion="CREAR_INDICADOR_CACES_MASIVO",
            descripcion=f"Se registro el indicador {indicador.codigo_indicador} desde modelo CACES.",
            tabla="indicador",
            registro=indicador,
        )

    if created or ensure_existing_storage:
        _try_provision_storage(
            drive_path=build_indicador_drive_path(indicador),
            actor=actor,
            request=request,
            accion="CREAR_CARPETA_INDICADOR_CACES_MASIVO",
            descripcion=f"Se valido la carpeta Graph del indicador {indicador.codigo_indicador}.",
            tabla="indicador",
            registro=indicador,
            storage_context=storage_context,
        )
    return indicador, created


def _ensure_caces_mapeo(*, indicador, modelo, actor=None, request=None):
    from apps.evaluacion.models import IndicadorCacesMapeo

    existing_by_indicator = IndicadorCacesMapeo.objects.filter(indicador=indicador).first()
    if existing_by_indicator:
        if existing_by_indicator.modelo_id != modelo.numero_modelo:
            raise ValueError(
                f"El indicador {indicador.codigo_indicador} ya esta mapeado al modelo "
                f"{existing_by_indicator.modelo_id}."
            )
        return existing_by_indicator, False

    existing_by_model = IndicadorCacesMapeo.objects.filter(modelo=modelo).first()
    if existing_by_model:
        if existing_by_model.indicador_id != indicador.pk:
            raise ValueError(
                f"El modelo CACES {modelo.codigo_modelo} ya esta mapeado a otro indicador."
            )
        return existing_by_model, False

    try:
        with transaction.atomic():
            mapping = IndicadorCacesMapeo.objects.create(
                indicador=indicador,
                modelo=modelo,
                fecha_mapeo=timezone.now(),
                observacion="Mapeo creado por sincronizacion masiva CACES.",
            )
    except IntegrityError:
        existing_by_indicator = IndicadorCacesMapeo.objects.filter(indicador=indicador).first()
        if existing_by_indicator:
            return existing_by_indicator, False
        existing_by_model = IndicadorCacesMapeo.objects.filter(modelo=modelo).first()
        if existing_by_model:
            return existing_by_model, False
        raise
    registrar_evento(
        accion="CREAR_MAPEO_INDICADOR_CACES_MASIVO",
        descripcion=f"Se mapeo el indicador {indicador.codigo_indicador} al modelo {modelo.codigo_modelo}.",
        usuario=actor,
        tipo_evento="ACREDITACION",
        tabla_afectada="indicador_caces_mapeo",
        id_registro=mapping.pk,
        valores_nuevos={
            "indicador_id": indicador.pk,
            "numero_modelo": modelo.numero_modelo,
        },
        criticidad="MEDIA",
        request=request,
    )
    return mapping, True


def sincronizar_catalogo_desde_modelo_caces(
    *,
    actor=None,
    request=None,
    ensure_existing_storage=False,
):
    from apps.evaluacion.models import ModeloIndicadorCaces

    modelos = list(
        ModeloIndicadorCaces.objects.filter(activo=True).order_by("numero_modelo")
    )
    criterion_order = {}
    subcriterion_order = {}
    summary = {
        "modelos": len(modelos),
        "criterios_creados": 0,
        "subcriterios_creados": 0,
        "indicadores_creados": 0,
        "indicadores_existentes": 0,
        "mapeos_creados": 0,
        "mapeos_existentes": 0,
    }
    storage_context = None
    if modelos:
        try:
            graph_payload, graph_access_token = get_graph_session()
            storage_context = {
                "graph_payload": graph_payload,
                "graph_access_token": graph_access_token,
                "refresh": False,
            }
        except GraphServiceError as exc:
            storage_context = {"graph_error": exc}

    for modelo in modelos:
        criterio_nombre = _normalize_text(modelo.criterio)
        subcriterio_nombre = _normalize_text(modelo.subcriterio) or "General"
        if criterio_nombre not in criterion_order:
            criterion_order[criterio_nombre] = len(criterion_order) + 1
        sub_key = (criterio_nombre, subcriterio_nombre)
        if sub_key not in subcriterion_order:
            subcriterion_order[sub_key] = len(
                [key for key in subcriterion_order if key[0] == criterio_nombre]
            ) + 1

        criterio, criterio_created = _ensure_caces_criterio(
            nombre=criterio_nombre,
            order=criterion_order[criterio_nombre],
            actor=actor,
            request=request,
            ensure_existing_storage=ensure_existing_storage,
            storage_context=storage_context,
        )
        subcriterio, subcriterio_created = _ensure_caces_subcriterio(
            criterio=criterio,
            nombre=subcriterio_nombre,
            criterion_order=criterion_order[criterio_nombre],
            subcriterion_order=subcriterion_order[sub_key],
            actor=actor,
            request=request,
            ensure_existing_storage=ensure_existing_storage,
            storage_context=storage_context,
        )
        indicador, indicador_created = _ensure_caces_indicador(
            modelo=modelo,
            subcriterio=subcriterio,
            actor=actor,
            request=request,
            ensure_existing_storage=ensure_existing_storage,
            storage_context=storage_context,
        )
        _mapping, mapping_created = _ensure_caces_mapeo(
            indicador=indicador,
            modelo=modelo,
            actor=actor,
            request=request,
        )

        summary["criterios_creados"] += 1 if criterio_created else 0
        summary["subcriterios_creados"] += 1 if subcriterio_created else 0
        summary["indicadores_creados"] += 1 if indicador_created else 0
        summary["indicadores_existentes"] += 0 if indicador_created else 1
        summary["mapeos_creados"] += 1 if mapping_created else 0
        summary["mapeos_existentes"] += 0 if mapping_created else 1

    _invalidate_acreditacion_metrics_cache()
    registrar_evento(
        accion="SINCRONIZAR_CATALOGO_MODELO_CACES",
        descripcion="Se sincronizo la estructura criterio/subcriterio/indicador desde modelo_indicador_caces.",
        usuario=actor,
        tipo_evento="ACREDITACION",
        tabla_afectada="modelo_indicador_caces / criterio / subcriterio / indicador",
        valores_nuevos=summary,
        criticidad="ALTA",
        request=request,
    )
    return summary


def _actor_role_ids(actor):
    actor_id = getattr(actor, "pk", None)
    if not actor_id:
        return []
    return list(
        UsuarioRol.objects.filter(
            usuario_id=actor_id,
            activo=True,
            rol__activo=True,
        ).values_list("rol_id", flat=True)
    )


@transaction.atomic
def sincronizar_indicadores_ciclo(*, ciclo, indicadores, actor=None, request=None):
    selected_ids = {
        int(getattr(indicador, "pk", indicador))
        for indicador in (indicadores or [])
        if getattr(indicador, "pk", indicador)
    }
    role_ids = _actor_role_ids(actor)
    if not selected_ids or not role_ids:
        return {
            "roles": len(role_ids),
            "indicadores": len(selected_ids),
            "activados": 0,
            "desactivados": 0,
        }

    existing = {
        (access.rol_id, access.indicador_id): access
        for access in RolIndicador.objects.filter(ciclo=ciclo, rol_id__in=role_ids)
    }
    activated = 0
    deactivated = 0
    assigned_at = timezone.now()

    for access in existing.values():
        if access.indicador_id in selected_ids:
            continue
        if access.activo:
            access.activo = False
            access.acceso_total = False
            access.asignado_por = actor
            access.save(update_fields=["activo", "acceso_total", "asignado_por"])
            deactivated += 1

    for role_id in role_ids:
        for indicator_id in selected_ids:
            access = existing.get((role_id, indicator_id))
            if access is None:
                RolIndicador.objects.create(
                    rol_id=role_id,
                    indicador_id=indicator_id,
                    ciclo=ciclo,
                    acceso_total=True,
                    activo=True,
                    fecha_asignacion=assigned_at,
                    asignado_por=actor,
                )
                activated += 1
                continue

            update_fields = []
            if not access.activo:
                access.activo = True
                update_fields.append("activo")
                activated += 1
            if not access.acceso_total:
                access.acceso_total = True
                update_fields.append("acceso_total")
            if access.asignado_por_id != getattr(actor, "pk", None):
                access.asignado_por = actor
                update_fields.append("asignado_por")
            if update_fields:
                access.save(update_fields=update_fields)

    summary = {
        "roles": len(role_ids),
        "indicadores": len(selected_ids),
        "activados": activated,
        "desactivados": deactivated,
    }
    registrar_evento(
        accion="SINCRONIZAR_INDICADORES_CICLO",
        descripcion=f"Se sincronizo la seleccion de indicadores del ciclo {ciclo.nombre}.",
        usuario=actor,
        tipo_evento="ACREDITACION",
        tabla_afectada="rol_indicador",
        id_registro=ciclo.pk,
        valores_nuevos={
            "ciclo_id": ciclo.pk,
            "indicator_ids": sorted(selected_ids),
            **summary,
        },
        criticidad="MEDIA",
        request=request,
    )
    return summary


def crear_criterio(*, form, actor=None, request=None):
    with transaction.atomic():
        criterio = form.save()
        _registrar_evento_catalogo(
            actor=actor,
            request=request,
            accion="CREAR_CRITERIO",
            descripcion=f"Se registro el criterio {criterio.codigo_criterio}.",
            tabla="criterio",
            registro=criterio,
        )
    _invalidate_acreditacion_metrics_cache()
    _try_provision_storage(
        drive_path=build_criterio_drive_path(criterio),
        actor=actor,
        request=request,
        accion="CREAR_CARPETA_CRITERIO",
        descripcion=f"Se creo la carpeta Graph del criterio {criterio.codigo_criterio}.",
        tabla="criterio",
        registro=criterio,
    )
    return criterio


def crear_subcriterio(*, form, actor=None, request=None):
    with transaction.atomic():
        subcriterio = form.save()
        _registrar_evento_catalogo(
            actor=actor,
            request=request,
            accion="CREAR_SUBCRITERIO",
            descripcion=f"Se registro el subcriterio {subcriterio.codigo_subcriterio}.",
            tabla="subcriterio",
            registro=subcriterio,
        )
    _invalidate_acreditacion_metrics_cache()
    _try_provision_storage(
        drive_path=build_subcriterio_drive_path(subcriterio),
        actor=actor,
        request=request,
        accion="CREAR_CARPETA_SUBCRITERIO",
        descripcion=f"Se creo la carpeta Graph del subcriterio {subcriterio.codigo_subcriterio}.",
        tabla="subcriterio",
        registro=subcriterio,
    )
    return subcriterio


def crear_indicador(*, form, actor=None, request=None):
    with transaction.atomic():
        indicador = form.save()
        _registrar_evento_catalogo(
            actor=actor,
            request=request,
            accion="CREAR_INDICADOR",
            descripcion=f"Se registro el indicador {indicador.codigo_indicador}.",
            tabla="indicador",
            registro=indicador,
        )
    _invalidate_acreditacion_metrics_cache()
    _try_provision_storage(
        drive_path=build_indicador_drive_path(indicador),
        actor=actor,
        request=request,
        accion="CREAR_CARPETA_INDICADOR",
        descripcion=f"Se creo la carpeta Graph del indicador {indicador.codigo_indicador}.",
        tabla="indicador",
        registro=indicador,
    )
    return indicador


def crear_elemento(*, form, actor=None, request=None):
    with transaction.atomic():
        elemento = form.save()
        _registrar_evento_catalogo(
            actor=actor,
            request=request,
            accion="CREAR_ELEMENTO_FUNDAMENTAL",
            descripcion=f"Se registro el elemento {elemento.codigo_elemento}.",
            tabla="elemento_fundamental",
            registro=elemento,
        )
    _invalidate_acreditacion_metrics_cache()
    _try_provision_storage(
        drive_path=build_elemento_drive_path(elemento.indicador, elemento),
        actor=actor,
        request=request,
        accion="CREAR_CARPETA_ELEMENTO",
        descripcion=f"Se creo la carpeta Graph del elemento {elemento.codigo_elemento}.",
        tabla="elemento_fundamental",
        registro=elemento,
        extra={"indicador_id": elemento.indicador_id},
    )
    return elemento


@transaction.atomic
def vincular_indicador_elemento(*, indicador, elemento_fundamental, actor=None, request=None):
    indicador_anterior_id = elemento_fundamental.indicador_id
    if indicador_anterior_id == indicador.pk:
        return elemento_fundamental
    if _element_has_linked_content(elemento_fundamental=elemento_fundamental):
        raise ValueError(
            "No puedes mover este elemento a otro indicador porque ya tiene documentos o evidencias registradas."
        )
    elemento_fundamental.indicador = indicador
    elemento_fundamental.save(update_fields=["indicador"])
    storage = _provision_storage(
        drive_path=build_elemento_drive_path(indicador, elemento_fundamental),
    )
    registrar_evento(
        accion="VINCULAR_INDICADOR_ELEMENTO",
        descripcion=f"Se vinculo el elemento {elemento_fundamental.codigo_elemento} al indicador {indicador.codigo_indicador}.",
        usuario=actor,
        tipo_evento="ACREDITACION",
        tabla_afectada="elemento_fundamental",
        id_registro=elemento_fundamental.pk,
        valores_anteriores={
            "indicador_id": indicador_anterior_id,
        },
        valores_nuevos={
            "indicador_id": indicador.pk,
            "elemento_id": elemento_fundamental.pk,
            "ruta_drive": storage["drive_path"].as_posix(),
            "ruta_espejo_local": str(storage["local_path"]) if storage.get("local_path") else None,
            "graph_web_url": (storage["graph_item"] or {}).get("webUrl"),
        },
        criticidad="MEDIA",
        request=request,
    )
    return elemento_fundamental


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
    ciclo = form.save(commit=False)
    ciclo.documento_autorizacion = authorization_result["documento"]
    if (getattr(form.cleaned_data["estado"], "descripcion", "") or "").strip().upper() == "APROBADO":
        ciclo.aprobado_por = actor
        ciclo.fecha_aprobacion = timezone.now()
    ciclo.save()
    sincronizar_indicadores_ciclo(
        ciclo=ciclo,
        indicadores=form.cleaned_data.get("indicadores_evaluar"),
        actor=actor,
        request=request,
    )
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
            "ruta_espejo_local": (
                str(authorization_result["local_mirror_path"])
                if authorization_result.get("local_mirror_path")
                else None
            ),
            "graph_web_url": (authorization_result["graph_item"] or {}).get("webUrl"),
        },
        criticidad="ALTA",
        request=request,
    )
    return ciclo


@transaction.atomic
def actualizar_estado_ciclo(
    *,
    ciclo,
    estado,
    observacion_aprobacion: str | None = None,
    actor=None,
    request=None,
):
    estado_destino = (getattr(estado, "descripcion", "") or "").strip().upper()
    if estado_destino == "APROBADO" and not authorization_document_exists_for_cycle(ciclo):
        raise ValueError(
            "No puedes aprobar el ciclo si no existe su documento de autorizacion."
        )

    estado_anterior = getattr(ciclo.estado, "descripcion", None)
    ciclo.estado = estado
    update_fields = ["estado"]
    if estado_destino == "APROBADO":
        ciclo.aprobado_por = actor
        ciclo.fecha_aprobacion = timezone.now()
        ciclo.observacion_aprobacion = observacion_aprobacion
        update_fields.extend(
            ["aprobado_por", "fecha_aprobacion", "observacion_aprobacion"]
        )
    elif observacion_aprobacion:
        ciclo.observacion_aprobacion = observacion_aprobacion
        update_fields.append("observacion_aprobacion")
    ciclo.save(update_fields=update_fields)
    registrar_evento(
        accion="ACTUALIZAR_ESTADO_CICLO",
        descripcion=f"Se actualizo el estado del ciclo {ciclo.nombre} a {estado.descripcion}.",
        usuario=actor,
        tipo_evento="ACREDITACION",
        tabla_afectada="ciclo_evaluacion",
        id_registro=ciclo.pk,
        valores_anteriores={"estado": estado_anterior},
        valores_nuevos={
            "estado": estado.descripcion,
            "aprobado_por": getattr(actor, "pk", None) if estado_destino == "APROBADO" else ciclo.aprobado_por_id,
            "fecha_aprobacion": ciclo.fecha_aprobacion.isoformat() if ciclo.fecha_aprobacion else None,
            "observacion_aprobacion": ciclo.observacion_aprobacion,
        },
        criticidad="MEDIA",
        request=request,
    )
    return ciclo
