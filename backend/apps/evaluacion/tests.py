from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.test import TestCase
from django.utils import timezone

from apps.evaluacion.services.registro_service import MatrixEvidenceRegistrationError, register_matrix_evidence
from apps.evaluacion.services.revision_service import EvaluacionWorkflowError
from apps.evaluacion.services.notification_service import _render_email as render_evaluation_email
from apps.evaluacion.views.caces import CacesBaseView
from apps.evaluacion.views.web import EvaluacionBaseView, TareaEvidenciaListView, _is_evaluator_only_request


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


class EvaluationRoleScopeTests(SimpleTestCase):
    def _request(self, *, roles=(), operational_roles=()):
        return SimpleNamespace(
            session={
                "sig_roles": list(roles),
                "sig_operational_roles": list(operational_roles),
            },
            resolver_match=None,
        )

    def _scope_flags(self, *, roles=(), operational_roles=()):
        view = EvaluacionBaseView()
        view.request = self._request(roles=roles, operational_roles=operational_roles)
        return view._actor_scope_flags()

    def test_evaluator_can_grade_evidence(self):
        request = self._request(operational_roles=("EVALUADOR",))
        scope = self._scope_flags(operational_roles=("EVALUADOR",))

        self.assertTrue(_is_evaluator_only_request(request))
        self.assertTrue(scope["can_grade_evidence"])
        self.assertTrue(scope["can_review_compliance"])
        self.assertFalse(scope["is_external"])

    def test_external_can_review_but_cannot_grade(self):
        request = self._request(roles=("EXTERNO",))
        scope = self._scope_flags(roles=("EXTERNO",))

        self.assertFalse(_is_evaluator_only_request(request))
        self.assertTrue(scope["can_enter_evaluation"])
        self.assertTrue(scope["can_review_compliance"])
        self.assertFalse(scope["can_grade_evidence"])
        self.assertTrue(scope["is_external"])

    def test_external_has_read_access_to_caces_detail_scope(self):
        view = CacesBaseView()
        view.request = self._request(roles=("EXTERNO",))

        self.assertTrue(view._allow_unrestricted_caces_access())
        self.assertFalse(view._can_grade_caces())


