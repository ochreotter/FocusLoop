"""Clock-independent multi-phase timer and settings serialization.

Monotonic deadlines avoid accumulating QTimer interval drift.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from typing import Sequence

# (identifier, user-facing name, hexadecimal text color)
COLOR_PRESETS = (
    ("white", "ホワイト", "#F5F7FC"),
    ("mint", "ミント", "#55E6B6"),
    ("sky", "スカイブルー", "#69C7FF"),
    ("amber", "アンバー", "#FFC36B"),
    ("rose", "ローズ", "#FF8CAB"),
    ("violet", "バイオレット", "#C9A7FF"),
)

COLOR_HEX = {key: hex_value for key, _, hex_value in COLOR_PRESETS}
MIN_MINUTES = 1
MAX_MINUTES = 240


@dataclass(frozen=True)
class PhaseConfig:
    name: str
    minutes: int
    color: str = "white"
    opacity: int = 100

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not 1 <= len(self.name.strip()) <= 40:
            raise ValueError("phase name must be between 1 and 40 characters")
        if type(self.minutes) is not int or not MIN_MINUTES <= self.minutes <= MAX_MINUTES:
            raise ValueError(f"minutes must be between {MIN_MINUTES} and {MAX_MINUTES}")
        if self.color not in COLOR_HEX:
            raise ValueError("unknown phase color")
        if type(self.opacity) is not int or not 0 <= self.opacity <= 100:
            raise ValueError("opacity must be between 0 and 100")


def default_phases(work_minutes: int = 45, break_minutes: int = 15) -> tuple[PhaseConfig, ...]:
    """Construct the default pair, optionally retaining old time settings."""
    return (
        PhaseConfig("作業", work_minutes, "white", 100),
        PhaseConfig("休憩", break_minutes, "mint", 100),
    )


def phases_to_json(phases: Sequence[PhaseConfig]) -> str:
    validated = validate_phases(phases)
    return json.dumps([asdict(phase) for phase in validated], ensure_ascii=False)


def phases_from_json(
    value: object,
    *,
    legacy_work: int = 45,
    legacy_break: int = 15,
) -> tuple[PhaseConfig, ...]:
    """Read new settings; fall back to the old pair if empty or invalid."""
    fallback = default_phases(legacy_work, legacy_break)
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
    ) -> None:
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

        while current >= self._deadline:
            self.phase_index = (self.phase_index + 1) % len(self.phases)
            self._deadline += self.current_phase.minutes * 60
        return True

    def remaining_seconds(self, *, now: float | None = None) -> int:
        if self.paused:
            return max(0, math.ceil(self._remaining))
        return max(0, math.ceil(self._deadline - self._clock(now)))

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
        self.restart(now=now)

    def restart(self, *, now: float | None = None) -> None:
        self._remaining = float(self.current_phase.minutes * 60)
        self._deadline = self._clock(now) + self._remaining

    def configure(self, phases: Sequence[PhaseConfig], *, now: float | None = None) -> None:
        """Preserve countdown for color/opacity changes, reset for sequence changes."""
        new_phases = validate_phases(phases)
        sequence_changed = [
            (phase.name, phase.minutes) for phase in self.phases
        ] != [
            (phase.name, phase.minutes) for phase in new_phases
        ]
        self.phases = new_phases
        if sequence_changed:
            self.phase_index = 0
            self.restart(now=now)
