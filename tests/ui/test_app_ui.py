"""Offscreen UI and application regressions for accordion phase settings."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QAbstractButton, QComboBox, QDialogButtonBox, QMessageBox,
    QLabel, QPushButton, QScrollArea, QSystemTrayIcon,
)

from focusloop.app import FocusLoopApp, PhaseCard, PhaseDragHandle, SettingsDialog
from focusloop.icons import clock_icon, clock_image
from focusloop.overlay import remaining_arc_angles
from focusloop.timer import COLOR_HEX, FocusTimer, PhaseConfig, default_phases
from scripts.generate_icon import build_ico


class CardSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.dialog = SettingsDialog(None, FocusTimer())
        self.events = []
        self.dialog.changed.connect(lambda _dialog, restart: self.events.append(restart))
        self.dialog.show()
        self.app.processEvents()

    def tearDown(self):
        self.dialog.close()
        self.app.processEvents()

    def test_card_header_design_click_targets_and_multiple_open(self):
        self.assertEqual(len(self.dialog.cards), 2)
        self.assertIsInstance(self.dialog.scroll, QScrollArea)
        self.assertEqual(self.dialog.scroll.horizontalScrollBarPolicy(),
                         Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        first, second = self.dialog.cards
        self.assertIsInstance(first, PhaseCard)
        self.assertTrue(first.expand_button.isChecked())
        self.assertEqual(first.expand_button.text(), "∧")
        self.assertFalse(second.expand_button.isChecked())
        self.assertEqual(second.expand_button.text(), "∨")
        self.assertIn("45分", first.summary.text())
        self.assertIn("左下", first.summary.text())
        self.assertIn("最前面ON", first.summary.text())
        self.assertFalse(first.hidden.isChecked())
        self.assertNotIn("非表示", first.summary.text())
        self.assertIn("アンバー", first.summary.text())
        self.assertIn("標準", first.summary.text())
        self.assertFalse(hasattr(first, "main_swatch"))
        self.assertFalse(hasattr(first, "sub_swatch"))
        self.assertTrue(first.title.font().bold())
        self.assertGreaterEqual(first.title.font().pointSize(), 13)
        self.assertIn("palette(window)", first.header_widget.styleSheet())
        self.assertIn("palette(window-text)", first.summary.styleSheet())
        self.assertNotIn("palette(mid)", first.summary.styleSheet())
        self.assertIn("font-weight: 500", first.summary.styleSheet())
        self.assertIn("palette(base)", first.body.styleSheet())
        self.assertNotEqual(first.header_widget.styleSheet(), first.body.styleSheet())
        self.assertEqual(first.simple.text(), "Simple")
        self.assertFalse(any(
            item.text() == "フェーズ操作" for item in first.findChildren(QLabel)
        ))
        self.assertIsInstance(first.drag_handle, PhaseDragHandle)
        self.assertTrue(first.acceptDrops())

        # Two cards can remain open, and opening/closing never saves settings.
        second.expand_button.click()
        self.assertTrue(second.body.isVisible())
        self.assertTrue(first.body.isVisible())
        self.assertEqual(second.expand_button.text(), "∧")

        # Clicking the entire header background, title and summary toggles.
        QTest.mouseClick(first.header_widget, Qt.MouseButton.LeftButton)
        self.assertFalse(first.expand_button.isChecked())
        self.assertFalse(first.body.isVisible())
        self.assertTrue(second.body.isVisible())
        self.assertEqual(first.expand_button.text(), "∨")
        QTest.mouseClick(first.title, Qt.MouseButton.LeftButton)
        self.assertTrue(first.expand_button.isChecked())
        QTest.mouseClick(first.summary, Qt.MouseButton.LeftButton)
        self.assertFalse(first.expand_button.isChecked())
        QTest.mouseClick(first.header_widget, Qt.MouseButton.LeftButton)
        self.assertTrue(first.expand_button.isChecked())

        # Body background, field labels and the outer border must NOT toggle.
        self.assertTrue(first.body.isVisible())
        QTest.mouseClick(first.body, Qt.MouseButton.LeftButton, pos=QPoint(3, 3))
        self.assertTrue(first.body.isVisible())
        name_label = next(
            label for label in first.body.findChildren(QLabel)
            if label.text() == "フェーズ名"
        )
        QTest.mouseClick(name_label, Qt.MouseButton.LeftButton)
        self.assertTrue(first.body.isVisible())
        QTest.mouseClick(first.delete_button.parentWidget(), Qt.MouseButton.LeftButton,
                         pos=QPoint(2, 2))
        self.assertTrue(first.body.isVisible())
        QTest.mouseClick(first, Qt.MouseButton.LeftButton, pos=QPoint(1, 1))
        self.assertTrue(first.body.isVisible())

        # Editor interactions and reorder controls remain independent.
        first.simple.click()
        self.assertTrue(first.body.isVisible())
        QTest.mouseClick(first.drag_handle, Qt.MouseButton.LeftButton)
        self.assertTrue(first.body.isVisible())
        self.assertEqual(len(self.events), 1)
        self.assertTrue(second.body.isVisible())

    def test_wheel_scroll_ignores_dropdowns_and_duration_without_saving(self):
        """Scrolling over form controls must not change values or reset the timer."""
        first = self.dialog.cards[0]
        first.gradient.setChecked(True)
        self.events.clear()
        controls = (
            self.dialog.language_combo,
            first.color,
            first.gradient_end,
            first.position,
            first.minutes,
        )
        for widget in controls:
            with self.subTest(widget=widget.objectName() or type(widget).__name__):
                widget.setFocus()
                original = (
                    widget.currentIndex() if isinstance(widget, QComboBox)
                    else widget.value()
                )
                local = QPointF(widget.rect().center())
                wheel = QWheelEvent(
                    local,
                    QPointF(widget.mapToGlobal(widget.rect().center())),
                    QPoint(0, 0),
                    QPoint(0, -120),
                    Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier,
                    Qt.ScrollPhase.ScrollUpdate,
                    False,
                )
                QApplication.sendEvent(widget, wheel)
                actual = (
                    widget.currentIndex() if isinstance(widget, QComboBox)
                    else widget.value()
                )
                self.assertEqual(actual, original)
        self.assertEqual(self.events, [])

        # Intentional keyboard and direct edits still work as before.
        first.position.setFocus()
        QTest.keyClick(first.position, Qt.Key.Key_Down)
        self.assertEqual(first.position.currentIndex(), 1)
        first.minutes.setValue(50)
        self.assertEqual(first.minutes.value(), 50)
        self.assertTrue(self.events)
        self.assertTrue(all(restart is False for restart in self.events))

    def test_update_controls_show_version_without_changing_timer(self):
        version = self.dialog.version_label.text()
        self.assertEqual(version, "1.0.1")
        self.assertEqual(self.dialog.update_button.text(), "更新を確認")
        self.assertTrue(self.dialog.update_button.isEnabled())
        phases = [card.snapshot() for card in self.dialog.cards]

        self.dialog.set_update_status(True, "ダウンロード中... 25%")
        self.assertFalse(self.dialog.update_button.isEnabled())
        self.assertEqual(self.dialog.update_button.text(), "ダウンロード中... 25%")
        self.dialog.set_update_status(False)
        self.assertTrue(self.dialog.update_button.isEnabled())
        self.assertEqual([card.snapshot() for card in self.dialog.cards], phases)
        self.assertEqual(self.events, [])

        self.dialog.language_combo.setCurrentIndex(
            self.dialog.language_combo.findData("en")
        )
        self.assertEqual(self.dialog.update_button.text(), "Check for updates")
        self.assertEqual(self.dialog.version_label.text(), version)

    def test_japanese_help_text_and_tooltips_use_polite_style(self):
        card = self.dialog.cards[0]
        self.assertEqual(
            self.dialog.note_label.text(),
            "設定は即時反映・保存されます。⠿をドラッグするか、↑↓で並べ替えられます。"
            "順番・分数を変更すると、先頭から再スタートします。",
        )
        expected = (
            (card.drag_handle, "ドラッグしてフェーズの順番を変更できます。"),
            (card.move_up, "フェーズを上に移動します。"),
            (card.move_down, "フェーズを下に移動します。"),
            (card.expand_button, "フェーズの設定欄を開閉します。"),
            (card.hidden, "このフェーズ中はタイマー表示のみを非表示にします。"),
            (card.delete_button, "フェーズを削除します。確認画面が表示されます。"),
            (self.dialog.initialize_button, "設定とタイマーを初期値に戻します。"),
        )
        for widget, text in expected:
            with self.subTest(widget=widget):
                self.assertEqual(widget.toolTip(), text)

        self.dialog.language_combo.setCurrentIndex(
            self.dialog.language_combo.findData("en")
        )
        self.assertIn("Changes are saved immediately", self.dialog.note_label.text())
        self.assertEqual(
            self.dialog.cards[0].drag_handle.toolTip(), "Drag to reorder phases"
        )

    def test_all_buttons_and_checkboxes_show_pointing_hand(self):
        for button in self.dialog.findChildren(QAbstractButton):
            self.assertEqual(
                button.cursor().shape(), Qt.CursorShape.PointingHandCursor,
                button.text(),
            )
        self.dialog._add_phase()
        for button in self.dialog.cards[-1].findChildren(QAbstractButton):
            self.assertEqual(button.cursor().shape(), Qt.CursorShape.PointingHandCursor)

    def test_two_column_editor_all_controls_and_instant_preview(self):
        card = self.dialog.cards[0]
        card.name.setText("集中")
        card.minutes.setValue(55)
        card.color.setCurrentIndex(card.color.findData("black"))
        card.gradient_end.setCurrentIndex(card.gradient_end.findData("mint"))
        card.size.setValue(196)
        card.opacity.setValue(42)
        card.simple.setChecked(True)
        card.position.setCurrentIndex(card.position.findData("center"))
        card.topmost.setChecked(False)
        card.hidden.setChecked(True)
        self.assertEqual(card.size_label.text(), "196 pt")
        self.assertEqual(card.opacity_label.text(), "42%")
        phase = self.dialog.result_phases[0]
        self.assertEqual(
            (phase.name, phase.minutes, phase.color, phase.gradient_end,
             phase.font_size, phase.opacity, phase.simple, phase.position, phase.topmost),
            ("集中", 55, "black", "mint", 196, 42, True, "center", False),
        )
        self.assertIn("Simple", card.summary.text())
        self.assertIn("最前面OFF", card.summary.text())
        self.assertIn("非表示", card.summary.text())
        self.assertTrue(self.dialog.result_phases[0].hidden)
        self.assertIn("中央", card.summary.text())
        self.assertIn("集中", card.title.text())
        self.assertEqual(card.name.maxLength(), 40)
        self.assertEqual((card.minutes.minimum(), card.minutes.maximum()), (1, 240))
        self.assertEqual((card.size.minimum(), card.size.maximum()), (8, 300))
        self.assertEqual((card.opacity.minimum(), card.opacity.maximum()), (0, 100))
        self.assertTrue(all(event is False for event in self.events))

    def test_full_palette_swatches_and_grouped_gradient(self):
        card = self.dialog.cards[0]
        self.assertEqual(card.color.count(), 7)
        self.assertEqual(card.gradient_end.count(), 7)
        for combo in (card.color, card.gradient_end):
            for color in COLOR_HEX:
                index = combo.findData(color)
                self.assertGreaterEqual(index, 0)
                self.assertFalse(combo.itemIcon(index).isNull())
        container = card.gradient.parentWidget()
        self.assertIs(container.layout().itemAt(0).widget(), card.gradient)
        self.assertIs(container.layout().itemAt(1).widget(), card.gradient_end)
        card.gradient_end.setCurrentIndex(card.gradient_end.findData("black"))
        card.gradient.setChecked(False)
        self.assertFalse(card.gradient_end.isEnabled())
        self.assertEqual(self.dialog.result_phases[0].gradient_end, "black")
        card.gradient.setChecked(True)
        self.assertTrue(card.gradient_end.isEnabled())

    def test_add_and_reorder_keeps_all_per_phase_settings(self):
        first = self.dialog.cards[0]
        first.simple.setChecked(True)
        first.position.setCurrentIndex(first.position.findData("top_right"))
        first.topmost.setChecked(False)
        self.dialog._add_phase()
        first = self.dialog.cards[0]  # _add_phase rebuilds card widgets.
        self.assertEqual(len(self.dialog.cards), 3)
        self.assertEqual(self.dialog.cards[-1].name.text(), "新しいフェーズ")
        self.assertEqual(self.dialog.cards[-1].minutes.value(), 5)
        self.assertFalse(self.dialog.cards[-1].simple.isChecked())
        self.assertTrue(self.dialog.cards[-1].topmost.isChecked())
        self.assertTrue(self.dialog.cards[-1].expand_button.isChecked())
        self.assertTrue(self.dialog.cards[0].expand_button.isChecked())
        self.dialog._reorder_cards(first, self.dialog.cards[-1])
        self.assertEqual([c.name.text() for c in self.dialog.cards], ["休憩中", "新しいフェーズ", "作業中"])
        self.assertEqual(self.dialog.result_phases[-1].position, "top_right")
        self.assertFalse(self.dialog.result_phases[-1].topmost)
        self.assertTrue(self.events[-1])
        self.dialog.cards[-1].move_up.click()
        self.assertEqual([c.name.text() for c in self.dialog.cards], ["休憩中", "作業中", "新しいフェーズ"])

    def test_delete_confirmation_and_minimum_one_phase(self):
        first = self.dialog.cards[0]
        before = [c.snapshot() for c in self.dialog.cards]
        for answer in (QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.NoButton):
            with patch.object(QMessageBox, "exec", return_value=answer):
                first.delete_button.click()
            self.assertEqual([c.snapshot() for c in self.dialog.cards], before)
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes):
            first.delete_button.click()
        self.assertEqual(len(self.dialog.cards), 1)
        self.assertEqual(self.dialog.cards[0].name.text(), "休憩中")
        self.assertTrue(self.events[-1])
        with patch.object(QMessageBox, "information") as info:
            self.dialog.cards[0].delete_button.click()
            info.assert_called_once()
        self.assertEqual(len(self.dialog.cards), 1)

    def test_multicard_expansion_persists_when_deleting_another_card(self):
        first, second = self.dialog.cards
        second.expand_button.click()
        self.assertTrue(first.expand_button.isChecked())
        self.assertTrue(second.expand_button.isChecked())
        with patch.object(
            QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes
        ):
            first.delete_button.click()
        self.assertEqual(len(self.dialog.cards), 1)
        self.assertEqual(self.dialog.cards[0].name.text(), "休憩中")
        self.assertTrue(self.dialog.cards[0].expand_button.isChecked())
        self.assertTrue(self.dialog.cards[0].body.isVisible())

    def test_delete_button_is_compact_and_muted(self):
        card = self.dialog.cards[0]
        button = card.delete_button
        self.assertEqual((button.width(), button.height()), (54, 26))
        self.assertIn("#F9EAEC", button.styleSheet())
        self.assertNotIn("#C62828", button.styleSheet())
        self.assertTrue(button.isVisible())

    def test_initialization_confirmation_default_cancel(self):
        calls = []
        self.dialog.initialize_requested.connect(lambda: calls.append(True))
        initialize = self.dialog.findChild(QPushButton, "initialize_button")
        for answer in (QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.NoButton):
            with patch.object(QMessageBox, "exec", return_value=answer) as popup:
                initialize.click()
                popup.assert_called_once()
            self.assertEqual(calls, [])
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes):
            initialize.click()
        self.assertEqual(calls, [True])
        self.assertTrue(self.dialog.isVisible())

    def test_footer_groups_live_loop_resets_pause_and_settings_initialize(self):
        """Order must match the tray, with only LOOP remaining footer-only."""
        root = self.dialog.layout()
        self.assertIs(root.itemAt(1).widget(), self.dialog.scroll)
        self.assertIs(root.itemAt(0).layout().itemAt(1).widget(),
                      self.dialog.language_combo)
        footer = root.itemAt(root.count() - 1).layout()
        self.assertIsNotNone(footer)
        self.assertEqual(footer.spacing(), 6)

        self.assertEqual(
            [footer.itemAt(i).widget().text() for i in range(6)],
            [
                "一時停止",
                "前のフェーズへ",
                "次のフェーズへ",
                "現在のフェーズをリセット",
                "ループ数をリセット",
                "LOOP 01",
            ],
        )
        self.assertIs(footer.itemAt(0).widget(), self.dialog.pause_button)
        self.assertIs(footer.itemAt(1).widget(), self.dialog.previous_button)
        self.assertIs(footer.itemAt(2).widget(), self.dialog.skip_button)
        self.assertIs(footer.itemAt(3).widget(), self.dialog.timer_reset_button)
        self.assertIs(footer.itemAt(4).widget(), self.dialog.loop_reset_button)
        self.assertIs(footer.itemAt(5).widget(), self.dialog.loop_label)
        self.assertIsNotNone(footer.itemAt(6).spacerItem())

        # No spacer between settings reset and Close: both belong to one
        # right-aligned group using the same 6px as the left-hand controls.
        right = footer.itemAt(7).layout()
        self.assertIsNotNone(right)
        self.assertEqual(right.spacing(), footer.spacing())
        self.assertEqual((right.contentsMargins().left(),
                          right.contentsMargins().right()), (0, 0))
        self.assertEqual(right.count(), 2)
        self.assertIs(right.itemAt(0).widget(), self.dialog.initialize_button)
        self.assertIsInstance(right.itemAt(1).widget(), QDialogButtonBox)
        self.assertIs(right.itemAt(1).widget().button(
            QDialogButtonBox.StandardButton.Close), self.dialog.close_button)

        calls = []
        self.dialog.pause_toggle.connect(lambda: calls.append("pause"))
        self.dialog.previous_requested.connect(lambda: calls.append("previous"))
        self.dialog.skip_requested.connect(lambda: calls.append("next"))
        self.dialog.timer_reset.connect(lambda: calls.append("timer"))
        self.dialog.loop_reset.connect(lambda: calls.append("loop"))
        for index in range(5):
            footer.itemAt(index).widget().click()
        self.assertEqual(calls, ["pause", "previous", "next", "timer", "loop"])
        self.dialog.set_loop_number(12)
        self.assertEqual(footer.itemAt(5).widget().text(), "LOOP 12")
        self.dialog.set_pause_state(True)
        self.assertEqual(footer.itemAt(0).widget().text(), "再開")

    def test_only_close_button_in_dialog_button_box(self):
        buttons = self.dialog.findChild(QDialogButtonBox)
        self.assertIsNone(buttons.button(QDialogButtonBox.StandardButton.Apply))
        self.assertIsNone(buttons.button(QDialogButtonBox.StandardButton.Ok))
        self.assertIsNone(buttons.button(QDialogButtonBox.StandardButton.Cancel))
        self.assertIsNotNone(buttons.button(QDialogButtonBox.StandardButton.Close))



class TabNavigationTests(unittest.TestCase):
    """Tab stays on top-level actions and phase headers, even after rebuilding cards."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.dialog = SettingsDialog(None, FocusTimer())
        self.dialog.show()
        self.dialog.activateWindow()
        self.app.processEvents()

    def tearDown(self):
        self.dialog.close()
        self.app.processEvents()

    def tab_controls(self):
        """Return the intended screen order, skipping disabled or hidden buttons."""
        dialog = self.dialog
        controls = [dialog.language_combo, dialog.notifications_checkbox,
                    dialog.update_button]
        for card in dialog.cards:
            controls.extend((card.move_up, card.move_down, card.expand_button))
        controls.extend((
            dialog.add_button, dialog.pause_button, dialog.previous_button,
            dialog.skip_button, dialog.timer_reset_button, dialog.loop_reset_button,
            dialog.initialize_button, dialog.close_button,
        ))
        return [widget for widget in controls if widget.isVisible()
                and widget.isEnabled()]

    def assert_keyboard_navigation(self):
        """Send real Qt Tab / Shift+Tab key events, including the wraparound."""
        controls = self.tab_controls()
        self.assertGreater(len(controls), 9)
        for control in controls:
            self.assertTrue(bool(control.focusPolicy() & Qt.FocusPolicy.TabFocus))

        controls[0].setFocus()
        self.app.processEvents()
        self.assertIs(self.dialog.focusWidget(), controls[0])
        for expected in controls[1:] + controls[:1]:
            current = self.dialog.focusWidget()
            QTest.keyClick(current, Qt.Key.Key_Tab)
            self.app.processEvents()
            self.assertIs(self.dialog.focusWidget(), expected,
                          f"Tab after {current.objectName() or current.text()}")

        for expected in list(reversed(controls[1:])) + controls[:1]:
            current = self.dialog.focusWidget()
            QTest.keyClick(current, Qt.Key.Key_Backtab)
            self.app.processEvents()
            self.assertIs(self.dialog.focusWidget(), expected,
                          f"Shift+Tab after {current.objectName() or current.text()}")

    def test_initial_tab_and_reverse_tab_follow_visual_order(self):
        self.assertFalse(self.dialog.cards[0].move_up.isEnabled())
        self.assertFalse(self.dialog.cards[-1].move_down.isEnabled())
        self.assert_keyboard_navigation()

    def test_editor_controls_skip_tab_but_remain_click_focusable(self):
        card = self.dialog.cards[0]
        for widget in (
            card.name, card.minutes, card.color, card.gradient,
            card.gradient_end, card.size, card.opacity, card.simple,
            card.topmost, card.hidden, card.position, card.delete_button,
        ):
            self.assertEqual(widget.focusPolicy(), Qt.FocusPolicy.ClickFocus)
            self.assertFalse(bool(widget.focusPolicy() & Qt.FocusPolicy.TabFocus))
        self.assertEqual(card.drag_handle.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertEqual(self.dialog.scroll.focusPolicy(), Qt.FocusPolicy.NoFocus)

        # Mouse editing must still work with ClickFocus. The timer and
        # persistence callback are unchanged by the focus policy.
        card.name.setFocus()
        self.app.processEvents()
        self.assertIs(self.dialog.focusWidget(), card.name)
        QTest.keyClicks(card.name, " X")
        self.assertTrue(card.name.text().endswith(" X"))
        old_simple = card.simple.isChecked()
        QTest.mouseClick(card.simple, Qt.MouseButton.LeftButton)
        self.assertNotEqual(card.simple.isChecked(), old_simple)
        self.assert_keyboard_navigation()

    def test_accordion_toggle_never_adds_body_fields_to_tab_chain(self):
        first, second = self.dialog.cards
        self.assertTrue(first.expand_button.isChecked())
        first.expand_button.click()
        second.expand_button.click()
        self.app.processEvents()
        self.assertFalse(first.body.isVisible())
        self.assertTrue(second.body.isVisible())
        self.assert_keyboard_navigation()
        first.expand_button.click()
        second.expand_button.click()
        self.app.processEvents()
        self.assert_keyboard_navigation()

    def test_add_reorder_delete_and_reset_rebuild_tab_chain(self):
        self.dialog._add_phase()
        self.app.processEvents()
        self.assertEqual(len(self.dialog.cards), 3)
        self.assert_keyboard_navigation()

        moving = self.dialog.cards[-1]
        self.dialog._shift_card(moving, -1)
        self.app.processEvents()
        self.assertIs(self.dialog.cards[1], moving)
        self.assert_keyboard_navigation()

        with patch("focusloop.app.confirm_change", return_value=True):
            self.dialog._confirm_delete_card(self.dialog.cards[1])
        self.app.processEvents()
        self.assertEqual(len(self.dialog.cards), 2)
        self.assert_keyboard_navigation()

        self.dialog.restore_defaults(default_phases(), loop_number=1)
        self.app.processEvents()
        self.assert_keyboard_navigation()

    def test_language_switch_rebuilds_tab_chain_in_both_directions(self):
        for index in (1, 0):
            self.dialog.language_combo.setCurrentIndex(index)
            self.app.processEvents()
            self.assert_keyboard_navigation()

    def test_disabled_and_hidden_controls_are_skipped(self):
        self.dialog.update_button.setEnabled(False)
        self.dialog.add_button.hide()
        self.app.processEvents()
        self.assert_keyboard_navigation()


class AppRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.ini = str(Path(self.directory.name) / "app.ini")
        self.settings_patch = patch(
            "focusloop.app.QSettings",
            side_effect=lambda *_args: QSettings(self.ini, QSettings.Format.IniFormat),
        )
        self.settings_patch.start()
        self.controller = FocusLoopApp(self.app)

    def tearDown(self):
        self.controller.close()
        self.settings_patch.stop()
        self.directory.cleanup()
        self.app.processEvents()

    def test_japanese_update_dialogs_use_polite_messages(self):
        self.controller.show_settings()
        self.assertEqual(self.controller.language, "ja")
        release = Mock(version="1.0.2")

        with patch.object(QMessageBox, "warning") as warning:
            self.controller._on_update_checked(None, "network error")
            self.assertIn("更新を確認できませんでした。", warning.call_args.args[2])
        with patch.object(QMessageBox, "information") as info:
            self.controller._on_update_checked(None, None)
            self.assertEqual(info.call_args.args[2], "FocusLoopは最新バージョンです。")

        with (
            patch("focusloop.app.updates.can_self_update", return_value=False),
            patch.object(QMessageBox, "information") as info,
        ):
            self.controller._on_update_checked(release, None)
            message = info.call_args.args[2]
            self.assertIn("新しいバージョン 1.0.2 を利用できます。", message)
            self.assertIn("Windows配布版のみ対応しています。", message)

        with (
            patch("focusloop.app.updates.can_self_update", return_value=True),
            patch.object(QMessageBox, "question",
                         return_value=QMessageBox.StandardButton.No) as question,
        ):
            self.controller._on_update_checked(release, None)
            message = question.call_args.args[2]
            self.assertIn("1.0.2 に更新しますか？", message)
            self.assertIn("自動的に再起動します。", message)

        with patch.object(QMessageBox, "warning") as warning:
            self.controller._on_update_prepared(None, "download error")
            self.assertIn("更新ファイルを準備できませんでした。", warning.call_args.args[2])

        with (
            patch("focusloop.app.updates.launch_updater", side_effect=OSError("failed")),
            patch("focusloop.app.updates.discard_prepared_update"),
            patch.object(QMessageBox, "warning") as warning,
        ):
            self.controller._on_update_prepared(object(), None)
            self.assertIn("更新処理を開始できませんでした。", warning.call_args.args[2])

    def test_first_run_and_settings_reset_match_screenshot(self):
        expected = default_phases()
        self.assertEqual(self.controller.timer_model.phases, expected)
        self.assertEqual(
            [(p.name, p.minutes, p.color, p.gradient, p.gradient_end,
              p.font_size, p.opacity, p.simple, p.position, p.topmost, p.hidden)
             for p in expected],
            [
                ("作業中", 45, "amber", True, "rose", 50, 30,
                 False, "bottom_left", True, False),
                ("休憩中", 15, "mint", False, "white", 300, 20,
                 False, "center", True, False),
            ],
        )
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        for card, phase in zip(dialog.cards, expected):
            self.assertEqual(card.name.text(), phase.name)
            self.assertEqual(card.minutes.value(), phase.minutes)
            self.assertEqual(card.color.currentData(), phase.color)
            self.assertEqual(card.gradient_end.currentData(), phase.gradient_end)
            self.assertEqual(card.gradient.isChecked(), phase.gradient)
            self.assertEqual(card.gradient_end.isEnabled(), phase.gradient)
            self.assertEqual(card.size.value(), phase.font_size)
            self.assertEqual(card.opacity.value(), phase.opacity)
            self.assertEqual(card.simple.isChecked(), phase.simple)
            self.assertEqual(card.position.currentData(), phase.position)
            self.assertEqual(card.topmost.isChecked(), phase.topmost)
            self.assertEqual(card.hidden.isChecked(), phase.hidden)

        # Saved customizations survive a second launch unless reset is requested.
        first = dialog.cards[0]
        first.name.setText("カスタム")
        first.opacity.setValue(67)
        first.position.setCurrentIndex(first.position.findData("top_right"))
        dialog.cards[1].gradient.setChecked(True)
        self.assertTrue(dialog.cards[1].gradient_end.isEnabled())
        self.controller.settings.sync()
        reopened = FocusLoopApp(self.app)
        self.assertEqual(reopened.timer_model.phases[0].name, "カスタム")
        self.assertEqual(reopened.timer_model.phases[0].opacity, 67)
        self.assertEqual(reopened.timer_model.phases[0].position, "top_right")
        self.assertTrue(reopened.timer_model.phases[1].gradient)
        reopened.close()

        reset = dialog.findChild(QPushButton, "initialize_button")
        self.assertEqual(reset.text(), "設定初期化")
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Cancel):
            reset.click()
        self.assertEqual(self.controller.timer_model.phases[0].name, "カスタム")
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes):
            reset.click()
        self.assertEqual(self.controller.timer_model.phases, expected)
        self.assertFalse(dialog.cards[1].gradient.isChecked())
        self.assertFalse(dialog.cards[1].gradient_end.isEnabled())
        self.assertEqual(dialog.cards[1].gradient_end.currentData(), "white")
        self.assertEqual(
            [(card.name.text(), card.size.value(), card.opacity.value(),
              card.color.currentData(), card.gradient_end.currentData(),
              card.position.currentData())
             for card in dialog.cards],
            [
                ("作業中", 50, 30, "amber", "rose", "bottom_left"),
                ("休憩中", 300, 20, "mint", "white", "center"),
            ],
        )
        self.controller.settings.sync()
        persisted = FocusLoopApp(self.app)
        self.assertEqual(persisted.timer_model.phases, expected)
        persisted.close()

    def test_modern_ring_30fps_timer_stops_when_paused_simple_or_hidden(self):
        self.assertEqual(self.controller.ring_timer.interval(), 33)
        self.assertEqual(
            self.controller.ring_timer.timerType(), Qt.TimerType.PreciseTimer
        )
        self.assertFalse(self.controller.ring_timer.isActive())
        self.controller.overlay.show()
        self.controller.update()
        self.assertTrue(self.controller.ring_timer.isActive())

        with patch.object(self.controller.overlay, "set_ring_progress") as animate:
            self.controller._animate_ring()
            animate.assert_called_once()
            self.assertGreaterEqual(animate.call_args.args[0], 0.0)
            self.assertLessEqual(animate.call_args.args[0], 1.0)

        self.controller.toggle_pause()
        self.assertFalse(self.controller.ring_timer.isActive())
        self.controller.toggle_pause()
        self.assertTrue(self.controller.ring_timer.isActive())

        self.controller.show_settings()
        card = self.controller.settings_dialog.cards[0]
        card.simple.setChecked(True)
        self.assertFalse(self.controller.ring_timer.isActive())
        card.simple.setChecked(False)
        self.assertTrue(self.controller.ring_timer.isActive())

        self.controller.overlay.hide()
        self.controller._animate_ring()
        self.assertFalse(self.controller.ring_timer.isActive())

        self.controller.overlay.show()
        self.controller.update()
        self.assertTrue(self.controller.ring_timer.isActive())
        self.controller.close()
        self.assertFalse(self.controller.ring_timer.isActive())

    def test_settings_pause_resume_button_tracks_tray_and_initialization(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        button = dialog.pause_button
        self.assertEqual(button.objectName(), "pause_button")
        self.assertEqual(button.text(), "一時停止")
        self.assertEqual(
            button.cursor().shape(), Qt.CursorShape.PointingHandCursor,
        )
        original_loop = self.controller.timer_model.loop_number
        original_remaining = self.controller.timer_model.remaining_seconds()

        button.click()
        self.assertTrue(self.controller.timer_model.paused)
        self.assertEqual(button.text(), "再開")
        self.assertEqual(self.controller.pause_action.text(), "再開")
        paused_remaining = self.controller.timer_model.remaining_seconds()
        self.assertLessEqual(abs(paused_remaining - original_remaining), 1)
        self.assertEqual(self.controller.timer_model.remaining_seconds(), paused_remaining)

        # The tray action must also update the settings button state.
        self.controller.pause_action.trigger()
        self.assertFalse(self.controller.timer_model.paused)
        self.assertEqual(button.text(), "一時停止")
        self.assertEqual(self.controller.pause_action.text(), "一時停止")
        self.assertEqual(self.controller.timer_model.loop_number, original_loop)

        self.controller.toggle_pause()
        self.assertEqual(button.text(), "再開")
        self.assertTrue(self.controller.timer_model.paused)
        self.controller._initialize_defaults()
        self.assertFalse(self.controller.timer_model.paused)
        self.assertEqual(dialog.pause_button.text(), "一時停止")
        self.assertEqual(self.controller.pause_action.text(), "一時停止")

        self.controller.toggle_pause()
        dialog.close()
        self.controller.show_settings()
        self.assertEqual(self.controller.settings_dialog.pause_button.text(), "再開")

    def test_hidden_phase_hides_only_overlay_and_resumes_on_phase_transition(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        work, rest = dialog.cards
        self.assertFalse(work.hidden.isChecked())
        self.assertFalse(rest.hidden.isChecked())

        # Mimic app.start() without requiring an OS tray in offscreen Qt tests.
        self.controller._overlay_started = True
        self.controller.update()
        self.assertTrue(self.controller.overlay.isVisible())
        before = self.controller.timer_model.remaining_seconds()
        work.hidden.setChecked(True)
        self.assertTrue(self.controller.timer_model.phases[0].hidden)
        self.assertFalse(self.controller.overlay.isVisible())
        self.assertTrue(dialog.isVisible())
        self.assertTrue(work.isVisible())
        self.assertIn("非表示", work.summary.text())
        self.assertLessEqual(abs(self.controller.timer_model.remaining_seconds() - before), 1)

        # The hidden phase can be paused/resumed without changing visibility.
        dialog.pause_button.click()
        self.assertTrue(self.controller.timer_model.paused)
        self.assertFalse(self.controller.overlay.isVisible())
        self.assertEqual(dialog.pause_button.text(), "再開")
        dialog.pause_button.click()
        self.assertFalse(self.controller.timer_model.paused)

        self.controller.skip()
        self.assertEqual(self.controller.timer_model.current_phase.name, "休憩中")
        self.assertTrue(self.controller.overlay.isVisible())
        self.assertEqual(self.controller.overlay.clock_text, "15:00")
        self.controller.skip()
        self.assertEqual(self.controller.timer_model.current_phase.name, "作業中")
        self.assertFalse(self.controller.overlay.isVisible())
        self.assertEqual(self.controller.timer_model.loop_number, 2)

        work.hidden.setChecked(False)
        self.assertTrue(self.controller.overlay.isVisible())
        self.assertNotIn("非表示", work.summary.text())

    def test_hidden_setting_persists_and_initialization_restores_visibility(self):
        self.controller._overlay_started = True
        self.controller.update()
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        first, second = dialog.cards
        first.hidden.setChecked(True)
        second.hidden.setChecked(True)
        self.assertFalse(self.controller.overlay.isVisible())
        self.controller.settings.sync()
        stored = QSettings(self.ini, QSettings.Format.IniFormat)
        self.assertIn('"hidden": true', stored.value("phases_json"))

        reopened = FocusLoopApp(self.app)
        self.assertTrue(all(p.hidden for p in reopened.timer_model.phases))
        self.assertFalse(reopened.overlay.isVisible())
        reopened._overlay_started = True
        reopened.update()
        self.assertFalse(reopened.overlay.isVisible())
        reopened.timer_model.skip()
        reopened.update()
        self.assertFalse(reopened.overlay.isVisible())
        reopened.close()

        self.controller._initialize_defaults()
        self.assertEqual(self.controller.timer_model.phases, default_phases())
        self.assertTrue(self.controller.overlay.isVisible())
        self.assertFalse(dialog.cards[0].hidden.isChecked())
        self.assertFalse(dialog.cards[1].hidden.isChecked())
        self.assertEqual(dialog.pause_button.text(), "一時停止")

    def test_per_phase_display_position_and_topmost_switch_on_skip(self):
        self.controller.overlay.show()
        self.controller.show_settings()
        card = self.controller.settings_dialog.cards[0]
        second = self.controller.settings_dialog.cards[1]
        card.simple.setChecked(True)
        card.position.setCurrentIndex(card.position.findData("center"))
        card.topmost.setChecked(False)
        second.simple.setChecked(False)
        second.position.setCurrentIndex(second.position.findData("top_right"))
        second.topmost.setChecked(True)
        self.assertEqual(self.controller.overlay.display_style, "simple")
        self.assertEqual(self.controller.overlay.position_name, "center")
        self.assertFalse(self.controller.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(self.controller.overlay.isVisible())
        initial = self.controller.timer_model.remaining_seconds()
        card.size.setValue(80)
        self.assertLessEqual(abs(self.controller.timer_model.remaining_seconds() - initial), 1)
        self.controller.skip()
        self.assertEqual(self.controller.overlay.display_style, "modern")
        self.assertEqual(self.controller.overlay.position_name, "top_right")
        self.assertTrue(self.controller.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(self.controller.overlay.isVisible())
        self.assertTrue(self.controller.overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertTrue(self.controller.overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.controller.settings.sync()
        stored = QSettings(self.ini, QSettings.Format.IniFormat)
        self.assertIn('"topmost": false', stored.value("phases_json"))

    def test_center_in_both_styles_and_font_size_limit(self):
        self.controller.overlay.show()
        self.controller.show_settings()
        card = self.controller.settings_dialog.cards[0]
        card.position.setCurrentIndex(card.position.findData("center"))
        bounds = self.app.primaryScreen().availableGeometry()
        for simple in (False, True):
            card.simple.setChecked(simple)
            card.size.setValue(300)
            overlay = self.controller.overlay.geometry()
            self.assertEqual(self.controller.timer_model.current_phase.font_size, 300)
            self.assertLessEqual(self.controller.overlay._render_font_size, 300)
            self.assertLessEqual(abs(overlay.center().x() - bounds.center().x()), 1)
            self.assertLessEqual(abs(overlay.center().y() - bounds.center().y()), 1)
            self.assertTrue(bounds.contains(overlay))
            self.assertEqual(self.controller.overlay.display_style,
                             "simple" if simple else "modern")

    def test_reopen_persists_distinct_phase_preferences(self):
        self.controller.show_settings()
        first, second = self.controller.settings_dialog.cards
        first.simple.setChecked(True)
        first.position.setCurrentIndex(first.position.findData("center"))
        first.topmost.setChecked(False)
        second.position.setCurrentIndex(second.position.findData("bottom_right"))
        self.controller.settings.sync()
        restored = FocusLoopApp(self.app)
        self.assertTrue(restored.timer_model.phases[0].simple)
        self.assertEqual(restored.timer_model.phases[0].position, "center")
        self.assertFalse(restored.timer_model.phases[0].topmost)
        self.assertEqual(restored.timer_model.phases[1].position, "bottom_right")
        self.assertFalse(restored.timer_model.phases[1].simple)
        restored.close()

    def test_global_style_and_position_migrate_to_every_phase(self):
        old = QSettings(self.ini, QSettings.Format.IniFormat)
        old.setValue("display_style", "simple")
        old.setValue("position", "top_left")
        old.setValue("work_minutes", 25)
        old.setValue("break_minutes", 10)
        old.sync()
        restored = FocusLoopApp(self.app)
        self.assertEqual([(p.simple, p.position) for p in restored.timer_model.phases],
                         [(True, "top_left"), (True, "top_left")])
        self.assertEqual(restored.timer_model.phases[0].minutes, 25)
        restored.close()

    def test_loop_reset_timer_reset_initialization_and_cancel(self):
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        first = dialog.cards[0]
        first.name.setText("仕事")
        first.simple.setChecked(True)
        first.position.setCurrentIndex(first.position.findData("center"))
        first.topmost.setChecked(False)
        self.controller.timer_model.skip()
        self.controller.timer_model.loop_number = 9
        self.controller.timer_model.pause()
        self.controller.update()
        before = self.controller.timer_model.remaining_seconds()
        loop_reset = next(b for b in dialog.findChildren(QPushButton)
                          if b.text() == "ループ数をリセット")
        loop_reset.click()
        self.assertEqual(self.controller.timer_model.loop_number, 1)
        self.assertEqual(self.controller.timer_model.remaining_seconds(), before)
        timer_reset = next(b for b in dialog.findChildren(QPushButton)
                           if b.text() == "現在のフェーズをリセット")
        timer_reset.click()
        self.assertEqual(self.controller.timer_model.current_phase.minutes * 60,
                         self.controller.timer_model.remaining_seconds())
        self.assertTrue(self.controller.timer_model.paused)

        init = dialog.findChild(QPushButton, "initialize_button")
        for result in (QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.NoButton):
            with patch.object(QMessageBox, "exec", return_value=result):
                init.click()
            self.assertEqual(dialog.cards[0].name.text(), "仕事")
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes):
            init.click()
        self.assertEqual(self.controller.timer_model.phases, default_phases())
        self.assertFalse(self.controller.timer_model.paused)
        self.assertEqual(self.controller.timer_model.loop_number, 1)
        self.assertEqual(self.controller.overlay.clock_text, "45:00")
        self.assertTrue(dialog.isVisible())
        self.assertFalse(dialog.cards[0].simple.isChecked())
        self.assertTrue(dialog.cards[0].topmost.isChecked())
        self.assertFalse(dialog.cards[0].hidden.isChecked())
        self.assertEqual(dialog.cards[0].position.currentData(), "bottom_left")

    def test_tray_footer_action_order_and_both_reset_entrypoints(self):
        expected = [
            "一時停止", "前のフェーズへ", "次のフェーズへ",
            "現在のフェーズをリセット", "ループ数をリセット",
        ]
        tray_actions = self.controller.menu.actions()
        actual = [
            action.text() for action in tray_actions
            if action in (
                self.controller.pause_action,
                self.controller.previous_action,
                self.controller.skip_action,
                self.controller.reset_action,
                self.controller.loop_reset_action,
            )
        ]
        self.assertEqual(actual, expected)
        self.assertEqual([a.text() for a in tray_actions
                          if a.text().startswith("LOOP")], [])
        self.controller.show_settings()
        dialog = self.controller.settings_dialog
        footer = dialog.layout().itemAt(dialog.layout().count() - 1).layout()
        self.assertEqual([footer.itemAt(i).widget().text() for i in range(5)],
                         expected)

        # Footer's next action must call the same skip operation as the tray.
        self.controller.timer_model.pause()
        self.controller.update()
        dialog.skip_button.click()
        self.assertEqual(self.controller.timer_model.current_phase.name, "休憩中")
        self.assertTrue(self.controller.timer_model.paused)
        self.controller.skip_action.trigger()
        self.assertEqual(self.controller.timer_model.current_phase.name, "作業中")
        self.assertTrue(self.controller.timer_model.paused)

        # Both previous entrypoints navigate backward and keep the paused state.
        self.controller.timer_model.loop_number = 3
        dialog.previous_button.click()
        self.assertEqual(self.controller.timer_model.current_phase.name, "休憩中")
        self.assertEqual(self.controller.timer_model.loop_number, 2)
        self.assertEqual(self.controller.timer_model.remaining_seconds(), 900)
        self.assertTrue(self.controller.timer_model.paused)
        self.controller.previous_action.trigger()
        self.assertEqual(self.controller.timer_model.current_phase.name, "作業中")
        self.assertEqual(self.controller.timer_model.loop_number, 2)
        self.assertEqual(self.controller.timer_model.remaining_seconds(), 2700)
        self.assertTrue(self.controller.timer_model.paused)
        self.assertEqual(dialog.loop_label.text(), "LOOP 02")

        # Both loop reset paths preserve the actual countdown and phase.
        for reset in (self.controller.loop_reset_action.trigger,
                      dialog.loop_reset_button.click):
            self.controller.timer_model.loop_number = 12
            self.controller.update()
            before = self.controller.timer_model.remaining_seconds()
            current = self.controller.timer_model.current_phase
            reset()
            self.assertEqual(self.controller.timer_model.loop_number, 1)
            self.assertEqual(self.controller.timer_model.remaining_seconds(), before)
            self.assertEqual(self.controller.timer_model.current_phase, current)
            self.assertEqual(dialog.loop_label.text(), "LOOP 01")

    def test_tray_actions_notifications_and_icons(self):
        labels = [x.text() for x in self.controller.menu.actions()]
        for value in ("一時停止", "前のフェーズへ", "次のフェーズへ",
                      "現在のフェーズをリセット", "ループ数をリセット",
                      "設定", "終了"):
            self.assertIn(value, labels)
        with patch.object(self.controller, "show_settings") as show:
            self.controller._tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
            show.assert_called_once()
        with patch.object(self.controller, "_show_tray_menu") as menu:
            self.controller._tray_activated(QSystemTrayIcon.ActivationReason.Context)
            menu.assert_called_once()
        self.controller.tray = Mock()
        self.controller.skip()
        self.controller.tray.showMessage.assert_called_once()
        args = self.controller.tray.showMessage.call_args.args
        self.assertIn("開始しました", args[1])
        self.assertIn("分", args[1])
        self.assertFalse(clock_image(256).isNull())
        self.assertFalse(clock_icon().isNull())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "FocusLoop.ico"
            build_ico(path)
            binary = path.read_bytes()
            self.assertEqual(struct.unpack("<HHH", binary[:6]), (0, 1, 7))

    def test_click_through_and_per_phase_opacity_cover_all_drawn_elements(self):
        overlay = self.controller.overlay
        overlay.show()
        self.controller.show_settings()
        card = self.controller.settings_dialog.cards[0]
        flags = overlay.windowFlags()
        self.assertTrue(flags & Qt.WindowType.WindowTransparentForInput)
        self.assertTrue(flags & Qt.WindowType.WindowDoesNotAcceptFocus)
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        card.opacity.setValue(37)
        values = []
        with patch.object(overlay, "_paint_modern", side_effect=lambda painter: values.append(painter.opacity())):
            overlay.grab()
        self.assertTrue(values)
        self.assertAlmostEqual(values[-1], 0.37, places=2)
        card.simple.setChecked(True)
        values.clear()
        with patch.object(overlay, "_paint_simple", side_effect=lambda painter: values.append(painter.opacity())):
            overlay.grab()
        self.assertTrue(values)
        self.assertAlmostEqual(values[-1], 0.37, places=2)

    def test_automatic_phase_transition_sends_notification(self):
        self.controller.tray = Mock()
        with patch.object(self.controller.timer_model, "tick", return_value=True):
            self.controller.update()
        self.controller.tray.showMessage.assert_called_once()
        args = self.controller.tray.showMessage.call_args.args
        self.assertIn("開始しました", args[1])

    def test_remaining_arc_angles_clockwise(self):
        self.assertEqual(remaining_arc_angles(1), (1440, -5760))
        self.assertEqual(remaining_arc_angles(.75), (0, -4320))
        self.assertEqual(remaining_arc_angles(.50), (-1440, -2880))
        self.assertEqual(remaining_arc_angles(.25), (-2880, -1440))
        self.assertEqual(remaining_arc_angles(0), (-4320, 0))


if __name__ == "__main__":
    unittest.main()