class MatrixEvidenceRegistrationTests(TestCase):
    def test_assigned_responsible_can_upload_without_level_one_cargo(self):
        actor = SimpleNamespace(pk=6)
        tarea = SimpleNamespace(usuario_responsable_id=6, asignado_por_id=5)

        from apps.evaluacion.services.registro_service import _actor_can_mark_evidence_uploaded

        with patch("apps.evaluacion.services.registro_service._actor_has_admin_role", return_value=False):
            self.assertTrue(_actor_can_mark_evidence_uploaded(actor=actor, tarea=tarea))

    def test_responsible_cannot_upload_again_while_waiting_director_review(self):
        actor = SimpleNamespace(pk=6)
        ciclo = SimpleNamespace(pk=1, nombre="Ciclo 2026")
        indicador = SimpleNamespace(pk=10)
        elemento = SimpleNamespace(pk=20, indicador_id=10, codigo_elemento="EL001")
        tarea = SimpleNamespace(
            pk=70,
            ciclo=ciclo,
            indicador=indicador,
            elemento_fundamental=elemento,
            usuario_responsable_id=6,
            asignado_por_id=5,
            fecha_cierre=timezone.now(),
        )
        registro = SimpleNamespace(pk=60)

        with (
            patch("apps.evaluacion.services.registro_service._find_related_task", return_value=tarea),
            patch("apps.evaluacion.services.registro_service._actor_can_mark_evidence_uploaded", return_value=True),
            patch("apps.evaluacion.services.registro_service._actor_can_auto_signoff_task", return_value=False),
            patch("apps.evaluacion.services.registro_service._latest_evidence_record_for_task", return_value=registro),
        ):
            with self.assertRaises(MatrixEvidenceRegistrationError):
                register_matrix_evidence(
                    ciclo=ciclo,
                    indicador=indicador,
                    elemento_fundamental=elemento,
                    clasificacion=SimpleNamespace(pk=80),
                    uploaded_file=SimpleNamespace(name="evidencia.pdf"),
                    actor=actor,
                )

    def test_auto_release_failure_does_not_rollback_registered_evidence(self):
        actor = SimpleNamespace(pk=5)
        ciclo = SimpleNamespace(pk=1, nombre="Ciclo 2026")
        indicador = SimpleNamespace(pk=10)
        elemento = SimpleNamespace(pk=20, indicador_id=10, codigo_elemento="EL001")
        estado = SimpleNamespace(pk=30)
        documento = SimpleNamespace(pk=40)
        version = SimpleNamespace(pk=50)
        registro = SimpleNamespace(
            pk=60,
            documento=documento,
            elemento_fundamental=elemento,
            ciclo=ciclo,
        )
        tarea = SimpleNamespace(pk=70)
        queryset = MagicMock()
        queryset.order_by.return_value.first.return_value = None

        with (
            patch("apps.evaluacion.services.registro_service._find_related_task", return_value=tarea),
            patch("apps.evaluacion.services.registro_service._actor_can_mark_evidence_uploaded", return_value=True),
            patch("apps.evaluacion.services.registro_service._actor_can_auto_signoff_task", return_value=True),
            patch("apps.evaluacion.services.registro_service._get_default_evidence_status", return_value=estado),
            patch(
                "apps.evaluacion.services.registro_service.upload_structured_document",
                return_value={"documento": documento, "version": version},
            ),
            patch("apps.evaluacion.services.registro_service.RegistroEvidencia.objects.filter", return_value=queryset),
            patch("apps.evaluacion.services.registro_service.RegistroEvidencia.objects.create", return_value=registro),
            patch("apps.evaluacion.services.registro_service._close_task_after_upload", return_value=False),
            patch("apps.evaluacion.services.registro_service._signoff_task_after_director_upload", return_value=True),
            patch("apps.evaluacion.services.registro_service._actor_has_admin_role", return_value=False),
            patch(
                "apps.evaluacion.services.registro_service.habilitar_salida_evaluador",
                side_effect=EvaluacionWorkflowError("pendiente de aprobacion"),
            ),
            patch("apps.evaluacion.services.registro_service.registrar_evento") as registrar_evento,
            patch("apps.evaluacion.services.registro_service.queue_evidence_uploaded_email"),
        ):
            result = register_matrix_evidence(
                ciclo=ciclo,
                indicador=indicador,
                elemento_fundamental=elemento,
                clasificacion=SimpleNamespace(pk=80),
                uploaded_file=SimpleNamespace(name="evidencia.pdf"),
                actor=actor,
            )

        self.assertEqual(result["registro"], registro)
        self.assertTrue(result["auto_approved_by_director"])
        self.assertFalse(result["auto_sent_to_evaluator"])
        self.assertEqual(result["auto_release_error"], "pendiente de aprobacion")
        self.assertTrue(
            any(
                call.kwargs.get("accion") == "SALIDA_EVALUADOR_AUTOMATICA_PENDIENTE"
                for call in registrar_evento.call_args_list
            )
        )

    def test_responsible_upload_requires_director_check_without_auto_signoff(self):
        actor = SimpleNamespace(pk=6)
        ciclo = SimpleNamespace(pk=1, nombre="Ciclo 2026")
        indicador = SimpleNamespace(pk=10)
        elemento = SimpleNamespace(pk=20, indicador_id=10, codigo_elemento="EL001")
        estado_revision = SimpleNamespace(pk=31)
        documento = SimpleNamespace(pk=40)
        version = SimpleNamespace(pk=50)
        registro = SimpleNamespace(
            pk=60,
            documento=documento,
            elemento_fundamental=elemento,
            ciclo=ciclo,
        )
        tarea = SimpleNamespace(pk=70)
        queryset = MagicMock()
        queryset.order_by.return_value.first.return_value = None

        with (
            patch("apps.evaluacion.services.registro_service._find_related_task", return_value=tarea),
            patch("apps.evaluacion.services.registro_service._actor_can_mark_evidence_uploaded", return_value=True),
            patch("apps.evaluacion.services.registro_service._actor_can_auto_signoff_task", return_value=False),
            patch("apps.evaluacion.services.registro_service._get_internal_review_status", return_value=estado_revision),
            patch(
                "apps.evaluacion.services.registro_service.upload_structured_document",
                return_value={"documento": documento, "version": version},
            ),
            patch("apps.evaluacion.services.registro_service.RegistroEvidencia.objects.filter", return_value=queryset),
            patch("apps.evaluacion.services.registro_service.RegistroEvidencia.objects.create", return_value=registro),
            patch("apps.evaluacion.services.registro_service._close_task_after_upload", return_value=True),
            patch("apps.evaluacion.services.registro_service._signoff_task_after_director_upload") as signoff,
            patch("apps.evaluacion.services.registro_service.habilitar_salida_evaluador") as release,
            patch("apps.evaluacion.services.registro_service.registrar_evento"),
            patch("apps.evaluacion.services.registro_service.queue_evidence_uploaded_email"),
        ):
            result = register_matrix_evidence(
                ciclo=ciclo,
                indicador=indicador,
                elemento_fundamental=elemento,
                clasificacion=SimpleNamespace(pk=80),
                uploaded_file=SimpleNamespace(name="evidencia.pdf"),
                actor=actor,
            )

        self.assertTrue(result["requires_director_check"])
        self.assertFalse(result["auto_approved_by_director"])
        self.assertFalse(result["auto_sent_to_evaluator"])
        signoff.assert_not_called()
        release.assert_not_called()


