#!/usr/bin/env python3
"""Time Capsule -- install the emulators the capsule drives.

One cross-platform entry point for every host Time Capsule supports:

    Linux   (x86_64 / aarch64)          Windows (x86_64 / ARM64)

It obtains

    Wine      for ``type: "wine"`` entries    -- Windows 95/98/XP software, with
                real GPU support (wined3d/DXVK translate to host OpenGL/Vulkan)
    DOSBox-X  for ``type: "dosbox"`` entries  -- DOS titles, incl. 3dfx Voodoo

by trying, in order: the host's own package manager, a distribution-neutral
installer (Flatpak / winget / portable ZIP), and finally printed instructions.
Nothing is installed without the command being printed first, and the run ends
with the same verification as ``python launcher.py check``.

Usage
-----
    python scripts/setup.py                  install whatever is missing
    python scripts/setup.py --check          report only, change nothing
    python scripts/setup.py --dry-run        print the plan, change nothing
    python scripts/setup.py --only dosbox    one emulator only
    python scripts/setup.py --apply          also repoint manifest.json
    python scripts/setup.py --portable       Windows: portable ZIPs, no admin
    python scripts/setup.py --no-hangover    aarch64 Linux: no big download
    python scripts/setup.py --wsl            Windows: Wine inside WSL2
    python scripts/setup.py --verbose        show every probe and command
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from timecapsule import emulators  # noqa: E402  (needs ROOT on sys.path)
from timecapsule.manifest import ManifestError, load_manifest  # noqa: E402

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
WINGET_DOSBOX_ID = "joncampbell123.DOSBox-X"
FLATPAK_DOSBOX_ID = "com.dosbox_x.DOSBox-X"
FLATPAK_WINE_ID = "org.winehq.Wine"
FLATHUB_REMOTE_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
DOSBOX_REPO = "joncampbell123/dosbox-x"
HANGOVER_REPO = "AndreRH/hangover"
GITHUB_LATEST = "https://api.github.com/repos/{repo}/releases/latest"

WINEHQ_URL = "https://wiki.winehq.org/Download"
DOSBOX_URL = "https://dosbox-x.com/"
DOSBOX_BUILD_URL = "https://dosbox-x.com/wiki/Guide%3ABuilding_DOSBox-X"
HANGOVER_URL = "https://github.com/AndreRH/hangover"
BOX64_URL = "https://github.com/ptitSeb/box64"

SHIM_PATH = ROOT / "tools" / "bin" / "wine.cmd"
PORTABLE_DIR = ROOT / "tools" / "dosbox-x"

SUPPORTED = "Linux or Windows, on x86_64 or ARM64"


class UnsupportedHost(Exception):
    """The machine is not one of the hosts this project supports."""


# --------------------------------------------------------------------------- #
# Console helpers
# --------------------------------------------------------------------------- #
COLOR = False
VERBOSE = False


def _paint(code: str, text: str) -> str:
    return f"\x1b[{code}m{text}\x1b[0m" if COLOR else text


def enable_ansi() -> bool:
    """True when the terminal can render ANSI colours."""
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    try:  # Windows consoles need virtual terminal processing switched on.
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def info(message: str) -> None:
    print(f"{_paint('36', '[setup]')} {message}")


def step(message: str) -> None:
    print(f"{_paint('36', '    ->')} {message}")


def detail(message: str) -> None:
    print(f"       {_paint('2', message)}")


def good(message: str) -> None:
    print(f"{_paint('32', '[  ok ]')} {message}")


def warn(message: str) -> None:
    print(f"{_paint('33', '[warn ]')} {message}")


def bad(message: str) -> None:
    print(f"{_paint('31', '[fail ]')} {message}", file=sys.stderr)


def heading(message: str) -> None:
    print(f"\n{_paint('1', message)}")


def show_command(argv: Sequence[str]) -> None:
    detail("$ " + " ".join(str(part) for part in argv))


# --------------------------------------------------------------------------- #
# Running commands
# --------------------------------------------------------------------------- #
@dataclass
class Command:
    """An external command, plus whether it needs privileges to run."""

    argv: List[str]
    root: bool = False
    cwd: Optional[Path] = None


class Runner:
    """Runs commands, adding ``sudo`` and honouring ``--dry-run``."""

    def __init__(self, target: "Target", *, dry_run: bool) -> None:
        self.target = target
        self.dry_run = dry_run
        self.sudo = self._detect_sudo()

    def _detect_sudo(self) -> Optional[List[str]]:
        if not self.target.is_linux:
            return None
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return []
        sudo = shutil.which("sudo")
        return [sudo] if sudo else None

    def prepare(self, command: Command) -> Optional[List[str]]:
        argv = list(command.argv)
        if command.root and self.target.is_linux:
            if self.sudo is None:
                return None
            argv = self.sudo + argv
        return argv

    def run(
        self, command: Command, *, capture: bool = False
    ) -> Optional[subprocess.CompletedProcess]:
        """Run *command*; ``None`` means it could not be started at all."""
        argv = self.prepare(command)
        if argv is None:
            warn(f"'{command.argv[0]}' needs root, but sudo is not available")
            return None
        if not capture:
            show_command(argv)
        try:
            return subprocess.run(
                argv,
                cwd=str(command.cwd) if command.cwd else None,
                text=True,
                capture_output=capture,
                check=False,
            )
        except OSError as exc:
            detail(f"{command.argv[0]}: {exc}")
            return None

    def probe(self, argv: Sequence[str], cwd: Optional[Path] = None) -> Tuple[bool, str]:
        """Run a read-only command; returns ``(succeeded, combined output)``."""
        if VERBOSE:
            show_command(list(argv))
        result = self.run(Command(list(argv), cwd=cwd), capture=True)
        if result is None:
            return False, ""
        return result.returncode == 0, (result.stdout or "") + (result.stderr or "")

    def install(
        self, argv: Sequence[str], *, root: bool = False, cwd: Optional[Path] = None
    ) -> bool:
        """Run an installing command; ``True`` when it succeeded."""
        if self.dry_run:
            show_command((self.sudo if root and self.sudo else []) + list(argv))
            detail("dry run: not executed")
            return False
        result = self.run(Command(list(argv), root=root, cwd=cwd))
        return bool(result is not None and result.returncode == 0)


# --------------------------------------------------------------------------- #
# What are we running on?
# --------------------------------------------------------------------------- #
def _windows_native_arch() -> str:
    """Ask Windows itself, so emulated (x64-on-ARM64) Python cannot mislead us."""

    class SYSTEM_INFO(ctypes.Structure):
        _fields_ = [
            ("wProcessorArchitecture", ctypes.c_uint16),
            ("wReserved", ctypes.c_uint16),
            ("dwPageSize", ctypes.c_uint32),
            ("lpMinimumApplicationAddress", ctypes.c_void_p),
            ("lpMaximumApplicationAddress", ctypes.c_void_p),
            ("dwActiveProcessorMask", ctypes.c_void_p),
            ("dwNumberOfProcessors", ctypes.c_uint32),
            ("dwProcessorType", ctypes.c_uint32),
            ("dwAllocationGranularity", ctypes.c_uint32),
            ("wProcessorLevel", ctypes.c_uint16),
            ("wProcessorRevision", ctypes.c_uint16),
        ]

    try:
        info_struct = SYSTEM_INFO()
        ctypes.windll.kernel32.GetNativeSystemInfo(ctypes.byref(info_struct))  # type: ignore[attr-defined]
        return {12: "aarch64", 9: "x86_64", 0: "x86_64"}.get(
            info_struct.wProcessorArchitecture, ""
        )
    except Exception:
        return ""


def _read_os_release() -> Dict[str, str]:
    for candidate in ("/etc/os-release", "/usr/lib/os-release"):
        path = Path(candidate)
        if not path.is_file():
            continue
        values: Dict[str, str] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values
    return {}


@dataclass(frozen=True)
class Target:
    """The host we are setting up: OS, CPU architecture and distribution."""

    system: str  # "linux" | "windows"
    arch: str  # "x86_64" | "aarch64"
    distro: str = ""  # "debian", "ubuntu", "fedora", "arch", ...
    codename: str = ""  # "noble", "bookworm", ...
    version: str = ""
    release: str = ""  # free-form, for the banner

    @property
    def is_linux(self) -> bool:
        return self.system == "linux"

    @property
    def is_windows(self) -> bool:
        return self.system == "windows"

    @property
    def is_arm(self) -> bool:
        return self.arch == "aarch64"

    @property
    def deblike(self) -> bool:
        return self.distro in {"debian", "ubuntu", "raspbian", "linuxmint", "pop"}

    def describe(self) -> str:
        cpu = "ARM64" if self.is_arm else "x86_64"
        if self.is_windows:
            return f"Windows {self.release} ({cpu})"
        name = self.distro or "Linux"
        if self.version:
            name += f" {self.version}"
        if self.codename:
            name += f" ({self.codename})"
        return f"{name} ({cpu})"


def detect_target() -> Target:
    """Identify the host, or raise :class:`UnsupportedHost`."""
    if os.name == "nt":
        arch = _windows_native_arch()
        if not arch:
            signals = " ".join(
                [
                    platform.machine(),
                    os.environ.get("PROCESSOR_ARCHITECTURE", ""),
                    os.environ.get("PROCESSOR_ARCHITEW6432", ""),
                    os.environ.get("PROCESSOR_IDENTIFIER", ""),
                ]
            ).lower()
            if "arm64" in signals or "aarch64" in signals or "armv8" in signals:
                arch = "aarch64"
            elif "amd64" in signals or "x86_64" in signals or "intel" in signals:
                arch = "x86_64"
        if arch not in {"x86_64", "aarch64"}:
            raise UnsupportedHost(
                f"unsupported Windows CPU '{platform.machine()}' ({SUPPORTED})"
            )
        return Target("windows", arch, release=platform.release())

    if not sys.platform.startswith("linux"):
        raise UnsupportedHost(f"unsupported operating system '{sys.platform}' ({SUPPORTED})")

    machine = platform.machine().lower()
    if machine in {"aarch64", "arm64", "armv8l", "armv8"}:
        arch = "aarch64"
    elif machine in {"x86_64", "amd64", "x64"}:
        arch = "x86_64"
    else:
        raise UnsupportedHost(f"unsupported Linux CPU '{platform.machine()}' ({SUPPORTED})")

    release = _read_os_release()
    distro = (release.get("ID") or "").lower()
    if not distro:
        likes = (release.get("ID_LIKE") or "").lower().split()
        distro = likes[0] if likes else ""
    codename = release.get("VERSION_CODENAME", "")
    version = release.get("VERSION_ID", "")
    return Target("linux", arch, distro=distro, codename=codename, version=version)


# --------------------------------------------------------------------------- #
# Releases, downloads, questions
# --------------------------------------------------------------------------- #
_ASSET_CACHE: Dict[str, List[Tuple[str, str]]] = {}


def github_assets(repo: str) -> List[Tuple[str, str]]:
    """``(file name, download url)`` for the latest release; empty on failure."""
    if repo in _ASSET_CACHE:
        return _ASSET_CACHE[repo]
    request = urllib.request.Request(
        GITHUB_LATEST.format(repo=repo),
        headers={
            "User-Agent": "timecapsule-setup",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        warn(f"cannot read the release list of {repo}: {exc}")
        return []
    assets: List[Tuple[str, str]] = []
    for asset in payload.get("assets", []) or []:
        name = str(asset.get("name") or "")
        link = str(asset.get("browser_download_url") or "")
        if name and link:
            assets.append((name, link))
    _ASSET_CACHE[repo] = assets
    return assets


def pick_asset(
    assets: Sequence[Tuple[str, str]], patterns: Sequence[str]
) -> Optional[Tuple[str, str]]:
    """First asset whose name contains *patterns[0]*, then *patterns[1]*, ..."""
    for pattern in patterns:
        for name, link in assets:
            if pattern.lower() in name.lower():
                return name, link
    return None


def download(url: str, destination: Path) -> bool:
    """Stream *url* into *destination* (size is printed at the end)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "timecapsule-setup"})
    step(f"downloading {destination.name}")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with destination.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
    except (urllib.error.URLError, OSError) as exc:
        bad(f"download failed: {exc}")
        return False
    size = destination.stat().st_size / (1024 * 1024)
    good(f"downloaded {destination.name} ({size:.0f} MiB)")
    return True


