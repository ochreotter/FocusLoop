"""Offscreen Qt tests for live language switching and locale persistence."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QApplication, QDialogButtonBox, QLabel, QMessageBox, QPushButton,
)

from focusloop.app import FocusLoopApp
from focusloop.timer import default_phases


class LocalizedAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ini = str(Path(self.tmp.name) / "focusloop.ini")
        self.settings_patch = patch(
            "focusloop.app.QSettings",
            side_effect=lambda *_args: QSettings(self.ini, QSettings.Format.IniFormat),
        )
        self.settings_patch.start()
        self.controller = FocusLoopApp(self.app)

    def tearDown(self):
        self.controller.close()
        self.settings_patch.stop()
        self.tmp.cleanup()
        self.app.processEvents()

    def test_language_selector_is_at_top_and_japanese_is_default(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        self.assertEqual(dialog.language, "ja")
        self.assertEqual(dialog.language_combo.currentData(), "ja")
        self.assertEqual([dialog.language_combo.itemData(i) for i in range(2)],
                         ["ja", "en"])
        self.assertEqual(dialog.layout().itemAt(0).layout().itemAt(1).widget(),
                         dialog.language_combo)
        self.assertEqual(dialog.language_label.text(), "言語")
        self.assertIn("設定", dialog.windowTitle())

    def test_english_translation_and_no_timer_or_phase_mutation(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        self.controller.timer_model.loop_number = 5
        self.controller.update()
        first, second = dialog.cards
        second.expand_button.setChecked(True)
        before = self.controller.timer_model.remaining_seconds()
        phases = self.controller.timer_model.phases
        dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))
        self.assertEqual(self.controller.settings.value("language"), "en")
        self.assertEqual(dialog.language_label.text(), "Language")
        self.assertIn("Settings", dialog.windowTitle())
        self.assertEqual(dialog.cards[0].name.text(), "Working")
        self.assertEqual(dialog.cards[1].name.text(), "On Break")
        self.assertTrue(all(c.expand_button.isChecked() for c in dialog.cards))
        self.assertEqual(self.controller.timer_model.phases, phases)
        self.assertEqual(self.controller.timer_model.loop_number, 5)
        self.assertLessEqual(abs(before - self.controller.timer_model.remaining_seconds()), 1)
        self.assertEqual(self.controller.overlay.phase_config.name, "Working")
        self.assertIn("Amber", dialog.cards[0].summary.text())
        self.assertIn("Bottom left", dialog.cards[0].summary.text())
        self.assertIn("Topmost ON", dialog.cards[0].summary.text())
        self.assertEqual(dialog.cards[0].minutes.suffix(), " min")
        self.assertEqual(dialog.cards[0].topmost.text(), "Always on top")
        self.assertEqual(dialog.cards[0].hidden.text(), "Hidden")
        self.assertEqual(dialog.cards[0].color.itemText(
            dialog.cards[0].color.findData("rose")), "Rose")
        self.assertEqual(dialog.cards[1].position.itemText(
            dialog.cards[1].position.findData("center")), "Center")
        self.assertIn("Pause", [a.text() for a in self.controller.menu.actions()])
        self.assertIn("Previous phase", [a.text() for a in self.controller.menu.actions()])
        self.assertIn("Next phase", [a.text() for a in self.controller.menu.actions()])
        self.assertIn("Reset loop count", [a.text() for a in self.controller.menu.actions()])
        self.assertEqual(
            [action.text() for action in self.controller.menu.actions()
             if action in (self.controller.pause_action, self.controller.previous_action,
                           self.controller.skip_action,
                           self.controller.reset_action, self.controller.loop_reset_action)],
            ["Pause", "Previous phase", "Next phase", "Reset current phase", "Reset loop count"],
        )
        self.assertEqual(
            [dialog.layout().itemAt(dialog.layout().count() - 1).layout()
             .itemAt(i).widget().text() for i in range(5)],
            ["Pause", "Previous phase", "Next phase", "Reset current phase", "Reset loop count"],
        )
        self.assertIn("Settings", [a.text() for a in self.controller.menu.actions()])
        self.assertIn("Quit", [a.text() for a in self.controller.menu.actions()])
        self.assertEqual(dialog.pause_button.text(), "Pause")
        self.assertEqual(dialog.findChild(QPushButton, "initialize_button").text(),
                         "Reset settings")
        self.assertEqual(dialog.close_button.text(), "Close")

        # Built-in display translations must not leak into the user's saved data.
        dialog.cards[0].opacity.setValue(48)
        self.assertEqual(self.controller.timer_model.phases[0].name, "作業中")
        self.controller.settings.sync()
        self.assertIn('"作業中"', self.controller.settings.value("phases_json"))

    def test_translated_tray_loop_reset_and_settings_next_phase(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))
        self.assertEqual(dialog.previous_button.text(), "Previous phase")
        self.assertEqual(dialog.skip_button.text(), "Next phase")
        self.assertEqual(dialog.loop_reset_button.text(), "Reset loop count")
        self.assertEqual(dialog.pause_button.text(), "Pause")

        dialog.skip_button.click()
        self.assertEqual(self.controller.timer_model.current_phase.name, "休憩中")
        self.assertEqual(self.controller.overlay.phase_config.name, "On Break")

        dialog.previous_button.click()
        self.assertEqual(self.controller.timer_model.current_phase.name, "作業中")
        self.assertEqual(self.controller.overlay.phase_config.name, "Working")
        self.controller.previous_action.trigger()
        self.assertEqual(self.controller.timer_model.current_phase.name, "休憩中")
        self.assertEqual(self.controller.overlay.phase_config.name, "On Break")

        self.controller.timer_model.pause()
        self.controller.timer_model.loop_number = 7
        self.controller.update()
        before = self.controller.timer_model.remaining_seconds()
        self.controller.loop_reset_action.trigger()
        self.assertEqual(self.controller.timer_model.remaining_seconds(), before)
        self.assertTrue(self.controller.timer_model.paused)
        self.assertEqual(self.controller.timer_model.loop_number, 1)
        self.assertEqual(dialog.loop_label.text(), "LOOP 01")
        self.assertEqual(dialog.pause_button.text(), "Resume")

        dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("ja"))
        self.assertEqual(dialog.previous_button.text(), "前のフェーズへ")
        self.assertEqual(dialog.skip_button.text(), "次のフェーズへ")
        self.assertEqual(dialog.loop_reset_button.text(), "ループ数をリセット")
        self.assertEqual(self.controller.previous_action.text(), "前のフェーズへ")
        self.assertEqual(self.controller.loop_reset_action.text(), "ループ数をリセット")
        self.assertEqual(self.controller.menu.actions()[0], self.controller.status_action)

    def test_language_change_bidirectional_and_custom_names_unchanged(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        first = dialog.cards[0]
        first.name.setText("深い集中")
        self.assertEqual(self.controller.timer_model.current_phase.name, "深い集中")
        before = self.controller.timer_model.remaining_seconds()

        dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))
        self.assertEqual(dialog.cards[0].name.text(), "深い集中")
        self.assertEqual(dialog.cards[1].name.text(), "On Break")
        self.assertEqual(self.controller.overlay.phase_config.name, "深い集中")
        self.assertLessEqual(abs(before - self.controller.timer_model.remaining_seconds()), 1)
        dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("ja"))
        self.assertEqual(dialog.cards[0].name.text(), "深い集中")
        self.assertEqual(dialog.cards[1].name.text(), "休憩中")
        self.assertEqual(self.controller.settings.value("language"), "ja")
        self.assertEqual(dialog.pause_button.text(), "一時停止")

    def test_language_survives_relaunch_and_settings_reset(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))
        dialog.cards[0].name.setText("Focus sprint")
        self.controller.settings.sync()

        restarted = FocusLoopApp(self.app)
        self.assertEqual(restarted.language, "en")
        self.assertEqual(restarted.timer_model.current_phase.name, "Focus sprint")
        restarted.show_settings()
        self.assertEqual(restarted.settings_dialog.language_combo.currentData(), "en")
        restarted.close()

        self.controller._initialize_defaults()
        self.assertEqual(self.controller.language, "en")
        self.assertEqual(self.controller.timer_model.phases, default_phases())
        self.assertEqual(self.controller.settings.value("language"), "en")
        self.assertEqual(dialog.cards[0].name.text(), "Working")
        self.assertEqual(dialog.cards[1].name.text(), "On Break")
        self.assertEqual(dialog.language_combo.currentData(), "en")
        self.assertEqual(dialog.findChild(QPushButton, "initialize_button").text(),
                         "Reset settings")

    def test_english_confirmation_and_notifications(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))
        seen = []

        def observe(*args):
            seen.append(args)
            return False

        with patch("focusloop.app.confirm_change", side_effect=observe):
            dialog.initialize_button.click()
            dialog.cards[0].delete_button.click()
        self.assertEqual(len(seen), 2)
        self.assertIn("Reset settings", seen[0][1])
        self.assertEqual(seen[0][2], "Reset all settings?")
        self.assertIn("Working 45:00", seen[0][3])
        self.assertEqual(seen[0][-1], "en")
        self.assertIn('Delete "Working"?', seen[1][2])
        self.assertEqual(seen[1][-1], "en")
        self.assertEqual(len(dialog.cards), 2)

        self.controller.tray = Mock()
        self.controller._notify_phase_change()
        self.assertIn('Started "Working" (45 min).',
                      self.controller.tray.showMessage.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
