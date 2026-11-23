"""Build a multi-resolution Windows .ico from the same Clock artwork as the tray.

Run from the repository root:
    python -m scripts.generate_icon
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

# GitHub Actions Windows runners have no visible desktop.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QGuiApplication

from focusloop.icons import clock_image


def png_bytes(size: int) -> bytes:
    picture = clock_image(size)
    data = QByteArray()
    buffer = QBuffer(data)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Could not open buffer for PNG output")
    if not picture.save(buffer, "PNG"):
        raise RuntimeError(f"Could not encode {size}x{size} PNG icon")
    buffer.close()
    return bytes(data)


def build_ico(path: Path) -> None:
    images = [(size, png_bytes(size)) for size in (16, 24, 32, 48, 64, 128, 256)]
    offset = 6 + 16 * len(images)
    entries = []
    frames = []
    for size, payload in images:
        wh = 0 if size == 256 else size
        # Modern Windows .ico supports PNG-compressed images.
        entries.append(struct.pack("<BBBBHHII", wh, wh, 0, 0, 1, 32, len(payload), offset))
        frames.append(payload)
        offset += len(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + b"".join(entries) + b"".join(frames))


def main() -> None:
    app = QGuiApplication([])
    destination = Path(".build") / "FocusLoop.ico"
    build_ico(destination)
    print(f"Generated {destination} ({destination.stat().st_size} bytes)")
    app.quit()


if __name__ == "__main__":
    main()
