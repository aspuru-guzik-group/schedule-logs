import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import google_drive_oauth
except ModuleNotFoundError:
    google_drive_oauth = None


REDIRECT_URI = "https://schedule.example.test"


def oauth_client_fixture():
    return {
        "web": {
            "client_id": "client-id.apps.googleusercontent.com",
            "client_secret": "client-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }


class FakeAbout:
    def get(self, **_kwargs):
        return SimpleNamespace(
            execute=lambda: {
                "user": {
                    "displayName": "Felix",
                    "emailAddress": "felix@example.test",
                }
            }
        )


class FakeDrive:
    def about(self):
        return FakeAbout()


@unittest.skipIf(
    google_drive_oauth is None, "Google OAuth dependencies are not installed"
)
class GoogleDriveOAuthTest(unittest.TestCase):
    def test_oauth_scope_covers_all_google_resource_types(self):
        self.assertIn(
            "https://www.googleapis.com/auth/drive",
            google_drive_oauth.OAUTH_SCOPES,
        )
        self.assertIn(
            "https://www.googleapis.com/auth/presentations",
            google_drive_oauth.OAUTH_SCOPES,
        )
        self.assertIn(
            "https://www.googleapis.com/auth/spreadsheets",
            google_drive_oauth.OAUTH_SCOPES,
        )

    def test_client_requires_exact_web_redirect_uri(self):
        client = oauth_client_fixture()
        self.assertEqual(
            google_drive_oauth.parse_oauth_client_json(
                json.dumps(client), REDIRECT_URI
            ),
            client,
        )
        with self.assertRaisesRegex(ValueError, "exact Authorized redirect URI"):
            google_drive_oauth.parse_oauth_client_json(
                client, "https://wrong.example.test"
            )

    def test_connection_is_one_time_and_builds_refreshable_credentials(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "groups.json"
            google_drive_oauth.save_oauth_client(
                oauth_client_fixture(), REDIRECT_URI, path
            )
            captured = {}

            class AuthorizationFlow:
                code_verifier = None

                def authorization_url(self, **_kwargs):
                    self.code_verifier = "saved-pkce-verifier"
                    return "https://accounts.example.test/authorize", self.state

            def authorization_flow(_client, **kwargs):
                flow = AuthorizationFlow()
                flow.state = kwargs["state"]
                captured["state"] = flow.state
                return flow

            with patch.object(
                google_drive_oauth.Flow,
                "from_client_config",
                side_effect=authorization_flow,
            ):
                url = google_drive_oauth.create_authorization_url(
                    "elagente", REDIRECT_URI, path, now=100
                )

            self.assertEqual(url, "https://accounts.example.test/authorize")
            pending = google_drive_oauth.get_group_runtime_config(
                "elagente", path
            )["drive_oauth_pending"]
            self.assertEqual(
                pending["code_verifier"], "saved-pkce-verifier"
            )

            class CallbackFlow:
                credentials = SimpleNamespace(refresh_token="refresh-token")

                def fetch_token(self, **_kwargs):
                    return None

            def callback_flow(_client, **kwargs):
                captured["callback_kwargs"] = kwargs
                return CallbackFlow()

            with patch.object(
                google_drive_oauth.Flow,
                "from_client_config",
                side_effect=callback_flow,
            ), patch.object(
                google_drive_oauth, "build", return_value=FakeDrive()
            ):
                slug, connection = google_drive_oauth.finish_connection(
                    "authorization-code",
                    captured["state"],
                    REDIRECT_URI,
                    path,
                    now=101,
                )

            self.assertEqual(slug, "elagente")
            self.assertEqual(connection["email"], "felix@example.test")
            self.assertEqual(
                captured["callback_kwargs"]["code_verifier"],
                "saved-pkce-verifier",
            )
            self.assertFalse(
                captured["callback_kwargs"]["autogenerate_code_verifier"]
            )
            self.assertTrue(google_drive_oauth.has_connection("elagente", path))
            credentials = google_drive_oauth.get_user_credentials("elagente", path)
            self.assertEqual(credentials.refresh_token, "refresh-token")

            with self.assertRaisesRegex(
                google_drive_oauth.GoogleDriveOAuthError, "already used"
            ):
                google_drive_oauth.finish_connection(
                    "replay", captured["state"], REDIRECT_URI, path, now=102
                )

    def test_expired_connection_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "groups.json"
            google_drive_oauth.save_oauth_client(
                oauth_client_fixture(), REDIRECT_URI, path
            )
            captured = {}

            class FlowValue:
                code_verifier = None

                def authorization_url(self, **_kwargs):
                    self.code_verifier = "saved-pkce-verifier"
                    return "https://accounts.example.test", self.state

            def flow_factory(_client, **kwargs):
                flow = FlowValue()
                flow.state = kwargs["state"]
                captured["state"] = flow.state
                return flow

            with patch.object(
                google_drive_oauth.Flow,
                "from_client_config",
                side_effect=flow_factory,
            ):
                google_drive_oauth.create_authorization_url(
                    "elagente", REDIRECT_URI, path, now=100
                )

            with self.assertRaisesRegex(
                google_drive_oauth.GoogleDriveOAuthError, "expired"
            ):
                google_drive_oauth.finish_connection(
                    "code",
                    captured["state"],
                    REDIRECT_URI,
                    path,
                    now=100 + google_drive_oauth.STATE_MAX_AGE_SECONDS + 1,
                )

    def test_connection_state_without_pkce_verifier_requires_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "groups.json"
            google_drive_oauth.save_oauth_client(
                oauth_client_fixture(), REDIRECT_URI, path
            )
            state = "schedule-drive:elagente:legacy-state"
            google_drive_oauth.save_group_runtime_config(
                "elagente",
                {
                    "drive_oauth_pending": {
                        "state_digest": google_drive_oauth._state_digest(state),
                        "created_at": 100,
                    }
                },
                path,
            )

            with patch.object(
                google_drive_oauth.Flow, "from_client_config"
            ) as flow_factory, self.assertRaisesRegex(
                google_drive_oauth.GoogleDriveOAuthError, "latest update"
            ):
                google_drive_oauth.finish_connection(
                    "code", state, REDIRECT_URI, path, now=101
                )

            flow_factory.assert_not_called()
            self.assertEqual(
                google_drive_oauth.get_group_runtime_config(
                    "elagente", path
                )["drive_oauth_pending"],
                {},
            )


if __name__ == "__main__":
    unittest.main()
