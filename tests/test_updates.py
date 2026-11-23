"""GitHub updater tests: no network access or Windows installation required."""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from focusloop import updates


def release_json(version="1.0.3", archive=b"zip"):
    return {
        "tag_name": version, "draft": False, "prerelease": False,
        "assets": [{
            "name": updates.ASSET_NAME,
            "browser_download_url": (
                f"https://github.com/ochreotter/FocusLoop/releases/download/"
                f"{version}/{updates.ASSET_NAME}"
            ),
            "size": len(archive),
            "digest": "sha256:" + hashlib.sha256(archive).hexdigest(),
            "state": "uploaded",
        }],
    }


def make_archive(entries=None):
    files = entries or {
        "FocusLoop/FocusLoop.exe": b"exe",
        "FocusLoop/_internal/Qt6Core.dll": b"dll",
        "FocusLoop/LICENSE": b"MIT",
        "FocusLoop/THIRD_PARTY_NOTICES.md": b"LGPL",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return buffer.getvalue()


class ReleaseCheckTests(unittest.TestCase):
    def test_versions_are_numeric_without_v_and_not_downgraded(self):
        self.assertEqual(updates.parse_version("1.0.10"), (1, 0, 10))
        self.assertIsNone(updates.release_from_payload(release_json("1.0.2")))
        self.assertIsNone(updates.release_from_payload(release_json("1.0.0")))
        self.assertIsNone(updates.release_from_payload(release_json("1.0.1")))
        self.assertEqual(updates.release_from_payload(release_json("1.0.3")).version, "1.0.3")
        for invalid in ("v1.0.3", "1.0.3-beta", "1.0", "main", ""):
            with self.subTest(invalid=invalid), self.assertRaises(updates.UpdateError):
                updates.parse_version(invalid)

    def test_release_asset_and_digest_must_be_trustworthy(self):
        sample = release_json()
        sample["assets"][0]["browser_download_url"] = "https://example.com/fake.zip"
        with self.assertRaisesRegex(updates.UpdateError, "URL"):
            updates.release_from_payload(sample)
        sample = release_json()
        sample["assets"][0]["digest"] = ""
        with self.assertRaisesRegex(updates.UpdateError, "SHA-256"):
            updates.release_from_payload(sample)
        sample = release_json()
        sample["assets"] = []
        with self.assertRaisesRegex(updates.UpdateError, "missing"):
            updates.release_from_payload(sample)
        sample = release_json()
        sample["draft"] = True
        with self.assertRaises(updates.UpdateError):
            updates.release_from_payload(sample)

    def test_latest_endpoint_is_queried_and_parsed(self):
        response = io.BytesIO(json.dumps(release_json()).encode())
        with patch.object(updates.urllib.request, "urlopen", return_value=response) as get:
            release = updates.check_latest_release()
        self.assertEqual(release.version, "1.0.3")
        self.assertEqual(get.call_args.args[0].full_url, updates.RELEASES_URL)


class ArchiveSafetyTests(unittest.TestCase):
    def test_valid_bundle_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "release.zip"
            archive.write_bytes(make_archive())
            folder = updates.extract_verified_bundle(archive, Path(temp) / "expanded")
            self.assertEqual((folder / "FocusLoop.exe").read_bytes(), b"exe")
            self.assertEqual((folder / "_internal" / "Qt6Core.dll").read_bytes(), b"dll")

    def test_path_traversal_and_absolute_entries_are_rejected(self):
        for unsafe in (
            "FocusLoop/../outside.txt", "/FocusLoop/evil.txt",
            "FocusLoop/_internal/../../evil.txt",
            "OtherProgram/evil.txt", "FocusLoop/C:\\evil.exe",
        ):
            with self.subTest(unsafe=unsafe), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "unsafe.zip"
                path.write_bytes(make_archive({unsafe: b"bad"}))
                with self.assertRaises(updates.UpdateError):
                    updates.extract_verified_bundle(path, Path(temp) / "out")

    def test_symlinks_and_missing_licenses_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "symlink.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                member = zipfile.ZipInfo("FocusLoop/_internal/Qt6Core.dll")
                member.create_system = 3
                member.external_attr = (stat.S_IFLNK | 0o777) << 16
                zipped.writestr(member, "other.dll")
            with self.assertRaises(updates.UpdateError):
                updates.extract_verified_bundle(archive, Path(temp) / "out")
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "no-license.zip"
            archive.write_bytes(make_archive({
                "FocusLoop/FocusLoop.exe": b"exe",
                "FocusLoop/_internal/Qt6Core.dll": b"dll",
            }))
            with self.assertRaisesRegex(updates.UpdateError, "license"):
                updates.extract_verified_bundle(archive, Path(temp) / "out")


class UpdatePreparationTests(unittest.TestCase):
    def test_prepared_update_is_staged_outside_running_app(self):
        archive = make_archive()
        metadata = release_json(archive=archive)
        release = updates.release_from_payload(metadata)
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "FocusLoop"
            (home / "_internal").mkdir(parents=True)
            executable = home / "FocusLoop.exe"
            executable.write_bytes(b"old exe")
            progress = []
            with (
                patch.object(updates, "can_self_update", return_value=True),
                patch.object(updates.urllib.request, "urlopen", return_value=io.BytesIO(archive)),
            ):
                prepared = updates.prepare_update(
                    release, executable, lambda done, total: progress.append((done, total))
                )
            self.assertEqual(executable.read_bytes(), b"old exe")
            self.assertNotEqual(prepared.staged_dir, home)
            self.assertEqual((prepared.staged_dir / "FocusLoop.exe").read_bytes(), b"exe")
            self.assertTrue(prepared.helper_script.is_file())
            self.assertEqual(progress[-1], (len(archive), len(archive)))
            with (
                patch.object(updates, "can_self_update", return_value=True),
                patch.object(updates.subprocess, "Popen") as launch,
            ):
                updates.launch_updater(prepared)
            args = launch.call_args.args[0]
            self.assertEqual(args[0].lower(), "powershell.exe")
            self.assertIn("-StagedDir", args)
            self.assertIn("-ParentPid", args)
            self.assertEqual(
                launch.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1"
            )
            updates.discard_prepared_update(prepared)
            self.assertFalse(prepared.staged_dir.exists())

    def test_mismatched_digest_fails_before_replacing_files(self):
        archive = make_archive()
        metadata = release_json(archive=archive)
        metadata["assets"][0]["digest"] = "sha256:" + "0" * 64
        release = updates.release_from_payload(metadata)
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "FocusLoop"
            (home / "_internal").mkdir(parents=True)
            exe = home / "FocusLoop.exe"
            exe.write_bytes(b"untouched")
            with (
                patch.object(updates, "can_self_update", return_value=True),
                patch.object(updates.urllib.request, "urlopen", return_value=io.BytesIO(archive)),
            ):
                with self.assertRaisesRegex(updates.UpdateError, "SHA-256"):
                    updates.prepare_update(release, exe)
            self.assertEqual(exe.read_bytes(), b"untouched")
            self.assertEqual(list(Path(temp).glob(".FocusLoop-stage-*")), [])


@unittest.skipUnless(sys.platform == "win32", "Windows helper smoke test only")
class PowerShellRollbackTests(unittest.TestCase):
    def test_failed_new_executable_restores_previous_installation(self):
        """The detached helper must restore old files after a failed restart."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / "FocusLoop"
            staged = root / ".FocusLoop-stage-test"
            old.mkdir()
            staged.mkdir()
            (old / "FocusLoop.exe").write_bytes(b"old executable")
            (staged / "FocusLoop.exe").write_bytes(b"not a valid Windows executable")
            helper = root / "apply.ps1"
            helper.write_text(updates.UPDATER_SCRIPT, encoding="utf-8-sig")
            logfile = root / "updater.log"
            env = os.environ.copy()
            env["FOCUSLOOP_UPDATER_TESTING"] = "1"
            subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass", "-File", str(helper),
                    "-TargetDir", str(old), "-StagedDir", str(staged),
                    "-ParentPid", "99999999", "-LogFile", str(logfile),
                ],
                env=env, check=True, timeout=35,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertEqual((old / "FocusLoop.exe").read_bytes(), b"old executable")
            self.assertIn("Previous installation restored", logfile.read_text())


if __name__ == "__main__":
    unittest.main()
