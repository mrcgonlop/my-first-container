#!/usr/bin/env python3
"""Scaffold a new application folder and register it in ``manifest.json``.

    python scripts/new_app.py my_game --name "My Game" --type wine \
        --category games --command MYGAME.EXE --description "Win95 puzzler"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Add an app to the capsule.")
    parser.add_argument("key", help="short identifier, e.g. my_game")
    parser.add_argument("--name", default="", help="display name")
    parser.add_argument("--type", choices=["wine", "dosbox", "native"], default="wine")
    parser.add_argument("--category", default="games", help="games or apps (free-form)")
    parser.add_argument("--command", default="", help="executable inside the app folder")
    parser.add_argument("--args", default="", help="default arguments")
    parser.add_argument("--description", default="", help="one-line description")
    parser.add_argument("--force", action="store_true", help="overwrite an existing entry")
    args = parser.parse_args()

    if not MANIFEST.is_file():
        print(f"manifest not found: {MANIFEST}")
        return 1

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    apps = data.setdefault("apps", {})
    if args.key in apps and not args.force:
        print(f"'{args.key}' already exists (use --force to overwrite).")
        return 1

    data_root = Path((data.get("settings") or {}).get("data_root") or "data")
    folder = ROOT / data_root / args.category / args.key
    folder.mkdir(parents=True, exist_ok=True)

    entry: dict = {
        "name": args.name or args.key.replace("_", " ").title(),
        "type": args.type,
        "category": args.category,
        "path_relative_to_data": f"{args.category}/{args.key}",
        "description": args.description,
    }
    if args.type in ("wine", "native"):
        entry["command"] = args.command or "PROGRAM.EXE"
        entry["args"] = args.args
    else:  # dosbox
        entry["mount"] = "C"
        if args.command:
            entry["command"] = args.command
        if args.args:
            entry["args"] = args.args

    apps[args.key] = entry
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    print(f"Created folder : {folder}")
    print(f"Registered app : {args.key} in {MANIFEST.name}")
    print("Next           : copy the files in, then run 'python launcher.py check'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
