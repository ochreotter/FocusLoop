"""Dependency-free tests for scheduling and phase serialization."""

import json
import unittest

from focusloop.timer import (
    COLOR_HEX,
    COLOR_PRESETS,
    FocusTimer,
    PhaseConfig,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    default_phases,
    phases_from_json,
    phases_to_json,
)


class TimerTests(unittest.TestCase):
    def test_image_defaults_are_exact_and_round_trip(self):
        phases = default_phases()
        self.assertEqual(
            phases,
            (
                PhaseConfig(
                    "作業中", 45, color="amber", opacity=30, font_size=50,
                    gradient=True, gradient_end="rose", simple=False,
                    position="bottom_left", topmost=True, hidden=False,
                ),
                PhaseConfig(
                    "休憩中", 15, color="mint", opacity=20, font_size=300,
                    gradient=False, gradient_end="white", simple=False,
                    position="center", topmost=True, hidden=False,
                ),
            ),
        )
        self.assertEqual(phases_from_json(phases_to_json(phases)), phases)
        self.assertEqual(FocusTimer(now=0.0).phases, phases)

    def test_legacy_fonts_are_not_overwritten_by_per_phase_defaults(self):
        legacy = default_phases(20, 10, 72)
        self.assertEqual([p.minutes for p in legacy], [20, 10])
        self.assertEqual([p.font_size for p in legacy], [72, 72])
        restored = phases_from_json(
            None, legacy_work=20, legacy_break=10, legacy_font_size=72,
        )
        self.assertEqual(restored, legacy)

        # Existing old JSON that has no per-phase font still gets the old 42pt.
        old = json.dumps([{
            "name": "以前の作業", "minutes": 33,
            "color": "sky", "opacity": 70,
        }])
        self.assertEqual(phases_from_json(old)[0].font_size, 42)

    def test_defaults_and_transition(self):
        timer = FocusTimer(now=10.0)
        self.assertEqual([phase.minutes for phase in timer.phases], [45, 15])
        self.assertEqual(timer.remaining_seconds(now=10.0), 2700)
        self.assertFalse(timer.tick(now=2709.99))
        self.assertTrue(timer.tick(now=2710.0))
        self.assertEqual(timer.current_phase.name, "休憩中")
        self.assertEqual(timer.remaining_seconds(now=2710.0), 900)
        self.assertTrue(timer.tick(now=3610.0))
        self.assertEqual(timer.current_phase.name, "作業中")

    def test_fractional_remaining_ratio_is_monotonic_and_pause_safe(self):
        timer = FocusTimer((PhaseConfig("作業", 1), PhaseConfig("休憩", 2)), now=0.0)
        self.assertEqual(timer.remaining_ratio(now=0.0), 1.0)
        self.assertAlmostEqual(timer.remaining_ratio(now=0.033), 59.967 / 60.0)
        self.assertEqual(timer.remaining_seconds(now=0.033), 60)
        self.assertAlmostEqual(timer.remaining_ratio(now=30.25), 29.75 / 60.0)
        self.assertEqual(timer.remaining_ratio(now=61.0), 0.0)
        timer.pause(now=30.25)
        frozen_ratio = timer.remaining_ratio(now=30.25)
        self.assertAlmostEqual(frozen_ratio, 29.75 / 60.0)
        self.assertEqual(timer.remaining_ratio(now=10000.0), frozen_ratio)
        timer.resume(now=1000.0)
        self.assertAlmostEqual(timer.remaining_ratio(now=1000.0), frozen_ratio)
        self.assertLess(timer.remaining_ratio(now=1000.033), frozen_ratio)
        timer.skip(now=1001.0)
        self.assertEqual(timer.current_phase.name, "休憩")
        self.assertEqual(timer.remaining_ratio(now=1001.0), 1.0)
        timer.restart(now=1002.0)
        self.assertEqual(timer.remaining_ratio(now=1002.0), 1.0)

    def test_remaining_display_does_not_exceed_phase_duration(self):
        timer = FocusTimer(now=100.0)
        self.assertEqual(timer.remaining_seconds(now=99.9999), 2700)
        timer.skip(now=500.0)
        self.assertEqual(timer.current_phase.name, "休憩中")
        self.assertEqual(timer.remaining_seconds(now=499.9999), 900)
        timer.pause(now=499.9999)
        self.assertEqual(timer.remaining_seconds(now=2000.0), 900)

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
        self.assertEqual(timer.current_phase.name, "作業中")
        self.assertEqual(timer.remaining_seconds(now=3605), 2695)

    def test_large_time_jump_skips_whole_cycles(self):
        timer = FocusTimer(now=0.0)
        current = 3600 * 100000 + 2701
        self.assertTrue(timer.tick(now=current))
        self.assertEqual(timer.current_phase.name, "休憩中")
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
        self.assertEqual(timer.current_phase.name, "休憩中")
        self.assertEqual(timer.remaining_seconds(now=300), 900)

    def test_single_phase_repeats(self):
        timer = FocusTimer((PhaseConfig("集中", 1),), now=0)
        self.assertTrue(timer.tick(now=61))
        self.assertEqual(timer.current_phase.name, "集中")
        self.assertEqual(timer.remaining_seconds(now=61), 59)

    def test_font_sizes_are_independent_and_not_timer_affecting(self):
        timer = FocusTimer(now=0)
        phases = (
            PhaseConfig("作業", 45, "white", 100, 8),
            PhaseConfig("休憩", 15, "mint", 80, 200),
        )
        timer.configure(phases, now=60)
        self.assertEqual(timer.current_phase.font_size, 8)
        self.assertEqual(timer.remaining_seconds(now=60), 2640)
        timer.skip(now=80)
        self.assertEqual(timer.current_phase.font_size, 200)
        self.assertEqual(timer.remaining_seconds(now=80), 900)

    def test_hidden_flag_defaults_to_visible_and_round_trips(self):
        visible = PhaseConfig("作業", 45)
        hidden = PhaseConfig("休憩", 15, hidden=True)
        self.assertFalse(visible.hidden)
        self.assertTrue(hidden.hidden)
        saved = phases_to_json((visible, hidden))
        self.assertEqual(phases_from_json(saved), (visible, hidden))
        self.assertIn('"hidden": true', saved)
        self.assertIn('"hidden": false', saved)

        old = json.dumps([{
            "name": "以前の休憩", "minutes": 5, "color": "mint",
            "opacity": 100,
        }])
        self.assertFalse(phases_from_json(old)[0].hidden)
        with self.assertRaises(ValueError):
            PhaseConfig("作業", 45, hidden="true")
        with self.assertRaises(ValueError):
            PhaseConfig("作業", 45, hidden=1)
        self.assertEqual(
            phases_from_json(saved.replace('"hidden": true', '"hidden": "yes"')),
            default_phases(),
        )

    def test_hidden_is_presentation_only_and_does_not_reset_timer(self):
        timer = FocusTimer(now=0.0)
        phases = (
            PhaseConfig("作業", 45, hidden=True),
            PhaseConfig("休憩", 15, hidden=False),
        )
        timer.configure(phases, now=125.0)
        self.assertEqual(timer.remaining_seconds(now=125.0), 2575)
        self.assertTrue(timer.current_phase.hidden)
        timer.skip(now=130.0)
        self.assertFalse(timer.current_phase.hidden)
        self.assertEqual(timer.remaining_seconds(now=130.0), 900)
        timer.pause(now=140.0)
        self.assertEqual(timer.remaining_seconds(now=999.0), 890)

    def test_old_json_phases_migrate_legacy_font_size(self):
        old = [
            {"name": "作業", "minutes": 45, "color": "white", "opacity": 100},
            {"name": "休憩", "minutes": 15, "color": "mint", "opacity": 90},
        ]
        migrated = phases_from_json(json.dumps(old), legacy_font_size=72)
        self.assertEqual([x.font_size for x in migrated], [72, 72])
        self.assertEqual([x.minutes for x in migrated], [45, 15])
        saved = phases_from_json(phases_to_json(migrated))
        self.assertEqual(saved, migrated)

    def test_legacy_pair_migrates_font_size(self):
        fallback = phases_from_json(None, legacy_work=40, legacy_break=10,
                                    legacy_font_size=80)
        self.assertEqual([x.font_size for x in fallback], [80, 80])

    def test_font_size_bounds(self):
        self.assertEqual((MIN_FONT_SIZE, MAX_FONT_SIZE), (8, 300))
        for size in (7, 301, True, 2.5):
            with self.subTest(size=size), self.assertRaises(ValueError):
                PhaseConfig("作業", 45, font_size=size)
        for size in (8, 200, 300):
            self.assertEqual(PhaseConfig("作業", 45, font_size=size).font_size, size)

    def test_loop_count_increments_on_wrap_and_skipping(self):
        timer = FocusTimer(now=0.0)
        self.assertEqual(timer.loop_number, 1)
        timer.tick(now=2700)
        self.assertEqual(timer.loop_number, 1)
        timer.tick(now=3600)
        self.assertEqual(timer.loop_number, 2)
        timer.skip(now=3601)
        self.assertEqual(timer.loop_number, 2)
        timer.skip(now=3602)
        self.assertEqual(timer.loop_number, 3)

    def test_loop_count_catches_up_after_large_sleep(self):
        timer = FocusTimer(now=0.0)
        timer.tick(now=3600 * 5 + 2701)
        self.assertEqual(timer.current_phase.name, "休憩中")
        self.assertEqual(timer.loop_number, 6)

    def test_previous_from_first_wraps_and_decrements_loop_without_underflow(self):
        timer = FocusTimer((
            PhaseConfig("Work", 1),
            PhaseConfig("Break", 2),
            PhaseConfig("Rest", 3),
        ), now=0.0, initial_loop=5)
        self.assertEqual(timer.loop_number, 5)
        timer.previous(now=10.0)
        self.assertEqual(timer.phase_index, 2)
        self.assertEqual(timer.loop_number, 4)
        self.assertEqual(timer.remaining_seconds(now=10.0), 180)
        self.assertEqual(timer.remaining_seconds(now=40.0), 150)

        timer.skip(now=50.0)
        self.assertEqual(timer.phase_index, 0)
        self.assertEqual(timer.loop_number, 5)
        self.assertEqual(timer.remaining_seconds(now=50.0), 60)
        timer.skip(now=60.0)
        self.assertEqual(timer.phase_index, 1)
        timer.previous(now=75.0)
        self.assertEqual(timer.phase_index, 0)
        self.assertEqual(timer.loop_number, 5)
        self.assertEqual(timer.remaining_seconds(now=75.0), 60)

        timer.reset_loop_count()
        timer.previous(now=80.0)
        self.assertEqual(timer.phase_index, 2)
        self.assertEqual(timer.loop_number, 1)
        self.assertEqual(timer.remaining_seconds(now=80.0), 180)

    def test_previous_while_paused_and_single_phase(self):
        timer = FocusTimer(now=0.0, initial_loop=3)
        timer.pause(now=15.0)
        self.assertTrue(timer.paused)
        timer.previous(now=100.0)
        self.assertEqual(timer.phase_index, 1)
        self.assertEqual(timer.loop_number, 2)
        self.assertTrue(timer.paused)
        self.assertEqual(timer.remaining_seconds(now=10000.0), 900)
        timer.resume(now=200.0)
        self.assertEqual(timer.remaining_seconds(now=220.0), 880)

        one = FocusTimer((PhaseConfig("Solo", 2),), now=0.0, initial_loop=2)
        one.previous(now=40.0)
        self.assertEqual(one.phase_index, 0)
        self.assertEqual(one.loop_number, 1)
        self.assertEqual(one.remaining_seconds(now=40.0), 120)
        one.previous(now=50.0)
        self.assertEqual(one.loop_number, 1)

    def test_reset_loop_count_does_not_restart_running_timer(self):
        timer = FocusTimer(initial_loop=12, now=0.0)
        deadline = timer._deadline
        timer.reset_loop_count()
        self.assertEqual(timer.loop_number, 1)
        self.assertEqual(timer._deadline, deadline)
        self.assertEqual(timer.remaining_seconds(now=30), 2670)
        timer.skip(now=35)
        self.assertEqual(timer.loop_number, 1)

    def test_gradient_settings_roundtrip_and_old_fallback(self):
        gradient_phase = PhaseConfig(
            "作業", 45, "sky", 55, 100, True, "violet"
        )
        solid_phase = PhaseConfig(
            "休憩", 15, "mint", 85, 48, False, "amber"
        )
        self.assertEqual(
            phases_from_json(phases_to_json((gradient_phase, solid_phase))),
            (gradient_phase, solid_phase),
        )
        old = json.dumps([
            {"name": "作業", "minutes": 45, "color": "white",
             "opacity": 100, "font_size": 42}
        ])
        migrated = phases_from_json(old)
        self.assertTrue(migrated[0].gradient)
        self.assertEqual(migrated[0].gradient_end, "violet")

    def test_black_palette_works_as_main_and_secondary_color(self):
        self.assertEqual(COLOR_HEX["black"], "#000000")
        self.assertIn(("black", "ブラック", "#000000"), COLOR_PRESETS)
        self.assertEqual(len(COLOR_PRESETS), 7)
        phase = PhaseConfig("作業", 45, color="black", gradient_end="black")
        self.assertEqual(phases_from_json(phases_to_json((phase,))), (phase,))
        self.assertEqual(
            phases_from_json(phases_to_json((phase,)))[0].gradient_end,
            "black",
        )

    def test_invalid_gradient_settings(self):
        for kwargs in ({"gradient": "true"}, {"gradient_end": "invalid"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PhaseConfig("作業", 45, **kwargs)
        for initial in (0, -1, True):
            with self.subTest(initial=initial), self.assertRaises(ValueError):
                FocusTimer(initial_loop=initial, now=0)

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
