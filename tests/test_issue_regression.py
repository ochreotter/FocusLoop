"""Issue-numbered regression contracts for the portable timer and CI workflows.

These run on Linux without importing Qt. GUI contracts live in tests/ui.
"""

from dataclasses import replace
import json
from pathlib import Path
import unittest

from focusloop.timer import (
    COLOR_HEX, COLOR_PRESETS, DEFAULT_FONT_SIZE, FocusTimer, PhaseConfig,
    default_phases, phases_from_json, phases_to_json,
)


ROOT = Path(__file__).resolve().parents[1]


class IssueContractTests(unittest.TestCase):
    def test_05_default_cycle_and_monotonic_deadlines(self):
        timer = FocusTimer(now=0.0)
        self.assertEqual([(p.name, p.minutes) for p in timer.phases],
                         [("作業", 45), ("休憩", 15)])
        self.assertEqual(timer.remaining_seconds(now=120.0), 2580)
        self.assertTrue(timer.tick(now=2700.0))
        self.assertEqual(timer.current_phase.name, "休憩")
        self.assertEqual(timer.remaining_seconds(now=2700.0), 900)
        self.assertTrue(timer.tick(now=3600.0))
        self.assertEqual(timer.current_phase.name, "作業")
        self.assertEqual(timer.loop_number, 2)

        timer.pause(now=3700.0)
        frozen = timer.remaining_seconds(now=9000.0)
        self.assertEqual(frozen, 2600)
        timer.resume(now=9000.0)
        self.assertEqual(timer.remaining_seconds(now=9000.0), frozen)
        timer.skip(now=9001.0)
        self.assertEqual(timer.current_phase.name, "休憩")
        timer.restart(now=9002.0)
        self.assertEqual(timer.remaining_seconds(now=9002.0), 900)

    def test_07_10_15_21_appearance_only_and_reorder_contract(self):
        phases = default_phases()
        timer = FocusTimer(phases, now=0.0)
        replacement = replace(
            phases[0], name="編集", color="black", opacity=0,
            font_size=200, gradient=False, gradient_end="white",
        )
        timer.configure((replacement, phases[1]), now=100.0)
        self.assertEqual(timer.remaining_seconds(now=100.0), 2600)
        self.assertEqual(timer.phase_index, 0)
        self.assertEqual(timer.current_phase, replacement)
        self.assertEqual(phases_from_json(phases_to_json(timer.phases)), timer.phases)

        # A drag/reorder restarts even when the durations are the same.
        timer.configure(tuple(reversed(timer.phases)), now=100.0, force_restart=True)
        self.assertEqual(timer.current_phase.name, "休憩")
        self.assertEqual(timer.remaining_seconds(now=100.0), 900)
        self.assertEqual(timer.phases[1].font_size, 200)

        with self.assertRaises(ValueError):
            PhaseConfig("a", 45, font_size=7)
        with self.assertRaises(ValueError):
            PhaseConfig("a", 45, font_size=201)
        with self.assertRaises(ValueError):
            PhaseConfig("a" * 41, 45)
        with self.assertRaises(ValueError):
            PhaseConfig("a", 241)
        with self.assertRaises(ValueError):
            PhaseConfig("a", 0)

    def test_08_19_25_latest_palette_gradient_and_transparency(self):
        self.assertEqual(len(COLOR_PRESETS), 7)
        self.assertEqual(COLOR_HEX["black"], "#000000")
        self.assertEqual(len(set(COLOR_HEX.values())), 7)
        for main in COLOR_HEX:
            for secondary in COLOR_HEX:
                phase = PhaseConfig(
                    "作業", 45, color=main, opacity=0,
                    font_size=8, gradient=True, gradient_end=secondary,
                )
                self.assertEqual(phases_from_json(phases_to_json((phase,))), (phase,))
        for opacity in (0, 42, 100):
            self.assertEqual(PhaseConfig("X", 1, opacity=opacity).opacity, opacity)
        with self.assertRaises(ValueError):
            PhaseConfig("X", 1, opacity=101)

    def test_43_44_old_global_display_fields_migrate_per_phase(self):
        legacy = json.dumps([
            {"name": "従来", "minutes": 12, "color": "rose", "opacity": 100}
        ])
        restored = phases_from_json(
            legacy, legacy_position="top_right", legacy_simple=True,
        )
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].position, "top_right")
        self.assertTrue(restored[0].simple)
        self.assertTrue(restored[0].topmost)
        updated = replace(restored[0], position="center", simple=False, topmost=False)
        roundtrip = phases_from_json(phases_to_json((updated,)), legacy_position="top_left",
                                     legacy_simple=True)
        self.assertEqual(roundtrip, (updated,))
        for invalid in ({"simple": 1}, {"position": "outside"}, {"topmost": "yes"}):
            data = {
                "name": "invalid", "minutes": 5, "color": "white", "opacity": 100,
                **invalid,
            }
            self.assertEqual(phases_from_json(json.dumps([data])), default_phases())

    def test_10_15_19_legacy_settings_and_invalid_fallback(self):
        old = json.dumps([{
            "name": "旧作業", "minutes": 18, "color": "sky", "opacity": 45,
        }])
        restored = phases_from_json(old, legacy_font_size=90)
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].font_size, 90)
        self.assertTrue(restored[0].gradient)
        self.assertEqual(restored[0].gradient_end, "violet")
        self.assertEqual(
            phases_from_json("{broken", legacy_work=20, legacy_break=9,
                             legacy_font_size=55),
            default_phases(20, 9, 55),
        )

    def test_18_late_sleep_skip_and_loop_reset_do_not_touch_remaining(self):
        timer = FocusTimer(now=0.0)
        self.assertTrue(timer.tick(now=37 * 3600 + 2700))
        self.assertEqual(timer.loop_number, 38)
        self.assertEqual(timer.current_phase.name, "休憩")
        before = timer.remaining_seconds(now=37 * 3600 + 2710)
        timer.reset_loop_count()
        self.assertEqual(timer.loop_number, 1)
        self.assertEqual(timer.remaining_seconds(now=37 * 3600 + 2710), before)
        timer.skip(now=37 * 3600 + 2711)
        self.assertEqual(timer.loop_number, 2)

    def test_12_13_34_node24_build_and_windows_icon_contract(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        build = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        for workflow in (ci, build):
            self.assertIn("actions/checkout@v7", workflow)
            self.assertIn("actions/setup-python@v7", workflow)
            self.assertIn("python-version: '3.12'", workflow)
            self.assertNotIn("actions/checkout@v4", workflow)
            self.assertNotIn("actions/setup-python@v5", workflow)
            self.assertNotIn("node20", workflow.lower())
        self.assertIn("pull_request:", ci)
        self.assertIn("runs-on: ubuntu-latest", ci)
        self.assertIn("runs-on: windows-latest", ci)
        self.assertIn("python -m unittest discover -s tests/ui -v", ci)
        self.assertIn("QT_QPA_PLATFORM: offscreen", ci)
        self.assertIn("actions/upload-artifact@v7", build)
        self.assertIn("FocusLoop-Windows", build)
        self.assertIn("--icon .build/FocusLoop.ico", build)
        self.assertIn("python -m scripts.generate_icon", build)
        self.assertIn("python -m unittest discover -s tests -v", build)


if __name__ == "__main__":
    unittest.main()
