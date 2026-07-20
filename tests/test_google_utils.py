import unittest
from unittest.mock import patch

try:
    import google_utils
except ModuleNotFoundError:
    google_utils = None


@unittest.skipIf(
    google_utils is None, "application dependencies are not installed"
)
class GoogleUtilsTest(unittest.TestCase):
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
            "Shared Drive workspace",
        ):
            google_utils._execute_drive_write(FailingRequest())

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
