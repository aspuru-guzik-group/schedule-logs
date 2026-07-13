import os
import tempfile
import unittest
from pathlib import Path

from config import GROUPS, get_presenter_cols
from setup_group import extract_resource_id, render_secret, tomllib, write_secret


class SetupGroupTest(unittest.TestCase):
    def test_el_agente_uses_two_presenter_columns(self):
        self.assertEqual(
            get_presenter_cols(GROUPS["elagente"]),
            ["Presenter 1", "Presenter 2"],
        )

    def test_extracts_ids_from_google_urls(self):
        self.assertEqual(
            extract_resource_id(
                "https://docs.google.com/spreadsheets/d/sheet_id_12345/edit",
                "spreadsheet",
            ),
            "sheet_id_12345",
        )
        self.assertEqual(
            extract_resource_id(
                "https://drive.google.com/drive/folders/folder_id_12345?usp=sharing",
                "folder",
            ),
            "folder_id_12345",
        )
        self.assertEqual(
            extract_resource_id(
                "https://docs.google.com/presentation/d/slides_id_12345/edit",
                "presentation",
            ),
            "slides_id_12345",
        )

    @unittest.skipIf(tomllib is None, "tomllib requires Python 3.11 or newer")
    def test_rendered_secret_is_valid_toml(self):
        values = {
            "admin_password": 'quotes " and slash \\',
            "organizer_name": "Test Organizer",
            "folder_id": "materials_folder",
            "slides_folder_id": "slides_folder",
            "slides_template_id": "slides_template",
            "zoom_link": "https://example.test/meeting",
            "spreadsheet_id": "spreadsheet_id",
            "encryption_key": "encryption_key",
        }
        service_account = {
            "type": "service_account",
            "project_id": "project",
            "private_key_id": "key_id",
            "private_key": "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----\n",
            "client_email": "test@example.test",
            "client_id": "12345",
            "auth_uri": "https://example.test/auth",
            "token_uri": "https://example.test/token",
            "auth_provider_x509_cert_url": "https://example.test/certs",
            "client_x509_cert_url": "https://example.test/client-cert",
        }

        parsed = tomllib.loads(render_secret("elagente", values, service_account))

        self.assertEqual(parsed["elagente"]["admin_password"], values["admin_password"])
        self.assertEqual(
            parsed["elagente"]["gcp_service_account"]["private_key"],
            service_account["private_key"],
        )

    def test_secret_is_mode_600_and_not_overwritten_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "elagente.toml"
            write_secret(path, "[elagente]\nvalue = 1\n")

            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                write_secret(path, "replacement")


if __name__ == "__main__":
    unittest.main()
