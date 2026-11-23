"""Qt-level regressions for FocusLoop's per-user single-instance behavior."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from focusloop.app import FocusLoopApp
from focusloop.single_instance import SingleInstance


class SingleInstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setApplicationName("FocusLoop")
        cls.app.setOrganizationName("FocusLoop")

    def setUp(self) -> None:
        self.working = tempfile.TemporaryDirectory()
        self.path = Path(self.working.name)
        self.guards: list[SingleInstance] = []

    def tearDown(self) -> None:
        for guard in reversed(self.guards):
            guard.release()
        self.app.processEvents()
        self.working.cleanup()

    def guard(self) -> SingleInstance:
        guard = SingleInstance(self.path)
        self.guards.append(guard)
        return guard

    def wait_until(self, test, timeout_ms: int = 1000) -> bool:
        for _ in range(max(1, timeout_ms // 20)):
            self.app.processEvents()
            if test():
                return True
            QTest.qWait(20)
        self.app.processEvents()
        return bool(test())

    def test_second_launch_sends_activation_without_taking_lock(self) -> None:
        original = self.guard()
        self.assertTrue(original.acquire())
        original.listen()
        activations: list[str] = []
        original.activate_requested.connect(lambda: activations.append("activate"))

        second = self.guard()
        self.assertFalse(second.acquire())
        self.assertTrue(second.notify_existing())
        self.assertTrue(self.wait_until(lambda: len(activations) == 1))
        self.assertEqual(activations, ["activate"])

        third = self.guard()
        self.assertFalse(third.acquire())
        self.assertTrue(third.notify_existing())
        self.assertTrue(self.wait_until(lambda: len(activations) == 2))
        self.assertEqual(activations, ["activate", "activate"])

    def test_activation_reuses_settings_dialog_and_preserves_timer(self) -> None:
        original = self.guard()
        self.assertTrue(original.acquire())
        original.listen()
        ini = str(self.path / "settings.ini")
        with patch(
            "focusloop.app.QSettings",
            side_effect=lambda *_: QSettings(ini, QSettings.Format.IniFormat),
        ):
            controller = FocusLoopApp(self.app)
            try:
                original.activate_requested.connect(controller.show_settings)
                first = self.guard()
                self.assertFalse(first.acquire())
                self.assertTrue(first.notify_existing())
                self.assertTrue(self.wait_until(lambda: controller.settings_dialog is not None))
                dialog = controller.settings_dialog
                before = (
                    controller.timer_model.phase_index,
                    controller.timer_model.loop_number,
                    controller.timer_model.remaining_seconds(),
                )
                second = self.guard()
                self.assertFalse(second.acquire())
                self.assertTrue(second.notify_existing())
                self.assertTrue(self.wait_until(lambda: controller.settings_dialog is dialog))
                after = (
                    controller.timer_model.phase_index,
                    controller.timer_model.loop_number,
                    controller.timer_model.remaining_seconds(),
                )
                self.assertEqual(before, after)
                self.assertIs(controller.settings_dialog, dialog)
                self.assertTrue(dialog.isVisible())
            finally:
                controller.close()

    def test_lock_is_released_for_next_start_and_update_restart(self) -> None:
        original = self.guard()
        self.assertTrue(original.acquire())
        original.listen()
        duplicate = self.guard()
        self.assertFalse(duplicate.acquire())
        original.release()
        newcomer = self.guard()
        self.assertTrue(newcomer.acquire())
        newcomer.listen()
        self.assertFalse(self.guard().acquire())

    def test_isolated_lock_locations_do_not_block_each_other(self) -> None:
        first = self.guard()
        self.assertTrue(first.acquire())
        first.listen()
        other = SingleInstance(self.path / "different-user")
        self.guards.append(other)
        self.assertNotEqual(first.server_name, other.server_name)
        self.assertTrue(other.acquire())
        other.listen()


if __name__ == "__main__":
    unittest.main()
