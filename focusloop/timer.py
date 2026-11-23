"""Clock-independent focus/break timer logic.

Uses monotonic deadlines rather than counting QTimer events, avoiding drift.
"""

from __future__ import annotations

import math
import time
from enum import Enum


class Phase(str, Enum):
    WORK = "work"
    BREAK = "break"


class FocusTimer:
    """Repeat work and break phases until stopped by the application."""

    MIN_MINUTES = 1
    MAX_MINUTES = 240

    def __init__(
        self,
        work_minutes: int = 45,
        break_minutes: int = 15,
        *,
        now: float | None = None,
    ) -> None:
        self._validate(work_minutes, break_minutes)
        self.work_minutes = work_minutes
        self.break_minutes = break_minutes
        self.phase = Phase.WORK
        self.paused = False
        self._remaining = float(self._duration(self.phase))
        self._deadline = self._clock(now) + self._remaining

    @classmethod
    def _validate(cls, work_minutes: int, break_minutes: int) -> None:
        for name, minutes in (("work_minutes", work_minutes), ("break_minutes", break_minutes)):
            if isinstance(minutes, bool) or not isinstance(minutes, int):
                raise ValueError(f"{name} must be an integer")
            if not cls.MIN_MINUTES <= minutes <= cls.MAX_MINUTES:
                raise ValueError(f"{name} must be between {cls.MIN_MINUTES} and {cls.MAX_MINUTES}")

    @staticmethod
    def _clock(now: float | None) -> float:
        return time.monotonic() if now is None else now

    def _duration(self, phase: Phase) -> int:
        return (self.work_minutes if phase is Phase.WORK else self.break_minutes) * 60

    def tick(self, *, now: float | None = None) -> bool:
        """Advance past completed phases. Return True if any phase expired."""
        if self.paused:
            return False
        current = self._clock(now)
        changed = False
        while current >= self._deadline:
            self.phase = Phase.BREAK if self.phase is Phase.WORK else Phase.WORK
            self._deadline += self._duration(self.phase)
            changed = True
        return changed

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
        self.phase = Phase.BREAK if self.phase is Phase.WORK else Phase.WORK
        self._remaining = float(self._duration(self.phase))
        self._deadline = self._clock(now) + self._remaining

    def restart(self, *, now: float | None = None) -> None:
        self._remaining = float(self._duration(self.phase))
        self._deadline = self._clock(now) + self._remaining

    def configure(
        self,
        work_minutes: int,
        break_minutes: int,
        *,
        now: float | None = None,
    ) -> None:
        """Apply durations immediately, restarting the current phase."""
        self._validate(work_minutes, break_minutes)
        self.work_minutes = work_minutes
        self.break_minutes = break_minutes
        self.restart(now=now)
