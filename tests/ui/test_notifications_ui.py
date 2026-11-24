"""Windows/Qt regressions for per-phase system-tray notifications."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from focusloop.app import FocusLoopApp
from focusloop.timer import default_phases, phases_to_json


class NotificationPreferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ini = str(Path(self.temp.name) / "settings.ini")
        self.settings_patch = patch(
            "focusloop.app.QSettings",
            side_effect=lambda *_args: QSettings(self.ini, QSettings.Format.IniFormat),
        )
        self.settings_patch.start()
        self.controller = FocusLoopApp(self.qt_app)

    def tearDown(self):
        self.controller.close()
        self.settings_patch.stop()
        self.temp.cleanup()
        self.qt_app.processEvents()

    def test_notification_checkbox_is_per_phase_not_global(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        row = dialog.layout().itemAt(0).layout()
        self.assertIs(row.itemAt(0).widget(), dialog.language_label)
        self.assertIs(row.itemAt(1).widget(), dialog.language_combo)
        self.assertIsNotNone(row.itemAt(2).spacerItem())
        self.assertIs(row.itemAt(3).widget(), dialog.version_label)
        self.assertIs(row.itemAt(4).widget(), dialog.update_button)
        self.assertEqual(row.count(), 5)
        self.assertFalse(hasattr(dialog, "notifications_checkbox"))
        self.assertEqual(len(dialog.cards), 2)
        for card in dialog.cards:
            self.assertTrue(card.notify.isChecked())
            self.assertEqual(card.notify.text(), "通知する")
            self.assertEqual(card.notify.objectName(), "phase_notifications_checkbox")
            self.assertEqual(card.notify.focusPolicy(), Qt.FocusPolicy.ClickFocus)

    def test_disabled_phase_suppresses_manual_and_automatic_notification_only_for_that_phase(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        self.controller.tray = Mock()
        remaining = self.controller.timer_model.remaining_seconds()
        original_loop = self.controller.timer_model.loop_number
        dialog.cards[0].notify.setChecked(False)
        self.assertEqual([p.notify for p in self.controller.timer_model.phases], [False, True])
        self.assertEqual(self.controller.timer_model.phase_index, 0)
        self.assertEqual(self.controller.timer_model.loop_number, original_loop)
        self.assertLessEqual(abs(self.controller.timer_model.remaining_seconds() - remaining), 1)
        self.assertFalse(self.controller.settings.contains("notifications_enabled"))

        # Work -> Break: enabled phase sends a notification.
        self.controller.skip()
        self.assertEqual(self.controller.timer_model.current_phase.name, "休憩中")
        self.controller.tray.showMessage.assert_called_once()
        self.controller.tray.showMessage.reset_mock()

        # Break -> Work: this phase's notification is disabled.
        self.controller.skip()
        self.assertEqual(self.controller.timer_model.current_phase.name, "作業中")
        self.controller.tray.showMessage.assert_not_called()

        # Automatic advance checks the phase that is entered.
        with patch.object(self.controller.timer_model, "tick", return_value=True):
            self.controller.update()
        self.controller.tray.showMessage.assert_not_called()

        self.controller.timer_model.skip()  # Break, without controller notification.
        with patch.object(self.controller.timer_model, "tick", return_value=True):
            self.controller.update()
        self.controller.tray.showMessage.assert_called_once()
        self.controller.tray.showMessage.reset_mock()

        # Previous phase also uses the destination phase's notification flag.
        self.controller.previous()
        self.controller.tray.showMessage.assert_not_called()

        # Re-enable Work without restarting the timer.
        dialog.cards[0].notify.setChecked(True)
        self.controller.previous()  # Break.
        self.controller.tray.showMessage.assert_called_once()
        self.controller.tray.showMessage.reset_mock()
        self.controller.skip()  # Work.
        self.controller.tray.showMessage.assert_called_once()

    def test_language_and_dynamic_cards_preserve_each_notification_flag(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        dialog.cards[0].notify.setChecked(False)
        dialog.cards[1].notify.setChecked(True)
        saved = [card.snapshot()["notify"] for card in dialog.cards]
        remaining = self.controller.timer_model.remaining_seconds()

        dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))
        self.assertEqual([card.notify.isChecked() for card in dialog.cards], saved)
        self.assertEqual(dialog.cards[0].notify.text(), "Notify on start")
        self.assertIn("Notifications off", dialog.cards[0].summary.text())
        self.assertLessEqual(abs(self.controller.timer_model.remaining_seconds() - remaining), 1)

        dialog._add_phase()
        self.assertEqual([card.notify.isChecked() for card in dialog.cards], [False, True, True])
        dialog._shift_card(dialog.cards[-1], -1)
        self.assertEqual([card.notify.isChecked() for card in dialog.cards], [False, True, True])

        with patch("focusloop.app.confirm_change", return_value=True):
            dialog._confirm_delete_card(dialog.cards[1])
        self.assertEqual([card.notify.isChecked() for card in dialog.cards], [False, True])

        dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("ja"))
        self.assertEqual(dialog.cards[0].notify.text(), "通知する")
        self.assertEqual([card.notify.isChecked() for card in dialog.cards], [False, True])

    def test_existing_global_off_preference_migrates_all_old_phases_and_is_saved(self):
        self.controller.close()
        settings = QSettings(self.ini, QSettings.Format.IniFormat)
        old_rows = json.loads(phases_to_json(default_phases()))
        for row in old_rows:
            row.pop("notify")
        settings.setValue("notifications_enabled", False)
        settings.setValue("phases_json", json.dumps(old_rows, ensure_ascii=False))
        settings.sync()

        self.controller = FocusLoopApp(self.qt_app)
        self.assertEqual([phase.notify for phase in self.controller.timer_model.phases], [False, False])
        self.assertFalse(self.controller.settings.contains("notifications_enabled"))
        migrated = json.loads(self.controller.settings.value("phases_json"))
        self.assertEqual([row["notify"] for row in migrated], [False, False])

        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        self.assertEqual([card.notify.isChecked() for card in dialog.cards], [False, False])
        self.controller.tray = Mock()
        self.controller.skip()
        self.controller.tray.showMessage.assert_not_called()
        dialog.cards[1].notify.setChecked(True)
        self.assertEqual([phase.notify for phase in self.controller.timer_model.phases], [False, True])

        # A subsequent restart must not re-apply the deleted global preference.
        restarted = FocusLoopApp(self.qt_app)
        try:
            self.assertEqual([p.notify for p in restarted.timer_model.phases], [False, True])
        finally:
            restarted.close()

    def test_legacy_global_true_and_new_phase_override(self):
        self.controller.close()
        settings = QSettings(self.ini, QSettings.Format.IniFormat)
        old_rows = json.loads(phases_to_json(default_phases()))
        old_rows[0].pop("notify")
        old_rows[1]["notify"] = False
        settings.setValue("notifications_enabled", True)
        settings.setValue("phases_json", json.dumps(old_rows, ensure_ascii=False))
        settings.sync()
        self.controller = FocusLoopApp(self.qt_app)
        self.assertEqual([phase.notify for phase in self.controller.timer_model.phases], [True, False])
        self.assertFalse(self.controller.settings.contains("notifications_enabled"))

    def test_reset_restores_notifications_on_for_every_phase(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        dialog.cards[0].notify.setChecked(False)
        dialog.cards[1].notify.setChecked(False)
        self.controller._initialize_defaults()
        self.assertTrue(all(phase.notify for phase in self.controller.timer_model.phases))
        self.assertTrue(all(card.notify.isChecked() for card in dialog.cards))
        self.assertEqual(self.controller.timer_model.phases, default_phases())
        self.assertFalse(self.controller.settings.contains("notifications_enabled"))
        restarted = FocusLoopApp(self.qt_app)
        try:
            self.assertTrue(all(p.notify for p in restarted.timer_model.phases))
        finally:
            restarted.close()


if __name__ == "__main__":
    unittest.main()
