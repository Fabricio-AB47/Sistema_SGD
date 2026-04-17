from __future__ import annotations

from apps.acreditacion.models import RolIndicador, RolIndicadorElemento
from apps.documentos.models import Documento
from apps.documentos.selectors.authorization_selector import get_authorization_root_context
from apps.evidencias.models import RegistroEvidencia
from apps.seguridad.permissions import (
    usuario_tiene_acceso_global,
    usuario_tiene_permiso,
    usuario_tiene_permiso_modulo,
)


def _is_authorization_document(documento) -> bool:
    clasificacion_codigo = (
        getattr(getattr(documento, "clasificacion", None), "codigo", "") or ""
    ).strip().upper()
    if clasificacion_codigo in {"AUT_CICLO", "ACTA"}:
        return True
    if getattr(documento, "ciclos_autorizados", None) is not None:
        if documento.ciclos_autorizados.exists():
            return True
    drive_root = get_authorization_root_context()["drive_root"]
    ruta_local = (getattr(documento, "ruta_local", "") or "").strip()
    return bool(ruta_local and drive_root and ruta_local.startswith(drive_root))


def _has_matching_structural_access(
    registros,
    *,
    total_access_pairs: set[tuple[int, int]],
    explicit_element_access: set[tuple[int, int, int]],
) -> bool:
    for registro in registros:
        indicador_id = registro.indicador_id or getattr(
            getattr(registro, "elemento_fundamental", None),
            "indicador_id",
            None,
        )
        ciclo_id = registro.ciclo_id
        elemento_id = registro.elemento_fundamental_id
        if not indicador_id or not ciclo_id or not elemento_id:
            continue
        if (indicador_id, ciclo_id) in total_access_pairs:
            return True
        if (indicador_id, ciclo_id, elemento_id) in explicit_element_access:
            return True
    return False


def usuario_puede_acceder_documento(actor, documento) -> bool:
    if actor is None or documento is None or not getattr(documento, "activo", False):
        return False
    if usuario_tiene_acceso_global(actor):
        return True
    if getattr(documento, "subido_por_id", None) == getattr(actor, "pk", None):
        return True
    if _is_authorization_document(documento):
        return (
            usuario_tiene_permiso(actor, "documentos.ver")
            or usuario_tiene_permiso(actor, "ciclos.gestionar")
            or usuario_tiene_permiso_modulo(actor, "DOCUMENTOS")
            or usuario_tiene_permiso_modulo(actor, "ACREDITACION")
        )

    registros = list(
        RegistroEvidencia.objects.select_related("elemento_fundamental")
        .filter(documento=documento)
    )
    if not registros:
        return usuario_tiene_permiso_modulo(actor, "DOCUMENTOS")

    active_accesses = list(
        RolIndicador.objects.filter(
            rol__usuarios__usuario=actor,
            rol__usuarios__activo=True,
            rol__activo=True,
            activo=True,
        )
        .distinct()
        .values_list("id_rol_indicador", "indicador_id", "ciclo_id", "acceso_total")
    )
    if not active_accesses:
        return False

    total_access_pairs = {
        (indicador_id, ciclo_id)
        for _, indicador_id, ciclo_id, acceso_total in active_accesses
        if acceso_total
    }
    explicit_access_ids = [
        access_id
        for access_id, _, _, acceso_total in active_accesses
        if not acceso_total
    ]
    explicit_element_access = set()
    if explicit_access_ids:
        explicit_element_access = {
            (indicador_id, ciclo_id, elemento_id)
            for indicador_id, ciclo_id, elemento_id in RolIndicadorElemento.objects.filter(
                rol_indicador_id__in=explicit_access_ids
            ).values_list(
                "rol_indicador__indicador_id",
                "rol_indicador__ciclo_id",
                "elemento_fundamental_id",
            )
        }

    return _has_matching_structural_access(
        registros,
        total_access_pairs=total_access_pairs,
        explicit_element_access=explicit_element_access,
    )


def get_documento_for_access(documento_id: int, *, actor=None):
    documento = (
        Documento.objects.select_related("clasificacion", "subido_por")
        .filter(pk=documento_id, activo=True)
        .first()
    )
    if documento is None:
        return None
    # Regla operativa vigente: cualquier usuario autenticado puede observar
    # documentos activos desde las vistas protegidas (abrir/preview/descargar/graph).
    if actor is None:
        return None
    return documento