class EvidenceTaskApprovalPermissionTests(SimpleTestCase):
    def test_director_review_decision_pending_before_internal_approval(self):
        tarea = SimpleNamespace(
            fecha_cierre=timezone.now(),
            observacion="Cerrada por responsable",
        )
        registro = SimpleNamespace(
            fecha_envio_revision=None,
            estado=SimpleNamespace(descripcion="EN_REVISION_INTERNA"),
        )

        decision = TareaEvidenciaListView._director_review_decision(
            tarea=tarea,
            registro=registro,
        )

        self.assertEqual(decision["status"], "pending")

    def test_director_review_decision_approved_when_sent_to_evaluator(self):
        tarea = SimpleNamespace(
            fecha_cierre=timezone.now(),
            observacion="[VISTO_BUENO_DIRECTOR] Aprobacion interna",
        )
        registro = SimpleNamespace(
            fecha_envio_revision=timezone.now(),
            estado=SimpleNamespace(descripcion="ENVIADA_EVALUADOR"),
        )

        decision = TareaEvidenciaListView._director_review_decision(
            tarea=tarea,
            registro=registro,
        )

        self.assertEqual(decision["status"], "approved")
        self.assertIn("evaluador", decision["message"])

    def test_director_or_rector_can_signoff_closed_subordinate_task(self):
        tarea = SimpleNamespace(
            fecha_cierre=timezone.now(),
            observacion="Cerrada por responsable",
            usuario_responsable_id=6,
            asignado_por_id=None,
        )

        self.assertTrue(
            TareaEvidenciaListView._can_signoff_task(
                tarea=tarea,
                actor_id=5,
                can_redirect_subordinates=True,
                subordinate_user_ids={6},
            )
        )

    def test_responsible_cannot_signoff_own_closed_task(self):
        tarea = SimpleNamespace(
            fecha_cierre=timezone.now(),
            observacion="Cerrada por responsable",
            usuario_responsable_id=6,
            asignado_por_id=6,
        )

        self.assertFalse(
            TareaEvidenciaListView._can_signoff_task(
                tarea=tarea,
                actor_id=6,
                can_redirect_subordinates=True,
                subordinate_user_ids={6},
            )
        )
