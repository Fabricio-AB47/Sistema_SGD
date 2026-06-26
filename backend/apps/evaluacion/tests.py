from django.test import SimpleTestCase
from django.utils import timezone

from apps.evaluacion.services.notification_service import _render_email as render_evaluation_email


class EvaluationEmailTemplateTests(SimpleTestCase):
    def test_transactional_email_templates_render_text_and_html(self):
        context = {
            "subject": "Notificacion de prueba",
            "actor_name": "Responsable SIG",
            "responsable_name": "Responsable del elemento",
            "usuario_destino": "Evaluador Externo",
            "recordatorio_numero": 1,
            "recordatorios_totales": 3,
            "ciclo_nombre": "Ciclo 2026",
            "indicador_codigo": "IND-1",
            "indicador_nombre": "Indicador de prueba",
            "elemento_codigo": "EF-1",
            "elemento_nombre": "Elemento de prueba",
            "documento_nombre": "evidencia.pdf",
            "fecha_evento": timezone.now(),
            "fecha_recordatorio": timezone.now(),
            "comentario": "Corregir el documento.",
            "requires_director_check": True,
            "evidence_url": "https://sig.local/evidencia",
            "upload_url": "https://sig.local/cargar",
        }
        templates = [
            "evaluator_release",
            "evaluator_release_reminder",
            "evidence_check_approved",
            "evidence_corrections_requested",
            "evidence_uploaded",
        ]

        for template_name in templates:
            with self.subTest(template_name=template_name):
                body, html_body = render_evaluation_email(template_name, context)

                self.assertIn("EF-1", body)
                self.assertIn("evidencia.pdf", body)
                self.assertTrue(html_body.strip())
