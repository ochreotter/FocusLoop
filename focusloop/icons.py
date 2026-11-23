"""FocusLoop's scalable Clock icon used by the tray and Windows EXE."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap


def clock_image(size: int = 64) -> QImage:
    """Render a vector-style clock face at any square icon resolution."""
    if size < 8:
        raise ValueError("icon size must be at least 8")

    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setPen(Qt.PenStyle.NoPen)

    # Dark-blue background with rounded corners.
    inset = size * 0.025
    box = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    painter.setBrush(QColor("#253B62"))
    painter.drawRoundedRect(box, size * 0.22, size * 0.22)

    # White clock dial and two hands pointing to twelve and three.
    pen = QPen(QColor("#FFFFFF"))
    pen.setWidthF(max(1.15, size * 0.063))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(size * 0.19, size * 0.19, size * 0.62, size * 0.62))
    center = QPointF(size * 0.5, size * 0.5)
    painter.drawLine(center, QPointF(size * 0.5, size * 0.30))
    painter.drawLine(center, QPointF(size * 0.67, size * 0.5))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#55E6B6"))
    painter.drawEllipse(center, size * 0.055, size * 0.055)
    painter.end()
    return image


def clock_icon() -> QIcon:
    """Return an icon with several source resolutions for sharp tray rendering."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(clock_image(size)))
    return icon
