from __future__ import annotations

from django.db.models import Q

from apps.acreditacion.models import RolIndicador, RolIndicadorElemento
from apps.core.services.navigation_service import ROLE_EVALUATOR, ROLE_EXTERNAL
from apps.documentos.models import Documento
from apps.documentos.selectors.authorization_selector import get_authorization_root_context
from apps.evaluacion.models import TareaEvidencia
from apps.evidencias.models import RegistroEvidencia
from apps.seguridad.permissions import (
    usuario_tiene_acceso_global,
    usuario_tiene_permiso,
    usuario_tiene_permiso_modulo,
)
from apps.usuarios.models import UsuarioRol


EVALUATOR_RELEASED_EVIDENCE_STATES = {
    "ENVIADA_EVALUADOR",
    "EN_REVISION_EVALUADOR",
    "REENVIADA",
}


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


def _has_matching_task_access(registros, *, actor) -> bool:
    actor_id = getattr(actor, "pk", None)
    if not actor_id:
        return False

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
        if TareaEvidencia.objects.filter(
            Q(usuario_responsable_id=actor_id) | Q(asignado_por_id=actor_id),
            ciclo_id=ciclo_id,
            indicador_id=indicador_id,
            elemento_fundamental_id=elemento_id,
            activo=True,
        ).exists():
            return True
    return False


def _actor_has_any_role(actor, role_names: set[str]) -> bool:
    actor_id = getattr(actor, "pk", None)
    if not actor_id:
        return False
    role_filter = Q()
    for role_name in role_names:
        role_filter |= Q(rol__nombre_rol__iexact=role_name)
    if not role_filter:
        return False
    return UsuarioRol.objects.filter(
        usuario_id=actor_id,
        activo=True,
        rol__activo=True,
    ).filter(role_filter).exists()


def _has_released_evaluator_access(registros, *, actor) -> bool:
    if not _actor_has_any_role(actor, {ROLE_EVALUATOR, ROLE_EXTERNAL}):
        return False
    for registro in registros:
        state = (
            getattr(getattr(registro, "estado", None), "descripcion", "") or ""
        ).strip().upper()
        if getattr(registro, "fecha_envio_revision", None) or state in EVALUATOR_RELEASED_EVIDENCE_STATES:
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
        RegistroEvidencia.objects.select_related("elemento_fundamental", "estado")
        .filter(documento=documento)
    )
    if not registros:
        return usuario_tiene_permiso_modulo(actor, "DOCUMENTOS")

    if _has_matching_task_access(registros, actor=actor):
        return True
    if _has_released_evaluator_access(registros, actor=actor):
        return True

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
    if not usuario_puede_acceder_documento(actor, documento):
        return None
    return documento
