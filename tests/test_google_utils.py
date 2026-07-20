import unittest
from unittest.mock import Mock, patch

try:
    import google_utils
except ModuleNotFoundError:
    google_utils = None


@unittest.skipIf(
    google_utils is None, "application dependencies are not installed"
)
class GoogleUtilsTest(unittest.TestCase):
    def test_oauth_only_group_is_configured_without_service_account(self):
        config = {
            field: "value"
            for field in google_utils.REQUIRED_INTEGRATION_FIELDS
        }
        config["drive_storage_mode"] = "oauth"
        with patch.object(
            google_utils, "get_group_connection_config", return_value=config
        ), patch.object(google_utils, "has_drive_oauth", return_value=True):
            self.assertTrue(google_utils.is_group_configured("robotics"))

    def test_storage_quota_error_becomes_actionable_configuration_error(self):
        from googleapiclient.errors import HttpError
        from httplib2 import Response

        error = HttpError(
            Response({"status": "403", "reason": "Forbidden"}),
            b'{"error":{"message":"quota exceeded","errors":['
            b'{"reason":"storageQuotaExceeded"}]}}',
            uri="https://www.googleapis.com/drive/v3/files/template/copy",
        )

        class FailingRequest:
            def execute(self):
                raise error

        with self.assertRaisesRegex(
            google_utils.DriveStorageConfigurationError,
            "Connect the subgroup lead",
        ):
            google_utils._execute_drive_write(FailingRequest())

    def test_every_group_can_use_connected_user_credentials(self):
        credentials = object()
        service = object()
        with patch.object(
            google_utils.google_drive_oauth,
            "has_connection",
            return_value=True,
        ), patch.object(
            google_utils.google_drive_oauth,
            "get_user_credentials",
            return_value=credentials,
        ) as get_credentials, patch.object(
            google_utils, "build", return_value=service
        ) as build:
            self.assertIs(google_utils.get_drive_service("ml"), service)

        get_credentials.assert_called_once_with("ml")
        build.assert_called_once_with("drive", "v3", credentials=credentials)

    def test_missing_elagente_connection_is_actionable(self):
        with patch.object(
            google_utils.google_drive_oauth,
            "has_connection",
            return_value=False,
        ):
            with self.assertRaisesRegex(
                google_utils.DriveOAuthConnectionError, "Connect the subgroup lead"
            ):
                google_utils.get_drive_service("elagente")

    def test_legacy_group_without_connection_keeps_service_account(self):
        credentials = object()
        service = object()
        with patch.object(
            google_utils.google_drive_oauth,
            "has_connection",
            return_value=False,
        ), patch.object(
            google_utils,
            "_get_service_account_info",
            return_value={"client_email": "service@example.test"},
        ), patch.object(
            google_utils.Credentials,
            "from_service_account_info",
            return_value=credentials,
        ), patch.object(
            google_utils, "build", return_value=service
        ):
            self.assertIs(google_utils.get_drive_service("ml"), service)

    def test_recorded_oauth_storage_requires_reconnection(self):
        with patch.object(
            google_utils.google_drive_oauth,
            "has_connection",
            return_value=False,
        ), patch.object(
            google_utils,
            "get_group_runtime_config",
            return_value={"drive_storage_mode": "oauth"},
        ):
            with self.assertRaisesRegex(
                google_utils.DriveOAuthConnectionError,
                "Connect the subgroup lead",
            ):
                google_utils.get_drive_service("robotics")

    def test_oauth_only_group_uses_user_for_sheets(self):
        credentials = Mock()
        client = object()
        with patch.object(
            google_utils,
            "get_group_connection_config",
            return_value={"drive_storage_mode": "oauth"},
        ), patch.object(
            google_utils.google_drive_oauth,
            "has_connection",
            return_value=True,
        ), patch.object(
            google_utils.google_drive_oauth,
            "get_user_credentials",
            return_value=credentials,
        ), patch.object(
            google_utils.gspread, "authorize", return_value=client
        ) as authorize:
            self.assertIs(google_utils.get_gspread_client("robotics"), client)

        credentials.refresh.assert_called_once()
        authorize.assert_called_once_with(credentials)

    def test_empty_schedule_preserves_sheet_headers(self):
        class EmptySchedule:
            def get_all_records(self):
                return []

            def row_values(self, _row):
                return ["Date", "Presenter 1", "Presenter 2"]

        with patch.object(
            google_utils, "get_sheet", return_value=EmptySchedule()
        ):
            schedule = google_utils.get_schedule_df("elagente")

        self.assertTrue(schedule.empty)
        self.assertEqual(
            list(schedule.columns), ["Date", "Presenter 1", "Presenter 2"]
        )


if __name__ == "__main__":
    unittest.main()
