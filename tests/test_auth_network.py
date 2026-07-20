import unittest
from types import SimpleNamespace
from unittest.mock import patch

try:
    import auth
except ModuleNotFoundError:
    auth = None


@unittest.skipIf(auth is None, "application dependencies are not installed")
class AuthNetworkTest(unittest.TestCase):
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
