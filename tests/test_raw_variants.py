from unittest import TestCase
import struct

from vesc_workbench.raw_variants import (
    MCCONF_OFFSETS_FW6_02_MKSESC_84_100_HP,
    patch_mcconf_for_variant,
    RawVariantSpec,
)


class RawVariantTests(TestCase):
    def test_patch_known_offsets(self) -> None:
        data = bytes(481)
        patched = patch_mcconf_for_variant(data, RawVariantSpec("demo", foc_sl_erpm=3000, foc_hall_interp_erpm=1000))
        offsets = MCCONF_OFFSETS_FW6_02_MKSESC_84_100_HP
        self.assertEqual(struct.unpack(">f", patched[offsets["l_current_max"] : offsets["l_current_max"] + 4])[0], 75)
        self.assertEqual(struct.unpack(">f", patched[offsets["l_in_current_max"] : offsets["l_in_current_max"] + 4])[0], 100)
        self.assertEqual(struct.unpack(">f", patched[offsets["foc_sl_erpm"] : offsets["foc_sl_erpm"] + 4])[0], 3000)
        self.assertEqual(
            struct.unpack(">f", patched[offsets["foc_hall_interp_erpm"] : offsets["foc_hall_interp_erpm"] + 4])[0],
            1000,
        )
        self.assertEqual(patched[offsets["foc_mtpa_mode"]], 0)
        self.assertEqual(patched[offsets["foc_hall_table"] : offsets["foc_hall_table"] + 8], bytes([255, 22, 90, 186, 162, 123, 43, 255]))

    def test_patch_mtpa_mode(self) -> None:
        data = bytes(481)
        patched = patch_mcconf_for_variant(data, RawVariantSpec("demo", foc_sl_erpm=2000, foc_mtpa_mode=1))
        offsets = MCCONF_OFFSETS_FW6_02_MKSESC_84_100_HP
        self.assertEqual(patched[offsets["foc_mtpa_mode"]], 1)
