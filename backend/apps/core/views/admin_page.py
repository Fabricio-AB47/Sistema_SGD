from django.views.generic import TemplateView

from apps.core.mixins import SigLoginRequiredMixin


class AdminPageView(SigLoginRequiredMixin, TemplateView):
    module_title = "Administracion"
    module_description = ""
    page_title = "Pagina"
    page_description = ""
    page_status = "Panel administrativo"
    module_tabs = []
    page_actions = []
    page_highlights = []
    page_sections = []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "module_title": self.module_title,
                "module_description": self.module_description,
                "page_title": self.page_title,
                "page_description": self.page_description,
                "page_status": self.page_status,
                "module_tabs": self.module_tabs,
                "page_actions": self.page_actions,
                "page_highlights": self.page_highlights,
                "page_sections": self.page_sections,
                "current_url_name": self.request.resolver_match.url_name if self.request.resolver_match else "",
            }
        )
        return context
