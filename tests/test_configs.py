from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from vesc_workbench.configs import (
    ConfigManager,
    profile_name_for_source,
    profile_name_from_path,
    validate_xml_file,
)


class ConfigTests(TestCase):
    def test_detect_motor_config(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "04_hfi_medium_motor.xml"
            path.write_text("<mcconf><foc_motor_r>0.013</foc_motor_r></mcconf>", encoding="utf-8")
            config = validate_xml_file(path)
            self.assertEqual(config.kind, "motor")

    def test_profile_name_strips_suffix(self) -> None:
        self.assertEqual(profile_name_from_path(Path("04_hfi_medium_motor.xml")), "04_hfi_medium")

    def test_profile_name_uses_nested_directory(self) -> None:
        root = Path("vesc-test-profiles")
        path = root / "04_hfi_medium" / "vesc_mcconf.xml"
        self.assertEqual(profile_name_for_source(path, root), "04_hfi_medium")

    def test_stage_new_configs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            incoming = root / "profiles" / "incoming"
            staged = root / "profiles" / "staged"
            applied = root / "profiles" / "applied"
            incoming.mkdir(parents=True)
            (incoming / "demo_app.xml").write_text(
                "<appconf><app_to_use>3</app_to_use></appconf>",
                encoding="utf-8",
            )

            manager = ConfigManager(root, incoming, staged, applied)
            bundles = manager.stage_new_configs()

            self.assertEqual(len(bundles), 1)
            self.assertEqual(bundles[0].profile, "demo")
            self.assertTrue((bundles[0].path / "manifest.json").exists())

    def test_stage_nested_profile_pair_as_one_bundle(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            incoming = root / "vesc-test-profiles"
            profile = incoming / "04_hfi_medium"
            staged = root / "profiles" / "staged"
            applied = root / "profiles" / "applied"
            profile.mkdir(parents=True)
            (profile / "vesc_appconf.xml").write_text(
                "<appconf><app_to_use>3</app_to_use></appconf>",
                encoding="utf-8",
            )
            (profile / "vesc_mcconf.xml").write_text(
                "<mcconf><foc_motor_r>0.013</foc_motor_r></mcconf>",
                encoding="utf-8",
            )

            manager = ConfigManager(root, incoming, staged, applied)
            bundles = manager.stage_new_configs()

            self.assertEqual(len(bundles), 1)
            self.assertEqual(bundles[0].profile, "04_hfi_medium")
            self.assertEqual(len(bundles[0].files), 2)

    def test_duplicate_files_in_different_profiles_are_distinct_bundles(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            incoming = root / "vesc-test-profiles"
            staged = root / "profiles" / "staged"
            applied = root / "profiles" / "applied"
            for profile_name in ("00_autotest_profile04_uart", "04_hfi_medium"):
                profile = incoming / profile_name
                profile.mkdir(parents=True)
                (profile / "vesc_appconf.xml").write_text(
                    "<appconf><app_to_use>3</app_to_use></appconf>",
                    encoding="utf-8",
                )
                (profile / "vesc_mcconf.xml").write_text(
                    "<mcconf><foc_motor_r>0.013</foc_motor_r></mcconf>",
                    encoding="utf-8",
                )

            manager = ConfigManager(root, incoming, staged, applied)
            bundles = manager.stage_new_configs()

            self.assertEqual({bundle.profile for bundle in bundles}, {
                "00_autotest_profile04_uart",
                "04_hfi_medium",
            })
