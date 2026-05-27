from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings

from application.services import (
    ensure_local_mirror_folder,
    get_existing_local_mirror_file,
    resolve_local_mirror_path,
    write_local_mirror_file,
)


class LocalDocumentMirrorTests(SimpleTestCase):
    def test_writes_file_using_graph_relative_structure_inside_project(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            backend_dir = project_root / "backend"
            backend_dir.mkdir()

            with override_settings(
                BASE_DIR=backend_dir,
                DOC_PATH_DRIVE="SISTEMA INFORMATICO DE GESTION",
                SIG_LOCAL_DOCUMENT_MIRROR_ENABLED=True,
                SIG_LOCAL_DOCUMENT_MIRROR_ROOT="",
            ):
                local_path = write_local_mirror_file(
                    PurePosixPath(
                        "SISTEMA INFORMATICO DE GESTION/CRITERIO/C001/archivo.pdf"
                    ),
                    b"contenido",
                )

            expected_path = (
                project_root
                / "SISTEMA INFORMATICO DE GESTION"
                / "CRITERIO"
                / "C001"
                / "archivo.pdf"
            )
            self.assertEqual(local_path, expected_path)
            self.assertEqual(expected_path.read_bytes(), b"contenido")

    def test_uses_configured_local_root_and_strips_drive_root(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            backend_dir = project_root / "backend"
            backend_dir.mkdir()

            with override_settings(
                BASE_DIR=backend_dir,
                DOC_PATH_DRIVE="SISTEMA INFORMATICO DE GESTION",
                SIG_LOCAL_DOCUMENT_MIRROR_ENABLED=True,
                SIG_LOCAL_DOCUMENT_MIRROR_ROOT="respaldo_local",
            ):
                folder_path = ensure_local_mirror_folder(
                    PurePosixPath("SISTEMA INFORMATICO DE GESTION/DOCUMENTOS CICLOS AUTH")
                )

            self.assertEqual(
                folder_path,
                project_root / "respaldo_local" / "DOCUMENTOS CICLOS AUTH",
            )
            self.assertTrue(folder_path.is_dir())

    def test_can_resolve_existing_local_mirror_file(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            backend_dir = project_root / "backend"
            backend_dir.mkdir()

            with override_settings(
                BASE_DIR=backend_dir,
                DOC_PATH_DRIVE="SISTEMA INFORMATICO DE GESTION",
                SIG_LOCAL_DOCUMENT_MIRROR_ENABLED=True,
                SIG_LOCAL_DOCUMENT_MIRROR_ROOT="",
            ):
                write_local_mirror_file(
                    PurePosixPath("SISTEMA INFORMATICO DE GESTION/a/b.txt"),
                    b"ok",
                )
                existing_file = get_existing_local_mirror_file(
                    PurePosixPath("SISTEMA INFORMATICO DE GESTION/a/b.txt")
                )

            self.assertIsNotNone(existing_file)
            self.assertEqual(existing_file.read_text(), "ok")

    def test_rejects_paths_that_escape_local_mirror_root(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            backend_dir = project_root / "backend"
            backend_dir.mkdir()

            with override_settings(
                BASE_DIR=backend_dir,
                DOC_PATH_DRIVE="SISTEMA INFORMATICO DE GESTION",
                SIG_LOCAL_DOCUMENT_MIRROR_ENABLED=True,
                SIG_LOCAL_DOCUMENT_MIRROR_ROOT="",
            ):
                with self.assertRaises(ValueError):
                    resolve_local_mirror_path(
                        PurePosixPath("SISTEMA INFORMATICO DE GESTION/../fuera.txt")
                    )
