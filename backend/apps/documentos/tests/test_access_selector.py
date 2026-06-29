from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.documentos.selectors.access_selector import usuario_puede_acceder_documento


class ProtectedDocumentAccessSelectorTests(SimpleTestCase):
    def test_task_responsible_can_access_matching_evidence_document(self):
        actor = SimpleNamespace(pk=6)
        documento = SimpleNamespace(
            pk=3,
            activo=True,
            subido_por_id=5,
            clasificacion=None,
            ciclos_autorizados=None,
            ruta_local="SISTEMA INFORMATICO DE GESTION/CRITERIO/doc.pdf",
        )
        registro = SimpleNamespace(
            ciclo_id=1,
            indicador_id=1,
            elemento_fundamental_id=1,
            elemento_fundamental=SimpleNamespace(indicador_id=1),
        )
        registro_qs = MagicMock()
        registro_qs.filter.return_value = [registro]
        task_qs = MagicMock()
        task_qs.exists.return_value = True

        with (
            patch(
                "apps.documentos.selectors.access_selector.usuario_tiene_acceso_global",
                return_value=False,
            ),
            patch(
                "apps.documentos.selectors.access_selector.usuario_tiene_permiso_modulo",
                return_value=False,
            ),
            patch(
                "apps.documentos.selectors.access_selector.RegistroEvidencia.objects.select_related",
                return_value=registro_qs,
            ),
            patch(
                "apps.documentos.selectors.access_selector.TareaEvidencia.objects.filter",
                return_value=task_qs,
            ) as task_filter,
        ):
            can_access = usuario_puede_acceder_documento(actor, documento)

        self.assertTrue(can_access)
        task_filter.assert_called_once()

    def test_evaluator_can_access_released_evidence_document(self):
        actor = SimpleNamespace(pk=8)
        documento = SimpleNamespace(
            pk=3,
            activo=True,
            subido_por_id=5,
            clasificacion=None,
            ciclos_autorizados=None,
            ruta_local="SISTEMA INFORMATICO DE GESTION/CRITERIO/doc.pdf",
        )
        registro = SimpleNamespace(
            ciclo_id=1,
            indicador_id=1,
            elemento_fundamental_id=1,
            elemento_fundamental=SimpleNamespace(indicador_id=1),
            fecha_envio_revision=object(),
            estado=SimpleNamespace(descripcion="ENVIADA_EVALUADOR"),
        )
        registro_qs = MagicMock()
        registro_qs.filter.return_value = [registro]
        task_qs = MagicMock()
        task_qs.exists.return_value = False
        role_qs = MagicMock()
        role_qs.filter.return_value.exists.return_value = True

        with (
            patch(
                "apps.documentos.selectors.access_selector.usuario_tiene_acceso_global",
                return_value=False,
            ),
            patch(
                "apps.documentos.selectors.access_selector.usuario_tiene_permiso_modulo",
                return_value=False,
            ),
            patch(
                "apps.documentos.selectors.access_selector.RegistroEvidencia.objects.select_related",
                return_value=registro_qs,
            ),
            patch(
                "apps.documentos.selectors.access_selector.TareaEvidencia.objects.filter",
                return_value=task_qs,
            ),
            patch(
                "apps.documentos.selectors.access_selector.UsuarioRol.objects.filter",
                return_value=role_qs,
            ),
        ):
            can_access = usuario_puede_acceder_documento(actor, documento)

        self.assertTrue(can_access)
