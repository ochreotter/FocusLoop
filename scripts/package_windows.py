"""Package a Windows PyInstaller onedir build with notices and license texts.

This creates a release CANDIDATE, not a legal-compliance certificate.
Corresponding Qt/PySide6 source availability is checked before publishing.
"""

from __future__ import annotations

import importlib.metadata
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUNDLE = DIST / "FocusLoop"
DEPENDENCIES = ("PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6")
LICENSE_URLS = {
    "LGPL-3.0.txt": "https://www.gnu.org/licenses/lgpl-3.0.txt",
    "GPL-3.0.txt": "https://www.gnu.org/licenses/gpl-3.0.txt",
}
MINIMUM_LICENSE_SIZE = 4000


def _retrieve(url: str, path: Path, marker: bytes) -> None:
    """Fail the build rather than publish missing license terms."""
    with urllib.request.urlopen(url, timeout=60) as response:
        content = response.read()
    if len(content) < MINIMUM_LICENSE_SIZE or marker not in content:
        raise RuntimeError(f"Unexpected license response at {url}")
    path.write_bytes(content)


def _include_installed_licenses(target: Path, package: str) -> None:
    """Copy any license files supplied by the installed Python wheel."""
    try:
        dist = importlib.metadata.distribution(package)
    except importlib.metadata.PackageNotFoundError:
        return
    for entry in dist.files or ():
        normalized = str(entry).replace("\\", "/").lower()
        if not (".dist-info/licenses/" in normalized or normalized.endswith(
            (".dist-info/license", ".dist-info/license.txt", ".dist-info/copying")
        )):
            continue
        origin = Path(dist.locate_file(entry))
        if not origin.is_file():
            continue
        dest = target / "wheel-licenses" / package / origin.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, dest)


def package() -> Path:
    if sys.platform != "win32":
        raise RuntimeError("The distributable Windows package must be built on Windows")
    if not (BUNDLE / "FocusLoop.exe").is_file() or not (BUNDLE / "_internal").is_dir():
        raise RuntimeError("Missing PyInstaller onedir output; do not package onefile")
    dlls = sorted(BUNDLE.rglob("Qt6Core.dll"))
    if not dlls:
        raise RuntimeError("Qt6Core.dll was not collected as a separate replaceable DLL")

    licenses = BUNDLE / "licenses"
    licenses.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "LICENSE", BUNDLE / "LICENSE")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", BUNDLE / "THIRD_PARTY_NOTICES.md")
    shutil.copy2(ROOT / "docs" / "library-replacement.md", BUNDLE / "LIBRARY_REPLACEMENT.md")

    for name, url in LICENSE_URLS.items():
        _retrieve(url, licenses / name, b"GNU ")

    python_license = Path(sys.executable).parent / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, licenses / "PYTHON_LICENSE.txt")
    else:
        _retrieve(
            "https://raw.githubusercontent.com/python/cpython/3.12/LICENSE",
            licenses / "PYTHON_LICENSE.txt",
            b"PYTHON SOFTWARE FOUNDATION",
        )

    for package_name in DEPENDENCIES:
        _include_installed_licenses(licenses, package_name)

    versions = [f"Python=={sys.version.split()[0]}"]
    for package_name in (*DEPENDENCIES, "pyinstaller"):
        try:
            version = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            continue
        versions.append(f"{package_name}=={version}")
    try:
        from PySide6.QtCore import qVersion
        versions.append(f"Qt=={qVersion()}")
    except ImportError as exc:
        raise RuntimeError("Qt version is not available for release inventory") from exc

    versions.extend(("", "Bundled Qt6 DLLs:"))
    versions.extend(str(p.relative_to(BUNDLE)).replace("\\", "/") for p in dlls)
    (BUNDLE / "DEPENDENCIES.txt").write_text(
        "\n".join(versions) + "\n", encoding="utf-8"
    )

    output = DIST / "FocusLoop-Windows.zip"
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(BUNDLE.rglob("*")):
            if path.is_file():
                archive.write(path, (Path("FocusLoop") / path.relative_to(BUNDLE)).as_posix())
    if output.stat().st_size < 100_000:
        raise RuntimeError("Unexpectedly small release package")
    print(f"Created release candidate: {output} ({output.stat().st_size:,} bytes)")
    return output


if __name__ == "__main__":
    package()
