from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from apps.acreditacion.models import (
    ElementoFundamental,
    RolIndicador,
    RolIndicadorElemento,
)
from apps.auditoria.services import registrar_evento
from apps.permisos.models import Permiso
from apps.usuarios.models import Rol, RolPermiso, UsuarioAreaCargo, UsuarioRol


@transaction.atomic
def crear_rol(form, actor=None, request=None):
    rol = form.save()
    registrar_evento(
        usuario=actor,
        accion="CREAR ROL",
        tipo_evento="PERMISOS",
        tabla_afectada="rol",
        id_registro=rol.pk,
        descripcion=f"Se creó el rol {rol.nombre_rol}.",
        valores_nuevos={
            "nombre_rol": rol.nombre_rol,
            "descripcion": rol.descripcion,
            "acceso_global": rol.acceso_global,
            "activo": rol.activo,
        },
        criticidad="MEDIA",
        request=request,
    )
    return rol


@transaction.atomic
def actualizar_rol(form, actor=None, request=None):
    rol = form.save()
    registrar_evento(
        usuario=actor,
        accion="ACTUALIZAR ROL",
        tipo_evento="PERMISOS",
        tabla_afectada="rol",
        id_registro=rol.pk,
        descripcion=f"Se actualizó el rol {rol.nombre_rol}.",
        valores_nuevos={
            "nombre_rol": rol.nombre_rol,
            "descripcion": rol.descripcion,
            "acceso_global": rol.acceso_global,
            "activo": rol.activo,
        },
        criticidad="MEDIA",
        request=request,
    )
    return rol


@transaction.atomic
def crear_permiso(form, actor=None, request=None):
    permiso = form.save()
    registrar_evento(
        usuario=actor,
        accion="CREAR PERMISO",
        tipo_evento="PERMISOS",
        tabla_afectada="permiso",
        id_registro=permiso.pk,
        descripcion=f"Se creó el permiso {permiso.codigo_permiso}.",
        valores_nuevos={
            "codigo_permiso": permiso.codigo_permiso,
            "descripcion": permiso.descripcion,
            "modulo": permiso.modulo,
            "activo": permiso.activo,
        },
        criticidad="MEDIA",
        request=request,
    )
    return permiso


@transaction.atomic
def sincronizar_permisos_rol(*, rol, permisos, actor=None, request=None):
    selected_ids = {permiso.pk for permiso in permisos}
    current_ids = set(rol.permisos_asignados.values_list("permiso_id", flat=True))

    create_ids = selected_ids - current_ids
    delete_ids = current_ids - selected_ids

    if create_ids:
        RolPermiso.objects.bulk_create(
            [RolPermiso(rol=rol, permiso_id=permiso_id) for permiso_id in create_ids]
        )

    if delete_ids:
        RolPermiso.objects.filter(rol=rol, permiso_id__in=delete_ids).delete()

    registrar_evento(
        usuario=actor,
        accion="SINCRONIZAR PERMISOS DE ROL",
        tipo_evento="PERMISOS",
        tabla_afectada="rol_permiso",
        id_registro=rol.pk,
        descripcion=f"Se actualizaron los permisos del rol {rol.nombre_rol}.",
        valores_nuevos={
            "rol": rol.nombre_rol,
            "permisos_ids": sorted(selected_ids),
        },
        criticidad="MEDIA",
        request=request,
    )


@transaction.atomic
def asignar_usuario_rol(*, usuario, rol, activo=True, actor=None, request=None):
    asignacion = UsuarioRol.objects.filter(usuario=usuario, rol=rol).first()

    if asignacion:
        asignacion.activo = activo
        asignacion.fecha_revocacion = None if activo else timezone.now()
        asignacion.asignado_por = actor
        asignacion.save(
            update_fields=["activo", "fecha_revocacion", "asignado_por"]
        )
    else:
        asignacion = UsuarioRol.objects.create(
            usuario=usuario,
            rol=rol,
            activo=activo,
            asignado_por=actor,
        )

    registrar_evento(
        usuario=actor,
        accion="ASIGNAR USUARIO ROL",
        tipo_evento="PERMISOS",
        tabla_afectada="usuario_rol",
        id_registro=asignacion.pk,
        descripcion=(
            f"Se asignó el rol {rol.nombre_rol} "
            f"al usuario {usuario.nombre_completo}."
        ),
        valores_nuevos={
            "usuario_id": usuario.pk,
            "rol_id": rol.pk,
            "activo": activo,
        },
        criticidad="MEDIA",
        request=request,
    )
    return asignacion


