from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.integraciones.services.graph_service import GraphConflictError, ensure_drive_folder


@override_settings(GRAPH_DRIVE_ID="drive-id")
class EnsureDriveFolderTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_reuses_existing_graph_folders_without_creating_them(self):
        root_item = {"id": "root", "name": "root", "folder": {}}
        existing_items = {
            "SIG": {"id": "sig", "name": "SIG", "folder": {}},
            "SIG/CRITERIO": {"id": "criterio", "name": "CRITERIO", "folder": {}},
        }

        with (
            patch(
                "apps.integraciones.services.graph_service.get_drive_root_item",
                return_value=root_item,
            ),
            patch(
                "apps.integraciones.services.graph_service._get_item_by_path",
                side_effect=lambda relative_path, **kwargs: existing_items[str(relative_path)],
            ) as get_item,
            patch(
                "apps.integraciones.services.graph_service._create_child_folder"
            ) as create_folder,
        ):
            item = ensure_drive_folder(
                "SIG/CRITERIO",
                payload={},
                access_token="token",
                refresh=True,
            )

        self.assertEqual(item["id"], "criterio")
        self.assertEqual(get_item.call_count, 2)
        create_folder.assert_not_called()

    def test_revalidates_folder_when_create_conflicts_because_it_already_exists(self):
        root_item = {"id": "root", "name": "root", "folder": {}}
        created_item = {"id": "sig", "name": "SIG", "folder": {}}

        with (
            patch(
                "apps.integraciones.services.graph_service.get_drive_root_item",
                return_value=root_item,
            ),
            patch(
                "apps.integraciones.services.graph_service._get_item_by_path",
                side_effect=[None, created_item],
            ) as get_item,
            patch(
                "apps.integraciones.services.graph_service._create_child_folder",
                side_effect=GraphConflictError("ya existe"),
            ) as create_folder,
        ):
            item = ensure_drive_folder(
                "SIG",
                payload={},
                access_token="token",
                refresh=True,
            )

        self.assertEqual(item["id"], "sig")
        self.assertEqual(get_item.call_count, 2)
        create_folder.assert_called_once()
