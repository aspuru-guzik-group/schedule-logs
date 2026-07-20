import os
import tempfile
import unittest
from pathlib import Path

from runtime_config import (
    get_google_oauth_client,
    get_group_runtime_config,
    hash_admin_password,
    is_runtime_group_ready,
    save_group_runtime_config,
    save_google_oauth_client,
    set_group_admin_password,
    verify_group_admin_password,
    verify_password_hash,
)


class RuntimeConfigTest(unittest.TestCase):
    def test_setup_draft_does_not_mark_group_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "groups.json"
            save_group_runtime_config(
                "elagente",
                {
                    "setup_draft": {
                        "organizer_name": "Organizer",
                        "folder_id": "folder",
                        "slides_folder_id": "slides-folder",
                        "slides_template_id": "template",
                        "spreadsheet_id": "sheet",
                        "encryption_key": "key",
                        "gcp_service_account": {"type": "service_account"},
                    }
                },
                path,
            )

            self.assertFalse(is_runtime_group_ready("elagente", path))

    def test_atomic_config_is_private_and_merges_updates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "private" / "groups.json"
            save_group_runtime_config("elagente", {"num_presenters": 2}, path)
            save_group_runtime_config("elagente", {"meeting_day": "friday"}, path)

            self.assertEqual(
                get_group_runtime_config("elagente", path),
                {"meeting_day": "friday", "num_presenters": 2},
            )
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(path.parent).st_mode & 0o777, 0o700)

    def test_site_oauth_client_is_private_and_preserves_groups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "private" / "groups.json"
            save_group_runtime_config("elagente", {"meeting_day": "thursday"}, path)
            client = {"web": {"client_id": "client-id", "client_secret": "secret"}}

            save_google_oauth_client(client, path)

            self.assertEqual(get_google_oauth_client(path), client)
            self.assertEqual(
                get_group_runtime_config("elagente", path),
                {"meeting_day": "thursday"},
            )
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_password_hash_round_trip_and_runtime_override(self):
        encoded = hash_admin_password("correct horse battery staple")
        self.assertTrue(
            verify_password_hash("correct horse battery staple", encoded)
        )
        self.assertFalse(verify_password_hash("wrong", encoded))

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "groups.json"
            set_group_admin_password("elagente", "replacement password", path)
            self.assertTrue(
                verify_group_admin_password(
                    "elagente", "replacement password", path=path
                )
            )
            self.assertFalse(
                verify_group_admin_password("elagente", "wrong", path=path)
            )

    def test_ready_requires_every_integration_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "groups.json"
            save_group_runtime_config(
                "elagente",
                {
                    "organizer_name": "Organizer",
                    "folder_id": "folder",
                    "slides_folder_id": "slides-folder",
                    "slides_template_id": "template",
                    "spreadsheet_id": "sheet",
                    "encryption_key": "key",
                },
                path,
            )
            self.assertFalse(is_runtime_group_ready("elagente", path))
            save_group_runtime_config(
                "elagente",
                {"gcp_service_account": {"type": "service_account"}},
                path,
            )
            self.assertFalse(is_runtime_group_ready("elagente", path))
            save_group_runtime_config(
                "elagente",
                {
                    "gcp_service_account": {
                        "type": "service_account",
                        "project_id": "project",
                        "private_key_id": "key-id",
                        "private_key": "private-key",
                        "client_email": "service@example.test",
                        "client_id": "client-id",
                        "auth_uri": "https://example.test/auth",
                        "token_uri": "https://example.test/token",
                        "auth_provider_x509_cert_url": "https://example.test/certs",
                        "client_x509_cert_url": "https://example.test/client-cert",
                    }
                },
                path,
            )
            self.assertTrue(is_runtime_group_ready("elagente", path))


if __name__ == "__main__":
    unittest.main()