@transaction.atomic
def revocar_usuario_rol(*, asignacion, actor=None, request=None):
    asignacion.activo = False
    asignacion.fecha_revocacion = timezone.now()
    asignacion.asignado_por = actor
    asignacion.save(update_fields=["activo", "fecha_revocacion", "asignado_por"])

    registrar_evento(
        usuario=actor,
        accion="REVOCAR USUARIO ROL",
        tipo_evento="PERMISOS",
        tabla_afectada="usuario_rol",
        id_registro=asignacion.pk,
        descripcion=(
            f"Se revocó el rol {asignacion.rol.nombre_rol} "
            f"al usuario {asignacion.usuario.nombre_completo}."
        ),
        criticidad="MEDIA",
        request=request,
    )


@transaction.atomic
def asignar_rol_indicador(
    *, rol, indicador, ciclo, acceso_total=False, actor=None, request=None
):
    assigned_at = timezone.now()
    acceso = RolIndicador.objects.filter(
        rol=rol,
        indicador=indicador,
        ciclo=ciclo,
    ).first()

    if acceso:
        acceso.acceso_total = acceso_total
        acceso.activo = True
        acceso.asignado_por = actor
        acceso.save(update_fields=["acceso_total", "activo", "asignado_por"])
    else:
        acceso = RolIndicador.objects.create(
            rol=rol,
            indicador=indicador,
            ciclo=ciclo,
            acceso_total=acceso_total,
            activo=True,
            fecha_asignacion=assigned_at,
            asignado_por=actor,
        )

    registrar_evento(
        usuario=actor,
        accion="ASIGNAR ACCESO POR INDICADOR",
        tipo_evento="PERMISOS",
        tabla_afectada="rol_indicador",
        id_registro=acceso.pk,
        descripcion=(
            f"Se asignó acceso del rol {rol.nombre_rol} "
            f"al indicador {indicador.codigo_indicador}."
        ),
        valores_nuevos={
            "rol_id": rol.pk,
            "indicador_id": indicador.pk,
            "ciclo_id": ciclo.pk,
            "acceso_total": acceso_total,
        },
        criticidad="MEDIA",
        request=request,
    )
    return acceso


@transaction.atomic
def desactivar_rol_indicador(*, acceso, actor=None, request=None):
    acceso.activo = False
    acceso.asignado_por = actor
    acceso.save(update_fields=["activo", "asignado_por"])

    registrar_evento(
        usuario=actor,
        accion="DESACTIVAR ACCESO POR INDICADOR",
        tipo_evento="PERMISOS",
        tabla_afectada="rol_indicador",
        id_registro=acceso.pk,
        descripcion=(
            f"Se desactivó el acceso del rol {acceso.rol.nombre_rol} "
            f"al indicador {acceso.indicador.codigo_indicador}."
        ),
        criticidad="MEDIA",
        request=request,
    )


@transaction.atomic
def asignar_rol_indicador_elemento(
    *, rol_indicador, elemento_fundamental, actor=None, request=None
):
    acceso = RolIndicadorElemento.objects.filter(
        rol_indicador=rol_indicador,
        elemento_fundamental=elemento_fundamental,
    ).first()

    if acceso:
        return acceso

    acceso = RolIndicadorElemento.objects.create(
        rol_indicador=rol_indicador,
        elemento_fundamental=elemento_fundamental,
        fecha_asignacion=timezone.now(),
        asignado_por=actor,
    )

    registrar_evento(
        usuario=actor,
        accion="ASIGNAR ACCESO POR ELEMENTO",
        tipo_evento="PERMISOS",
        tabla_afectada="rol_indicador_elemento",
        descripcion=(
            f"Se asignó el elemento {elemento_fundamental.codigo_elemento} "
            f"al acceso {rol_indicador.pk}."
        ),
        valores_nuevos={
            "rol_indicador_id": rol_indicador.pk,
            "elemento_fundamental_id": elemento_fundamental.pk,
        },
        criticidad="MEDIA",
        request=request,
    )
    return acceso


