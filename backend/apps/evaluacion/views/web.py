from apps.core.views.admin_page import AdminPageView


MODULE_TITLE = 'Evaluacion'
MODULE_DESCRIPTION = 'Gestiona evidencias, evaluaciones y observaciones del proceso.'
MODULE_TABS = [{'label': 'Registrar evidencia', 'url_name': 'evaluacion-evidencia-registrar', 'active_names': ['evaluacion-evidencia-registrar']}, {'label': 'Lista de evidencias', 'url_name': 'evaluacion-evidencias-lista', 'active_names': ['evaluacion-evidencias-lista']}, {'label': 'Detalle de evidencia', 'url_name': 'evaluacion-evidencia-detalle', 'active_names': ['evaluacion-evidencia-detalle']}, {'label': 'Bandeja de evaluacion', 'url_name': 'evaluacion-bandeja', 'active_names': ['evaluacion-bandeja']}, {'label': 'Evaluar evidencia', 'url_name': 'evaluacion-evaluar', 'active_names': ['evaluacion-evaluar']}, {'label': 'Observaciones', 'url_name': 'evaluacion-observaciones', 'active_names': ['evaluacion-observaciones']}]


def module_page(**kwargs):
    return AdminPageView.as_view(
        module_title=MODULE_TITLE,
        module_description=MODULE_DESCRIPTION,
        module_tabs=MODULE_TABS,
        **kwargs,
    )
