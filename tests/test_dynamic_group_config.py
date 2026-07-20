import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import GROUPS, get_group_config, get_presenter_cols
from runtime_config import save_group_runtime_config


class DynamicGroupConfigTest(unittest.TestCase):
    def test_unconfigured_self_service_groups_keep_normal_landing_entries(self):
        for slug in ("elagente", "handson", "robotics"):
            with self.subTest(slug=slug):
                self.assertTrue(GROUPS[slug]["self_service_setup"])

    def test_robotics_group_uses_robot_face_and_editable_presenter_default(self):
        robotics = GROUPS["robotics"]

        self.assertEqual(robotics["display_name"], "Robotics Subgroup")
        self.assertEqual(robotics["emoji"], "🤖")
        self.assertEqual(robotics["num_presenters"], 1)

    def test_runtime_presenter_mode_and_schedule_settings_override_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "groups.json"
            with patch.dict(
                os.environ, {"SCHEDULE_RUNTIME_CONFIG": str(path)}
            ):
                save_group_runtime_config(
                    "elagente",
                    {
                        "num_presenters": 1,
                        "meeting_day": "friday",
                        "presentation_duration": 35,
                    },
                )
                group = get_group_config("elagente")

            self.assertEqual(group["num_presenters"], 1)
            self.assertEqual(group["meeting_day"], "friday")
            self.assertEqual(group["presentation_duration"], 35)
            self.assertEqual(get_presenter_cols(group), ["Presenter"])


if __name__ == "__main__":
    unittest.main()