def confirm(question: str, assume_yes: bool) -> bool:
    """Ask *question*; without a terminal only ``--yes`` counts as a yes."""
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        detail("no terminal to ask on -- re-run with --yes to accept this step")
        return False
    return input(f"{question} [y/N] ").strip().lower() in {"y", "yes"}


# --------------------------------------------------------------------------- #
# Trying one route after another
# --------------------------------------------------------------------------- #
@dataclass
class Option:
    """One way of obtaining an emulator on this host."""

    name: str
    plan: str  # what it will do, shown by --check/--dry-run
    applies: Callable[[], Tuple[bool, str]]  # (usable here?, why not)
    install: Callable[[], bool]  # do it; True on success


@dataclass
class Setup:
    """Everything the option builders need to know."""

    target: Target
    runner: Runner
    assume_yes: bool = False
    portable: bool = False
    flatpak_wine: bool = False
    allow_hangover: bool = True
    wsl_requested: bool = False
    hints: Dict[str, str] = field(default_factory=dict)  # emulator -> manifest value

    @property
    def dry_run(self) -> bool:
        return self.runner.dry_run

    @property
    def system(self) -> str:
        """Host key used in the option tables: linux-x86_64, windows-arm64, ..."""
        return f"{self.target.system}-{self.target.arch}"


