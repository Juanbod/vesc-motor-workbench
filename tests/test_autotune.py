from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import csv
import json
import struct

from vesc_workbench.autotune import (
    TuneSpec,
    generate_autotune_queue,
    load_autotune_matrix,
    patch_verified_tuning_fields,
    score_telemetry,
)
from vesc_workbench.raw_variants import MCCONF_OFFSETS_FW6_02_MKSESC_84_100_HP


class AutotuneTests(TestCase):
    def _write_matrix(self, root: Path) -> Path:
        matrix = root / "matrix.json"
        matrix.write_text(
            json.dumps(
                {
                    "test": {"current_steps": [2, 5], "hold_s": 1, "cooldown_s": 0},
                    "variants": [
                        {
                            "name": "mtpa-off",
                            "foc_mtpa_mode": 0,
                            "phase_current_max": 25,
                            "input_current_max": 20,
                            "abs_current_max": 45,
                        },
                        {
                            "name": "mtpa-on",
                            "foc_mtpa_mode": 1,
                            "phase_current_max": 25,
                            "input_current_max": 20,
                            "abs_current_max": 45,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        return matrix

    def _write_backup(self, root: Path) -> Path:
        backup = root / "backup"
        backup.mkdir()
        motor = bytes(range(256)) + bytes(range(256))
        app = b"app"
        (backup / "mcconf.bin").write_bytes(motor)
        (backup / "appconf.bin").write_bytes(app)
        (backup / "manifest.json").write_text(
            json.dumps(
                {
                    "firmware": {"major": 6, "minor": 2, "hardware": "MKSESC_84_100_HP"},
                    "files": {
                        "motor": {"path": "mcconf.bin", "sha256": "unused"},
                        "app": {"path": "appconf.bin", "sha256": "unused"},
                    },
                }
            ),
            encoding="utf-8",
        )
        return backup

    def test_matrix_loads_first_safe_sweep(self) -> None:
        with TemporaryDirectory() as tmp:
            plan, specs = load_autotune_matrix(self._write_matrix(Path(tmp)))
        self.assertEqual(plan.current_steps, (2.0, 5.0))
        self.assertEqual([spec.foc_mtpa_mode for spec in specs], [0, 1])

    def test_verified_patch_leaves_unrelated_bytes_alone(self) -> None:
        source = bytes(range(256)) + bytes(range(256))
        patched = patch_verified_tuning_fields(source, TuneSpec("demo", 1, 25, 20, 45))
        offsets = MCCONF_OFFSETS_FW6_02_MKSESC_84_100_HP
        self.assertEqual(patched[100], source[100])
        self.assertEqual(patched[offsets["foc_hall_table"]], source[offsets["foc_hall_table"]])
        self.assertEqual(struct.unpack(">f", patched[offsets["l_current_max"] : offsets["l_current_max"] + 4])[0], 25)
        self.assertEqual(patched[offsets["foc_mtpa_mode"]], 1)

    def test_generating_queue_preserves_base_app_config(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            generated = generate_autotune_queue(self._write_backup(root), self._write_matrix(root), root / "queue")
            self.assertEqual(len(generated), 2)
            self.assertEqual((generated[0] / "appconf.bin").read_bytes(), b"app")
            manifest = json.loads((generated[1] / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["autotune"]["spec"]["foc_mtpa_mode"], 1)

    def test_score_rejects_wrong_direction(self) -> None:
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "telemetry.csv"
            with log.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["event", "erpm", "current_motor_a", "current_in_a", "id_a", "iq_a", "duty"],
                )
                writer.writeheader()
                writer.writerow({"event": "sample", "erpm": "800", "current_motor_a": "5", "current_in_a": "4", "id_a": "1", "iq_a": "5", "duty": "0.2"})
                writer.writerow({"event": "sample", "erpm": "900", "current_motor_a": "5", "current_in_a": "4", "id_a": "1", "iq_a": "5", "duty": "0.2"})
            good = score_telemetry(log, completed=True, expected_direction=1)
            bad = score_telemetry(log, completed=True, expected_direction=-1)
        self.assertGreater(float(good["score"]), 0)
        self.assertTrue(bad["wrong_direction"])
        self.assertLess(float(bad["score"]), -90000)
