from apps.core.views.admin_page import AdminPageView


MODULE_TITLE = 'Informes'
MODULE_DESCRIPTION = 'Gestiona informes de autoevaluacion y su flujo de aprobacion.'
MODULE_TABS = [{'label': 'Informes', 'url_name': 'informes-lista', 'active_names': ['informes-lista']}, {'label': 'Generar informe', 'url_name': 'informes-generar', 'active_names': ['informes-generar']}, {'label': 'Detalle de informe', 'url_name': 'informes-detalle', 'active_names': ['informes-detalle']}, {'label': 'Aprobar informe', 'url_name': 'informes-aprobar', 'active_names': ['informes-aprobar']}]


def module_page(**kwargs):
    return AdminPageView.as_view(
        module_title=MODULE_TITLE,
        module_description=MODULE_DESCRIPTION,
        module_tabs=MODULE_TABS,
        **kwargs,
    )
