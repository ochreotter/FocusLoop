"""Offscreen regression tests for the global system-tray notification toggle."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from focusloop.app import FocusLoopApp
from focusloop.timer import default_phases


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

    def test_notification_checkbox_is_directly_after_language_not_at_far_right(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        row = dialog.layout().itemAt(0).layout()

        self.assertIs(row.itemAt(0).widget(), dialog.language_label)
        self.assertIs(row.itemAt(1).widget(), dialog.language_combo)
        self.assertIs(row.itemAt(2).widget(), dialog.notifications_checkbox)
        self.assertIsNotNone(row.itemAt(3).spacerItem())
        self.assertIs(row.itemAt(4).widget(), dialog.version_label)
        self.assertIs(row.itemAt(5).widget(), dialog.update_button)
        self.assertEqual(row.count(), 6)
        self.assertEqual(dialog.notifications_checkbox.text(), "通知する")
        self.assertEqual(dialog.notifications_checkbox.objectName(), "notifications_checkbox")
        self.assertTrue(dialog.notifications_checkbox.isChecked())
        self.assertTrue(self.controller.notifications_enabled)

        # Geometry check: close to the language combobox, not pushed to the far right.
        right_of_language = dialog.language_combo.geometry().right()
        left_of_checkbox = dialog.notifications_checkbox.geometry().left()
        self.assertGreaterEqual(left_of_checkbox, right_of_language)
        self.assertLessEqual(left_of_checkbox - right_of_language, 24)

    def test_disabling_notifications_suppresses_manual_and_automatic_changes(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        self.controller.tray = Mock()
        phases_before = self.controller.timer_model.phases
        time_before = self.controller.timer_model.remaining_seconds()
        loop_before = self.controller.timer_model.loop_number

        dialog.notifications_checkbox.setChecked(False)
        self.assertFalse(self.controller.notifications_enabled)
        self.assertFalse(self.controller.settings.value("notifications_enabled", type=bool))
        self.assertEqual(phases_before, self.controller.timer_model.phases)
        self.assertLessEqual(abs(time_before - self.controller.timer_model.remaining_seconds()), 1)
        self.assertEqual(loop_before, self.controller.timer_model.loop_number)

        self.controller.skip()
        self.assertEqual(self.controller.timer_model.current_phase.name, "休憩中")
        self.controller.tray.showMessage.assert_not_called()
        self.controller.previous()
        self.assertEqual(self.controller.timer_model.current_phase.name, "作業中")
        self.controller.tray.showMessage.assert_not_called()

        # Simulate automatic phase advance without changing the notification setting.
        with patch.object(self.controller.timer_model, "tick", return_value=True):
            self.controller.update()
        self.controller.tray.showMessage.assert_not_called()

        dialog.notifications_checkbox.setChecked(True)
        self.assertTrue(self.controller.notifications_enabled)
        self.controller.previous()
        self.controller.tray.showMessage.assert_called_once()
        self.controller.tray.showMessage.reset_mock()
        self.controller.skip()
        self.controller.tray.showMessage.assert_called_once()
        self.controller.tray.showMessage.reset_mock()
        with patch.object(self.controller.timer_model, "tick", return_value=True):
            self.controller.update()
        self.controller.tray.showMessage.assert_called_once()

    def test_language_switch_keeps_checkbox_state_and_translates_label(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        dialog.notifications_checkbox.setChecked(False)
        before = self.controller.timer_model.remaining_seconds()
        phases = self.controller.timer_model.phases

        dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))
        self.assertEqual(dialog.notifications_checkbox.text(), "Notifications")
        self.assertFalse(dialog.notifications_checkbox.isChecked())
        self.assertFalse(self.controller.notifications_enabled)
        self.assertEqual(self.controller.timer_model.phases, phases)
        self.assertLessEqual(abs(before - self.controller.timer_model.remaining_seconds()), 1)

        dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("ja"))
        self.assertEqual(dialog.notifications_checkbox.text(), "通知する")
        self.assertFalse(dialog.notifications_checkbox.isChecked())

    def test_preference_is_persisted_and_settings_reset_restores_on(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        dialog.notifications_checkbox.setChecked(False)
        dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))
        self.controller.settings.sync()

        restarted = FocusLoopApp(self.qt_app)
        self.assertFalse(restarted.notifications_enabled)
        self.assertEqual(restarted.language, "en")
        restarted.show_settings()
        self.assertEqual(restarted.settings_dialog.notifications_checkbox.text(),
                         "Notifications")
        self.assertFalse(restarted.settings_dialog.notifications_checkbox.isChecked())
        restarted.close()

        self.controller._initialize_defaults()
        self.assertTrue(self.controller.notifications_enabled)
        self.assertTrue(dialog.notifications_checkbox.isChecked())
        self.assertTrue(self.controller.settings.value("notifications_enabled", type=bool))
        self.assertEqual(self.controller.language, "en")
        self.assertEqual(self.controller.timer_model.phases, default_phases())

        reopened = FocusLoopApp(self.qt_app)
        self.assertTrue(reopened.notifications_enabled)
        self.assertEqual(reopened.language, "en")
        reopened.close()


if __name__ == "__main__":
    unittest.main()
