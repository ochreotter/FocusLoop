"""Offscreen UI and application regressions for accordion phase settings."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QAbstractButton, QDialogButtonBox, QMessageBox,
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
        self.assertIn("ホワイト", first.summary.text())
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
        self.assertEqual([c.name.text() for c in self.dialog.cards], ["休憩", "新しいフェーズ", "作業"])
        self.assertEqual(self.dialog.result_phases[-1].position, "top_right")
        self.assertFalse(self.dialog.result_phases[-1].topmost)
        self.assertTrue(self.events[-1])
        self.dialog.cards[-1].move_up.click()
        self.assertEqual([c.name.text() for c in self.dialog.cards], ["休憩", "作業", "新しいフェーズ"])

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
        self.assertEqual(self.dialog.cards[0].name.text(), "休憩")
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
        self.assertEqual(self.dialog.cards[0].name.text(), "休憩")
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
        """All persistent controls belong below the scrollable phase cards."""
        root = self.dialog.layout()
        self.assertIs(root.itemAt(0).widget(), self.dialog.scroll)
        footer = root.itemAt(root.count() - 1).layout()
        self.assertIsNotNone(footer)

        buttons = [
            footer.itemAt(i).widget()
            for i in range(footer.count())
            if footer.itemAt(i).widget() is not None
        ]
        self.assertEqual(
            [w.text() if hasattr(w, "text") else "dialog_buttons" for w in buttons],
            [
                "LOOP 01",
                "ループ数をリセット",
                "現在のフェーズをリセット",
                "一時停止",
                "設定初期化",
                "dialog_buttons",
            ],
        )
        self.assertIs(buttons[0], self.dialog.loop_label)
        self.assertIs(buttons[3], self.dialog.pause_button)
        self.assertIs(buttons[4], self.dialog.findChild(QPushButton, "initialize_button"))
        self.assertIsInstance(buttons[5], QDialogButtonBox)

        # Relocating controls must not change their wiring or live status.
        calls = []
        self.dialog.loop_reset.connect(lambda: calls.append("loop"))
        self.dialog.timer_reset.connect(lambda: calls.append("timer"))
        self.dialog.pause_toggle.connect(lambda: calls.append("pause"))
        buttons[1].click()
        buttons[2].click()
        buttons[3].click()
        self.assertEqual(calls, ["loop", "timer", "pause"])
        self.dialog.set_loop_number(12)
        self.assertEqual(buttons[0].text(), "LOOP 12")
        self.dialog.set_pause_state(True)
        self.assertEqual(buttons[3].text(), "再開")

    def test_only_close_button_in_dialog_button_box(self):
        buttons = self.dialog.findChild(QDialogButtonBox)
        self.assertIsNone(buttons.button(QDialogButtonBox.StandardButton.Apply))
        self.assertIsNone(buttons.button(QDialogButtonBox.StandardButton.Ok))
        self.assertIsNone(buttons.button(QDialogButtonBox.StandardButton.Cancel))
        self.assertIsNotNone(buttons.button(QDialogButtonBox.StandardButton.Close))


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
        self.assertEqual(self.controller.timer_model.current_phase.name, "休憩")
        self.assertTrue(self.controller.overlay.isVisible())
        self.assertEqual(self.controller.overlay.clock_text, "15:00")
        self.controller.skip()
        self.assertEqual(self.controller.timer_model.current_phase.name, "作業")
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

    def test_tray_actions_notifications_and_icons(self):
        labels = [x.text() for x in self.controller.menu.actions()]
        for value in ("一時停止", "次のフェーズへ", "現在のフェーズをリセット", "設定", "終了"):
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