def obtain(what: str, options: Sequence[Option], setup: Setup) -> bool:
    """Work through *options* until one of them succeeds."""
    usable: List[Tuple[Option, bool, str]] = []
    for option in options:
        try:
            allowed, reason = option.applies()
        except Exception as exc:  # a broken probe must not kill the run
            allowed, reason = False, f"probe failed: {exc}"
        usable.append((option, allowed, reason))

    if setup.dry_run:
        for option, allowed, reason in usable:
            if allowed:
                info(f"{what}: would use {option.name} -- {option.plan}")
                return False
            detail(f"{option.name}: not usable ({reason})")
        warn(f"{what}: no automatic route on this host")
        return False

    for option, allowed, reason in usable:
        if not allowed:
            detail(f"{option.name}: skipped ({reason})")
            continue
        step(f"{what}: {option.name} -- {option.plan}")
        if option.install():
            good(f"{what}: done via {option.name}")
            return True
        warn(f"{what}: {option.name} did not succeed -- trying the next route")
    return False


# --------------------------------------------------------------------------- #
# Distribution package managers
# --------------------------------------------------------------------------- #
PM_BINARIES = (
    ("apt", "apt-get"),
    ("dnf", "dnf"),
    ("pacman", "pacman"),
    ("zypper", "zypper"),
    ("apk", "apk"),
)


def pm_name() -> str:
    """The package manager of this distribution, or ``""`` when there is none."""
    for name, binary in PM_BINARIES:
        if shutil.which(binary):
            return name
    return ""


def pm_has(pm: str, package: str, runner: Runner) -> bool:
    """Is *package* installable from the configured repositories?"""
    if pm == "apt":
        succeeded, output = runner.probe(["apt-cache", "policy", package])
        if not succeeded:
            return False
        return any(
            line.strip().startswith("Candidate:") and "(none)" not in line
            for line in output.splitlines()
        )
    if pm == "dnf":
        succeeded, output = runner.probe(
            ["dnf", "--quiet", "list", "--available", package]
        )
        return succeeded and package in output
    if pm == "pacman":
        return runner.probe(["pacman", "-Si", package])[0]
    if pm == "zypper":
        return runner.probe(["zypper", "--quiet", "info", "-t", "package", package])[0]
    if pm == "apk":
        succeeded, output = runner.probe(["apk", "search", "-x", package])
        return succeeded and package in output
    return False


