"""Release workflow and packaging regression tests; no network/Qt required."""

from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import package_windows

ROOT = Path(__file__).resolve().parents[1]


class ReleaseContractTests(unittest.TestCase):
    def test_tag_release_is_draft_and_never_publishes_automatically(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("tags:", workflow)
        self.assertIn("'v*'", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("softprops/action-gh-release@v3", workflow)
        self.assertIn("draft: true", workflow)
        self.assertNotIn("draft: false", workflow)
        self.assertIn("fail_on_unmatched_files: true", workflow)
        self.assertIn("dist/FocusLoop-Windows.zip", workflow)
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

    def test_user_guide_has_current_terminology(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("Modern", readme)
        self.assertNotIn("透過率", readme)
        self.assertNotIn("Working / On Break", readme)
        self.assertIn("フェーズ名は標準名・独自名を問わず一切翻訳しません", readme)
        self.assertIn("不透明度", readme)
        self.assertIn("休憩中", readme)
        self.assertIn("グラデーション | ON（ローズ） | OFF", readme)

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
            qt_module.qVersion = lambda: "6.10.1"
            pyside_module = types.ModuleType("PySide6")
            pyside_module.QtCore = qt_module

            def license_file(_url, path, _marker):
                path.write_text("Test license text", encoding="utf-8")

            with (
                patch.object(package_windows, "ROOT", root),
                patch.object(package_windows, "DIST", root / "dist"),
                patch.object(package_windows, "BUNDLE", bundle),
                patch.object(package_windows.sys, "platform", "win32"),
                patch.object(package_windows, "_retrieve", side_effect=license_file),
                patch.object(package_windows, "_include_installed_licenses"),
                patch.object(package_windows.importlib.metadata, "version", return_value="6.10.1"),
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
                self.assertIn("Qt==6.10.1", deps)
                self.assertIn("Qt6Core.dll", deps)


if __name__ == "__main__":
    unittest.main()
