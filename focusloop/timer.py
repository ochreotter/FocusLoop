"""Clock-independent multi-phase timer and settings serialization.

Monotonic deadlines avoid accumulating QTimer interval drift.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, replace
from typing import Sequence

# (identifier, user-facing name, hexadecimal text color)
COLOR_PRESETS = (
    ("white", "ホワイト", "#F5F7FC"),
    ("black", "ブラック", "#000000"),
    ("mint", "ミント", "#55E6B6"),
    ("sky", "スカイブルー", "#69C7FF"),
    ("amber", "アンバー", "#FFC36B"),
    ("rose", "ローズ", "#FF8CAB"),
    ("violet", "バイオレット", "#C9A7FF"),
)

COLOR_HEX = {key: hex_value for key, _, hex_value in COLOR_PRESETS}
MIN_MINUTES = 1
MAX_MINUTES = 240
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 300
DEFAULT_FONT_SIZE = 42
POSITION_VALUES = ("bottom_left", "bottom_right", "top_left", "top_right", "center")


@dataclass(frozen=True)
class PhaseConfig:
    name: str
    minutes: int
    color: str = "white"
    opacity: int = 100
    font_size: int = DEFAULT_FONT_SIZE
    gradient: bool = True
    gradient_end: str = "violet"
    simple: bool = False
    position: str = "bottom_left"
    topmost: bool = True
    hidden: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not 1 <= len(self.name.strip()) <= 40:
            raise ValueError("phase name must be between 1 and 40 characters")
        if type(self.minutes) is not int or not MIN_MINUTES <= self.minutes <= MAX_MINUTES:
            raise ValueError(f"minutes must be between {MIN_MINUTES} and {MAX_MINUTES}")
        if self.color not in COLOR_HEX:
            raise ValueError("unknown phase color")
        if type(self.opacity) is not int or not 0 <= self.opacity <= 100:
            raise ValueError("opacity must be between 0 and 100")
        if type(self.font_size) is not int or not MIN_FONT_SIZE <= self.font_size <= MAX_FONT_SIZE:
            raise ValueError(f"font_size must be between {MIN_FONT_SIZE} and {MAX_FONT_SIZE}")
        if type(self.gradient) is not bool:
            raise ValueError("gradient must be a boolean")
        if self.gradient_end not in COLOR_HEX:
            raise ValueError("unknown gradient end color")
        if type(self.simple) is not bool:
            raise ValueError("simple must be a boolean")
        if self.position not in POSITION_VALUES:
            raise ValueError("unknown phase position")
        if type(self.topmost) is not bool:
            raise ValueError("topmost must be a boolean")
        if type(self.hidden) is not bool:
            raise ValueError("hidden must be a boolean")


def default_phases(
    work_minutes: int = 45,
    break_minutes: int = 15,
    font_size: int | None = None,
) -> tuple[PhaseConfig, ...]:
    """Build the screenshot defaults, while honoring an explicit legacy font size."""
    return (
        PhaseConfig(
            "作業中", work_minutes, color="amber", opacity=30,
            font_size=50 if font_size is None else font_size,
            gradient_end="rose", position="bottom_left",
        ),
        PhaseConfig(
            "休憩中", break_minutes, color="mint", opacity=20,
            font_size=300 if font_size is None else font_size,
            gradient_end="white", position="center",
        ),
    )


def phases_to_json(phases: Sequence[PhaseConfig]) -> str:
    validated = validate_phases(phases)
    return json.dumps([asdict(phase) for phase in validated], ensure_ascii=False)


def phases_from_json(
    value: object,
    *,
    legacy_work: int = 45,
    legacy_break: int = 15,
    legacy_font_size: int | None = None,
    legacy_position: str = "bottom_left",
    legacy_simple: bool = False,
) -> tuple[PhaseConfig, ...]:
    """Migrate old global style/position to each phase when not yet stored there."""
    fallback = tuple(
        replace(p, simple=legacy_simple, position=legacy_position)
        for p in default_phases(legacy_work, legacy_break, legacy_font_size)
    )
    if not isinstance(value, str) or not value:
        return fallback
    try:
        rows = json.loads(value)
        if not isinstance(rows, list) or not rows:
            return fallback
        return validate_phases(
            [
                PhaseConfig(
                    name=row["name"],
                    minutes=row["minutes"],
                    color=row["color"],
                    opacity=row["opacity"],
                    font_size=row.get("font_size", DEFAULT_FONT_SIZE if legacy_font_size is None else legacy_font_size),
                    gradient=row.get("gradient", True),
                    gradient_end=row.get("gradient_end", "violet"),
                    simple=row.get("simple", legacy_simple),
                    position=row.get("position", legacy_position),
                    topmost=row.get("topmost", True),
                    hidden=row.get("hidden", False),
                )
                for row in rows
            ]
        )
    except (ValueError, TypeError, KeyError):
        return fallback


def validate_phases(phases: Sequence[PhaseConfig]) -> tuple[PhaseConfig, ...]:
    result = tuple(phases)
    if not result or any(not isinstance(phase, PhaseConfig) for phase in result):
        raise ValueError("at least one valid phase is required")
    return result


class FocusTimer:
    """Repeat an arbitrary ordered set of phases until the app exits."""

    def __init__(
        self,
        phases: Sequence[PhaseConfig] | None = None,
        *,
        now: float | None = None,
        initial_loop: int = 1,
    ) -> None:
        if type(initial_loop) is not int or initial_loop < 1:
            raise ValueError("initial_loop must be a positive integer")
        self.loop_number = initial_loop
        self.phases = validate_phases(phases if phases is not None else default_phases())
        self.phase_index = 0
        self.paused = False
        self._remaining = float(self.current_phase.minutes * 60)
        self._deadline = self._clock(now) + self._remaining

    @property
    def current_phase(self) -> PhaseConfig:
        return self.phases[self.phase_index]

    @staticmethod
    def _clock(now: float | None) -> float:
        return time.monotonic() if now is None else now

    def tick(self, *, now: float | None = None) -> bool:
        """Advance finished phases, including time elapsed during sleep."""
        if self.paused:
            return False
        current = self._clock(now)
        if current < self._deadline:
            return False

        # Skip complete cycles without a potentially huge per-phase loop.
        cycle_seconds = sum(phase.minutes * 60 for phase in self.phases)
        complete_cycles = math.floor((current - self._deadline) / cycle_seconds)
        if complete_cycles > 0:
            self._deadline += complete_cycles * cycle_seconds
            self.loop_number += complete_cycles

        while current >= self._deadline:
            self.phase_index = (self.phase_index + 1) % len(self.phases)
            if self.phase_index == 0:
                self.loop_number += 1
            self._deadline += self.current_phase.minutes * 60
        return True

    def remaining_seconds(self, *, now: float | None = None) -> int:
        if self.paused:
            return max(0, math.ceil(self._remaining))
        return max(0, math.ceil(self._deadline - self._clock(now)))

    def remaining_ratio(self, *, now: float | None = None) -> float:
        """Precise monotonic progress for the ring; unaffected by Qt timer drift."""
        remaining = (
            self._remaining if self.paused
            else self._deadline - self._clock(now)
        )
        duration = self.current_phase.minutes * 60
        return max(0.0, min(1.0, remaining / duration))


    def pause(self, *, now: float | None = None) -> None:
        if self.paused:
            return
        current = self._clock(now)
        self.tick(now=current)
        self._remaining = max(0.0, self._deadline - current)
        self.paused = True

    def resume(self, *, now: float | None = None) -> None:
        if not self.paused:
            return
        self._deadline = self._clock(now) + self._remaining
        self.paused = False

    def toggle_pause(self, *, now: float | None = None) -> None:
        if self.paused:
            self.resume(now=now)
        else:
            self.pause(now=now)

    def skip(self, *, now: float | None = None) -> None:
        self.phase_index = (self.phase_index + 1) % len(self.phases)
        if self.phase_index == 0:
            self.loop_number += 1
        self.restart(now=now)

    def reset_loop_count(self) -> None:
        """Reset the loop counter without changing the active phase or deadline."""
        self.loop_number = 1

    def restart(self, *, now: float | None = None) -> None:
        self._remaining = float(self.current_phase.minutes * 60)
        self._deadline = self._clock(now) + self._remaining

    def configure(
        self,
        phases: Sequence[PhaseConfig],
        *,
        now: float | None = None,
        force_restart: bool = False,
    ) -> None:
        """Keep time when only display properties (including font size) or names change.

        A duration/count change or explicit reorder restarts the cycle.
        """
        new_phases = validate_phases(phases)
        timing_changed = [phase.minutes for phase in self.phases] != [
            phase.minutes for phase in new_phases
        ]
        self.phases = new_phases
        if timing_changed or force_restart:
            self.phase_index = 0
            self.restart(now=now)