def pm_install(pm: str, packages: Sequence[str], runner: Runner) -> bool:
    tables = {
        "apt": ["apt-get", "install", "-y"],
        "dnf": ["dnf", "install", "-y"],
        "pacman": ["pacman", "-S", "--needed", "--noconfirm"],
        "zypper": ["zypper", "--non-interactive", "install"],
        "apk": ["apk", "add"],
    }
    if pm not in tables:
        return False
    return runner.install(tables[pm] + list(packages), root=True)


def apt_enable_i386(runner: Runner) -> None:
    """Let Debian/Ubuntu install wine32 -- most 9x-era titles are 32-bit."""
    if not shutil.which("dpkg"):
        return
    succeeded, output = runner.probe(["dpkg", "--print-foreign-architectures"])
    if succeeded and "i386" in output.split():
        return
    step("enabling the i386 architecture, for 32-bit Wine support")
    runner.install(["dpkg", "--add-architecture", "i386"], root=True)
    runner.install(["apt-get", "update"], root=True)


def aur_helper() -> str:
    """An AUR helper already present on this machine (Arch only)."""
    for name in ("yay", "paru"):
        found = shutil.which(name)
        if found:
            return found
    return ""


# --------------------------------------------------------------------------- #
# Flatpak (distribution neutral)
# --------------------------------------------------------------------------- #
def flatpak_available() -> bool:
    return bool(shutil.which("flatpak"))


def flatpak_install(app_id: str, setup: Setup, *, host_access: bool) -> bool:
    runner = setup.runner
    runner.install(
        ["flatpak", "remote-add", "--if-not-exists", "--user", "flathub", FLATHUB_REMOTE_URL]
    )
    if not runner.install(["flatpak", "install", "--user", "-y", "flathub", app_id]):
        present, _ = runner.probe(["flatpak", "info", "--user", app_id])
        if not present:
            return False
    if host_access:
        # The capsule's content sits wherever data_root points, so the sandbox
        # needs to see it (a user-level override -- no root required).
        runner.install(["flatpak", "override", "--user", "--filesystem=host", app_id])
    return True


def flatpak_export(app_id: str) -> Optional[Path]:
    """The wrapper script Flatpak exports for *app_id*, if it is installed."""
    for base in (
        Path.home() / ".local" / "share" / "flatpak" / "exports" / "bin",
        Path("/var/lib/flatpak/exports/bin"),
    ):
        candidate = base / app_id
        if candidate.is_file():
            return candidate
    return None


def link_on_path(target: Path, name: str) -> Optional[Path]:
    """Symlink *target* into ``~/.local/bin/<name>``."""
    local_bin = Path.home() / ".local" / "bin"
    link = local_bin / name
    try:
        local_bin.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or link.exists():
            if link.resolve() == target.resolve():
                return link
            link.unlink()
        link.symlink_to(target)
    except OSError as exc:
        detail(f"could not create {link}: {exc}")
        return None
    return link


# --------------------------------------------------------------------------- #
# Wine
# --------------------------------------------------------------------------- #
WINE_PACKAGES = {
    "apt": ["wine"],
    "dnf": ["wine"],
    "pacman": ["wine"],
    "zypper": ["wine"],
    "apk": ["wine"],
}
# Nice-to-have packages, installed best effort once the main one is in.
WINE_EXTRAS = {
    "apt": ["wine32"],  # 32-bit support: most 9x-era titles need it
    "dnf": ["wine-mono"],
    "pacman": ["wine-mono"],
}


def install_wine_via_pm(pm: str, setup: Setup) -> bool:
    """Wine from the distribution's own repositories."""
    packages = WINE_PACKAGES.get(pm, ["wine"])
    if pm == "apt" and setup.target.arch == "x86_64":
        apt_enable_i386(setup.runner)
    if not pm_install(pm, packages, setup.runner):
        return False
    for extra in WINE_EXTRAS.get(pm, []):
        if pm_has(pm, extra, setup.runner):
            pm_install(pm, [extra], setup.runner)
    return True


def install_flatpak_wine(setup: Setup) -> bool:
    """Wine from Flathub (x86_64 only) when no distribution package exists."""
    if not flatpak_install(FLATPAK_WINE_ID, setup, host_access=True):
        return False
    export = flatpak_export(FLATPAK_WINE_ID)
    if export is None:
        warn("the Flatpak is installed, but its wrapper script was not found")
        return False
    if shutil.which("wine") is None:
        link_on_path(export, "wine")
    if shutil.which("wine") is None:
        setup.hints["wine"] = str(export)
    return True


def hangover_asset(target: Target) -> Optional[Tuple[str, str]]:
    """The Hangover bundle whose Debian/Ubuntu build matches this host."""
    needles: List[str] = []
    if target.codename:
        needles.append(f"_{target.codename}_")
    if target.version:
        needles.append(f"{target.distro}{target.version.replace('.', '')}")
    if not needles:
        return None
    bundles = [
        (name, link)
        for name, link in github_assets(HANGOVER_REPO)
        if name.lower().endswith("_arm64.tar")
    ]
    return pick_asset(bundles, needles)


