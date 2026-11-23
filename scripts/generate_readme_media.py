"""Capture real FocusLoop Qt widgets for README screenshots and a short accelerated GIF.

Run on Windows with:
    python -m pip install -r requirements.txt Pillow
    set QT_QPA_PLATFORM=offscreen
    python -m scripts.generate_readme_media

The GIF accelerates the timer deliberately; its timer/ring pixels come from Overlay.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont, QFontDatabase, QImage, QPainter, QRegion
from PySide6.QtWidgets import QApplication, QWidget

from focusloop.app import SettingsDialog
from focusloop.overlay import Overlay
from focusloop.timer import FocusTimer, PhaseConfig, default_phases

OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "assets"


def capture(widget: QWidget) -> Image.Image:
    """Render the actual widget, including translucent paint, to an RGBA image."""
    qt = QImage(widget.size(), QImage.Format.Format_RGBA8888)
    qt.fill(Qt.GlobalColor.transparent)
    painter = QPainter(qt)
    widget.render(
        painter, QPoint(0, 0), QRegion(),
        QWidget.RenderFlag.DrawWindowBackground | QWidget.RenderFlag.DrawChildren,
    )
    painter.end()
    image = Image.frombytes(
        "RGBA", (qt.width(), qt.height()),
        bytes(qt.bits()), "raw", "RGBA", qt.bytesPerLine(),
    )
    if image.getbbox() is None:
        raise RuntimeError(f"Qt captured an empty widget: {type(widget).__name__}")
    return image


def label_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        (r"C:\Windows\Fonts\seguisb.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def desktop_frame(timer_image: Image.Image, stage: str, index: int) -> Image.Image:
    """Composite a real, rendered transparent overlay on a neutral *demo* desktop."""
    w, h = 960, 580
    base = Image.new("RGBA", (w, h), "#111925")
    draw = ImageDraw.Draw(base)
    for y in range(h):
        k = y / (h - 1)
        draw.line((0, y, w, y), fill=(
            round(15 + 9 * k), round(23 + 8 * k), round(39 + 11 * k), 255
        ))
    for x in range(0, w, 60):
        draw.line((x, 0, x, h), fill=(49, 61, 82, 35), width=1)
    for y in range(0, h, 60):
        draw.line((0, y, w, y), fill=(49, 61, 82, 35), width=1)

    draw.rounded_rectangle((30, 25, 930, 555), radius=20, outline=(90, 109, 138, 100), width=2)
    draw.ellipse((54, 47, 65, 58), fill="#ff6b6b")
    draw.ellipse((73, 47, 84, 58), fill="#f6c75c")
    draw.ellipse((92, 47, 103, 58), fill="#5de5b5")
    draw.text((128, 42), "FOCUSLOOP  /  TRANSPARENT TIMER", fill="#e8edf8",
              font=label_font(19, bold=True))
    draw.text((128, 70), "Accelerated timer preview", fill="#9baac3",
              font=label_font(15))
    draw.text((70, 509), "CUSTOMIZABLE  •  ALWAYS ON TOP  •  WORK / BREAK CYCLES",
              fill="#b6c2d6", font=label_font(14))
    draw.text((814, 509), stage, fill="#f7d7b2" if stage == "FOCUS" else "#82e2bb",
              font=label_font(17, bold=True))

    # Center the actual Qt overlay render; all digits, phase labels and circular
    # progress rings here come from FocusLoop's Overlay.paintEvent.
    x = (w - timer_image.width) // 2
    y = (h - timer_image.height) // 2 + 12
    base.alpha_composite(timer_image, (x, y))
    return base.convert("RGB")


def render() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    # The headless Windows Qt platform does not reliably discover system fonts.
    # Register the actual font files so screenshots contain readable glyphs.
    font_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for filename in ("segoeui.ttf", "seguisb.ttf", "consola.ttf", "consolab.ttf"):
        path = font_dir / filename
        if path.is_file():
            font_id = QFontDatabase.addApplicationFont(str(path))
            print(f"Qt font {filename}: {QFontDatabase.applicationFontFamilies(font_id)}")
    app.setFont(QFont("Segoe UI", 10))
    print(f"Qt has Segoe UI: {QFontDatabase.hasFamily('Segoe UI')}")
    print(f"Qt has Consolas: {QFontDatabase.hasFamily('Consolas')}")
    cjk_path = Path(os.environ["FOCUSLOOP_DOCS_CJK_FONT"])
    cjk_id = QFontDatabase.addApplicationFont(str(cjk_path))
    cjk_families = QFontDatabase.applicationFontFamilies(cjk_id)
    if not cjk_families:
        raise RuntimeError(f"Could not register Japanese preview font: {cjk_path}")
    japanese_family = cjk_families[0]
    print(f"Japanese preview font: {japanese_family}")

    english_phases = (
        PhaseConfig("Focus", 45, color="amber", opacity=75, font_size=50,
                    gradient=True, gradient_end="rose", position="bottom_left"),
        PhaseConfig("Break", 15, color="mint", opacity=80, font_size=72,
                    gradient=False, position="center"),
    )
    for filename, phases, language, font_family in (
        ("focusloop-settings-en.png", english_phases, "en", "Segoe UI"),
        ("focusloop-settings-ja.png", default_phases(), "ja", japanese_family),
    ):
        app.setFont(QFont(font_family, 10))
        dialog = SettingsDialog(None, FocusTimer(phases), language)
        dialog.resize(900, 690)
        dialog.show()
        app.processEvents()
        screenshot = capture(dialog).convert("RGB")
        screenshot.save(OUTPUT / filename, optimize=True)
        print(f"Saved {filename}: {screenshot.size}")
        dialog.close()
        app.processEvents()
    app.setFont(QFont("Segoe UI", 10))

    focus = PhaseConfig("FOCUS", 45, color="amber", opacity=100, font_size=40,
                        gradient=True, gradient_end="rose", position="center")
    rest = PhaseConfig("BREAK", 15, color="mint", opacity=100, font_size=40,
                       gradient=False, position="center")
    overlay = Overlay(focus)
    overlay.show()
    app.processEvents()
    frames = []
    for i in range(20):
        if i < 12:
            phase, stage, n = focus, "FOCUS", i
            seconds = round((45 * 60 - 1) * (1 - n / 12))
            progress = (seconds + 1) / (45 * 60)
        else:
            phase, stage, n = rest, "BREAK", i - 12
            seconds = round((15 * 60 - 1) * (1 - n / 8))
            progress = (seconds + 1) / (15 * 60)
        overlay.set_clock(
            f"{seconds // 60:02d}:{seconds % 60:02d}",
            phase, remaining_ratio=progress, loop_number=1,
        )
        app.processEvents()
        frame = desktop_frame(capture(overlay), stage, i)
        frames.append(frame.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
    overlay.close()

    gif_path = OUTPUT / "focusloop-demo.gif"
    frames[0].save(
        gif_path, save_all=True, append_images=frames[1:],
        loop=0, duration=190, optimize=True, disposal=2,
    )
    print(f"Saved {gif_path.name}: {gif_path.stat().st_size:,} bytes")
    for filename in ("focusloop-settings-en.png", "focusloop-settings-ja.png"):
        if (OUTPUT / filename).stat().st_size < 10_000:
            raise RuntimeError(f"{filename} is unexpectedly small")
    if gif_path.stat().st_size < 20_000:
        raise RuntimeError("Animated demo GIF is unexpectedly small")
    print("README media generated successfully")


if __name__ == "__main__":
    render()
