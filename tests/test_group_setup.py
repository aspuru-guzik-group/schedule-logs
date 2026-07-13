import unittest

from group_setup import (
    _migrate_schedule,
    required_slide_placeholders,
)


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
    def test_slide_placeholders_match_presenter_mode(self):
        self.assertEqual(
            required_slide_placeholders(1),
            {"{{DATE}}", "{{PRESENTER}}"},
        )
        self.assertEqual(
            required_slide_placeholders(2),
            {"{{DATE}}", "{{PRESENTER1}}", "{{PRESENTER2}}"},
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
