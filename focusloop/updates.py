"""GitHub Releases updater for the Windows PyInstaller onedir distribution.

Only published, strictly numeric tags and checksum-verified FocusLoop-Windows.zip
assets are eligible. Never replace the files of a running executable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

VERSION = "1.0.0"
RELEASES_URL = "https://api.github.com/repos/ochreotter/FocusLoop/releases/latest"
RELEASES_PAGE = "https://github.com/ochreotter/FocusLoop/releases"
ASSET_NAME = "FocusLoop-Windows.zip"
MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024
MAX_UNPACKED_BYTES = 1024 * 1024 * 1024
MAX_MEMBERS = 6000
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
DIGEST_PATTERN = re.compile(r"sha256:([0-9a-fA-F]{64})\Z")


class UpdateError(Exception):
    """An update cannot be verified, staged, or installed safely."""


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    digest: str
    size: int


@dataclass(frozen=True)
class PreparedUpdate:
    install_dir: Path
    staged_dir: Path
    helper_script: Path


def parse_version(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not VERSION_PATTERN.fullmatch(value):
        raise UpdateError("Unsupported release version (expected 1.2.3 without v)")
    return tuple(int(piece) for piece in value.split("."))


def release_from_payload(payload: dict, current: str = VERSION) -> Release | None:
    """Return a newer release, or None when the installed version is current."""
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        raise UpdateError("No stable release information was returned")
    version = payload.get("tag_name")
    latest = parse_version(version)
    if latest <= parse_version(current):
        return None

    for asset in payload.get("assets", []):
        if not isinstance(asset, dict) or asset.get("name") != ASSET_NAME:
            continue
        digest_match = DIGEST_PATTERN.fullmatch(str(asset.get("digest", "")))
        expected_url = (
            f"https://github.com/ochreotter/FocusLoop/releases/download/"
            f"{version}/{ASSET_NAME}"
        )
        if asset.get("browser_download_url") != expected_url:
            raise UpdateError("The Windows release asset URL is unexpected")
        if not digest_match:
            raise UpdateError("This release has no verifiable SHA-256 digest")
        size = asset.get("size")
        if type(size) is not int or not 0 < size <= MAX_DOWNLOAD_BYTES:
            raise UpdateError("The release archive has an invalid size")
        if asset.get("state") not in (None, "uploaded"):
            raise UpdateError("The release archive has not finished uploading")
        return Release(version, expected_url, digest_match.group(1).lower(), size)
    raise UpdateError(f"{ASSET_NAME} is missing from the latest stable release")


def check_latest_release(current: str = VERSION) -> Release | None:
    """Query the public GitHub API without using a token."""
    request = urllib.request.Request(
        RELEASES_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"FocusLoop/{VERSION} (Windows updater)",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content = response.read(1_000_001)
    except (OSError, TimeoutError) as exc:
        raise UpdateError(f"Could not contact GitHub Releases: {exc}") from exc
    if len(content) > 1_000_000:
        raise UpdateError("Unexpectedly large GitHub API response")
    try:
        payload = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise UpdateError("GitHub sent invalid release metadata") from exc
    return release_from_payload(payload, current)


def can_self_update() -> bool:
    """Source checkouts and non-Windows builds should never overwrite themselves."""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def _download(release: Release, target: Path, progress: Callable[[int, int], None] | None) -> None:
    request = urllib.request.Request(
        release.url, headers={"User-Agent": f"FocusLoop/{VERSION}"}
    )
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, target.open("xb") as handle:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                if size > MAX_DOWNLOAD_BYTES or size > release.size:
                    raise UpdateError("Release download exceeded its expected size")
                handle.write(block)
                digest.update(block)
                if progress:
                    progress(size, release.size)
    except (OSError, TimeoutError) as exc:
        raise UpdateError(f"Could not download the Windows update: {exc}") from exc
    if size != release.size or digest.hexdigest() != release.digest:
        raise UpdateError("Release size or SHA-256 verification failed")


def extract_verified_bundle(archive: Path, output: Path) -> Path:
    """Reject path traversal, symlinks, malformed ZIPs and decompression bombs."""
    bundle = output / "FocusLoop"
    total = 0
    try:
        with zipfile.ZipFile(archive) as zipped:
            members = zipped.infolist()
            if not members or len(members) > MAX_MEMBERS:
                raise UpdateError("Invalid number of ZIP entries")
            for entry in members:
                name = entry.filename
                path = PurePosixPath(name)
                parts = path.parts
                if (
                    not parts or parts[0] != "FocusLoop"
                    or any(part in (".", "..") or ":" in part for part in parts)
                    or name.startswith("/") or "\\" in name
                    or stat.S_ISLNK(entry.external_attr >> 16)
                ):
                    raise UpdateError("Unsafe path in Windows release archive")
                if entry.is_dir():
                    continue
                total += entry.file_size
                if total > MAX_UNPACKED_BYTES:
                    raise UpdateError("Windows release archive is too large")
                destination = output.joinpath(*parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    raise UpdateError("Duplicate path in Windows release archive")
                with zipped.open(entry) as source, destination.open("xb") as handle:
                    shutil.copyfileobj(source, handle, length=1024 * 1024)
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise UpdateError(f"Could not unpack the release archive: {exc}") from exc
    if not (bundle / "FocusLoop.exe").is_file() or not (bundle / "_internal").is_dir():
        raise UpdateError("Release archive does not contain a Windows onedir build")
    if not list(bundle.rglob("Qt6Core.dll")):
        raise UpdateError("Qt runtime is missing from the release archive")
    if not (bundle / "LICENSE").is_file() or not (bundle / "THIRD_PARTY_NOTICES.md").is_file():
        raise UpdateError("Required release license notices are missing")
    return bundle


# The script runs OUTSIDE the installed folder, after FocusLoop has exited.
# Renames happen on the same volume. A failed restart restores the old bundle.
UPDATER_SCRIPT = r"""
param(
    [Parameter(Mandatory=$true)][string]$TargetDir,
    [Parameter(Mandatory=$true)][string]$StagedDir,
    [Parameter(Mandatory=$true)][int]$ParentPid,
    [Parameter(Mandatory=$true)][string]$LogFile
)
$ErrorActionPreference = 'Stop'
function Write-UpdateLog([string]$Message) {
    try { Add-Content -LiteralPath $LogFile -Value "$(Get-Date -Format o) $Message" } catch {}
}
$parent = Split-Path -Parent $TargetDir
$name = Split-Path -Leaf $TargetDir
$backup = Join-Path $parent ('.FocusLoop-backup-' + [guid]::NewGuid().ToString('N'))
$renamed = $false
$installed = $false
try {
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        if (-not (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 500
    }
    if (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) {
        throw 'FocusLoop did not exit within 60 seconds'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $StagedDir 'FocusLoop.exe'))) {
        throw 'The prepared update has disappeared'
    }
    Rename-Item -LiteralPath $TargetDir -NewName (Split-Path -Leaf $backup)
    $renamed = $true
    Rename-Item -LiteralPath $StagedDir -NewName $name
    $installed = $true
    $exe = Join-Path $TargetDir 'FocusLoop.exe'
    $newProcess = Start-Process -FilePath $exe -WorkingDirectory $TargetDir -PassThru
    Start-Sleep -Seconds 5
    $newProcess.Refresh()
    if ($newProcess.HasExited) { throw 'Updated FocusLoop exited immediately' }
    Write-UpdateLog 'Update installed and new process started'
    try {
        Remove-Item -LiteralPath $backup -Recurse -Force
    } catch {
        Write-UpdateLog "Old bundle retained for manual cleanup: $backup"
    }
}
catch {
    Write-UpdateLog "Update failed: $_"
    if ($renamed) {
        try {
            if ($installed -and (Test-Path -LiteralPath $TargetDir)) {
                $failed = Join-Path $parent ('.FocusLoop-failed-' + [guid]::NewGuid().ToString('N'))
                Rename-Item -LiteralPath $TargetDir -NewName (Split-Path -Leaf $failed)
            }
            Rename-Item -LiteralPath $backup -NewName $name
            Write-UpdateLog 'Previous installation restored'
            try {
                Start-Process -FilePath (Join-Path $TargetDir 'FocusLoop.exe') -WorkingDirectory $TargetDir
            } catch {
                Write-UpdateLog "Previous version restored but could not be restarted: $_"
            }
        }
        catch { Write-UpdateLog "Rollback failed: $_ (backup: $backup)" }
    }
    if ($env:FOCUSLOOP_UPDATER_TESTING -ne '1') {
        try {
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.MessageBox]::Show(
                "FocusLoop update failed. See: $LogFile",
                'FocusLoop Update', 'OK', 'Error'
            ) | Out-Null
        } catch {}
    }
}
"""


def prepare_update(
    release: Release,
    executable: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> PreparedUpdate:
    """Download, validate, and stage alongside the installation before quitting."""
    if not can_self_update():
        raise UpdateError("Automatic replacement works only in the packaged Windows EXE")
    exe = Path(executable or sys.executable).absolute()
    install_dir = exe.parent
    if exe.name.lower() != "focusloop.exe" or not (install_dir / "_internal").is_dir():
        raise UpdateError("The running program is not a FocusLoop onedir installation")
    if install_dir.is_symlink():
        raise UpdateError("Updating through a directory symlink is not supported")
    stage = install_dir.parent / (".FocusLoop-stage-" + uuid.uuid4().hex)
    try:
        with tempfile.TemporaryDirectory(prefix="FocusLoop-download-") as temp:
            download = Path(temp) / ASSET_NAME
            _download(release, download, progress)
            bundle = extract_verified_bundle(download, Path(temp) / "unpacked")
            # By using a sibling directory the helper can atomically rename it.
            shutil.copytree(bundle, stage)
        helper_dir = Path(tempfile.mkdtemp(prefix="FocusLoop-updater-"))
        helper = helper_dir / "apply.ps1"
        helper.write_text(UPDATER_SCRIPT, encoding="utf-8-sig")
        return PreparedUpdate(install_dir, stage, helper)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise


def discard_prepared_update(prepared: PreparedUpdate) -> None:
    if prepared.staged_dir.exists():
        shutil.rmtree(prepared.staged_dir, ignore_errors=True)
    if prepared.helper_script.parent.exists():
        shutil.rmtree(prepared.helper_script.parent, ignore_errors=True)


def launch_updater(prepared: PreparedUpdate) -> None:
    """Launch a detached Windows helper; call QApplication.quit immediately after."""
    if not can_self_update() or not prepared.staged_dir.is_dir():
        raise UpdateError("Windows update is not staged correctly")
    log = prepared.helper_script.parent / "updater.log"
    env = os.environ.copy()
    # The new frozen executable is an independent process, not a PyInstaller
    # subprocess of the old bootloader whose bundle path is about to vanish.
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    # PyInstaller sets a process-local DLL lookup path on Windows. Restore the
    # system lookup path while starting PowerShell, then put it back for Qt.
    bundle_dir = getattr(sys, "_MEIPASS", None)
    kernel32 = None
    if bundle_dir:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
        kernel32.SetDllDirectoryW.restype = ctypes.c_bool
        if not kernel32.SetDllDirectoryW(None):
            raise UpdateError("Could not restore the system DLL search path")
    try:
        try:
            subprocess.Popen(
                [
                    "powershell.exe", "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass",
                    "-File", str(prepared.helper_script),
                    "-TargetDir", str(prepared.install_dir),
                    "-StagedDir", str(prepared.staged_dir),
                    "-ParentPid", str(os.getpid()),
                    "-LogFile", str(log),
                ],
                env=env,
                cwd=str(prepared.helper_script.parent),
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise UpdateError(f"Could not start the Windows update helper: {exc}") from exc
    finally:
        if kernel32 is not None:
            kernel32.SetDllDirectoryW(str(bundle_dir))
