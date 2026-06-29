import shutil
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings

from application.services.storage_path_service import _filesystem_path
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

    def test_writes_long_windows_local_mirror_paths(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            backend_dir = project_root / "backend"
            backend_dir.mkdir()
            long_parts = [
                "CACES_C01_" + ("ORGANIZACION_" * 4),
                "C01_S01_" + ("PLANIFICACION_" * 4),
                "CACES_01_" + ("PLANIFICACION_ESTRATEGICA_" * 3),
                "EL001_" + ("ELEMENTO_DE_EVALUACION_" * 3),
                "2026_PRIMER_CICLO_DE_EVALAUCION",
            ]

            with override_settings(
                BASE_DIR=backend_dir,
                DOC_PATH_DRIVE="SISTEMA INFORMATICO DE GESTION",
                SIG_LOCAL_DOCUMENT_MIRROR_ENABLED=True,
                SIG_LOCAL_DOCUMENT_MIRROR_ROOT="",
            ):
                relative_file_path = PurePosixPath("SISTEMA INFORMATICO DE GESTION").joinpath(
                    *long_parts,
                    "evidencia.pdf",
                )
                local_path = write_local_mirror_file(
                    relative_file_path,
                    b"contenido",
                )
                existing_file = get_existing_local_mirror_file(relative_file_path)

            self.assertGreater(len(str(local_path)), 260)
            self.assertIsNotNone(existing_file)
            self.assertEqual(existing_file.read_bytes(), b"contenido")
            shutil.rmtree(_filesystem_path(project_root / "SISTEMA INFORMATICO DE GESTION"))

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
