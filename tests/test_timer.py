"""Dependency-free tests for scheduling and phase serialization."""

import unittest

from focusloop.timer import (
    FocusTimer,
    PhaseConfig,
    default_phases,
    phases_from_json,
    phases_to_json,
)


class TimerTests(unittest.TestCase):
    def test_defaults_and_transition(self):
        timer = FocusTimer(now=10.0)
        self.assertEqual([phase.minutes for phase in timer.phases], [45, 15])
        self.assertEqual(timer.remaining_seconds(now=10.0), 2700)
        self.assertFalse(timer.tick(now=2709.99))
        self.assertTrue(timer.tick(now=2710.0))
        self.assertEqual(timer.current_phase.name, "休憩")
        self.assertEqual(timer.remaining_seconds(now=2710.0), 900)
        self.assertTrue(timer.tick(now=3610.0))
        self.assertEqual(timer.current_phase.name, "作業")

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
        self.assertTrue(timer.tick(now=3605))
        self.assertEqual(timer.current_phase.name, "作業")
        self.assertEqual(timer.remaining_seconds(now=3605), 2695)

    def test_large_time_jump_skips_whole_cycles(self):
        timer = FocusTimer(now=0.0)
        current = 3600 * 100000 + 2701
        self.assertTrue(timer.tick(now=current))
        self.assertEqual(timer.current_phase.name, "休憩")
        self.assertEqual(timer.remaining_seconds(now=current), 899)

    def test_three_phases_loop_in_order(self):
        phases = (
            PhaseConfig("集中", 2, "rose", 95),
            PhaseConfig("水分補給", 1, "sky", 60),
            PhaseConfig("休憩", 3, "mint", 100),
        )
        timer = FocusTimer(phases, now=0.0)
        self.assertEqual(timer.current_phase.name, "集中")
        timer.tick(now=120)
        self.assertEqual(timer.current_phase.name, "水分補給")
        timer.tick(now=180)
        self.assertEqual(timer.current_phase.name, "休憩")
        timer.tick(now=360)
        self.assertEqual(timer.current_phase.name, "集中")

    def test_configure_sequence_restarts_from_first(self):
        timer = FocusTimer(now=0.0)
        timer.skip(now=10)
        timer.configure((
            PhaseConfig("深い集中", 50, "sky", 80),
            PhaseConfig("休憩", 10, "mint", 90),
        ), now=20)
        self.assertEqual(timer.phase_index, 0)
        self.assertEqual(timer.remaining_seconds(now=20), 3000)

    def test_appearance_only_changes_preserve_countdown(self):
        timer = FocusTimer(now=0.0)
        replacement = (
            PhaseConfig("作業", 45, "violet", 35),
            PhaseConfig("休憩", 15, "amber", 70),
        )
        timer.configure(replacement, now=200.0)
        self.assertEqual(timer.current_phase.color, "violet")
        self.assertEqual(timer.current_phase.opacity, 35)
        self.assertEqual(timer.remaining_seconds(now=200), 2500)
        timer.skip(now=250)
        self.assertEqual(timer.current_phase.color, "amber")

    def test_name_change_preserves_running_countdown(self):
        timer = FocusTimer(now=0)
        renamed = (
            PhaseConfig("集中中", 45, "white", 90),
            PhaseConfig("リラックス", 15, "mint", 80),
        )
        timer.configure(renamed, now=25)
        self.assertEqual(timer.phase_index, 0)
        self.assertEqual(timer.remaining_seconds(now=25), 2675)
        self.assertEqual(timer.current_phase.name, "集中中")

    def test_forced_reorder_restarts_even_if_durations_match(self):
        phases = (PhaseConfig("集中", 5), PhaseConfig("休憩", 5, "mint"))
        timer = FocusTimer(phases, now=0)
        timer.skip(now=10)
        timer.configure(phases[::-1], force_restart=True, now=20)
        self.assertEqual(timer.phase_index, 0)
        self.assertEqual(timer.current_phase.name, "休憩")
        self.assertEqual(timer.remaining_seconds(now=20), 300)

    def test_configure_while_paused_stays_paused(self):
        timer = FocusTimer(now=0.0)
        timer.pause(now=10.0)
        timer.configure(
            (PhaseConfig("集中", 25), PhaseConfig("休憩", 5)), now=20
        )
        self.assertTrue(timer.paused)
        self.assertEqual(timer.remaining_seconds(now=1000), 1500)
        timer.resume(now=1000)
        self.assertEqual(timer.remaining_seconds(now=1000), 1500)

    def test_skip_while_paused(self):
        timer = FocusTimer(now=0.0)
        timer.pause(now=100)
        timer.skip(now=200)
        self.assertTrue(timer.paused)
        self.assertEqual(timer.current_phase.name, "休憩")
        self.assertEqual(timer.remaining_seconds(now=300), 900)

    def test_single_phase_repeats(self):
        timer = FocusTimer((PhaseConfig("集中", 1),), now=0)
        self.assertTrue(timer.tick(now=61))
        self.assertEqual(timer.current_phase.name, "集中")
        self.assertEqual(timer.remaining_seconds(now=61), 59)

    def test_invalid_settings(self):
        for duration in (0, 241, -1, 1.5, True):
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    PhaseConfig("作業", duration)
        for opacity in (-1, 101, 2.5, True):
            with self.subTest(opacity=opacity):
                with self.assertRaises(ValueError):
                    PhaseConfig("作業", 10, opacity=opacity)
        for color in ("red", "#FF0000", ""):
            with self.subTest(color=color):
                with self.assertRaises(ValueError):
                    PhaseConfig("作業", 10, color=color)
        with self.assertRaises(ValueError):
            PhaseConfig("", 10)
        with self.assertRaises(ValueError):
            FocusTimer((), now=0)

    def test_serialization_round_trip(self):
        phases = (
            PhaseConfig("Work", 50, "white", 0),
            PhaseConfig("Tea", 5, "amber", 45),
            PhaseConfig("Rest", 10, "rose", 100),
        )
        self.assertEqual(phases_from_json(phases_to_json(phases)), phases)

    def test_legacy_settings_and_corrupt_json_fallback(self):
        legacy = default_phases(50, 10)
        for raw in (
            None, "", "not json", "[]", "{}", "[42]", '[{"name":"x"}]'
        ):
            with self.subTest(raw=raw):
                self.assertEqual(
                    phases_from_json(raw, legacy_work=50, legacy_break=10),
                    legacy,
                )

    def test_phase_reorder_is_applied(self):
        phases = (
            PhaseConfig("休憩", 5, "mint", 70),
            PhaseConfig("作業", 45, "white", 100),
        )
        timer = FocusTimer(phases, now=0)
        self.assertEqual(timer.current_phase.name, "休憩")
        self.assertEqual(timer.remaining_seconds(now=0), 300)
        timer.skip(now=10)
        self.assertEqual(timer.current_phase.name, "作業")


if __name__ == "__main__":
    unittest.main()
