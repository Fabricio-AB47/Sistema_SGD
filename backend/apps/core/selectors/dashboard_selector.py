from __future__ import annotations

from apps.core.services.navigation_service import build_navigation_groups
from apps.evaluacion.models import Evaluacion
from apps.evidencias.models import RegistroEvidencia
from apps.informes.models import InformeAutoevaluacion
from apps.mejora.models import PlanMejora


def get_dashboard_metrics():
    return {
        "evidencias": RegistroEvidencia.objects.count(),
        "evaluaciones_pendientes": Evaluacion.objects.filter(
            estado__descripcion__in=["PENDIENTE", "EN_ANALISIS"]
        ).count(),
        "informes_revision": InformeAutoevaluacion.objects.filter(
            estado__descripcion__in=["BORRADOR", "EN_REVISION"]
        ).count(),
        "planes_activos": PlanMejora.objects.filter(
            estado__descripcion__in=["BORRADOR", "ENVIADO", "EN_EJECUCION", "PAUSADO", "APROBADO"]
        ).count(),
    }


def get_dashboard_quick_links(*, role_names=(), permission_codes=(), limit: int = 8):
    groups = build_navigation_groups(role_names=role_names, permission_codes=permission_codes)
    quick_links = []
    for group in groups:
        for item in group["items"]:
            if item.url_name == "core-dashboard":
                continue
            quick_links.append(
                {
                    "group": group["label"],
                    "label": item.label,
                    "url_name": item.url_name,
                    "icon": getattr(item, "icon", "compass"),
                }
            )
            if len(quick_links) >= limit:
                return quick_links
    return quick_links