@transaction.atomic
def eliminar_rol_indicador_elemento(*, acceso, actor=None, request=None):
    detalle = {
        "rol_indicador_id": acceso.rol_indicador_id,
        "elemento_fundamental_id": acceso.elemento_fundamental_id,
    }

    acceso.delete()

    registrar_evento(
        usuario=actor,
        accion="ELIMINAR ACCESO POR ELEMENTO",
        tipo_evento="PERMISOS",
        tabla_afectada="rol_indicador_elemento",
        descripcion="Se eliminó una asignación de elemento fundamental.",
        valores_anteriores=detalle,
        criticidad="MEDIA",
        request=request,
    )


def _to_int_set(values):
    return {int(value) for value in (values or [])}


def _build_element_map(selected_indicator_ids):
    element_map = defaultdict(set)

    if not selected_indicator_ids:
        return element_map

    queryset = ElementoFundamental.objects.filter(
        activo=True,
        indicador_id__in=selected_indicator_ids,
    ).only("id_elemento_fundamental", "indicador_id")

    for element in queryset:
        element_map[element.indicador_id].add(element.pk)

    return element_map


def _load_existing_accesses(*, rol, ciclo):
    queryset = RolIndicador.objects.filter(rol=rol, ciclo=ciclo)
    return {access.indicador_id: access for access in queryset}


def _load_current_elements_by_access(access_ids):
    elements_by_access = defaultdict(set)

    if not access_ids:
        return elements_by_access

    queryset = RolIndicadorElemento.objects.filter(
        rol_indicador_id__in=access_ids
    ).values_list("rol_indicador_id", "elemento_fundamental_id")

    for access_id, element_id in queryset:
        elements_by_access[access_id].add(element_id)

    return elements_by_access


def _deactivate_unselected_accesses(
    *, existing_accesses, selected_indicator_ids, actor, elements_by_access
):
    deactivated_count = 0

    for indicator_id, access in existing_accesses.items():
        if indicator_id in selected_indicator_ids:
            continue

        RolIndicadorElemento.objects.filter(rol_indicador=access).delete()
        elements_by_access[access.pk] = set()

        if access.activo or access.acceso_total:
            access.activo = False
            access.acceso_total = False
            access.asignado_por = actor
            access.save(update_fields=["activo", "acceso_total", "asignado_por"])
            deactivated_count += 1

    return deactivated_count


def _ensure_indicator_access(
    *,
    existing_accesses,
    rol,
    ciclo,
    indicator_id,
    desired_total,
    assigned_at,
    actor,
):
    access = existing_accesses.get(indicator_id)
    activated_count = 0

    if access is None:
        access = RolIndicador.objects.create(
            rol=rol,
            indicador_id=indicator_id,
            ciclo=ciclo,
            acceso_total=desired_total,
            activo=True,
            fecha_asignacion=assigned_at,
            asignado_por=actor,
        )
        existing_accesses[indicator_id] = access
        return access, 1

    update_fields = []

    if not access.activo:
        access.activo = True
        update_fields.append("activo")
        activated_count = 1

    if access.acceso_total != desired_total:
        access.acceso_total = desired_total
        update_fields.append("acceso_total")

    if access.asignado_por_id != getattr(actor, "pk", None):
        access.asignado_por = actor
        update_fields.append("asignado_por")

    if update_fields:
        access.save(update_fields=update_fields)

    return access, activated_count


def _get_desired_element_ids(
    *, indicator_id, desired_total, selected_element_ids, element_map
):
    available_element_ids = element_map.get(indicator_id, set())

    if desired_total:
        return set(available_element_ids)

    return available_element_ids.intersection(selected_element_ids)


