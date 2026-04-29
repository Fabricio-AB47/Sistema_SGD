from apps.acreditacion.models import ElementoFundamental
from application.services import build_document_drive_path
from apps.documentos.selectors import (
    attach_cycle_authorization_status,
    get_approved_cycles_queryset,
    get_recent_cycle_upload_statuses,
)
from apps.evidencias.models import RegistroEvidencia


UPLOADED_EVIDENCE_STATES = {
    "APROBADA",
    "CARGADA",
    "EN_REVISION_EVALUADOR",
    "ENVIADA_EVALUADOR",
    "REGISTRADA",
    "VALIDADA",
}


def _normalize_state(value):
    return " ".join((value or "").strip().upper().split())


def _coerce_pk(value):
    try:
        pk = int(value)
    except (TypeError, ValueError):
        return None
    return pk if pk > 0 else None


def _get_enabled_cycles():
    approved_cycles = list(attach_cycle_authorization_status(get_approved_cycles_queryset()))
    enabled_cycles = [
        ciclo for ciclo in approved_cycles if getattr(ciclo, "document_upload_enabled", False)
    ]
    return approved_cycles, enabled_cycles


def _resolve_selected_cycle(*, ciclo_id=None, enabled_cycles=None):
    enabled_cycles = enabled_cycles or []
    selected_pk = _coerce_pk(ciclo_id)
    if selected_pk:
        for ciclo in enabled_cycles:
            if ciclo.pk == selected_pk:
                return ciclo
    return enabled_cycles[0] if enabled_cycles else None


def get_current_enabled_cycle():
    _approved_cycles, enabled_cycles = _get_enabled_cycles()
    return _resolve_selected_cycle(enabled_cycles=enabled_cycles)


def get_matrix_registration_rows(*, ciclo=None):
    elementos = list(
        ElementoFundamental.objects.select_related(
            "indicador__subcriterio__criterio"
        )
        .filter(indicador_id__isnull=False)
        .order_by(
            "indicador__subcriterio__criterio__codigo_criterio",
            "indicador__subcriterio__codigo_subcriterio",
            "indicador__codigo_indicador",
            "orden_visual",
            "codigo_elemento",
        )
    )
    if ciclo is None or not elementos:
        return []

    element_ids = [elemento.pk for elemento in elementos]
    registros = list(
        RegistroEvidencia.objects.select_related(
            "documento",
            "estado",
            "ciclo",
            "indicador",
            "elemento_fundamental",
            "registrado_por",
        )
        .filter(ciclo=ciclo, elemento_fundamental_id__in=element_ids)
        .order_by("elemento_fundamental_id", "-fecha_registro", "-id_registro")
    )

    latest_by_element = {}
    counts_by_element = {}
    for registro in registros:
        element_id = registro.elemento_fundamental_id
        counts_by_element[element_id] = counts_by_element.get(element_id, 0) + 1
        latest_by_element.setdefault(element_id, registro)

    rows = []
    for elemento in elementos:
        latest_record = latest_by_element.get(elemento.pk)
        latest_state = _normalize_state(
            getattr(getattr(latest_record, "estado", None), "descripcion", None)
        )
        has_uploaded_evidence = bool(
            latest_record is not None and latest_state in UPLOADED_EVIDENCE_STATES
        )
        drive_folder = build_document_drive_path(elemento.indicador, elemento, ciclo)
        rows.append(
            {
                "criterio": elemento.indicador.subcriterio.criterio,
                "subcriterio": elemento.indicador.subcriterio,
                "indicador": elemento.indicador,
                "elemento": elemento,
                "latest_record": latest_record,
                "latest_document": latest_record.documento if latest_record else None,
                "drive_folder": drive_folder.as_posix(),
                "has_evidence": has_uploaded_evidence,
                "has_pending_review": bool(latest_record is not None and not has_uploaded_evidence),
                "evidence_status": latest_state,
                "record_count": counts_by_element.get(elemento.pk, 0),
            }
        )
    return rows


def get_recent_registered_evidences(*, ciclo=None, limit=10):
    if ciclo is None:
        return []
    return list(
        RegistroEvidencia.objects.select_related(
            "documento",
            "estado",
            "indicador",
            "elemento_fundamental",
            "registrado_por",
        )
        .filter(ciclo=ciclo)
        .order_by("-fecha_registro", "-id_registro")[:limit]
    )


def get_matrix_registration_dashboard(*, ciclo_id=None):
    approved_cycles, enabled_cycles = _get_enabled_cycles()
    selected_cycle = _resolve_selected_cycle(ciclo_id=ciclo_id, enabled_cycles=enabled_cycles)
    rows = get_matrix_registration_rows(ciclo=selected_cycle)
    uploaded_rows = sum(1 for row in rows if row["has_evidence"])
    pending_review_rows = sum(1 for row in rows if row["has_pending_review"])
    pending_rows = max(len(rows) - uploaded_rows, 0)
    missing_rows = [row for row in rows if not row["has_evidence"]]

    return {
        "approved_cycles": approved_cycles,
        "available_cycles": enabled_cycles,
        "selected_cycle": selected_cycle,
        "matrix_registration_rows": rows,
        "matrix_registration_summary": {
            "total": len(rows),
            "uploaded": uploaded_rows,
            "pending": pending_rows,
            "pending_review": pending_review_rows,
            "records": sum(row["record_count"] for row in rows),
            "completion_percent": int((uploaded_rows / len(rows)) * 100) if rows else 0,
        },
        "missing_matrix_rows": missing_rows,
        "recent_registered_evidences": get_recent_registered_evidences(ciclo=selected_cycle),
        "cycle_statuses": get_recent_cycle_upload_statuses(),
    }
