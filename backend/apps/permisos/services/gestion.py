from django.db import transaction
from django.utils import timezone

from apps.acreditacion.models import ElementoFundamental, RolIndicador, RolIndicadorElemento
from apps.auditoria.services import registrar_evento
from apps.permisos.models import Permiso, Rol
from apps.usuarios.models import RolPermiso, UsuarioRol


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
        permisos_map = {
            permiso.pk: permiso for permiso in Permiso.objects.filter(pk__in=create_ids)
        }
        for permiso_id in create_ids:
            RolPermiso.objects.create(rol=rol, permiso=permisos_map[permiso_id])
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
        asignacion.save(update_fields=["activo", "fecha_revocacion", "asignado_por"])
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
        descripcion=f"Se asignó el rol {rol.nombre_rol} al usuario {usuario.nombre_completo}.",
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
        descripcion=f"Se revocó el rol {asignacion.rol.nombre_rol} al usuario {asignacion.usuario.nombre_completo}.",
        criticidad="MEDIA",
        request=request,
    )


@transaction.atomic
def asignar_rol_indicador(
    *, rol, indicador, ciclo, acceso_total=False, actor=None, request=None
):
    assigned_at = timezone.now()
    acceso = RolIndicador.objects.filter(rol=rol, indicador=indicador, ciclo=ciclo).first()
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
        descripcion=f"Se asignó acceso del rol {rol.nombre_rol} al indicador {indicador.codigo_indicador}.",
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
        descripcion=f"Se desactivó el acceso del rol {acceso.rol.nombre_rol} al indicador {acceso.indicador.codigo_indicador}.",
        criticidad="MEDIA",
        request=request,
    )


@transaction.atomic
def asignar_rol_indicador_elemento(*, rol_indicador, elemento_fundamental, actor=None, request=None):
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
    selected_indicator_ids = {int(value) for value in indicator_ids}
    selected_total_ids = {int(value) for value in total_indicator_ids}
    selected_element_ids = {int(value) for value in element_ids}

    element_map = {}
    for element in ElementoFundamental.objects.filter(
        activo=True,
        indicador_id__in=selected_indicator_ids,
    ).only("id_elemento_fundamental", "indicador"):
        element_map.setdefault(element.indicador_id, set()).add(element.pk)

    existing_accesses = {
        access.indicador_id: access
        for access in RolIndicador.objects.filter(rol=rol, ciclo=ciclo).select_related(
            "indicador"
        )
    }

    activated_count = 0
    deactivated_count = 0
    synced_element_count = 0

    for indicator_id, access in existing_accesses.items():
        if indicator_id not in selected_indicator_ids:
            RolIndicadorElemento.objects.filter(rol_indicador=access).delete()
            if access.activo or access.acceso_total:
                access.activo = False
                access.acceso_total = False
                access.asignado_por = actor
                access.save(update_fields=["activo", "acceso_total", "asignado_por"])
                deactivated_count += 1

    for indicator_id in selected_indicator_ids:
        desired_total = indicator_id in selected_total_ids
        access = existing_accesses.get(indicator_id)
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
            activated_count += 1
        else:
            update_fields = []
            if not access.activo:
                access.activo = True
                update_fields.append("activo")
                activated_count += 1
            if access.acceso_total != desired_total:
                access.acceso_total = desired_total
                update_fields.append("acceso_total")
            if access.asignado_por_id != getattr(actor, "pk", None):
                access.asignado_por = actor
                update_fields.append("asignado_por")
            if update_fields:
                access.save(update_fields=update_fields)

        desired_element_ids = (
            element_map.get(indicator_id, set())
            if desired_total
            else {
                element_id
                for element_id in selected_element_ids
                if element_id in element_map.get(indicator_id, set())
            }
        )
        current_element_ids = set(
            RolIndicadorElemento.objects.filter(rol_indicador=access).values_list(
                "elemento_fundamental_id", flat=True
            )
        )
        create_ids = desired_element_ids - current_element_ids
        delete_ids = current_element_ids - desired_element_ids

        for element_id in create_ids:
            RolIndicadorElemento.objects.create(
                rol_indicador=access,
                elemento_fundamental_id=element_id,
                fecha_asignacion=assigned_at,
                asignado_por=actor,
            )
        if delete_ids:
            RolIndicadorElemento.objects.filter(
                rol_indicador=access,
                elemento_fundamental_id__in=delete_ids,
            ).delete()
        synced_element_count += len(desired_element_ids)

    registrar_evento(
        usuario=actor,
        accion="SINCRONIZAR ACCESO ESTRUCTURAL",
        tipo_evento="PERMISOS",
        tabla_afectada="rol_indicador / rol_indicador_elemento",
        id_registro=rol.pk,
        descripcion=(
            f"Se sincronizo el acceso estructural del rol {rol.nombre_rol} "
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
    return {
        "activated_count": activated_count,
        "deactivated_count": deactivated_count,
        "synced_element_count": synced_element_count,
    }
