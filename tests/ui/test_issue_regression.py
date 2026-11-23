"""End-to-end regression matrix for the active Issue #5–#45 behaviors."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from focusloop.app import FocusLoopApp, PhaseCard
from focusloop.timer import COLOR_HEX, PhaseConfig, default_phases, phases_to_json


class IssueIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ini = str(Path(self.temp.name) / "issue.ini")
        self.patch_settings = patch(
            "focusloop.app.QSettings",
            side_effect=lambda *_args: QSettings(self.ini, QSettings.Format.IniFormat),
        )
        self.patch_settings.start()
        self.controller = FocusLoopApp(self.app)

    def tearDown(self):
        self.controller.close()
        self.patch_settings.stop()
        self.temp.cleanup()
        self.app.processEvents()

    def test_07_15_21_23_24_25_32_39_45_card_editor_persists_latest_options(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        self.assertEqual(len(dialog.cards), 2)
        first = dialog.cards[0]
        self.assertIsInstance(first, PhaseCard)
        self.assertEqual(first.size.maximum(), 200)
        self.assertEqual(first.opacity.maximum(), 100)
        for color in COLOR_HEX:
            index = first.color.findData(color)
            self.assertGreaterEqual(index, 0)
            self.assertFalse(first.color.itemIcon(index).isNull())
        first.color.setCurrentIndex(first.color.findData("black"))
        first.gradient_end.setCurrentIndex(first.gradient_end.findData("white"))
        first.gradient.setChecked(False)
        self.assertFalse(first.gradient_end.isEnabled())
        first.gradient.setChecked(True)
        first.size.setValue(75)
        first.opacity.setValue(17)
        self.assertEqual(first.size_label.text(), "75 pt")
        self.assertEqual(first.opacity_label.text(), "17%")
        self.assertEqual(first.delete_button.width(), 54)
        self.assertIn("#F9EAEC", first.delete_button.styleSheet())
        self.assertEqual(first.delete_button.cursor().shape(), Qt.CursorShape.PointingHandCursor)
        self.controller.settings.sync()
        saved = QSettings(self.ini, QSettings.Format.IniFormat)
        self.assertIn('"color": "black"', saved.value("phases_json"))
        self.assertIn('"gradient_end": "white"', saved.value("phases_json"))

    def test_07_10_18_26_30_38_45_reorder_delete_reset_initialize(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        first = dialog.cards[0]
        second = dialog.cards[1]
        first.name.setText("集中")
        first.minutes.setValue(80)
        first.simple.setChecked(True)
        first.position.setCurrentIndex(first.position.findData("center"))
        first.topmost.setChecked(False)
        dialog._reorder_cards(first, second)
        self.assertEqual([p.name for p in self.controller.timer_model.phases],
                         ["休憩", "集中"])
        self.assertEqual(self.controller.timer_model.current_phase.name, "休憩")
        self.assertEqual(self.controller.timer_model.phases[1].position, "center")

        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Cancel):
            dialog.cards[0].delete_button.click()
        self.assertEqual(len(dialog.cards), 2)
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes):
            dialog.cards[0].delete_button.click()
        self.assertEqual(len(dialog.cards), 1)
        self.assertEqual(self.controller.timer_model.phases[0].name, "集中")
        self.assertTrue(self.controller.timer_model.phases[0].simple)

        self.controller.timer_model.loop_number = 12
        self.controller.timer_model.pause()
        self.controller.update()
        loop_reset = next(b for b in dialog.findChildren(QPushButton)
                          if b.text() == "ループ数をリセット")
        before = self.controller.timer_model.remaining_seconds()
        loop_reset.click()
        self.assertEqual(self.controller.timer_model.loop_number, 1)
        self.assertEqual(self.controller.timer_model.remaining_seconds(), before)
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes):
            dialog.findChild(QPushButton, "initialize_button").click()
        self.assertEqual(self.controller.timer_model.phases, default_phases())
        self.assertEqual(self.controller.timer_model.phase_index, 0)
        self.assertFalse(self.controller.timer_model.paused)
        self.assertEqual(self.controller.overlay.display_style, "modern")
        self.assertTrue(self.controller.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    def test_16_17_19_27_28_36_42_43_44_45_runtime_display_switch(self):
        self.controller.overlay.show()
        self.controller.show_settings()
        work, rest = self.controller.settings_dialog.cards
        work.simple.setChecked(True)
        work.position.setCurrentIndex(work.position.findData("center"))
        work.topmost.setChecked(False)
        rest.simple.setChecked(False)
        rest.position.setCurrentIndex(rest.position.findData("bottom_left"))
        rest.topmost.setChecked(True)
        self.assertEqual(self.controller.overlay.display_style, "simple")
        self.assertFalse(self.controller.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(self.controller.overlay.isVisible())
        self.controller.skip()
        self.assertEqual(self.controller.overlay.display_style, "modern")
        self.assertEqual(self.controller.overlay.position_name, "bottom_left")
        self.assertTrue(self.controller.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(self.controller.overlay.isVisible())

    def test_10_15_19_43_44_json_migration_preserves_per_phase_priority(self):
        original = PhaseConfig(
            "元のフェーズ", 25, simple=True, position="center", topmost=False
        )
        old_settings = QSettings(self.ini, QSettings.Format.IniFormat)
        old_settings.setValue("position", "top_right")
        old_settings.setValue("display_style", "modern")
        old_settings.setValue("phases_json", phases_to_json((original,)))
        old_settings.sync()
        other = FocusLoopApp(self.app)
        self.assertEqual(other.timer_model.phases[0], original)
        self.assertEqual(other.overlay.display_style, "simple")
        self.assertEqual(other.overlay.position_name, "center")
        self.assertFalse(other.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        other.close()

    def test_05_08_18_34_41_active_defaults_and_saved_counter(self):
        self.assertEqual(self.controller.timer_model.phases, default_phases())
        self.assertEqual(self.controller.timer_model.loop_number, 1)
        self.assertEqual(len(COLOR_HEX), 7)
        self.controller.timer_model.loop_number = 12
        self.controller.update()
        self.assertEqual(int(self.controller.settings.value("loop_number")), 12)
        self.controller._reset_loop_count()
        self.assertEqual(int(self.controller.settings.value("loop_number")), 1)


if __name__ == "__main__":
    unittest.main()