def _sync_access_elements(
    *, access, desired_element_ids, assigned_at, actor, elements_by_access
):
    current_element_ids = elements_by_access.get(access.pk, set())

    create_ids = desired_element_ids - current_element_ids
    delete_ids = current_element_ids - desired_element_ids

    if create_ids:
        RolIndicadorElemento.objects.bulk_create(
            [
                RolIndicadorElemento(
                    rol_indicador=access,
                    elemento_fundamental_id=element_id,
                    fecha_asignacion=assigned_at,
                    asignado_por=actor,
                )
                for element_id in create_ids
            ]
        )

    if delete_ids:
        RolIndicadorElemento.objects.filter(
            rol_indicador=access,
            elemento_fundamental_id__in=delete_ids,
        ).delete()

    elements_by_access[access.pk] = set(desired_element_ids)
    return len(desired_element_ids)


def _registrar_evento_sincronizacion(
    *,
    rol,
    ciclo,
    selected_indicator_ids,
    selected_total_ids,
    selected_element_ids,
    activated_count,
    deactivated_count,
    synced_element_count,
    actor,
    request,
):
    registrar_evento(
        usuario=actor,
        accion="SINCRONIZAR ACCESO ESTRUCTURAL",
        tipo_evento="PERMISOS",
        tabla_afectada="rol_indicador / rol_indicador_elemento",
        id_registro=rol.pk,
        descripcion=(
            f"Se sincronizó el acceso estructural del rol {rol.nombre_rol} "
            f"para el ciclo {ciclo.nombre}."
        ),
        valores_nuevos={
            "rol_id": rol.pk,
            "ciclo_id": ciclo.pk,
            "indicator_ids": sorted(selected_indicator_ids),
            "total_indicator_ids": sorted(selected_total_ids),
            "element_ids": sorted(selected_element_ids),
            "activated_count": activated_count,
            "deactivated_count": deactivated_count,
            "synced_element_count": synced_element_count,
        },
        criticidad="MEDIA",
        request=request,
    )


@transaction.atomic
def sincronizar_acceso_estructura(
    *,
    rol,
    ciclo,
    indicator_ids,
    total_indicator_ids,
    element_ids,
    actor=None,
    request=None,
):
    assigned_at = timezone.now()
    selected_indicator_ids = _to_int_set(indicator_ids)
    selected_total_ids = _to_int_set(total_indicator_ids) & selected_indicator_ids
    selected_element_ids = _to_int_set(element_ids)

    element_map = _build_element_map(selected_indicator_ids)
    existing_accesses = _load_existing_accesses(rol=rol, ciclo=ciclo)
    elements_by_access = _load_current_elements_by_access(
        [access.pk for access in existing_accesses.values()]
    )

    activated_count = 0
    synced_element_count = 0
    deactivated_count = _deactivate_unselected_accesses(
        existing_accesses=existing_accesses,
        selected_indicator_ids=selected_indicator_ids,
        actor=actor,
        elements_by_access=elements_by_access,
    )

    for indicator_id in sorted(selected_indicator_ids):
        desired_total = indicator_id in selected_total_ids

        access, activated_delta = _ensure_indicator_access(
            existing_accesses=existing_accesses,
            rol=rol,
            ciclo=ciclo,
            indicator_id=indicator_id,
            desired_total=desired_total,
            assigned_at=assigned_at,
            actor=actor,
        )
        activated_count += activated_delta

        desired_element_ids = _get_desired_element_ids(
            indicator_id=indicator_id,
            desired_total=desired_total,
            selected_element_ids=selected_element_ids,
            element_map=element_map,
        )

        synced_element_count += _sync_access_elements(
            access=access,
            desired_element_ids=desired_element_ids,
            assigned_at=assigned_at,
            actor=actor,
            elements_by_access=elements_by_access,
        )

    _registrar_evento_sincronizacion(
        rol=rol,
        ciclo=ciclo,
        selected_indicator_ids=selected_indicator_ids,
        selected_total_ids=selected_total_ids,
        selected_element_ids=selected_element_ids,
        activated_count=activated_count,
        deactivated_count=deactivated_count,
        synced_element_count=synced_element_count,
        actor=actor,
        request=request,
    )

    return {
        "activated_count": activated_count,
        "deactivated_count": deactivated_count,
        "synced_element_count": synced_element_count,
    }