def install_hangover(setup: Setup) -> bool:
    """Hangover = Wine plus FEX/Box64: x86 and x86_64 Windows apps on ARM64."""
    asset = hangover_asset(setup.target)
    if asset is None:
        warn(f"no Hangover build matches {setup.target.describe()}")
        return False
    name, link = asset
    warn("Hangover replaces the system Wine with an ARM64 build that emulates")
    detail("x86/x86_64 code (FEX + Box64). Remove it later with 'apt remove hangover'.")
    if not confirm(f"download and install {name} (about 300 MB)?", setup.assume_yes):
        return False
    with tempfile.TemporaryDirectory(prefix="hangover-") as workspace:
        archive = Path(workspace) / name
        if not download(link, archive):
            return False
        debs: List[str] = []
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                if not member.name.endswith(".deb"):
                    continue
                try:
                    bundle.extract(member, path=workspace, filter="data")
                except TypeError:  # Python < 3.11.4 has no 'filter' argument
                    bundle.extract(member, path=workspace)
                debs.append(str(Path(workspace) / member.name))
        if not debs:
            bad("the Hangover bundle contained no .deb packages")
            return False
        step(f"installing {len(debs)} Hangover package(s)")
        if not setup.runner.install(["apt-get", "install", "-y", *debs], root=True):
            return False
    good("Hangover installed: 'wine' now runs x86 and x86_64 titles")
    detail("wine-mono is fetched on first use; if that download fails, run:")
    detail("    WINEDEBUG=wininet wine wineboot -u")
    return True


# -- Windows: Wine itself does not run here, so hand "wine" a pass-through ---
WINE_SHIM = """@echo off
rem ===========================================================================
rem Time Capsule -- "wine" stand-in for a Windows host.
rem ---------------------------------------------------------------------------
rem Windows runs Windows software itself: Win32 programs start directly, and on
rem ARM64 Windows emulates x86/x64 (Prism). No Wine layer is involved.
rem This shim lets manifest entries of type "wine" work unchanged:
rem
rem     wine.cmd <program.exe> [args...]
rem
rem Point the manifest at it:
rem     "settings": { "emulators": { "wine": "tools/bin/wine.cmd" } }
rem ===========================================================================
setlocal
if "%~1"=="" (
    >&2 echo wine.cmd: no program given
    exit /b 2
)
start "Time Capsule" /b /wait %*
exit /b %ERRORLEVEL%
"""


def write_windows_shim(setup: Setup) -> bool:
    """Create the Windows stand-in for ``wine``."""
    relative = SHIM_PATH.relative_to(ROOT).as_posix()
    if setup.dry_run:
        detail(f"would write {SHIM_PATH}")
        return False
    try:
        SHIM_PATH.parent.mkdir(parents=True, exist_ok=True)
        SHIM_PATH.write_bytes(WINE_SHIM.replace("\n", "\r\n").encode("utf-8"))
    except OSError as exc:
        bad(f"cannot write {SHIM_PATH}: {exc}")
        return False
    good(f"wrote {SHIM_PATH}")
    setup.hints["wine"] = relative
    detail(f'manifest.json -> "emulators": {{ "wine": "{relative}" }}')
    return True


def wsl_distribution(runner: Runner) -> str:
    """Name of an installed WSL distribution, or "" (WSL prints UTF-16)."""
    succeeded, output = runner.probe(["wsl", "--list", "--quiet"])
    if not succeeded:
        return ""
    for line in output.replace("\x00", "").splitlines():
        name = line.strip().lstrip("*").strip()
        if name:
            return name
    return ""


def install_wine_wsl(setup: Setup) -> bool:
    """Windows hosts get real Wine through WSL2 (WSLg supplies display + GPU)."""
    distro = wsl_distribution(setup.runner)
    if not distro:
        if not confirm(
            "Wine needs a Linux userland: install Ubuntu in WSL2 now?", setup.assume_yes
        ):
            return False
        if not setup.runner.install(["wsl", "--install", "-d", "Ubuntu"]):
            return False
        warn("WSL2 was just installed: reboot if Windows asks, finish the")
        detail("first-run user setup, then re-run: python scripts/setup.py --wsl")
        return False
    step(f"running the Linux setup inside WSL2 ({distro})")
    inner = ["python3", "scripts/setup.py", "--only", "wine", "--yes"]
    if setup.runner.install(["wsl", "-d", distro, "--cd", str(ROOT), "--", *inner]):
        return True
    # Older WSL builds have no --cd: convert the path from inside the distro.
    script = (
        'cd "$(wslpath -a "$TIMECAPSULE_REPO")" && '
        "python3 scripts/setup.py --only wine --yes"
    )
    return setup.runner.install(
        ["wsl", "-d", distro, "env", f"TIMECAPSULE_REPO={ROOT}", "bash", "-lc", script]
    )


# -- the routes, per host ----------------------------------------------------
def wine_options_windows(setup: Setup) -> List[Option]:
    options = [
        Option(
            "Windows itself (no Wine needed)",
            f"write {SHIM_PATH.relative_to(ROOT).as_posix()} and point the manifest at it",
            lambda: (True, ""),
            lambda: write_windows_shim(setup),
        )
    ]
    if setup.wsl_requested:
        options.append(
            Option(
                "WSL2",
                "install Wine inside WSL2, where it really runs",
                lambda: (True, "")
                if shutil.which("wsl")
                else (False, "'wsl' is not available"),
                lambda: install_wine_wsl(setup),
            )
        )
    return options


