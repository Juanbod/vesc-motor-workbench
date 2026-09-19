from unittest import TestCase

from vesc_workbench.esp_hall import parse_debug_line


class EspHallTests(TestCase):
    def test_parse_debug_line(self) -> None:
        sample = parse_debug_line("raw=3867 sector=3 status=0x67 magnet=ok")
        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertEqual(sample.raw, 3867)
        self.assertEqual(sample.sector, 3)
        self.assertEqual(sample.status, "0x67")
        self.assertEqual(sample.magnet, "ok")

    def test_expected_sector_uses_pole_pairs(self) -> None:
        sample = parse_debug_line("raw=100 sector=1 status=0x67 magnet=ok", pole_pairs=7)
        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertEqual(sample.expected_sector, 1)

