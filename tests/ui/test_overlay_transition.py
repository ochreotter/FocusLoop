"""Regression tests for flicker-free overlay phase transitions.

Qt's offscreen platform verifies the ordering of hide, geometry changes and
re-exposure. Windows compositor behaviour still needs an actual desktop check.
"""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from focusloop.app import FocusLoopApp
from focusloop.overlay import Overlay
from focusloop.timer import default_phases


class TracedOverlay(Overlay):
    def __init__(self, phase):
        self.events = []
        super().__init__(phase)

    def _record(self, kind):
        self.events.append((
            kind, self.isVisible(), self.phase_config,
            self.display_style, self._render_font_size,
            self.width(), self.height(), self.pos(),
        ))

    def hide(self):
        self._record("hide")
        return super().hide()

    def show(self):
        self._record("show")
        return super().show()

    def setFixedSize(self, width, height):
        self._record("resize")
        return super().setFixedSize(width, height)

    def reposition(self):
        self._record("move")
        return super().reposition()

    def repaint(self):
        self._record("repaint")
        return super().repaint()

    def paintEvent(self, event):
        self._record("paint")
        return super().paintEvent(event)


class OverlayPhaseTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.overlay = TracedOverlay(default_phases()[0])
        self.overlay.show()
        self.app.processEvents()
        self.assertTrue(self.overlay.isVisible())
        self.overlay.events.clear()

    def tearDown(self):
        self.overlay.close()
        self.app.processEvents()

    def _events(self, kind):
        return [entry for entry in self.overlay.events if entry[0] == kind]

    def _assert_hidden_geometry_changes(self):
        for event in self.overlay.events:
            if event[0] in ("resize", "move"):
                self.assertFalse(event[1], f"{event[0]} occurred while visible")

    def test_size_position_style_and_topmost_apply_before_show(self):
        phase = replace(
            self.overlay.phase_config,
            font_size=200, position="top_right", simple=True, topmost=False,
            color="mint", opacity=70,
        )
        self.overlay.set_clock("15:00", phase, 0.9, 2)
        self.app.processEvents()

        names = [event[0] for event in self.overlay.events]
        self.assertIn("hide", names)
        self.assertIn("resize", names)
        self.assertIn("move", names)
        self.assertIn("show", names)
        self.assertIn("repaint", names)
        self.assertLess(names.index("hide"), names.index("resize"))
        self.assertLess(names.index("resize"), names.index("move"))
        self.assertLess(names.index("move"), names.index("show"))
        self.assertLess(names.index("show"), names.index("repaint"))
        self._assert_hidden_geometry_changes()

        shown = self._events("show")[0]
        self.assertEqual(shown[2], phase)
        self.assertEqual(shown[3], "simple")
        self.assertLessEqual(shown[4], phase.font_size)
        self.assertEqual(self.overlay.phase_config, phase)
        self.assertEqual(self.overlay.clock_text, "15:00")
        self.assertTrue(self.overlay.isVisible())
        self.assertFalse(self.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        area = QGuiApplication.primaryScreen().availableGeometry()
        self.assertEqual(self.overlay.pos().x(), area.right() - self.overlay.width() - 24)
        self.assertEqual(self.overlay.pos().y(), area.top() + 24)
        # Every paint after re-exposure must read the completed phase.
        for paint in self._events("paint"):
            self.assertEqual(paint[2], phase)
            self.assertEqual(paint[3], "simple")

    def test_position_only_and_topmost_only_are_also_hidden_transactions(self):
        phase = replace(self.overlay.phase_config, position="center")
        self.overlay.set_clock("44:59", phase)
        self.app.processEvents()
        names = [entry[0] for entry in self.overlay.events]
        self.assertLess(names.index("hide"), names.index("move"))
        self.assertLess(names.index("move"), names.index("show"))
        self.assertNotIn("resize", names)
        self._assert_hidden_geometry_changes()
        self.overlay.events.clear()

        # No resize/move is necessary for a window flag change, but the
        # window must only reappear once the topmost flag is applied.
        phase = replace(phase, topmost=False)
        self.overlay.set_clock("44:58", phase)
        self.app.processEvents()
        names = [entry[0] for entry in self.overlay.events]
        self.assertIn("hide", names)
        self.assertIn("show", names)
        self.assertLess(names.index("hide"), names.index("show"))
        self.assertNotIn("resize", names)
        self.assertNotIn("move", names)
        self.assertFalse(self.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    def test_regular_countdown_and_color_updates_do_not_hide_overlay(self):
        original_position = self.overlay.pos()
        self.overlay.set_clock("44:59", self.overlay.phase_config, 0.9)
        self.app.processEvents()
        self.assertFalse(any(item[0] in ("hide", "show", "move", "resize")
                             for item in self.overlay.events))
        self.overlay.events.clear()
        changed_colors = replace(self.overlay.phase_config, color="sky", opacity=45)
        self.overlay.set_clock("44:58", changed_colors, 0.8)
        self.app.processEvents()
        self.assertFalse(any(item[0] in ("hide", "show", "move", "resize")
                             for item in self.overlay.events))
        self.assertEqual(self.overlay.pos(), original_position)
        self.assertTrue(self.overlay.isVisible())

    def test_hidden_phase_is_never_reexposed_during_geometry_changes(self):
        hidden = replace(
            self.overlay.phase_config,
            font_size=180, position="center", hidden=True,
        )
        self.overlay.set_clock("15:00", hidden)
        self.app.processEvents()
        self.assertFalse(self.overlay.isVisible())
        self.assertIn("hide", [e[0] for e in self.overlay.events])
        self.assertNotIn("show", [e[0] for e in self.overlay.events])
        self._assert_hidden_geometry_changes()

        self.overlay.events.clear()
        visible = replace(hidden, hidden=False, position="bottom_right", simple=True)
        self.overlay.set_clock("10:00", visible)
        self.app.processEvents()
        # The controller, not set_clock, decides when a previously hidden
        # phase may be shown again.
        self.assertFalse(self.overlay.isVisible())
        self._assert_hidden_geometry_changes()
        self.assertNotIn("show", [e[0] for e in self.overlay.events])
        self.assertEqual(self.overlay.position_name, "bottom_right")



class ControllerPhaseTransitionTests(unittest.TestCase):
    """Ensure a hidden phase is positioned before the controller shows it."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hidden_to_visible_moves_only_while_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            ini = str(Path(directory) / "settings.ini")
            with patch(
                "focusloop.app.QSettings",
                side_effect=lambda *_args: QSettings(ini, QSettings.Format.IniFormat),
            ):
                controller = FocusLoopApp(self.app)
                try:
                    controller.overlay.close()
                    overlay = TracedOverlay(controller.timer_model.current_phase)
                    controller.overlay = overlay
                    controller._overlay_started = True
                    controller.update()
                    self.app.processEvents()
                    self.assertTrue(overlay.isVisible())

                    original = controller.timer_model.phases
                    hidden = replace(original[0], hidden=True)
                    visible = replace(
                        original[1], hidden=False, position="top_right",
                        simple=True, font_size=170,
                    )
                    controller.timer_model.configure((hidden, visible))
                    controller.update()
                    self.assertFalse(overlay.isVisible())
                    overlay.events.clear()

                    controller.skip()  # Hidden Work -> Visible Break.
                    self.app.processEvents()
                    names = [item[0] for item in overlay.events]
                    self.assertEqual(controller.timer_model.current_phase, visible)
                    self.assertTrue(overlay.isVisible())
                    self.assertIn("move", names)
                    self.assertIn("show", names)
                    self.assertLess(max(i for i, name in enumerate(names) if name == "move"),
                                    names.index("show"))
                    self.assertTrue(all(not item[1] for item in overlay.events
                                        if item[0] in ("resize", "move")))
                    self.assertEqual(overlay.phase_config, visible)
                    self.assertEqual(overlay.display_style, "simple")
                finally:
                    controller.close()
                    self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