def wine_options_linux_x86(setup: Setup) -> List[Option]:
    options: List[Option] = []
    pm = pm_name()
    if pm:
        names = WINE_PACKAGES.get(pm, ["wine"])

        def applies(pm: str = pm, names: List[str] = names) -> Tuple[bool, str]:
            if not pm_has(pm, names[0], setup.runner):
                return False, f"'{names[0]}' is not in the configured {pm} repositories"
            return True, ""

        options.append(
            Option(
                f"{pm} package",
                f"install {' '.join(names)}"
                + (" and wine32 (via the i386 architecture)" if pm == "apt" else ""),
                applies,
                lambda pm=pm: install_wine_via_pm(pm, setup),
            )
        )
    if flatpak_available():
        flatpak = Option(
            "Flatpak (flathub)",
            f"flatpak install {FLATPAK_WINE_ID} and link it as 'wine'",
            lambda: (True, ""),
            lambda: install_flatpak_wine(setup),
        )
        if setup.flatpak_wine:
            options.insert(0, flatpak)
        else:
            options.append(flatpak)
    return options


def wine_options_linux_arm(setup: Setup) -> List[Option]:
    options: List[Option] = []
    if setup.allow_hangover:

        def applies_hangover() -> Tuple[bool, str]:
            if not setup.target.deblike:
                return False, "Hangover ships Debian/Ubuntu packages only"
            if hangover_asset(setup.target) is None:
                return False, f"no Hangover build matches {setup.target.describe()}"
            return True, ""

        options.append(
            Option(
                "Hangover (Wine + FEX/Box64)",
                "install the Hangover .debs, so x86 and x86_64 titles run",
                applies_hangover,
                lambda: install_hangover(setup),
            )
        )
    pm = pm_name()
    if pm:
        options.append(
            Option(
                f"{pm} package (ARM64 Wine)",
                "install wine, which runs ARM64 Windows binaries only",
                lambda pm=pm: (
                    pm_has(pm, "wine", setup.runner),
                    f"'{pm}' offers no wine package here",
                ),
                lambda pm=pm: install_wine_via_pm(pm, setup),
            )
        )
    return options


def wine_options(setup: Setup) -> List[Option]:
    """Every route to a working ``wine`` on this host, best first."""
    if setup.target.is_windows:
        return wine_options_windows(setup)
    if setup.target.is_arm:
        return wine_options_linux_arm(setup)
    return wine_options_linux_x86(setup)


# --------------------------------------------------------------------------- #
# DOSBox-X
# --------------------------------------------------------------------------- #
def install_dosbox_via_pm(setup: Setup) -> bool:
    """DOSBox-X from the distribution (Ubuntu/Debian 24.04+, or any that has it)."""
    pm = pm_name()
    if not pm:
        return False
    return pm_install(pm, ["dosbox-x"], setup.runner)


def install_dosbox_aur(setup: Setup) -> bool:
    """Arch: dosbox-x lives in the AUR, so build it with an existing helper."""
    helper = aur_helper()
    if not helper:
        return False
    return setup.runner.install([helper, "-S", "--needed", "--noconfirm", "dosbox-x"])


def install_dosbox_flatpak(setup: Setup) -> bool:
    """The one route that covers every distribution, x86_64 and aarch64 alike."""
    if not flatpak_install(FLATPAK_DOSBOX_ID, setup, host_access=True):
        return False
    export = flatpak_export(FLATPAK_DOSBOX_ID)
    if export is None:
        warn("the Flatpak is installed, but its wrapper script was not found")
        return False
    if shutil.which("dosbox-x") is None:
        link_on_path(export, "dosbox-x")
    if shutil.which("dosbox-x") is None:
        setup.hints["dosbox"] = str(export)
    return True


def install_dosbox_winget(setup: Setup) -> bool:
    return setup.runner.install(
        [
            "winget",
            "install",
            "--id",
            WINGET_DOSBOX_ID,
            "--exact",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ]
    )


def install_dosbox_portable(setup: Setup) -> bool:
    """Portable ZIP from the release page: no admin, and a native ARM64 build."""
    patterns = (
        ["vsbuild-arm64", "mingw64"]
        if setup.target.is_arm
        else ["vsbuild-win64", "mingw64", "vsbuild-win32"]
    )
    bundles = [
        (name, link)
        for name, link in github_assets(DOSBOX_REPO)
        if name.lower().endswith("-portable.zip")
    ]
    asset = pick_asset(bundles, patterns)
    if asset is None:
        warn("no portable DOSBox-X build in the latest release")
        return False
    name, link = asset
    with tempfile.TemporaryDirectory(prefix="dosbox-x-") as workspace:
        archive = Path(workspace) / name
        if not download(link, archive):
            return False
        step(f"unpacking into {PORTABLE_DIR}")
        try:
            PORTABLE_DIR.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(PORTABLE_DIR)
        except (OSError, zipfile.BadZipFile) as exc:
            bad(f"cannot unpack {name}: {exc}")
            return False
    found = next(iter(sorted(PORTABLE_DIR.rglob("dosbox-x.exe"))), None)
    if found is None:
        warn(f"unpacked, but no dosbox-x.exe below {PORTABLE_DIR}")
        return False
    relative = found.relative_to(ROOT).as_posix()
    setup.hints["dosbox"] = relative
    detail(f'manifest.json -> "emulators": {{ "dosbox": "{relative}" }}')
    return True


def dosbox_options_linux(setup: Setup) -> List[Option]:
    options: List[Option] = []
    pm = pm_name()
    if pm:
        options.append(
            Option(
                f"{pm} package",
                "install dosbox-x",
                lambda pm=pm: (
                    pm_has(pm, "dosbox-x", setup.runner),
                    f"'{pm}' does not package dosbox-x here",
                ),
                lambda: install_dosbox_via_pm(setup),
            )
        )
    helper = aur_helper()
    if helper:
        options.append(
            Option(
                "AUR",
                f"{Path(helper).name} -S dosbox-x (compiles from source)",
                lambda: (True, ""),
                lambda: install_dosbox_aur(setup),
            )
        )
    if flatpak_available():
        options.append(
            Option(
                "Flatpak (flathub)",
                f"flatpak install {FLATPAK_DOSBOX_ID} and link it as 'dosbox-x'",
                lambda: (True, ""),
                lambda: install_dosbox_flatpak(setup),
            )
        )
    return options