def _director_user_ids_queryset():
    return (
        UsuarioAreaCargo.objects.filter(
            activo=True,
            usuario__activo=True,
            area__activo=True,
            cargo__activo=True,
            cargo__nombre_cargo__icontains="DIRECTOR",
        )
        .values_list("usuario_id", flat=True)
        .distinct()
    )


def _active_role_ids_for_users(user_ids):
    if not user_ids:
        return {}, set()

    role_rows = UsuarioRol.objects.filter(
        activo=True,
        usuario_id__in=user_ids,
        rol__activo=True,
    ).values_list("usuario_id", "rol_id")

    role_ids_by_user = defaultdict(set)
    role_ids = set()

    for user_id, role_id in role_rows:
        role_ids_by_user[user_id].add(role_id)
        role_ids.add(role_id)

    return role_ids_by_user, role_ids


@transaction.atomic
def sincronizar_acceso_estructura_directores(
    *,
    ciclo,
    indicator_ids,
    total_indicator_ids,
    element_ids,
    director_ids,
    assign_all_directors=False,
    actor=None,
    request=None,
):
    director_ids = {int(value) for value in (director_ids or [])}
    all_director_ids = set(_director_user_ids_queryset())

    if assign_all_directors:
        target_director_ids = all_director_ids
    else:
        target_director_ids = director_ids & all_director_ids

    if not target_director_ids:
        return {
            "directors_targeted": 0,
            "roles_synced": 0,
            "directors_without_roles": 0,
            "activated_count": 0,
            "deactivated_count": 0,
            "synced_element_count": 0,
        }

    role_ids_by_user, role_ids = _active_role_ids_for_users(target_director_ids)
    roles = {
        role.pk: role
        for role in Rol.objects.filter(pk__in=role_ids, activo=True).only("id_rol", "nombre_rol", "activo")
    }

    summary = {
        "directors_targeted": len(target_director_ids),
        "roles_synced": 0,
        "directors_without_roles": 0,
        "activated_count": 0,
        "deactivated_count": 0,
        "synced_element_count": 0,
    }

    consolidated_role_ids = set()
    for user_id in target_director_ids:
        user_role_ids = {role_id for role_id in role_ids_by_user.get(user_id, set()) if role_id in roles}
        if not user_role_ids:
            summary["directors_without_roles"] += 1
            continue
        consolidated_role_ids.update(user_role_ids)

    for role_id in sorted(consolidated_role_ids):
        role = roles[role_id]
        result = sincronizar_acceso_estructura(
            rol=role,
            ciclo=ciclo,
            indicator_ids=indicator_ids,
            total_indicator_ids=total_indicator_ids,
            element_ids=element_ids,
            actor=actor,
            request=request,
        )
        summary["roles_synced"] += 1
        summary["activated_count"] += result["activated_count"]
        summary["deactivated_count"] += result["deactivated_count"]
        summary["synced_element_count"] += result["synced_element_count"]

    registrar_evento(
        usuario=actor,
        accion="SINCRONIZAR ACCESO ESTRUCTURAL DIRECTORES",
        tipo_evento="PERMISOS",
        tabla_afectada="usuario_area_cargo / usuario_rol / rol_indicador",
        id_registro=getattr(ciclo, "pk", None),
        descripcion=(
            f"Se sincronizó el acceso estructural para directores en el ciclo {ciclo.nombre}."
        ),
        valores_nuevos={
            "ciclo_id": ciclo.pk,
            "assign_all_directors": bool(assign_all_directors),
            "target_director_ids": sorted(target_director_ids),
            "indicator_ids": sorted({int(value) for value in (indicator_ids or [])}),
            "total_indicator_ids": sorted({int(value) for value in (total_indicator_ids or [])}),
            "element_ids": sorted({int(value) for value in (element_ids or [])}),
            **summary,
        },
        criticidad="MEDIA",
        request=request,
    )

    return summary
