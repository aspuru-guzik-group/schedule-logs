import json
import unittest

from group_setup import (
    DEFAULT_SLIDES_TEMPLATE_ID,
    FOLDER_MIME_TYPE,
    PRESENTATION_MIME_TYPE,
    SPREADSHEET_MIME_TYPE,
    _headers_match_ignoring_whitespace,
    _migrate_schedule,
    _require_shared_drive_folder,
    missing_slide_placeholders,
    provision_google_resources,
    provision_google_resources_in_my_drive,
    required_slide_placeholders,
    parse_service_account_json,
    should_migrate_schedule,
)
from config import GROUPS


def service_account_fixture():
    return {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "key-id",
        "private_key": "test-private-key",
        "client_email": "robotics@test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://example.test/client-cert",
    }


class FakeRequest:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class FakeDriveFiles:
    def __init__(self, workspace_drive_id="shared_drive_12345"):
        self.resources = []
        self.copied_from = []
        self.workspace_drive_id = workspace_drive_id

    def get(self, *, fileId, **_kwargs):
        if fileId == "workspace_folder_12345":
            return FakeRequest(
                {
                    "id": fileId,
                    "name": "Robotics Workspace",
                    "mimeType": FOLDER_MIME_TYPE,
                    "driveId": self.workspace_drive_id,
                    "capabilities": {"canAddChildren": True},
                }
            )
        if fileId == DEFAULT_SLIDES_TEMPLATE_ID:
            return FakeRequest(
                {
                    "id": fileId,
                    "name": "ML Template",
                    "mimeType": PRESENTATION_MIME_TYPE,
                    "capabilities": {"canCopy": True},
                }
            )
        for resource in self.resources:
            if resource.get("id") == fileId:
                value = dict(resource)
                value["capabilities"] = {
                    "canAddChildren": resource.get("mimeType") == FOLDER_MIME_TYPE,
                    "canCopy": True,
                    "canEdit": True,
                }
                return FakeRequest(value)
        raise AssertionError(f"Unexpected file lookup: {fileId}")

    def list(self, *, q, **_kwargs):
        matches = [
            resource
            for resource in self.resources
            if resource["properties"]["matterScheduleRole"] in q
        ]
        return FakeRequest({"files": matches})

    def create(self, *, body, **_kwargs):
        resource = {
            **body,
            "id": f"created-resource-{len(self.resources) + 1}",
        }
        self.resources.append(resource)
        return FakeRequest(resource)

    def copy(self, *, fileId, body, **_kwargs):
        self.copied_from.append(fileId)
        resource = {
            **body,
            "id": f"created-resource-{len(self.resources) + 1}",
            "mimeType": PRESENTATION_MIME_TYPE,
        }
        self.resources.append(resource)
        return FakeRequest(resource)


class FakeDrive:
    def __init__(self, workspace_drive_id="shared_drive_12345"):
        self.files_api = FakeDriveFiles(workspace_drive_id)
        self.permissions_api = FakePermissions()

    def files(self):
        return self.files_api

    def permissions(self):
        return self.permissions_api


class FakePermissions:
    def __init__(self):
        self.values = []

    def list(self, **_kwargs):
        return FakeRequest({"permissions": list(self.values)})

    def create(self, *, body, **_kwargs):
        permission = {**body, "id": f"permission-{len(self.values) + 1}"}
        self.values.append(permission)
        return FakeRequest(permission)


class FakeWorksheet:
    id = 42

    def __init__(self, values):
        self.values = values
        self.cleared = False

    def row_values(self, _row):
        return self.values[0]

    def get_all_values(self):
        return self.values

    def clear(self):
        self.cleared = True

    def update(self, *, values, range_name):
        self.values = values
        self.range_name = range_name


class FakeSpreadsheet:
    def __init__(self):
        self.duplicates = []

    def duplicate_sheet(self, **kwargs):
        self.duplicates.append(kwargs)