def dosbox_options_windows(setup: Setup) -> List[Option]:
    winget = Option(
        "winget",
        f"winget install --id {WINGET_DOSBOX_ID} --exact",
        lambda: (True, "") if shutil.which("winget") else (False, "'winget' is not available"),
        lambda: install_dosbox_winget(setup),
    )
    portable = Option(
        "portable ZIP",
        f"unpack a release ZIP into {PORTABLE_DIR.relative_to(ROOT).as_posix()} (no admin)",
        lambda: (True, ""),
        lambda: install_dosbox_portable(setup),
    )
    # ARM64 Windows has a native portable build, so prefer it there.
    if setup.target.is_arm or setup.portable:
        return [portable, winget]
    return [winget, portable]


def dosbox_options(setup: Setup) -> List[Option]:
    """Every route to a working ``dosbox-x`` on this host, best first."""
    if setup.target.is_windows:
        return dosbox_options_windows(setup)
    return dosbox_options_linux(setup)


# --------------------------------------------------------------------------- #
# Verification, manifest, guidance
# --------------------------------------------------------------------------- #
def default_name(kind: str) -> str:
    """The executable name an emulator is expected to have on ``PATH``."""
    return {"wine": "wine", "dosbox": "dosbox-x"}[kind]


def artifact_path(kind: str) -> Optional[Path]:
    """Something this script may have placed itself, if it is still there."""
    if kind == "wine" and os.name == "nt" and SHIM_PATH.is_file():
        return SHIM_PATH
    if kind == "dosbox" and PORTABLE_DIR.is_dir():
        found = next(iter(sorted(PORTABLE_DIR.rglob("dosbox-x.exe"))), None)
        if found is not None:
            return found
    return None


def inspect(setup: Setup, manifest: "Manifest") -> List[Tuple[str, str, Optional[str]]]:
    """``(kind, label, resolved path)`` -- mimicked after ``launcher.py check``."""
    rows: List[Tuple[str, str, Optional[str]]] = []
    for kind in ("wine", "dosbox"):
        label = emulators.EMULATOR_LABELS[kind]
        wanted = None
        try:  # the manifest decides first, exactly like the launcher does
            wanted = emulators.emulator_name(manifest, kind)
        except Exception:
            wanted = default_name(kind)
        found = emulators.resolve_binary(wanted, ROOT)
        if found is None:
            candidate = artifact_path(kind)
            if candidate is not None and candidate.is_file():
                setup.hints.setdefault(kind, _manifest_value(candidate))
            else:
                found = emulators.resolve_binary(default_name(kind), ROOT)
        rows.append((kind, label, found))
    return rows


