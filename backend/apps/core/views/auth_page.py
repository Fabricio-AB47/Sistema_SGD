from django.views.generic import TemplateView


class AuthPageView(TemplateView):
    page_title = "Seguridad"
    page_description = ""
    page_actions = []
    page_sections = []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": self.page_title,
                "page_description": self.page_description,
                "page_actions": self.page_actions,
                "page_sections": self.page_sections,
            }
        )
        return context
