"""Dependency-free tests for the timer state machine."""

import unittest

from focusloop.timer import FocusTimer, Phase


class TimerTests(unittest.TestCase):
    def test_defaults_and_transition(self):
        timer = FocusTimer(now=10.0)
        self.assertEqual(timer.remaining_seconds(now=10.0), 45 * 60)
        self.assertFalse(timer.tick(now=2709.99))
        self.assertTrue(timer.tick(now=2710.0))
        self.assertIs(timer.phase, Phase.BREAK)
        self.assertEqual(timer.remaining_seconds(now=2710.0), 15 * 60)
        self.assertTrue(timer.tick(now=3610.0))
        self.assertIs(timer.phase, Phase.WORK)

    def test_pause_resume_preserves_remaining(self):
        timer = FocusTimer(now=0.0)
        timer.pause(now=30.5)
        self.assertEqual(timer.remaining_seconds(now=9000), 2670)
        self.assertFalse(timer.tick(now=9000))
        timer.resume(now=100.0)
        self.assertEqual(timer.remaining_seconds(now=100.0), 2670)
        self.assertEqual(timer.remaining_seconds(now=101.0), 2669)

    def test_late_update_catches_up_without_drift(self):
        timer = FocusTimer(now=0.0)
        self.assertTrue(timer.tick(now=3600 + 5))
        self.assertIs(timer.phase, Phase.WORK)
        self.assertEqual(timer.remaining_seconds(now=3605), 2695)

    def test_customize_durations_and_restart_current_phase(self):
        timer = FocusTimer(now=0.0)
        timer.configure(50, 10, now=12.0)
        self.assertEqual(timer.remaining_seconds(now=12.0), 3000)
        timer.skip(now=15.0)
        self.assertIs(timer.phase, Phase.BREAK)
        self.assertEqual(timer.remaining_seconds(now=15.0), 600)
        timer.configure(30, 5, now=20.0)
        self.assertIs(timer.phase, Phase.BREAK)
        self.assertEqual(timer.remaining_seconds(now=20.0), 300)

    def test_configure_while_paused_stays_paused(self):
        timer = FocusTimer(now=0.0)
        timer.pause(now=10.0)
        timer.configure(25, 5, now=20.0)
        self.assertTrue(timer.paused)
        self.assertEqual(timer.remaining_seconds(now=1000.0), 1500)
        timer.resume(now=1000.0)
        self.assertEqual(timer.remaining_seconds(now=1000.0), 1500)

    def test_skip_while_paused(self):
        timer = FocusTimer(now=0.0)
        timer.pause(now=100.0)
        timer.skip(now=200.0)
        self.assertTrue(timer.paused)
        self.assertIs(timer.phase, Phase.BREAK)
        self.assertEqual(timer.remaining_seconds(now=300.0), 900)

    def test_invalid_durations(self):
        for duration in (0, 241, -1, 1.5, True):
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    FocusTimer(work_minutes=duration)


if __name__ == "__main__":
    unittest.main()