class GroupSetupTest(unittest.TestCase):
    def test_my_drive_workspace_is_rejected_before_file_creation(self):
        drive = FakeDrive(workspace_drive_id=None)

        with self.assertRaisesRegex(ValueError, "Shared Drive"):
            provision_google_resources(
                "robotics",
                GROUPS["robotics"],
                "workspace_folder_12345",
                service_account_fixture(),
                _drive=drive,
            )

        self.assertEqual(drive.files_api.resources, [])

    def test_writable_destinations_must_be_in_a_shared_drive(self):
        with self.assertRaisesRegex(ValueError, "materials folder.*My Drive"):
            _require_shared_drive_folder({}, "materials folder")

    def test_personal_drive_setup_creates_and_reuses_complete_workspace(self):
        drive = FakeDrive(workspace_drive_id=None)

        values, messages = provision_google_resources_in_my_drive(
            "elagente",
            GROUPS["elagente"],
            service_account_fixture(),
            _drive=drive,
        )

        self.assertEqual(len(drive.files_api.resources), 5)
        self.assertEqual(len(drive.permissions_api.values), 1)
        self.assertEqual(
            drive.permissions_api.values[0]["emailAddress"],
            service_account_fixture()["client_email"],
        )
        self.assertTrue(any(message.startswith("Created ") for message in messages))

        repeated_values, _ = provision_google_resources_in_my_drive(
            "elagente",
            GROUPS["elagente"],
            service_account_fixture(),
            _drive=drive,
        )

        self.assertEqual(repeated_values, values)
        self.assertEqual(len(drive.files_api.resources), 5)
        self.assertEqual(len(drive.permissions_api.values), 1)

    def test_headers_allow_only_surrounding_whitespace_repair(self):
        expected = ["Date", "Title", "Description", "PDF_Name", "PDF_Link"]

        self.assertTrue(
            _headers_match_ignoring_whitespace(
                ["Date", "Title", "Description", "PDF_Name", "PDF_Link "],
                expected,
            )
        )
        self.assertFalse(
            _headers_match_ignoring_whitespace(
                ["Date", "Title", "Description", "PDF Name", "PDF_Link"],
                expected,
            )
        )

    def test_initial_setup_allows_supported_schedule_layout_migration(self):
        self.assertTrue(should_migrate_schedule(True, False, True))
        self.assertTrue(should_migrate_schedule(True, False, False))
        self.assertFalse(should_migrate_schedule(False, False, True))
        self.assertFalse(should_migrate_schedule(False, True, False))
        self.assertTrue(should_migrate_schedule(False, True, True))

    def test_cloud_shell_output_can_be_pasted_with_markers(self):
        service_account = service_account_fixture()
        output = (
            "Cloud setup log\n---BEGIN JSON---\n"
            + json.dumps(service_account)
            + "\n---END JSON---\n"
        )

        self.assertEqual(parse_service_account_json(output), service_account)

    def test_slide_placeholders_match_presenter_mode(self):
        self.assertEqual(
            required_slide_placeholders(1),
            {"{{DATE}}", "{{PRESENTER}}"},
        )
        self.assertEqual(
            required_slide_placeholders(2),
            {"{{DATE}}", "{{PRESENTER1}}", "{{PRESENTER2}}"},
        )
        ml_template_text = "{{DATE}} {{PRESENTER1}} {{PRESENTER2}}"
        self.assertEqual(missing_slide_placeholders(ml_template_text, 1), [])
        self.assertEqual(missing_slide_placeholders(ml_template_text, 2), [])

    def test_provisioning_creates_and_then_reuses_all_resources(self):
        drive = FakeDrive()

        values, messages = provision_google_resources(
            "robotics",
            GROUPS["robotics"],
            "https://drive.google.com/drive/folders/workspace_folder_12345",
            service_account_fixture(),
            _drive=drive,
        )

        self.assertEqual(values["workspace_folder_id"], "workspace_folder_12345")
        self.assertEqual(
            {resource["mimeType"] for resource in drive.files_api.resources},
            {FOLDER_MIME_TYPE, SPREADSHEET_MIME_TYPE, PRESENTATION_MIME_TYPE},
        )
        self.assertEqual(drive.files_api.copied_from, [DEFAULT_SLIDES_TEMPLATE_ID])
        self.assertEqual(len(drive.files_api.resources), 4)
        self.assertTrue(any(message.startswith("Created ") for message in messages))

        repeated_values, repeated_messages = provision_google_resources(
            "robotics",
            GROUPS["robotics"],
            "workspace_folder_12345",
            service_account_fixture(),
            _drive=drive,
        )

        self.assertEqual(repeated_values, values)
        self.assertEqual(len(drive.files_api.resources), 4)
        self.assertEqual(
            sum(message.startswith("Reused ") for message in repeated_messages),
            4,
        )

    def test_one_to_two_presenter_migration_keeps_existing_presenter(self):
        spreadsheet = FakeSpreadsheet()
        worksheet = FakeWorksheet(
            [["Date", "Presenter"], ["2026-07-15", "Ada"]]
        )

        backup = _migrate_schedule(
            spreadsheet,
            worksheet,
            ["Date", "Presenter 1", "Presenter 2"],
        )

        self.assertTrue(backup.startswith("Schedule Backup "))
        self.assertEqual(len(spreadsheet.duplicates), 1)
        self.assertTrue(worksheet.cleared)
        self.assertEqual(
            worksheet.values,
            [
                ["Date", "Presenter 1", "Presenter 2"],
                ["2026-07-15", "Ada", "EMPTY"],
            ],
        )

    def test_two_to_one_presenter_migration_uses_nonempty_slot(self):
        spreadsheet = FakeSpreadsheet()
        worksheet = FakeWorksheet(
            [
                ["Date", "Presenter 1", "Presenter 2"],
                ["2026-07-15", "EMPTY", "Grace"],
            ]
        )

        _migrate_schedule(
            spreadsheet,
            worksheet,
            ["Date", "Presenter"],
        )

        self.assertEqual(
            worksheet.values,
            [["Date", "Presenter"], ["2026-07-15", "Grace"]],
        )


if __name__ == "__main__":
    unittest.main()
