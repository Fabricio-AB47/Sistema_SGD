from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from application.services import write_local_mirror_file
from apps.documentos.services.access_service import resolve_protected_document_stream
from apps.integraciones.services.graph_service import GraphServiceError


class ProtectedDocumentLocalFallbackTests(SimpleTestCase):
    def test_uses_local_mirror_when_graph_download_fails(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            backend_dir = project_root / "backend"
            backend_dir.mkdir()
            relative_path = PurePosixPath(
                "SISTEMA INFORMATICO DE GESTION/CRITERIO/C001/documento.pdf"
            )

            with override_settings(
                BASE_DIR=backend_dir,
                DOC_PATH_DRIVE="SISTEMA INFORMATICO DE GESTION",
                SIG_LOCAL_DOCUMENT_MIRROR_ENABLED=True,
                SIG_LOCAL_DOCUMENT_MIRROR_ROOT="",
            ):
                write_local_mirror_file(relative_path, b"respaldo")
                documento = SimpleNamespace(
                    graph_item_id="graph-id",
                    ruta_local=relative_path.as_posix(),
                    mime_type="application/pdf",
                    nombre_archivo="documento.pdf",
                )
                with patch(
                    "apps.documentos.services.access_service.graph_service.download_file_by_item_id",
                    side_effect=GraphServiceError("Graph no disponible"),
                ):
                    stream, headers = resolve_protected_document_stream(documento)

            with stream:
                self.assertEqual(stream.read(), b"respaldo")
            self.assertEqual(headers["Content-Type"], "application/pdf")

    def test_uses_local_mirror_without_graph_item_id(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            backend_dir = project_root / "backend"
            backend_dir.mkdir()
            relative_path = PurePosixPath(
                "SISTEMA INFORMATICO DE GESTION/DOCUMENTOS CICLOS AUTH/ciclo/acta.pdf"
            )

            with override_settings(
                BASE_DIR=backend_dir,
                DOC_PATH_DRIVE="SISTEMA INFORMATICO DE GESTION",
                SIG_LOCAL_DOCUMENT_MIRROR_ENABLED=True,
                SIG_LOCAL_DOCUMENT_MIRROR_ROOT="",
            ):
                write_local_mirror_file(relative_path, b"acta")
                documento = SimpleNamespace(
                    graph_item_id=None,
                    ruta_local=relative_path.as_posix(),
                    mime_type="application/pdf",
                    nombre_archivo="acta.pdf",
                )
                stream, headers = resolve_protected_document_stream(documento)

            with stream:
                self.assertEqual(stream.read(), b"acta")
            self.assertEqual(headers["Content-Type"], "application/pdf")
