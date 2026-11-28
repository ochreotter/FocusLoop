"""Release workflow and packaging regression tests; no network/Qt required."""

from __future__ import annotations

import os
import hashlib
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import fetch_release_sources, package_windows

ROOT = Path(__file__).resolve().parents[1]


class ReleaseContractTests(unittest.TestCase):
    def test_tag_release_is_draft_and_never_publishes_automatically(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("tags:", workflow)
        self.assertIn("'[0-9]+.[0-9]+.[0-9]+'", workflow)
        self.assertNotIn("'v*'", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("softprops/action-gh-release@v3", workflow)
        self.assertIn("draft: true", workflow)
        self.assertNotIn("draft: false", workflow)
        self.assertIn("fail_on_unmatched_files: true", workflow)
        self.assertIn("dist/FocusLoop-Windows.zip", workflow)
        self.assertIn("python -m scripts.fetch_release_sources", workflow)
        for filename, _, _ in fetch_release_sources.SOURCES:
            self.assertIn(f"dist/{filename}", workflow)
        self.assertIn("pyinstaller --noconfirm --clean --onedir", workflow)
        self.assertNotIn(" --onefile", workflow)

    def test_windows_builds_ship_replaceable_qt_libraries(self):
        for path in (".github/workflows/build.yml", ".github/workflows/release.yml"):
            workflow = (ROOT / path).read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertIn("--onedir", workflow)
                self.assertIn("python -m scripts.package_windows", workflow)
                self.assertNotIn("--onefile", workflow)
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".build/", ignored)
        self.assertTrue((ROOT / "docs/library-replacement.md").is_file())
        self.assertTrue((ROOT / "THIRD_PARTY_NOTICES.md").is_file())
        release_docs = (ROOT / "docs/releasing.md").read_text(encoding="utf-8")
        self.assertIn("対応ソース", release_docs)
        self.assertIn("ドラフトRelease", release_docs)

    def test_source_staging_rejects_altered_tarball(self):
        with tempfile.TemporaryDirectory() as dirname:
            output = Path(dirname)
            archive = output / "release-source.tar.xz"
            archive.write_bytes(b"verified source")
            checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
            fixture = ((archive.name, "https://example.invalid/", checksum),)
            with patch.object(fetch_release_sources, "SOURCES", fixture):
                fetch_release_sources.fetch_all(output)
                manifest = output / "Qt-PySide6-SHA256SUMS.txt"
                self.assertIn(f"{checksum}  {archive.name}", manifest.read_text())
                archive.write_bytes(b"altered source")
                with self.assertRaisesRegex(RuntimeError, "Incorrect SHA-256"):
                    fetch_release_sources.fetch_all(output)

    def test_bundle_audit_refuses_unreviewed_dlls_and_plugins(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            internal = root / "_internal"
            plugin_dir = internal / "PySide6" / "plugins" / "platforminputcontexts"
            plugin_dir.mkdir(parents=True)
            core = internal / "Qt6Core.dll"
            core.touch()
            self.assertEqual(package_windows.audit_qt_bundle(root), [core])
            for discovered in (
                internal / "Qt6VirtualKeyboard.dll",
                plugin_dir / "qtvirtualkeyboardplugin.dll",
                plugin_dir / "UnreviewedPlugin.DLL",
                internal / "Qt6Unknown.dll",
            ):
                discovered.touch()
                with self.subTest(path=discovered), self.assertRaisesRegex(RuntimeError, "Unreviewed"):
                    package_windows.audit_qt_bundle(root)
                discovered.unlink()

    def test_user_guide_has_current_terminology(self):
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        japanese = (ROOT / "README.ja.md").read_text(encoding="utf-8")
        self.assertNotIn("Modern", english)
        self.assertNotIn("Modern", japanese)
        self.assertNotIn("透過率", japanese)
        self.assertNotIn("Working / On Break", japanese)
        self.assertIn("フェーズ名は標準名・独自名を問わず一切翻訳しません", japanese)
        self.assertIn("不透明度", japanese)
        self.assertIn("休憩中", japanese)
        self.assertIn("グラデーション | ON（ローズ） | OFF", japanese)
        self.assertIn("Phase names are never automatically translated", english)
        self.assertIn("opacity", english.lower())
        self.assertIn("[日本語](README.ja.md)", english)
        self.assertIn("[English](README.md)", japanese)
        for readme in (english, japanese):
            self.assertIn("docs/assets/focusloop-demo.gif", readme)
        self.assertIn("docs/assets/focusloop-settings-en.png", english)
        self.assertIn("docs/assets/focusloop-settings-ja.png", japanese)

    def test_windows_zip_includes_dlls_notices_and_dependency_list(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / "docs").mkdir()
            (root / "dist" / "FocusLoop" / "_internal").mkdir(parents=True)
            for path in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
                (root / path).write_text("Test notice", encoding="utf-8")
            (root / "docs" / "library-replacement.md").write_text(
                "DLL replacement", encoding="utf-8"
            )
            bundle = root / "dist" / "FocusLoop"
            (bundle / "FocusLoop.exe").write_bytes(os.urandom(150_000))
            (bundle / "_internal" / "Qt6Core.dll").write_bytes(b"qt")

            qt_module = types.ModuleType("PySide6.QtCore")
            qt_module.qVersion = lambda: package_windows.QT_VERSION
            pyside_module = types.ModuleType("PySide6")
            pyside_module.QtCore = qt_module

            def license_file(_url, path, _marker):
                path.write_text("Test license text", encoding="utf-8")

            def dependency_version(name):
                if name in package_windows.DISALLOWED_PACKAGES:
                    raise package_windows.importlib.metadata.PackageNotFoundError(name)
                return package_windows.QT_VERSION

            with (
                patch.object(package_windows, "ROOT", root),
                patch.object(package_windows, "DIST", root / "dist"),
                patch.object(package_windows, "BUNDLE", bundle),
                patch.object(package_windows.sys, "platform", "win32"),
                patch.object(package_windows, "_retrieve", side_effect=license_file),
                patch.object(package_windows, "_include_installed_licenses"),
                patch.object(
                    package_windows.importlib.metadata, "version",
                    side_effect=dependency_version,
                ),
                patch.dict(sys.modules, {"PySide6": pyside_module, "PySide6.QtCore": qt_module}),
            ):
                output = package_windows.package()

            self.assertTrue(output.is_file())
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                for required in (
                    "FocusLoop/FocusLoop.exe",
                    "FocusLoop/_internal/Qt6Core.dll",
                    "FocusLoop/LICENSE",
                    "FocusLoop/THIRD_PARTY_NOTICES.md",
                    "FocusLoop/LIBRARY_REPLACEMENT.md",
                    "FocusLoop/DEPENDENCIES.txt",
                    "FocusLoop/licenses/LGPL-3.0.txt",
                    "FocusLoop/licenses/GPL-3.0.txt",
                    "FocusLoop/licenses/PYTHON_LICENSE.txt",
                ):
                    with self.subTest(required=required):
                        self.assertIn(required, names)
                deps = archive.read("FocusLoop/DEPENDENCIES.txt").decode("utf-8")
                self.assertIn(f"Qt=={package_windows.QT_VERSION}", deps)
                self.assertIn("qt-everywhere-src-6.12.0.tar.xz", deps)
                self.assertIn("Qt6Core.dll", deps)


if __name__ == "__main__":
    unittest.main()
