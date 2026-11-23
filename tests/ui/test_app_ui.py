"""Offscreen Qt tests of live settings, per-phase text sizes and tray UI."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QSlider, QSystemTrayIcon

from focusloop.app import FocusLoopApp, SettingsDialog
from focusloop.icons import clock_icon, clock_image
from focusloop.timer import FocusTimer
from scripts.generate_icon import build_ico


class SettingsUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.dialog = SettingsDialog(None, FocusTimer(), "bottom_left")
        self.updates = []
        self.dialog.changed.connect(lambda _dialog, reorder: self.updates.append(reorder))
        self.dialog.show()
        self.qt_app.processEvents()

    def tearDown(self):
        self.dialog.close()
        self.qt_app.processEvents()

    def test_only_close_button(self):
        buttons = self.dialog.findChild(QDialogButtonBox)
        self.assertIsNone(buttons.button(QDialogButtonBox.StandardButton.Apply))
        self.assertIsNone(buttons.button(QDialogButtonBox.StandardButton.Ok))
        self.assertIsNone(buttons.button(QDialogButtonBox.StandardButton.Cancel))
        self.assertIsNotNone(buttons.button(QDialogButtonBox.StandardButton.Close))

    def test_minutes_change_emits_immediately_without_closing(self):
        self.dialog.table.cellWidget(0, 1).setValue(50)
        self.assertEqual(self.dialog.result_phases[0].minutes, 50)
        self.assertEqual(self.updates, [False])
        self.assertTrue(self.dialog.isVisible())
        self.dialog.table.cellWidget(0, 1).setValue(55)
        self.assertEqual(self.dialog.result_phases[0].minutes, 55)
        self.assertEqual(self.updates, [False, False])

    def test_font_size_is_per_phase_and_supports_8_to_200pt(self):
        first = self.dialog.table.cellWidget(0, 3)
        second = self.dialog.table.cellWidget(1, 3)
        self.assertEqual((first.minimum(), first.maximum()), (8, 200))
        self.assertEqual((second.minimum(), second.maximum()), (8, 200))
        first.setValue(8)
        second.setValue(200)
        self.assertEqual(self.dialog.result_phases[0].font_size, 8)
        self.assertEqual(self.dialog.result_phases[1].font_size, 200)
        self.assertEqual(self.updates, [False, False])
        self.assertEqual(self.dialog.table.rowCount(), 2)
        self.assertTrue(self.dialog.isVisible())

    def test_color_opacity_font_and_position_change_immediately(self):
        color = self.dialog.table.cellWidget(0, 2)
        color.setCurrentIndex(color.findData("rose"))
        opacity = self.dialog.table.cellWidget(0, 4).findChild(QSlider)
        opacity.setValue(35)
        self.dialog.table.cellWidget(0, 3).setValue(52)
        self.dialog.position_combo.setCurrentIndex(
            self.dialog.position_combo.findData("top_right")
        )
        self.assertEqual(self.dialog.result_phases[0].color, "rose")
        self.assertEqual(self.dialog.result_phases[0].opacity, 35)
        self.assertEqual(self.dialog.result_phases[0].font_size, 52)
        self.assertEqual(self.dialog.position_combo.currentData(), "top_right")
        self.assertEqual(len(self.updates), 4)
        self.assertTrue(self.dialog.isVisible())

    def test_add_delete_are_instant_and_new_phase_gets_default_font(self):
        self.dialog._add_phase()
        self.assertEqual(len(self.dialog.result_phases), 3)
        self.assertEqual(self.dialog.result_phases[2].font_size, 42)
        self.assertTrue(self.updates[-1])
        editor = self.dialog.table.cellWidget(2, 0)
        self.dialog._delete_row(editor)
        self.assertEqual(len(self.dialog.result_phases), 2)
        self.assertTrue(self.updates[-1])

    def test_drag_row_header_reorders_phases_preserving_font(self):
        self.dialog.table.cellWidget(0, 3).setValue(24)
        self.dialog.table.cellWidget(1, 3).setValue(140)
        header = self.dialog.table.verticalHeader()
        self.assertTrue(header.sectionsMovable())
        self.assertTrue(header.isVisible())
        self.assertEqual([x["name"] for x in self.dialog._snapshot()], ["作業", "休憩"])
        header.moveSection(0, 1)
        self.assertEqual(
            [phase.name for phase in self.dialog.result_phases], ["休憩", "作業"]
        )
        self.assertEqual(
            [phase.font_size for phase in self.dialog.result_phases], [140, 24]
        )
        self.assertEqual(self.updates[-1], True)

    def test_close_keeps_changes(self):
        self.dialog.table.cellWidget(0, 3).setValue(100)
        buttons = self.dialog.findChild(QDialogButtonBox)
        buttons.button(QDialogButtonBox.StandardButton.Close).click()
        self.assertFalse(self.dialog.isVisible())
        self.assertEqual(self.dialog.result_phases[0].font_size, 100)


class AppIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_font_resize_does_not_remove_phases_or_hide_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "settings.ini")
            with patch(
                "focusloop.app.QSettings",
                side_effect=lambda *_args: QSettings(path, QSettings.Format.IniFormat),
            ):
                controller = FocusLoopApp(self.qt_app)
                original_phases = len(controller.timer_model.phases)
                controller.overlay.show()
                controller.show_settings()
                dialog = controller.settings_dialog
                self.assertIsNotNone(dialog)
                first = dialog.table.cellWidget(0, 3)
                first.setValue(200)
                controller.update()
                self.assertEqual(len(controller.timer_model.phases), original_phases)
                self.assertEqual(dialog.table.rowCount(), original_phases)
                self.assertEqual(controller.timer_model.current_phase.font_size, 200)
                self.assertEqual(controller.overlay.phase_config.font_size, 200)
                self.assertTrue(controller.overlay.isVisible())
                self.assertGreater(controller.overlay.width(), 0)
                screen = self.qt_app.primaryScreen().availableGeometry()
                self.assertTrue(screen.contains(controller.overlay.geometry()))
                controller.close()

                reopened = FocusLoopApp(self.qt_app)
                self.assertEqual(len(reopened.timer_model.phases), original_phases)
                self.assertEqual(reopened.timer_model.phases[0].font_size, 200)
                reopened.close()

    def test_phase_skip_switches_rendered_font_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "settings.ini")
            with patch(
                "focusloop.app.QSettings",
                side_effect=lambda *_args: QSettings(path, QSettings.Format.IniFormat),
            ):
                controller = FocusLoopApp(self.qt_app)
                controller.show_settings()
                dialog = controller.settings_dialog
                dialog.table.cellWidget(0, 3).setValue(8)
                dialog.table.cellWidget(1, 3).setValue(200)
                self.assertEqual(controller.overlay.phase_config.font_size, 8)
                controller.skip()
                self.assertEqual(controller.overlay.phase_config.font_size, 200)
                self.assertEqual(controller.timer_model.current_phase.name, "休憩")
                controller.close()


class TrayTests(unittest.TestCase):
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

    def test_right_click_opens_menu(self):
        controller = FocusLoopApp(self.qt_app)
        with patch.object(controller, "show_settings") as show_settings, patch.object(
            controller, "_show_tray_menu"
        ) as show_menu:
            controller._tray_activated(QSystemTrayIcon.ActivationReason.Context)
            show_menu.assert_called_once_with()
            show_settings.assert_not_called()
        controller.close()

    def test_phase_notification_is_sent_for_skip(self):
        controller = FocusLoopApp(self.qt_app)
        controller.tray = Mock()
        controller.skip()
        controller.tray.showMessage.assert_called_once()
        title, message, _icon_type, timeout = controller.tray.showMessage.call_args.args
        self.assertEqual(title, "FocusLoop")
        self.assertIn(controller.timer_model.current_phase.name, message)
        self.assertIn(str(controller.timer_model.current_phase.minutes), message)
        self.assertEqual(timeout, 6000)
        controller.close()

    def test_clock_icon_renders(self):
        self.assertFalse(clock_image(16).isNull())
        self.assertFalse(clock_image(256).isNull())
        self.assertFalse(clock_icon().isNull())

    def test_generated_windows_ico_has_png_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "FocusLoop.ico"
            build_ico(path)
            data = path.read_bytes()
            reserved, kind, count = struct.unpack("<HHH", data[:6])
            self.assertEqual((reserved, kind, count), (0, 1, 7))
            first = struct.unpack("<BBBBHHII", data[6:22])
            self.assertEqual(first[0], 16)
            self.assertEqual(data[first[-1]:first[-1] + 8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