def _manifest_value(path: Path) -> str:
    """Prefer a path relative to the repository, so the manifest stays portable."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def apply_manifest(updates: Dict[str, str]) -> None:
    """Point ``manifest.json`` at the binaries this run discovered."""
    path = ROOT / "manifest.json"
    if not path.is_file():
        warn(f"no manifest at {path} -- set settings.emulators by hand")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        bad(f"{path.name} is not valid JSON: {exc}")
        return
    table = data.setdefault("settings", {}).setdefault("emulators", {})
    changes: List[str] = []
    for kind, value in updates.items():
        if table.get(kind) != value:
            changes.append(f"{kind}: {table.get(kind)!r} -> {value!r}")
            table[kind] = value
    if not changes:
        detail(f"{path.name} already points at the right binaries")
        return
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for change in changes:
        good(f"{path.name}: {change}")


def guidance_wine(setup: Setup) -> None:
    heading("Wine -- manual routes")
    target = setup.target
    if target.is_windows:
        detail("Wine does not run on Windows itself.")
        detail(f"  - use the shim: {SHIM_PATH.relative_to(ROOT).as_posix()}")
        detail("  - or install Wine inside WSL2:   wsl --install -d Ubuntu")
        detail("    then re-run:  python scripts/setup.py --wsl")
        return
    if target.is_arm:
        detail(f"Hangover, x86/x86_64 software on ARM64: {HANGOVER_URL}")
        detail(f"FEX and Box64, the emulation layers it uses: {BOX64_URL}")
        detail("Plain ARM64 Wine runs ARM64 Windows binaries only.")
    detail(f"Packages and repositories: {WINEHQ_URL}")
    detail("Debian/Ubuntu need the i386 architecture to install wine32 (32-bit titles).")
    detail(f"Missing runtimes once it starts: {WINETRICKS_HINT}")


def guidance_dosbox(setup: Setup) -> None:
    heading("DOSBox-X -- manual routes")
    detail(f"Download page: {DOSBOX_URL}")
    detail(f"Build from source: {DOSBOX_BUILD_URL}")
    if setup.target.is_windows:
        detail(f"winget install --id {WINGET_DOSBOX_ID} --exact")
        detail("or unpack a portable ZIP from the releases page")
    else:
        detail(f"Flatpak, x86_64 and aarch64: flatpak install flathub {FLATPAK_DOSBOX_ID}")
    detail("If it ends up outside PATH, put the full path in settings.emulators.dosbox.")


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #
def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="setup.py",
        description=(
            "Install Wine and DOSBox-X for Time Capsule. Linux and Windows "
            "hosts, on x86_64 or ARM64."
        ),
    )
    parser.add_argument(
        "--only",
        choices=("all", "wine", "dosbox"),
        default="all",
        help="set up one emulator only (default: both)",
    )
    parser.add_argument(
        "--check", action="store_true", help="report what is installed; change nothing"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the route that would be used"
    )
    parser.add_argument(
        "--apply", action="store_true", help="write discovered paths into manifest.json"
    )
    parser.add_argument(
        "--yes", "-y", action="store_true", help="answer yes to every question"
    )
    parser.add_argument(
        "--portable", action="store_true", help="Windows: prefer portable ZIPs"
    )
    parser.add_argument(
        "--flatpak-wine", action="store_true", help="Linux: prefer the Flatpak Wine"
    )
    parser.add_argument(
        "--no-hangover", action="store_true", help="aarch64 Linux: never install Hangover"
    )
    parser.add_argument(
        "--wsl", action="store_true", help="Windows: set Wine up inside WSL2"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="show probes and every command"
    )
    parser.add_argument("--no-color", action="store_true", help="plain text output")
    return parser.parse_args(argv)


def requested_kinds(only: str) -> Tuple[str, ...]:
    return {"all": ("wine", "dosbox"), "wine": ("wine",), "dosbox": ("dosbox",)}[only]


def already_available(kind: str) -> bool:
    """True when there is nothing left to install for *kind*."""
    return (
        emulators.resolve_binary(default_name(kind), ROOT) is not None
        or artifact_path(kind) is not None
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main(argv: Optional[Sequence[str]] = None) -> int:
    global COLOR, VERBOSE
    args = parse_args(argv)
    VERBOSE = args.verbose
    COLOR = not args.no_color and enable_ansi()

    try:
        target = detect_target()
    except UnsupportedHost as exc:
        bad(str(exc))
        return 2

    manifest_path = ROOT / "manifest.json"
    try:
        manifest = load_manifest(str(manifest_path) if manifest_path.is_file() else None)
    except ManifestError as exc:
        bad(f"manifest error: {exc}")
        return 2

    kinds = requested_kinds(args.only)
    heading("Time Capsule setup")
    detail(f"host    : {target.describe()}")
    detail(f"capsule : {ROOT}")
    detail(f"python  : {platform.python_version()}")

    runner = Runner(target, dry_run=args.check or args.dry_run)
    setup = Setup(
        target=target,
        runner=runner,
        assume_yes=args.yes,
        portable=args.portable,
        flatpak_wine=args.flatpak_wine,
        allow_hangover=not args.no_hangover,
        wsl_requested=args.wsl,
    )
    if args.check:
        info("checking only: nothing will be installed")
    elif args.dry_run:
        info("dry run: nothing will be installed")

    for kind in kinds:
        label = emulators.EMULATOR_LABELS[kind]
        heading(label)
        if kind == "wine" and target.is_windows:
            detail("Windows runs Win32 software itself; Wine itself needs WSL2.")
        if already_available(kind):
            good(f"{label} is already available")
            continue
        options = wine_options(setup) if kind == "wine" else dosbox_options(setup)
        if not options:
            warn(f"no automatic route for {label} on this host")
            continue
        obtain(label, options, setup)

    def survey() -> Tuple[List[Tuple[str, str, Optional[str]]], List[str]]:
        """Where the emulators are *now*, judged the way the launcher judges."""
        rows = [row for row in inspect(setup, manifest) if row[0] in kinds]
        return rows, [kind for kind, _label, path in rows if not path]

    rows, missing = survey()
    if missing and args.apply and setup.hints:
        apply_manifest(setup.hints)
        try:  # re-read, so the summary below reflects what we just wrote
            manifest = load_manifest(str(manifest_path))
        except ManifestError as exc:
            warn(f"could not re-read {manifest_path.name}: {exc}")
        else:
            rows, missing = survey()

    heading("Result")
    for kind, label, path in rows:
        if path:
            good(f"{label} : {path}")
        elif kind in setup.hints:
            warn(f"{label} : installed at {setup.hints[kind]}")
            detail(f"manifest.json still points at '{emulators.emulator_name(manifest, kind)}'")
        else:
            bad(f"{label} : not found")

    if not missing:
        if "wine" in kinds and not target.is_windows:
            found = emulators.resolve_binary(emulators.emulator_name(manifest, "wine"), ROOT)
            if found:
                succeeded, output = runner.probe([found, "--version"])
                if succeeded and output.strip():
                    detail(f"wine --version: {output.strip().splitlines()[0]}")
        heading("Next")
        detail("python launcher.py check    # emulators and content")
        detail("python dashboard.py         # browse and launch")
        return 0

    updates = {kind: setup.hints[kind] for kind in missing if kind in setup.hints}
    if updates:
        heading("manifest.json")
        detail("Point the launcher at what was just installed:")
        for kind, value in updates.items():
            detail(f'settings.emulators.{kind} = "{value}"')
        detail("or re-run this script with --apply")

    for kind in missing:
        if kind == "wine":
            guidance_wine(setup)
        else:
            guidance_dosbox(setup)
    print()
    detail("'python launcher.py check' shows the same picture at any time.")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        bad("interrupted")
        raise SystemExit(130)











