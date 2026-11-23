"""Offscreen Qt tests of live settings, per-phase text sizes and tray UI."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDialogButtonBox, QLabel, QMessageBox, QPushButton, QSlider, QSystemTrayIcon

from focusloop.app import FocusLoopApp, SettingsDialog
from focusloop.overlay import remaining_arc_angles
from focusloop.icons import clock_icon, clock_image
from focusloop.timer import FocusTimer
from scripts.generate_icon import build_ico


class SettingsUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.dialog = SettingsDialog(None, FocusTimer(), "bottom_left", "modern")
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
        first = self.dialog.table.cellWidget(0, 4).findChild(QSlider)
        second = self.dialog.table.cellWidget(1, 4).findChild(QSlider)
        self.assertEqual((first.minimum(), first.maximum()), (8, 200))
        self.assertEqual((second.minimum(), second.maximum()), (8, 200))
        first.setValue(8)
        second.setValue(200)
        self.assertEqual(self.dialog.result_phases[0].font_size, 8)
        self.assertEqual(self.dialog.result_phases[1].font_size, 200)
        self.assertEqual(self.updates, [False, False])
        self.assertEqual(self.dialog.table.rowCount(), 2)
        self.assertTrue(self.dialog.isVisible())

    def test_size_column_uses_slider_with_visible_live_pt_value(self):
        self.assertEqual(
            self.dialog.table.horizontalHeaderItem(4).text(), "サイズ"
        )
        cell = self.dialog.table.cellWidget(0, 4)
        slider = cell.findChild(QSlider)
        label = cell.findChild(QLabel)
        self.assertIsNotNone(slider)
        self.assertIsNotNone(label)
        self.assertEqual(slider.orientation(), Qt.Orientation.Horizontal)
        self.assertEqual((slider.minimum(), slider.maximum()), (8, 200))
        self.assertEqual(slider.singleStep(), 1)
        self.assertEqual(label.text(), "42 pt")

        slider.setValue(96)
        self.assertEqual(label.text(), "96 pt")
        self.assertEqual(self.dialog.result_phases[0].font_size, 96)
        self.assertEqual(self.updates, [False])
        self.assertTrue(self.dialog.isVisible())

        slider.setValue(8)
        self.assertEqual(label.text(), "8 pt")
        self.assertEqual(self.dialog.result_phases[0].font_size, 8)
        slider.setValue(200)
        self.assertEqual(label.text(), "200 pt")
        self.assertEqual(self.dialog.result_phases[0].font_size, 200)
        self.assertEqual(self.dialog.table.rowCount(), 2)

    def test_color_opacity_font_and_position_change_immediately(self):
        color = self.dialog.table.cellWidget(0, 2)
        color.setCurrentIndex(color.findData("rose"))
        opacity = self.dialog.table.cellWidget(0, 5).findChild(QSlider)
        opacity.setValue(35)
        self.dialog.table.cellWidget(0, 4).findChild(QSlider).setValue(52)
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
        self.dialog.table.cellWidget(0, 4).findChild(QSlider).setValue(24)
        self.dialog.table.cellWidget(1, 4).findChild(QSlider).setValue(140)
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

    def test_style_switch_is_immediate_and_does_not_erase_phases(self):
        self.assertEqual(self.dialog.style_combo.currentData(), "modern")
        self.dialog.style_combo.setCurrentIndex(
            self.dialog.style_combo.findData("simple")
        )
        self.assertEqual(self.dialog.style_combo.currentData(), "simple")
        self.assertEqual(self.dialog.table.rowCount(), 2)
        self.assertEqual(len(self.dialog.result_phases), 2)
        self.assertEqual(self.updates[-1], False)

    def test_per_phase_gradient_toggle_and_palette_is_immediate(self):
        enabled = self.dialog.table.cellWidget(0, 3).findChild(QCheckBox)
        palette = self.dialog.table.cellWidget(0, 3).findChild(QComboBox)
        self.assertTrue(enabled.isChecked())
        self.assertTrue(palette.isEnabled())
        enabled.setChecked(False)
        self.assertFalse(palette.isEnabled())
        self.assertFalse(self.dialog.result_phases[0].gradient)
        enabled.setChecked(True)
        palette.setCurrentIndex(palette.findData("amber"))
        self.assertTrue(self.dialog.result_phases[0].gradient)
        self.assertEqual(self.dialog.result_phases[0].gradient_end, "amber")

    def test_color_columns_swatches_and_black(self):
        self.assertEqual(self.dialog.table.columnCount(), 7)
        headers = [
            self.dialog.table.horizontalHeaderItem(i).text()
            for i in range(self.dialog.table.columnCount())
        ]
        self.assertEqual(
            headers, ["フェーズ名", "時間", "メイン色", "サブ色・グラデーション", "サイズ", "透過率", "削除"]
        )
        main = self.dialog.table.cellWidget(0, 2)
        combined = self.dialog.table.cellWidget(0, 3)
        check = combined.findChild(QCheckBox)
        secondary = combined.findChild(QComboBox)
        self.assertIsNotNone(check)
        self.assertIsNotNone(secondary)
        self.assertLess(check.geometry().left(), secondary.geometry().left())
        for combo in (main, secondary):
            self.assertEqual(combo.count(), 7)
            black_index = combo.findData("black")
            self.assertGreaterEqual(black_index, 0)
            for index in range(combo.count()):
                self.assertFalse(combo.itemIcon(index).isNull())
                icon_color = combo.itemIcon(index).pixmap(18, 18).toImage().pixelColor(9, 9)
                self.assertTrue(icon_color.isValid())
            combo.setCurrentIndex(black_index)
            self.assertEqual(combo.itemIcon(black_index).pixmap(18, 18).toImage().pixelColor(9, 9).name(), "#000000")
        self.assertEqual(self.dialog.result_phases[0].color, "black")
        self.assertEqual(self.dialog.result_phases[0].gradient_end, "black")

    def test_delete_buttons_are_compact_and_muted_after_adding_phase(self):
        for index in range(self.dialog.table.rowCount()):
            cell = self.dialog.table.cellWidget(index, 6)
            button = cell.findChild(QPushButton)
            self.assertIsNotNone(button)
            self.assertEqual(button.text(), "削除")
            self.assertIn("#F9EAEC", button.styleSheet())
            self.assertNotIn("#C62828", button.styleSheet())
            self.assertEqual((button.width(), button.height()), (54, 26))
            self.assertGreaterEqual(button.geometry().left(), 0)
            self.assertGreaterEqual(button.geometry().top(), 0)
            self.assertLessEqual(button.geometry().right(), cell.width())
            self.assertLessEqual(button.geometry().bottom(), cell.height())
        self.dialog._add_phase()
        self.qt_app.processEvents()
        added = self.dialog.table.cellWidget(2, 6).findChild(QPushButton)
        self.assertIn("#F9EAEC", added.styleSheet())
        with patch.object(
            QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes
        ) as confirm:
            added.click()
            confirm.assert_called_once()
        self.assertEqual(self.dialog.table.rowCount(), 2)

    def test_delete_requires_confirmation_and_cancel_keeps_timer_and_phases(self):
        phases_before = self.dialog._snapshot()
        button = self.dialog.table.cellWidget(0, 6).findChild(QPushButton)
        with patch.object(
            QMessageBox, "exec", return_value=QMessageBox.StandardButton.Cancel
        ) as popup:
            button.click()
            popup.assert_called_once()
        self.assertEqual(self.dialog._snapshot(), phases_before)
        self.assertEqual(self.dialog.table.rowCount(), 2)
        self.assertEqual(self.updates, [])

        with patch.object(
            QMessageBox, "exec", return_value=QMessageBox.StandardButton.NoButton
        ):
            button.click()
        self.assertEqual(self.dialog._snapshot(), phases_before)
        self.assertEqual(self.updates, [])

        with patch.object(
            QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes
        ):
            button.click()
        self.assertEqual(self.dialog.table.rowCount(), 1)
        self.assertEqual(self.dialog.result_phases[0].name, "休憩")
        self.assertEqual(self.updates, [True])

    def test_delete_confirmation_after_reorder_targets_correct_phase(self):
        header = self.dialog.table.verticalHeader()
        header.moveSection(0, 1)
        self.assertEqual(self.dialog._snapshot()[0]["name"], "休憩")
        name = self.dialog.table.cellWidget(0, 0)
        self.assertEqual(name.text(), "作業")
        button = self.dialog.table.cellWidget(0, 6).findChild(QPushButton)
        with patch.object(
            QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes
        ):
            button.click()
        self.assertEqual(self.dialog.table.rowCount(), 1)
        self.assertEqual(self.dialog.result_phases[0].name, "休憩")

    def test_close_keeps_changes(self):
        self.dialog.table.cellWidget(0, 4).findChild(QSlider).setValue(100)
        buttons = self.dialog.findChild(QDialogButtonBox)
        buttons.button(QDialogButtonBox.StandardButton.Close).click()
        self.assertFalse(self.dialog.isVisible())
        self.assertEqual(self.dialog.result_phases[0].font_size, 100)


class AppIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_clockwise_gauge_angles_are_elapsed_from_twelve(self):
        self.assertEqual(remaining_arc_angles(1.0), (1440, -5760))
        self.assertEqual(remaining_arc_angles(0.75), (0, -4320))
        self.assertEqual(remaining_arc_angles(0.5), (-1440, -2880))
        self.assertEqual(remaining_arc_angles(0.25), (-2880, -1440))
        self.assertEqual(remaining_arc_angles(0.0), (-4320, 0))

    def test_settings_timer_reset_preserves_phase_pause_and_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "settings.ini")
            with patch(
                "focusloop.app.QSettings",
                side_effect=lambda *_args: QSettings(path, QSettings.Format.IniFormat),
            ):
                controller = FocusLoopApp(self.qt_app)
                controller.timer_model.skip()
                controller.timer_model.loop_number = 8
                controller.timer_model.pause()
                controller.timer_model._remaining = 123.0
                controller.update()
                controller.show_settings()
                dialog = controller.settings_dialog
                reset = next(
                    x for x in dialog.findChildren(QPushButton)
                    if x.text() == "現在のフェーズをリセット"
                )
                reset.click()
                self.assertEqual(controller.timer_model.phase_index, 1)
                self.assertEqual(controller.timer_model.loop_number, 8)
                self.assertTrue(controller.timer_model.paused)
                self.assertEqual(controller.timer_model.remaining_seconds(),
                                 controller.timer_model.current_phase.minutes * 60)
                self.assertEqual(controller.overlay.clock_text, "15:00")
                self.assertTrue(dialog.isVisible())
                controller.close()

    def test_center_position_in_both_styles_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "settings.ini")
            with patch(
                "focusloop.app.QSettings",
                side_effect=lambda *_args: QSettings(path, QSettings.Format.IniFormat),
            ):
                controller = FocusLoopApp(self.qt_app)
                controller.show_settings()
                dialog = controller.settings_dialog
                self.assertGreaterEqual(dialog.position_combo.findData("center"), 0)
                dialog.position_combo.setCurrentIndex(
                    dialog.position_combo.findData("center")
                )
                for mode in ("simple", "modern"):
                    dialog.style_combo.setCurrentIndex(dialog.style_combo.findData(mode))
                    dialog.table.cellWidget(0, 4).findChild(QSlider).setValue(96)
                    bounds = self.qt_app.primaryScreen().availableGeometry()
                    overlay = controller.overlay.geometry()
                    self.assertLessEqual(abs(bounds.center().x() - overlay.center().x()), 1)
                    self.assertLessEqual(abs(bounds.center().y() - overlay.center().y()), 1)
                controller.close()
                reopened = FocusLoopApp(self.qt_app)
                self.assertEqual(reopened.position, "center")
                reopened.close()

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
                first = dialog.table.cellWidget(0, 4).findChild(QSlider)
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

    def test_style_and_gradient_persist_after_relaunch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "settings.ini")
            with patch(
                "focusloop.app.QSettings",
                side_effect=lambda *_args: QSettings(path, QSettings.Format.IniFormat),
            ):
                controller = FocusLoopApp(self.qt_app)
                self.assertEqual(controller.display_style, "modern")
                controller.overlay.show()
                controller.show_settings()
                dialog = controller.settings_dialog
                dialog.style_combo.setCurrentIndex(dialog.style_combo.findData("simple"))
                self.assertEqual(controller.display_style, "simple")
                self.assertEqual(controller.overlay.display_style, "simple")
                self.assertFalse(controller.overlay.grab().isNull())
                dialog.style_combo.setCurrentIndex(dialog.style_combo.findData("modern"))
                self.assertFalse(controller.overlay.grab().isNull())
                self.assertTrue(controller.overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
                dialog.table.cellWidget(0, 3).findChild(QCheckBox).setChecked(False)
                dialog.table.cellWidget(0, 3).findChild(QComboBox).setCurrentIndex(
                    dialog.table.cellWidget(0, 3).findChild(QComboBox).findData("rose")
                )
                self.assertFalse(controller.timer_model.phases[0].gradient)
                self.assertEqual(controller.timer_model.phases[0].gradient_end, "rose")
                controller.close()
                reopened = FocusLoopApp(self.qt_app)
                self.assertEqual(reopened.display_style, "modern")
                self.assertFalse(reopened.timer_model.phases[0].gradient)
                self.assertEqual(reopened.timer_model.phases[0].gradient_end, "rose")
                reopened.close()

    def test_reset_loop_via_settings_keeps_countdown_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "settings.ini")
            with patch(
                "focusloop.app.QSettings",
                side_effect=lambda *_args: QSettings(path, QSettings.Format.IniFormat),
            ):
                controller = FocusLoopApp(self.qt_app)
                controller.timer_model.loop_number = 7
                controller.timer_model.pause()
                controller.update()
                before = controller.timer_model.remaining_seconds()
                controller.show_settings()
                self.assertEqual(controller.settings_dialog.loop_label.text(), "LOOP 07")
                reset = next(
                    button for button in controller.settings_dialog.findChildren(QPushButton)
                    if button.text() == "ループ数をリセット"
                )
                reset.click()
                self.assertEqual(controller.timer_model.loop_number, 1)
                self.assertEqual(controller.settings_dialog.loop_label.text(), "LOOP 01")
                self.assertEqual(controller.timer_model.remaining_seconds(), before)
                self.assertTrue(controller.timer_model.paused)
                controller.close()
                reopened = FocusLoopApp(self.qt_app)
                self.assertEqual(reopened.timer_model.loop_number, 1)
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
                dialog.table.cellWidget(0, 4).findChild(QSlider).setValue(8)
                dialog.table.cellWidget(1, 4).findChild(QSlider).setValue(200)
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
