"""Turn manifest entries into concrete emulator commands.

Wine and DOSBox-X are treated as **external** tools that must already be
installed on the host (see ``scripts/setup.py``, which installs them for Linux
and Windows on x86_64 and ARM64). This module only *describes* what to run --
:func:`build_plan` produces a :class:`LaunchPlan` that callers can inspect,
print or execute.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .manifest import App, Manifest

# Human-friendly names for the three launch types.
EMULATOR_LABELS = {"wine": "Wine", "dosbox": "DOSBox-X", "native": "Native"}


class LaunchError(Exception):
    """Raised when a plan cannot be executed (missing files/emulator)."""


@dataclass
class LaunchPlan:
    """A ready-to-run command plus everything needed to execute it."""

    app: App
    argv: List[str]
    cwd: Path
    env: Dict[str, str]
    problems: List[str] = field(default_factory=list)  # fatal -> cannot run
    warnings: List[str] = field(default_factory=list)  # cosmetic -> still runs

    @property
    def ok(self) -> bool:
        return not self.problems

    def command_line(self) -> str:
        return " ".join(_quote(part) for part in self.argv)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def emulator_label(app_type: str) -> str:
    return EMULATOR_LABELS.get(app_type, app_type)


def _quote(value: str) -> str:
    if value == "" or any(ch in value for ch in ' \t"'):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _expand_user_path(value: str, base_dir: Path) -> str:
    path = Path(os.path.expandvars(os.path.expanduser(value)))
    if not path.is_absolute():
        path = base_dir / path
    return str(path.resolve())


def resolve_binary(name: str, base_dir: Optional[Path] = None) -> Optional[str]:
    """Find an executable on ``PATH`` (or relative to *base_dir*)."""
    if not name:
        return None
    if base_dir is not None and not Path(name).is_absolute():
        candidate = base_dir / name
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt" and not name.lower().endswith((".exe", ".bat", ".cmd")):
        found = shutil.which(name + ".exe")
        if found:
            return found
    return None


def emulator_name(manifest: Manifest, kind: str) -> str:
    """Configured executable name for an emulator kind ("wine" or "dosbox")."""
    table = manifest.settings.get("emulators", {}) or {}
    return str(table.get(kind) or ({"wine": "wine", "dosbox": "dosbox-x"}[kind]))


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------
def build_plan(app: App, manifest: Manifest) -> LaunchPlan:
    """Build the :class:`LaunchPlan` for a single manifest entry."""
    problems: List[str] = []
    warnings: List[str] = []
    base_dir = manifest.path.parent

    if app.type == "wine":
        argv, cwd, env = _plan_wine(app, manifest, base_dir, problems)
    elif app.type == "dosbox":
        argv, cwd, env = _plan_dosbox(app, manifest, base_dir, problems, warnings)
    elif app.type == "native":
        argv, cwd, env = _plan_native(app, problems)
    else:  # pragma: no cover - guarded by manifest validation
        raise LaunchError(f"unknown app type '{app.type}'")

    return LaunchPlan(
        app=app, argv=argv, cwd=cwd, env=env, problems=problems, warnings=warnings
    )


def _plan_wine(
    app: App, manifest: Manifest, base_dir: Path, problems: List[str]
) -> Tuple[List[str], Path, Dict[str, str]]:
    name = emulator_name(manifest, "wine")
    binary = resolve_binary(name, base_dir)
    if binary is None:
        problems.append(
            f"Wine executable not found: '{name}' "
            "(install Wine or set settings.emulators.wine)"
        )
        binary = name

    if not app.app_dir.is_dir():
        problems.append(f"application folder not found: {app.app_dir}")
    command_path = app.command_path
    if command_path is None or not command_path.exists():
        problems.append(f"program not found: {command_path}")

    argv: List[str] = [binary]
    if command_path is not None:
        argv.append(str(command_path))
    argv += app.arg_list

    env = os.environ.copy()
    wine_cfg = manifest.settings.get("wine", {}) or {}
    prefix = app.wine_prefix or str(wine_cfg.get("prefix") or "")
    if prefix:
        env["WINEPREFIX"] = _expand_user_path(prefix, base_dir)
    arch = app.wine_arch or str(wine_cfg.get("arch") or "")
    if arch:
        env["WINEARCH"] = arch
    env.update(app.env)

    return argv, app.working_directory, env


def _plan_dosbox(
    app: App,
    manifest: Manifest,
    base_dir: Path,
    problems: List[str],
    warnings: List[str],
) -> Tuple[List[str], Path, Dict[str, str]]:
    name = emulator_name(manifest, "dosbox")
    binary = resolve_binary(name, base_dir)
    if binary is None:
        problems.append(
            f"DOSBox-X executable not found: '{name}' "
            "(install DOSBox-X or set settings.emulators.dosbox)"
        )
        binary = name

    mount_dir = app.app_dir
    if not mount_dir.is_dir():
        problems.append(f"application folder not found: {mount_dir}")

    argv: List[str] = [binary]
    if app.config:
        config_path = app.config_path
        if config_path is not None and config_path.is_file():
            argv += ["-conf", str(config_path)]
        else:
            warnings.append(
                f"DOSBox config not found, using generated config: {config_path}"
            )

    # Mount the app folder and (optionally) start the program, all from the
    # command line so no game-specific absolute paths are needed in a config.
    drive = (app.mount or "C").rstrip(":").upper()
    argv += ["-c", f'mount {drive} "{mount_dir}"', "-c", f"{drive}:"]
    if app.command:
        line = app.command + (f" {app.args}" if app.args else "")
        argv += ["-c", line]
    argv += ["-c", "exit"]

    for extra in manifest.settings.get("dosbox", {}).get("extra_args", []) or []:
        argv.append(str(extra))

    env = os.environ.copy()
    env.update(app.env)
    return argv, app.working_directory, env


def _plan_native(
    app: App, problems: List[str]
) -> Tuple[List[str], Path, Dict[str, str]]:
    command_path = app.command_path
    if command_path is None or not command_path.exists():
        problems.append(f"program not found: {command_path}")

    argv: List[str] = [str(command_path) if command_path is not None else app.command]
    argv += app.arg_list

    env = os.environ.copy()
    env.update(app.env)
    return argv, app.working_directory, env


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
def run(plan: LaunchPlan) -> int:
    """Run a plan to completion (blocking) and return the exit code."""
    if not plan.ok:
        raise LaunchError("; ".join(plan.problems))
    return subprocess.call(plan.argv, cwd=str(plan.cwd), env=plan.env)


def spawn(plan: LaunchPlan) -> subprocess.Popen:
    """Start a plan without blocking; stdout/stderr are merged for streaming."""
    if not plan.ok:
        raise LaunchError("; ".join(plan.problems))
    return subprocess.Popen(
        plan.argv,
        cwd=str(plan.cwd),
        env=plan.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def emulator_status(manifest: Manifest) -> List[Tuple[str, str, Optional[str]]]:
    """Return ``(kind, label, path)`` for each emulator the manifest may use."""
    base_dir = manifest.path.parent
    result: List[Tuple[str, str, Optional[str]]] = []
    for kind in ("wine", "dosbox"):
        name = emulator_name(manifest, kind)
        result.append((kind, EMULATOR_LABELS[kind], resolve_binary(name, base_dir)))
    return result
