import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

try:
    import auth
except ModuleNotFoundError:
    auth = None


@unittest.skipIf(auth is None, "application dependencies are not installed")
class AuthNetworkTest(unittest.TestCase):
    def test_slack_authorization_preselects_the_matter_lab_workspace(self):
        fake_streamlit = SimpleNamespace(
            secrets={
                "app_url": "https://schedule.example.test/",
                "slack": {
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                    "team_id": "T02G0R3HY",
                },
            }
        )
        with patch.object(auth, "st", fake_streamlit):
            authorization_url = auth._get_auth_url()
            config = auth._get_slack_config()

        query = parse_qs(urlparse(authorization_url).query)
        self.assertEqual(query["team"], ["T02G0R3HY"])
        self.assertEqual(query["redirect_uri"], ["https://schedule.example.test"])
        self.assertEqual(
            config["workspace_url"], "https://aspuru.slack.com"
        )

    def test_google_drive_callback_is_not_treated_as_slack_callback(self):
        self.assertTrue(
            auth._is_google_drive_oauth_callback(
                {"code": "google-code", "state": "schedule-drive:elagente:nonce"}
            )
        )
        self.assertFalse(
            auth._is_google_drive_oauth_callback(
                {"code": "slack-code", "state": "slack-state"}
            )
        )

    def test_auth_uses_nginx_real_ip(self):
        fake_streamlit = SimpleNamespace(
            context=SimpleNamespace(headers={"X-Real-IP": "10.21.10.221"})
        )
        with patch.object(auth, "st", fake_streamlit):
            self.assertTrue(auth._is_ethernet_network())

    def test_auth_ignores_spoofed_forwarded_for(self):
        fake_streamlit = SimpleNamespace(
            context=SimpleNamespace(
                headers={
                    "X-Real-IP": "203.0.113.10",
                    "X-Forwarded-For": "10.21.10.221",
                }
            )
        )
        with patch.object(auth, "st", fake_streamlit):
            self.assertFalse(auth._is_ethernet_network())


if __name__ == "__main__":
    unittest.main()
