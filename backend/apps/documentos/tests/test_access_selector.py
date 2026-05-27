from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.documentos.selectors.access_selector import get_documento_for_access


class ProtectedDocumentAccessSelectorTests(SimpleTestCase):
    def _mock_document_lookup(self, documento_model, documento):
        queryset = documento_model.objects.select_related.return_value.filter.return_value
        queryset.first.return_value = documento

    @patch("apps.documentos.selectors.access_selector.usuario_puede_acceder_documento")
    @patch("apps.documentos.selectors.access_selector.Documento")
    def test_denies_active_document_when_actor_has_no_structural_access(
        self,
        documento_model,
        usuario_puede_acceder_documento,
    ):
        actor = Mock(pk=7)
        documento = Mock(pk=11, activo=True)
        self._mock_document_lookup(documento_model, documento)
        usuario_puede_acceder_documento.return_value = False

        result = get_documento_for_access(11, actor=actor)

        self.assertIsNone(result)
        usuario_puede_acceder_documento.assert_called_once_with(actor, documento)

    @patch("apps.documentos.selectors.access_selector.usuario_puede_acceder_documento")
    @patch("apps.documentos.selectors.access_selector.Documento")
    def test_returns_active_document_when_actor_has_structural_access(
        self,
        documento_model,
        usuario_puede_acceder_documento,
    ):
        actor = Mock(pk=7)
        documento = Mock(pk=11, activo=True)
        self._mock_document_lookup(documento_model, documento)
        usuario_puede_acceder_documento.return_value = True

        result = get_documento_for_access(11, actor=actor)

        self.assertIs(result, documento)
        usuario_puede_acceder_documento.assert_called_once_with(actor, documento)
