"""Stage the pinned upstream Qt and PySide/Shiboken source for Release assets."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import urllib.request

VERSION = "6.12.0"
SOURCES = (
    (
        f"qt-everywhere-src-{VERSION}.tar.xz",
        f"https://download.qt.io/archive/qt/6.12/{VERSION}/single/",
        "98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165",
    ),
    (
        f"pyside-setup-everywhere-src-{VERSION}.tar.xz",
        f"https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-{VERSION}-src/",
        "099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751",
    ),
)


def verify(path: Path, expected: str) -> None:
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise RuntimeError(f"Incorrect SHA-256 for {path.name}: {actual}")


def fetch_all(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, base_url, expected in SOURCES:
        path = directory / name
        if path.is_file():
            verify(path, expected)
            continue
        partial = path.with_name(name + ".part")
        try:
            with urllib.request.urlopen(base_url + name, timeout=90) as response, partial.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            verify(partial, expected)
            os.replace(partial, path)
        finally:
            partial.unlink(missing_ok=True)
    (directory / "Qt-PySide6-SHA256SUMS.txt").write_text(
        "".join(f"{digest}  {name}\n" for name, _, digest in SOURCES),
        encoding="ascii",
    )


if __name__ == "__main__":
    fetch_all(Path("dist"))
