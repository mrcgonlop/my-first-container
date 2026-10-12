"""Read and validate the Time Capsule manifest (``manifest.json``).

The manifest is the single source of truth for the capsule: it lists every
application together with the emulator that should run it (``wine``,
``dosbox`` or ``native``) and the options needed to launch it.

Nothing here touches the filesystem beyond reading ``manifest.json`` itself;
resolved paths are exposed as properties on :class:`App` so callers can inspect
them without launching anything.
"""

from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

VALID_TYPES = ("wine", "dosbox", "native")
DEFAULT_CATEGORY = "apps"
MANIFEST_FILENAME = "manifest.json"

# Emulator defaults; the manifest's "settings" block overrides these.
DEFAULT_SETTINGS: Dict[str, Any] = {
    "data_root": "data",
    "emulators": {"wine": "wine", "dosbox": "dosbox-x"},
    "wine": {"prefix": "", "arch": ""},
    "dosbox": {"extra_args": []},
}


class ManifestError(Exception):
    """Raised when the manifest cannot be found, parsed or validated."""


@dataclass
class App:
    """A single launchable entry from the manifest."""

    key: str
    name: str
    type: str
    category: str = DEFAULT_CATEGORY
    description: str = ""
    path_relative_to_data: str = ""
    command: str = ""
    args: str = ""
    config: str = ""
    mount: str = "C"
    working_dir: str = ""
    wine_prefix: str = ""
    wine_arch: str = ""
    env: Dict[str, str] = field(default_factory=dict)
    data_root: Path = field(default=Path("."), repr=False, compare=False)

    # -- resolved paths ----------------------------------------------------
    @property
    def app_dir(self) -> Path:
        """Folder that holds this application's files."""
        if not self.path_relative_to_data:
            return self.data_root
        return (self.data_root / self.path_relative_to_data).resolve()

    @property
    def command_path(self) -> Optional[Path]:
        """Absolute path of the executable, or ``None`` when none is set."""
        if not self.command:
            return None
        candidate = Path(self.command)
        if candidate.is_absolute():
            return candidate
        return (self.app_dir / self.command).resolve()

    @property
    def config_path(self) -> Optional[Path]:
        """Absolute path of the (optional) DOSBox config file."""
        if not self.config:
            return None
        return (self.app_dir / self.config).resolve()

    @property
    def working_directory(self) -> Path:
        """Directory the emulator is started in (defaults to the app folder)."""
        if not self.working_dir:
            return self.app_dir
        return (self.data_root / self.working_dir).resolve()

    @property
    def arg_list(self) -> List[str]:
        """``args`` split into an argv list (quote-aware)."""
        if not self.args:
            return []
        return shlex.split(self.args, posix=(os.name != "nt"))


@dataclass
class Manifest:
    """The parsed app index."""

    path: Path
    data_root: Path
    settings: Dict[str, Any]
    apps: Dict[str, App]

    def get(self, key: str) -> App:
        try:
            return self.apps[key]
        except KeyError:
            known = ", ".join(self.apps) or "(none)"
            raise ManifestError(f"unknown app '{key}' (known apps: {known})") from None

    def keys(self) -> List[str]:
        return list(self.apps)

    def categories(self) -> List[str]:
        """Category names in order of first appearance."""
        ordered: List[str] = []
        for app in self.apps.values():
            if app.category not in ordered:
                ordered.append(app.category)
        return ordered


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def find_manifest(path: Optional[os.PathLike] = None) -> Path:
    """Locate ``manifest.json`` (explicit path > $TIMECAPSULE_MANIFEST > repo root)."""
    if path:
        return Path(path).expanduser().resolve()
    env = os.environ.get("TIMECAPSULE_MANIFEST")
    if env:
        return Path(env).expanduser().resolve()
    # The package lives in <repo>/timecapsule/, so the manifest sits one level up.
    return (Path(__file__).resolve().parent.parent / MANIFEST_FILENAME)


def load_manifest(path: Optional[os.PathLike] = None) -> Manifest:
    """Read, validate and return the manifest."""
    manifest_path = find_manifest(path)
    if not manifest_path.is_file():
        raise ManifestError(
            f"manifest not found: {manifest_path}\n"
            "Run this from the repository root or set TIMECAPSULE_MANIFEST."
        )
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{manifest_path}: invalid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{manifest_path}: the top level must be a JSON object")

    settings = _merge_settings(raw.get("settings") or {})
    base_dir = manifest_path.parent
    data_root = _resolve_data_root(settings, base_dir)

    apps_raw = raw.get("apps") or {}
    if not isinstance(apps_raw, dict):
        raise ManifestError(f"{manifest_path}: 'apps' must be a JSON object")

    apps: Dict[str, App] = {}
    for key, entry in apps_raw.items():
        apps[key] = _parse_app(key, entry, data_root)

    return Manifest(path=manifest_path, data_root=data_root, settings=settings, apps=apps)


def _resolve_data_root(settings: Dict[str, Any], base_dir: Path) -> Path:
    value = settings.get("data_root") or "data"
    candidate = Path(os.path.expandvars(os.path.expanduser(str(value))))
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve()


def _merge_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow-merge the user's settings over :data:`DEFAULT_SETTINGS`."""
    merged: Dict[str, Any] = {}
    for key, value in DEFAULT_SETTINGS.items():
        merged[key] = value.copy() if isinstance(value, (dict, list)) else value
    if not isinstance(settings, dict):
        return merged
    for key, value in settings.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def _parse_app(key: str, entry: Any, data_root: Path) -> App:
    if not isinstance(entry, dict):
        raise ManifestError(f"app '{key}' must be a JSON object")

    app_type = str(entry.get("type", "")).strip().lower()
    if not app_type:
        raise ManifestError(
            f"app '{key}': missing 'type' (one of: {', '.join(VALID_TYPES)})"
        )
    if app_type not in VALID_TYPES:
        raise ManifestError(
            f"app '{key}': unknown type '{app_type}' "
            f"(expected one of: {', '.join(VALID_TYPES)})"
        )

    rel = str(entry.get("path_relative_to_data", "")).strip().strip("/\\")
    command = str(entry.get("command", "")).strip()
    if not rel and not Path(command).is_absolute():
        raise ManifestError(f"app '{key}': missing 'path_relative_to_data'")
    if app_type in ("wine", "native") and not command:
        raise ManifestError(f"app '{key}': type '{app_type}' requires a 'command'")

    env = entry.get("env") or {}
    if not isinstance(env, dict):
        raise ManifestError(f"app '{key}': 'env' must be a JSON object")

    return App(
        key=key,
        name=str(entry.get("name") or key),
        type=app_type,
        category=str(entry.get("category") or DEFAULT_CATEGORY).strip().lower()
        or DEFAULT_CATEGORY,
        description=str(entry.get("description", "")),
        path_relative_to_data=rel,
        command=command,
        args=str(entry.get("args", "")),
        config=str(entry.get("config", "")).strip(),
        mount=str(entry.get("mount", "C")).strip() or "C",
        working_dir=str(entry.get("working_dir", "")).strip().strip("/\\"),
        wine_prefix=str(entry.get("wine_prefix", "")).strip(),
        wine_arch=str(entry.get("wine_arch", "")).strip(),
        env={str(k): str(v) for k, v in env.items()},
        data_root=data_root,
    )
