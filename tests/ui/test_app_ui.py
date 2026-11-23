"""Offscreen Qt smoke tests, run separately from dependency-free unit tests."""

import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialogButtonBox, QSystemTrayIcon

from focusloop.app import FocusLoopApp, SettingsDialog
from focusloop.timer import FocusTimer


class SettingsUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.dialog = SettingsDialog(None, FocusTimer(), 42, "bottom_left")
        self.applied = []
        self.dialog.applied.connect(self.applied.append)
        self.dialog.show()
        self.qt_app.processEvents()

    def tearDown(self):
        self.dialog.close()
        self.qt_app.processEvents()

    def _button(self, role):
        box = self.dialog.findChild(QDialogButtonBox)
        return box.button(role)

    def test_apply_keeps_dialog_open_and_allows_repeated_changes(self):
        self.dialog.table.cellWidget(0, 0).setText("集中")
        self.dialog.table.cellWidget(0, 1).setValue(50)
        self._button(QDialogButtonBox.StandardButton.Apply).click()
        self.assertTrue(self.dialog.isVisible())
        self.assertEqual(len(self.applied), 1)
        self.assertEqual(self.dialog.result_phases[0].name, "集中")
        self.assertEqual(self.dialog.result_phases[0].minutes, 50)

        self.dialog.table.cellWidget(0, 1).setValue(55)
        self._button(QDialogButtonBox.StandardButton.Apply).click()
        self.assertEqual(len(self.applied), 2)
        self.assertTrue(self.dialog.isVisible())
        self.assertEqual(self.dialog.result_phases[0].minutes, 55)

    def test_ok_applies_and_closes(self):
        self._button(QDialogButtonBox.StandardButton.Ok).click()
        self.assertEqual(len(self.applied), 1)
        self.assertFalse(self.dialog.isVisible())

    def test_cancel_does_not_apply_unsaved_changes(self):
        self.dialog.table.cellWidget(0, 0).setText("未適用の変更")
        self._button(QDialogButtonBox.StandardButton.Cancel).click()
        self.assertFalse(self.dialog.isVisible())
        self.assertEqual(self.applied, [])


class TrayClickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_single_left_click_opens_settings_instead_of_pausing(self):
        controller = FocusLoopApp(self.qt_app)
        with patch.object(controller, "show_settings") as show_settings, patch.object(
            controller, "_show_tray_menu"
        ) as show_menu:
            controller._tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
            show_settings.assert_called_once_with()
            show_menu.assert_not_called()
            self.assertFalse(controller.timer_model.paused)
        controller.close()

    def test_right_click_opens_context_menu(self):
        controller = FocusLoopApp(self.qt_app)
        with patch.object(controller, "show_settings") as show_settings, patch.object(
            controller, "_show_tray_menu"
        ) as show_menu:
            controller._tray_activated(QSystemTrayIcon.ActivationReason.Context)
            show_menu.assert_called_once_with()
            show_settings.assert_not_called()
        controller.close()


if __name__ == "__main__":
    unittest.main()
