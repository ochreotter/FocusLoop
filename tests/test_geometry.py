"""Tests for the tray popup placement helper."""

import unittest

from focusloop.geometry import tray_menu_position


class TrayMenuPositionTests(unittest.TestCase):
    def test_bottom_right_tray_icon_places_menu_above_cursor(self):
        x, y = tray_menu_position(1900, 1060, 0, 0, 1920, 1040, 220, 250)
        self.assertLessEqual(y + 250, 1040 - 24)
        self.assertGreaterEqual(x, 24)
        self.assertLessEqual(x + 220, 1920 - 24)
        self.assertLess(y, 1060)

    def test_bottom_left_tray_icon_keeps_full_menu_visible(self):
        x, y = tray_menu_position(30, 1050, 0, 0, 1920, 1040, 240, 350)
        self.assertEqual(x, 24)
        self.assertGreaterEqual(y, 24)
        self.assertLessEqual(y + 350, 1040 - 24)

    def test_secondary_monitor_with_negative_origin(self):
        x, y = tray_menu_position(-1800, 900, -1920, 0, 1920, 1040, 250, 300)
        self.assertGreaterEqual(x, -1920 + 24)
        self.assertLessEqual(x + 250, -24)
        self.assertGreaterEqual(y, 24)
        self.assertLessEqual(y + 300, 1040 - 24)

    def test_cursor_near_top_stays_inside_available_area(self):
        x, y = tray_menu_position(400, 30, 0, 0, 1280, 720, 180, 210)
        self.assertEqual(y, 24)
        self.assertGreaterEqual(x, 24)

    def test_screen_with_offset_and_taskbar_reserved_space(self):
        x, y = tray_menu_position(2900, 1200, 1920, 200, 1280, 900, 300, 400)
        self.assertGreaterEqual(x, 1944)
        self.assertLessEqual(x + 300, 1920 + 1280 - 24)
        self.assertGreaterEqual(y, 224)
        self.assertLessEqual(y + 400, 200 + 900 - 24)


if __name__ == "__main__":
    unittest.main()
