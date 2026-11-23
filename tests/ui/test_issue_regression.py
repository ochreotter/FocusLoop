"""Cross-feature regression tests for the latest, non-superseded GitHub issues.

Issue-number mapping is documented in docs/issue-regression.md.
"""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialogButtonBox, QLineEdit,
    QMessageBox, QPushButton, QSlider, QSystemTrayIcon,
)

from focusloop.app import FocusLoopApp
from focusloop.overlay import draw_shadowed_text, remaining_arc_angles
from focusloop.timer import COLOR_HEX, default_phases


class FullIssueRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings_path = str(Path(self.temp.name) / "settings.ini")
        self.settings_patch = patch(
            "focusloop.app.QSettings",
            side_effect=lambda *_args: QSettings(
                self.settings_path, QSettings.Format.IniFormat
            ),
        )
        self.settings_patch.start()
        self.controller = FocusLoopApp(self.app)

    def tearDown(self):
        self.controller.close()
        self.settings_patch.stop()
        self.temp.cleanup()
        self.app.processEvents()

    def test_06_16_17_27_28_42_transparent_overlay_styles_and_positions(self):
        overlay = self.controller.overlay
        overlay.show()
        self.app.processEvents()
        flags = overlay.windowFlags()
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(flags & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(flags & Qt.WindowType.WindowTransparentForInput)
        self.assertTrue(flags & Qt.WindowType.WindowDoesNotAcceptFocus)
        self.assertTrue(overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertTrue(overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))

        available = self.app.primaryScreen().availableGeometry()
        for style in ("simple", "modern"):
            overlay.apply_appearance("center", style)
            self.app.processEvents()
            rect = overlay.geometry()
            self.assertLessEqual(abs(rect.center().x() - available.center().x()), 1)
            self.assertLessEqual(abs(rect.center().y() - available.center().y()), 1)
            self.assertFalse(overlay.grab().isNull())
            with patch("focusloop.overlay.draw_shadowed_text", wraps=draw_shadowed_text) as draw:
                overlay.grab()
                self.assertEqual(draw.call_count, 1 if style == "simple" else 3)
            for position in ("top_left", "top_right", "bottom_left", "bottom_right"):
                overlay.apply_appearance(position)
                self.assertTrue(available.contains(overlay.geometry()))

        self.assertEqual(remaining_arc_angles(1.0), (1440, -5760))
        self.assertEqual(remaining_arc_angles(0.75), (0, -4320))
        self.assertEqual(remaining_arc_angles(0.5), (-1440, -2880))
        self.assertEqual(remaining_arc_angles(0.25), (-2880, -1440))
        self.assertEqual(remaining_arc_angles(0.0), (-4320, 0))
        overlay.set_clock("11:11", self.controller.timer_model.current_phase, 0.25, 9)
        self.assertEqual(overlay.remaining_ratio, 0.25)
        self.assertEqual(overlay.loop_number, 9)

    def test_07_08_15_19_21_23_24_25_32_39_phase_editor_contract(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        self.app.processEvents()
        headers = [dialog.table.horizontalHeaderItem(i).text()
                   for i in range(dialog.table.columnCount())]
        self.assertEqual(
            headers, ["フェーズ名", "時間", "メイン色", "サブ色・グラデーション",
                      "サイズ", "透過率", "削除"],
        )
        row = 0
        main = dialog.table.cellWidget(row, 2)
        sub_cell = dialog.table.cellWidget(row, 3)
        gradient = sub_cell.findChild(QCheckBox)
        sub = sub_cell.findChild(QComboBox)
        self.assertIs(sub_cell.layout().itemAt(0).widget(), gradient)
        self.assertIs(sub_cell.layout().itemAt(1).widget(), sub)
        for combo in (main, sub):
            self.assertEqual(combo.count(), len(COLOR_HEX))
            for key in COLOR_HEX:
                index = combo.findData(key)
                self.assertGreaterEqual(index, 0)
                self.assertFalse(combo.itemIcon(index).isNull())
        main.setCurrentIndex(main.findData("black"))
        sub.setCurrentIndex(sub.findData("mint"))
        self.assertEqual(dialog.result_phases[0].color, "black")
        self.assertEqual(dialog.result_phases[0].gradient_end, "mint")
        gradient.setChecked(False)
        self.assertFalse(sub.isEnabled())
        self.assertEqual(dialog.result_phases[0].gradient_end, "mint")
        gradient.setChecked(True)
        self.assertTrue(sub.isEnabled())

        size = dialog.table.cellWidget(row, 4).findChild(QSlider)
        opacity = dialog.table.cellWidget(row, 5).findChild(QSlider)
        self.assertEqual((size.minimum(), size.maximum()), (8, 200))
        self.assertEqual((opacity.minimum(), opacity.maximum()), (0, 100))
        size.setValue(200)
        opacity.setValue(0)
        self.assertEqual(dialog.result_phases[0].font_size, 200)
        self.assertEqual(dialog.result_phases[0].opacity, 0)
        self.assertEqual(self.controller.timer_model.phases[0].font_size, 200)

        delete = dialog.table.cellWidget(0, 6).findChild(QPushButton)
        self.assertEqual((delete.width(), delete.height()), (54, 26))
        self.assertIn("#F9EAEC", delete.styleSheet())
        self.assertEqual(delete.cursor().shape(), Qt.CursorShape.PointingHandCursor)
        self.assertTrue(
            dialog.findChild(QDialogButtonBox)
            .button(QDialogButtonBox.StandardButton.Close).cursor().shape()
            == Qt.CursorShape.PointingHandCursor
        )

    def test_09_11_12_14_tray_actions_japanese_and_notifications(self):
        menu_text = [action.text() for action in self.controller.menu.actions()]
        for label in ("一時停止", "次のフェーズへ", "現在のフェーズをリセット", "設定", "終了"):
            self.assertIn(label, menu_text)
        self.assertFalse(self.controller.tray.icon().isNull())
        self.controller._tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
        dialog = self.controller.settings_dialog
        self.assertIsNotNone(dialog)
        self.controller._tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
        self.assertIs(self.controller.settings_dialog, dialog)
        self.assertFalse(self.controller.timer_model.paused)
        with patch.object(self.controller, "_show_tray_menu") as show:
            self.controller._tray_activated(QSystemTrayIcon.ActivationReason.Context)
            show.assert_called_once_with()

        self.controller.tray = Mock()
        with patch.object(self.controller.timer_model, "tick", return_value=True):
            self.controller.update()
        self.controller.tray.showMessage.assert_called_once()
        self.controller.tray.showMessage.reset_mock()
        self.controller.skip()
        self.controller.tray.showMessage.assert_called_once()
        args = self.controller.tray.showMessage.call_args.args
        self.assertIn("開始しました", args[1])
        self.assertIn("分", args[1])

    def test_10_18_26_30_38_saved_settings_and_confirmed_changes(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        dialog.table.cellWidget(0, 0).setText("長い作業")
        dialog.table.cellWidget(0, 1).setValue(60)
        dialog.table.cellWidget(0, 4).findChild(QSlider).setValue(90)
        dialog.position_combo.setCurrentIndex(dialog.position_combo.findData("center"))
        dialog.style_combo.setCurrentIndex(dialog.style_combo.findData("simple"))
        self.controller.timer_model.loop_number = 6
        self.controller.timer_model.pause()
        self.controller.update()
        saved_phases = self.controller.settings.value("phases_json")
        saved_position = self.controller.position

        delete = dialog.table.cellWidget(0, 6).findChild(QPushButton)
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Cancel):
            delete.click()
        self.assertEqual(self.controller.settings.value("phases_json"), saved_phases)

        initialize = next(x for x in dialog.findChildren(QPushButton) if x.text() == "初期化")
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Cancel):
            initialize.click()
        self.assertEqual(self.controller.position, saved_position)
        self.assertTrue(self.controller.timer_model.paused)
        self.assertEqual(self.controller.timer_model.loop_number, 6)

        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes):
            initialize.click()
        self.assertEqual(self.controller.timer_model.phases, default_phases())
        self.assertEqual(self.controller.display_style, "modern")
        self.assertEqual(self.controller.position, "bottom_left")
        self.assertEqual(self.controller.timer_model.loop_number, 1)
        self.assertFalse(self.controller.timer_model.paused)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.table.rowCount(), 2)

        dialog.table.cellWidget(0, 0).setText("初期化後に編集")
        self.assertEqual(self.controller.timer_model.phases[0].name, "初期化後に編集")
        check = QSettings(self.settings_path, QSettings.Format.IniFormat)
        self.assertIn("初期化後に編集", check.value("phases_json"))
        self.assertEqual(check.value("position"), "bottom_left")

    def test_17_19_25_42_palette_and_alpha_are_persisted_together(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        main = dialog.table.cellWidget(0, 2)
        secondary = dialog.table.cellWidget(0, 3).findChild(QComboBox)
        for color in COLOR_HEX:
            main.setCurrentIndex(main.findData(color))
            secondary.setCurrentIndex(secondary.findData("black"))
            self.assertEqual(self.controller.overlay.phase_config.color, color)
            self.assertEqual(self.controller.overlay.phase_config.gradient_end, "black")
            self.assertTrue(self.controller.overlay.phase_config.gradient)
        opacity = dialog.table.cellWidget(0, 5).findChild(QSlider)
        opacity.setValue(21)
        self.assertEqual(self.controller.overlay.phase_config.opacity, 21)
        self.assertEqual(self.controller.timer_model.phases[0].opacity, 21)


if __name__ == "__main__":
    unittest.main()
