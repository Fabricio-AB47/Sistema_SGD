from apps.core.views.admin_page import AdminPageView


MODULE_TITLE = 'Mejora'
MODULE_DESCRIPTION = 'Administra planes de mejora derivados de evaluaciones y observaciones.'
MODULE_TABS = [{'label': 'Planes de mejora', 'url_name': 'mejora-lista', 'active_names': ['mejora-lista']}, {'label': 'Crear plan', 'url_name': 'mejora-crear', 'active_names': ['mejora-crear']}, {'label': 'Detalle de plan', 'url_name': 'mejora-detalle', 'active_names': ['mejora-detalle']}, {'label': 'Seguimiento', 'url_name': 'mejora-seguimiento', 'active_names': ['mejora-seguimiento']}]


def module_page(**kwargs):
    return AdminPageView.as_view(
        module_title=MODULE_TITLE,
        module_description=MODULE_DESCRIPTION,
        module_tabs=MODULE_TABS,
        **kwargs,
    )
