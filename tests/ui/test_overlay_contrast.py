"""Offscreen rendering tests for readable text on light and dark desktops."""

import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from focusloop.overlay import (
    Overlay, contrasting_shadow_color, draw_shadowed_text,
)
from focusloop.timer import COLOR_HEX, PhaseConfig


class ContrastTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_white_uses_black_shadow_black_uses_white(self):
        self.assertEqual(contrasting_shadow_color(QColor(COLOR_HEX["white"])).name(), "#000000")
        self.assertEqual(contrasting_shadow_color(QColor(COLOR_HEX["black"])).name(), "#ffffff")

    def test_every_preset_chooses_contrasting_shadow(self):
        for key, value in COLOR_HEX.items():
            with self.subTest(color=key):
                result = contrasting_shadow_color(QColor(value))
                self.assertIn(result.name(), ("#000000", "#ffffff"))
                self.assertGreater(result.alpha(), 0)
                if key != "black":
                    self.assertEqual(result.name(), "#000000")

    def test_actual_pixels_contain_foreground_and_shadow(self):
        # Draw transparent images rather than relying on the OS desktop color.
        for key in ("white", "black", "mint", "sky", "amber", "rose", "violet"):
            with self.subTest(color=key):
                canvas = QImage(240, 110, QImage.Format.Format_ARGB32_Premultiplied)
                canvas.fill(Qt.GlobalColor.transparent)
                painter = QPainter(canvas)
                font = QFont("Consolas", 50)
                font.setBold(True)
                painter.setFont(font)
                draw_shadowed_text(
                    painter, QRect(0, 0, 240, 110), "88", QColor(COLOR_HEX[key]),
                )
                painter.end()

                fg = QColor(COLOR_HEX[key])
                shadow = contrasting_shadow_color(fg)
                found_foreground = False
                found_shadow = False
                for y in range(canvas.height()):
                    for x in range(canvas.width()):
                        c = canvas.pixelColor(x, y)
                        if c.alpha() < 170:
                            continue
                        if (
                            abs(c.red() - fg.red()) < 8
                            and abs(c.green() - fg.green()) < 8
                            and abs(c.blue() - fg.blue()) < 8
                            and c.alpha() > 230
                        ):
                            found_foreground = True
                        if (
                            abs(c.red() - shadow.red()) < 8
                            and abs(c.green() - shadow.green()) < 8
                            and abs(c.blue() - shadow.blue()) < 8
                        ):
                            found_shadow = True
                        if found_foreground and found_shadow:
                            break
                    if found_foreground and found_shadow:
                        break
                self.assertTrue(found_foreground, f"{key}: main text missing")
                self.assertTrue(found_shadow, f"{key}: shadow missing")

    def test_progress_redraw_is_limited_to_visible_arc_changes(self):
        overlay = Overlay(PhaseConfig("作業", 1))
        overlay.show()
        self.app.processEvents()
        with patch.object(overlay, "update") as repaint:
            # 30fps time increments too small to change the 1/16 degree Qt arc.
            overlay.set_ring_progress(0.999999)
            repaint.assert_not_called()
            self.assertAlmostEqual(overlay.remaining_ratio, 0.999999)
            overlay.set_ring_progress(0.99)
            repaint.assert_called_once()
            overlay.set_ring_progress(0.989999)
            repaint.assert_called_once()
            overlay.set_ring_progress(0.5)
            self.assertEqual(repaint.call_count, 2)
        overlay.close()

        simple = Overlay(PhaseConfig("作業", 1, simple=True))
        with patch.object(simple, "update") as repaint:
            simple.set_ring_progress(0.5)
            repaint.assert_not_called()
            self.assertEqual(simple.remaining_ratio, 0.5)
        simple.close()

    def test_modern_title_is_above_clock_and_loop_is_below(self):
        overlay = Overlay(PhaseConfig("作業", 45, font_size=300))
        overlay.show()
        self.app.processEvents()
        with patch("focusloop.overlay.draw_shadowed_text", wraps=draw_shadowed_text) as draw:
            image = overlay.grab()
            self.assertFalse(image.isNull())
            self.assertEqual(draw.call_count, 3)
            calls = draw.call_args_list
            self.assertEqual(calls[0].args[2], "LOOP 01")
            self.assertEqual(calls[1].args[2], "45:00")
            self.assertEqual(calls[2].args[2], "作業")
            loop_y = calls[0].args[1].center().y()
            clock_y = calls[1].args[1].center().y()
            title_y = calls[2].args[1].center().y()
            self.assertLess(title_y, clock_y)
            self.assertLess(clock_y, loop_y)
        screen = self.app.primaryScreen().availableGeometry()
        self.assertTrue(screen.contains(overlay.geometry()))
        self.assertLessEqual(overlay._render_font_size, 300)
        overlay.close()

    def test_simple_and_modern_draw_text_with_shared_shadow(self):
        for style, expected in (("simple", 1), ("modern", 3)):
            with self.subTest(style=style):
                overlay = Overlay(PhaseConfig("作業", 45, color="black", simple=(style == "simple")))
                overlay.show()
                self.app.processEvents()
                with patch("focusloop.overlay.draw_shadowed_text", wraps=draw_shadowed_text) as draw:
                    image = overlay.grab()
                    self.assertFalse(image.isNull())
                    self.assertEqual(draw.call_count, expected)
                overlay.close()


if __name__ == "__main__":
    unittest.main()
