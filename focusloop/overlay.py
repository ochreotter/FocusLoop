"""Transparent countdown overlay with Simple and Modern presentation modes."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QGuiApplication, QLinearGradient, QPainter, QPen,
)
from PySide6.QtWidgets import QWidget

from .timer import COLOR_HEX, MIN_FONT_SIZE, PhaseConfig

DISPLAY_STYLES = (("Modern", "modern"), ("Simple", "simple"))


def contrasting_outline_color(foreground: QColor) -> QColor:
    """Pick the high-contrast outline by WCAG relative luminance.

    A white foreground receives a dark stroke; a black foreground receives
    a light stroke. All other palette colors are handled automatically.
    """
    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    luminance = (
        0.2126 * linear(foreground.redF())
        + 0.7152 * linear(foreground.greenF())
        + 0.0722 * linear(foreground.blueF())
    )
    # Black wins the WCAG contrast-ratio comparison above this point.
    outline = QColor("#000000" if luminance >= 0.179 else "#FFFFFF")
    outline.setAlpha(205)
    return outline


def draw_outlined_text(
    painter: QPainter, bounds: QRect | QRectF, text: str, foreground: QColor,
) -> None:
    """Draw a subtle one-pixel text outline that respects painter opacity."""
    painter.setPen(contrasting_outline_color(foreground))
    for dx, dy in (
        (-1, -1), (0, -1), (1, -1),
        (-1, 0),           (1, 0),
        (-1, 1),  (0, 1),  (1, 1),
    ):
        painter.drawText(bounds.translated(dx, dy), Qt.AlignmentFlag.AlignCenter, text)
    painter.setPen(foreground)
    painter.drawText(bounds, Qt.AlignmentFlag.AlignCenter, text)


def remaining_arc_angles(remaining_ratio: float) -> tuple[int, int]:
    """Qt angle units: remove progress from 12 o'clock clockwise as time elapses.

    Qt angles are positive counterclockwise and expressed in 1/16 degrees.
    At 75% remaining, 12–3 o'clock is empty and 3–12 is still colored.
    """
    ratio = max(0.0, min(1.0, remaining_ratio))
    elapsed = 1.0 - ratio
    return round((90 - 360 * elapsed) * 16), -round(360 * ratio * 16)


class Overlay(QWidget):
    """Paint a click-through timer; never paint an opaque background panel."""

    def __init__(self, position: str, phase: PhaseConfig, style: str = "modern") -> None:
        super().__init__()
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.clock_text = f"{phase.minutes:02d}:00"
        self.phase_config = phase
        self.position_name = position
        self.display_style = style
        self.remaining_ratio = 1.0
        self.loop_number = 1
        self._render_font_size = phase.font_size
        self._resize_and_reposition()

    def _resize_and_reposition(self) -> None:
        """Fit both modes into the visible screen, including 200pt user settings."""
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        margin = 24
        max_width = max(1, area.width() - margin * 2) if area else None
        max_height = max(1, area.height() - margin * 2) if area else None

        size = self.phase_config.font_size
        while True:
            font = QFont("Consolas", size)
            font.setBold(True)
            fm = QFontMetrics(font)
            if self.display_style == "simple":
                width = fm.horizontalAdvance("000:00") + 30
                height = fm.height() + 26
            else:
                side = max(fm.horizontalAdvance("000:00") + 90, round(fm.height() * 4.2), 184)
                width = height = side
            if (
                size <= MIN_FONT_SIZE
                or max_width is None
                or (width <= max_width and height <= max_height)
            ):
                break
            size -= 1

        self._render_font_size = size
        self.setFixedSize(
            min(width, max_width) if max_width is not None else width,
            min(height, max_height) if max_height is not None else height,
        )
        self.reposition()
        self.update()

    def reposition(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        rect = screen.availableGeometry()
        margin = 24
        if self.position_name == "center":
            x = rect.left() + (rect.width() - self.width()) // 2
            y = rect.top() + (rect.height() - self.height()) // 2
        else:
            is_right = self.position_name.endswith("right")
            is_bottom = self.position_name.startswith("bottom")
            x = rect.right() - self.width() - margin if is_right else rect.left() + margin
            y = rect.bottom() - self.height() - margin if is_bottom else rect.top() + margin
        self.move(QPoint(x, y))

    def set_clock(
        self, text: str, phase: PhaseConfig,
        remaining_ratio: float = 1.0, loop_number: int = 1,
    ) -> None:
        remaining_ratio = max(0.0, min(1.0, remaining_ratio))
        resized = phase.font_size != self.phase_config.font_size
        changed = (
            (text, phase, remaining_ratio, loop_number)
            != (self.clock_text, self.phase_config, self.remaining_ratio, self.loop_number)
        )
        if not changed:
            return
        self.clock_text = text
        self.phase_config = phase
        self.remaining_ratio = remaining_ratio
        self.loop_number = loop_number
        if resized:
            self._resize_and_reposition()
        else:
            self.update()

    def apply_appearance(self, position: str, style: str | None = None) -> None:
        style = self.display_style if style is None else style
        resized = style != self.display_style
        self.position_name = position
        self.display_style = style
        if resized:
            self._resize_and_reposition()
        else:
            self.reposition()
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setOpacity(self.phase_config.opacity / 100)
        if self.display_style == "modern":
            self._paint_modern(painter)
        else:
            self._paint_simple(painter)
        painter.end()

    def _paint_simple(self, painter: QPainter) -> None:
        font = QFont("Consolas", self._render_font_size)
        font.setBold(True)
        painter.setFont(font)
        draw_outlined_text(
            painter, self.rect(), self.clock_text,
            QColor(COLOR_HEX[self.phase_config.color]),
        )

    def _paint_modern(self, painter: QPainter) -> None:
        side = min(self.width(), self.height())
        x = (self.width() - side) / 2
        y = (self.height() - side) / 2
        ring_width = max(6.0, side * 0.032)
        padding = ring_width * 1.5
        arc = QRectF(x + padding, y + padding, side - 2 * padding, side - 2 * padding)

        # Entire widget, including dim track, inherits the phase opacity.
        track = QPen(QColor(138, 155, 177, 55), ring_width)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(arc)

        if self.remaining_ratio > 0:
            if self.phase_config.gradient:
                brush = QLinearGradient(arc.topLeft(), arc.bottomRight())
                brush.setColorAt(0.0, QColor(COLOR_HEX[self.phase_config.color]))
                brush.setColorAt(1.0, QColor(COLOR_HEX[self.phase_config.gradient_end]))
            else:
                brush = QColor(COLOR_HEX[self.phase_config.color])
            progress_pen = QPen(QBrush(brush), ring_width)
            progress_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(progress_pen)
            painter.drawArc(arc, *remaining_arc_angles(self.remaining_ratio))

        loop_font = QFont("Segoe UI")
        loop_font.setPixelSize(max(9, round(side * 0.055)))
        loop_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(1.0, side * 0.004))
        painter.setFont(loop_font)
        loop_rect = QRectF(x + side * 0.18, y + side * 0.27, side * 0.64, side * 0.11)
        draw_outlined_text(
            painter, loop_rect, f"LOOP {self.loop_number:02d}", QColor("#E1E6F0"),
        )

        time_font = QFont("Consolas", self._render_font_size)
        time_font.setBold(True)
        painter.setFont(time_font)
        time_rect = QRectF(x + side * 0.07, y + side * 0.38, side * 0.86, side * 0.25)
        draw_outlined_text(
            painter, time_rect, self.clock_text,
            QColor(COLOR_HEX[self.phase_config.color]),
        )

        badge = QRectF(x + side * 0.30, y + side * 0.66, side * 0.40, side * 0.125)
        badge_color = QColor(COLOR_HEX[self.phase_config.color])
        badge_color.setAlpha(55)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(badge_color)
        painter.drawRoundedRect(badge, badge.height() / 2, badge.height() / 2)
        name_font = QFont("Segoe UI")
        name_font.setPixelSize(max(9, round(side * 0.062)))
        name_font.setBold(True)
        painter.setFont(name_font)
        label = QFontMetrics(name_font).elidedText(
            self.phase_config.name, Qt.TextElideMode.ElideRight, max(1, round(badge.width() - 14))
        )
        draw_outlined_text(painter, badge, label, QColor("#F5F7FC"))
