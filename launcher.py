#!/usr/bin/env python3
"""Time Capsule -- command line launcher.

Examples
--------
    python launcher.py                  list every application (default)
    python launcher.py list
    python launcher.py show <key>       print the command without running it
    python launcher.py run <key> [...]  launch an application
    python launcher.py check            verify emulators and app files
    python launcher.py dashboard        open the graphical dashboard

The manifest (``manifest.json``) is the source of truth; pass a different file
with ``--manifest PATH`` or the ``TIMECAPSULE_MANIFEST`` environment variable.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from timecapsule import emulators
from timecapsule.manifest import App, Manifest, ManifestError, load_manifest


def cmd_list(manifest: Manifest, args: argparse.Namespace) -> int:
    if not manifest.apps:
        print("The manifest lists no applications yet.")
        print('Add one with: python scripts/new_app.py <key> --name "..." --type wine|dosbox')
        return 0

    width = max(len(app.key) for app in manifest.apps.values())
    print(f"Time Capsule -- {len(manifest.apps)} application(s)")
    for category in manifest.categories():
        print(f"\n{category.upper()}")
        for app in manifest.apps.values():
            if app.category != category:
                continue
            print(f"  {app.key:<{width}}  [{app.type:<6}] {app.name}")
            if app.description:
                print(f"  {'':<{width}}  {app.description}")
    print("\nRun one with: python launcher.py run <key>")
    return 0


def cmd_show(manifest: Manifest, args: argparse.Namespace) -> int:
    app = manifest.get(args.key)
    plan = emulators.build_plan(app, manifest)
    print(f"{app.name}  ({emulators.emulator_label(app.type)})")
    print(f"  description : {app.description or '(none)'}")
    print(f"  folder      : {app.app_dir}")
    print(f"  working dir : {plan.cwd}")
    print(f"  command     : {plan.command_line()}")
    if plan.warnings:
        print("  warnings:")
        for warning in plan.warnings:
            print(f"    - {warning}")
    if plan.problems:
        print("  problems:")
        for problem in plan.problems:
            print(f"    - {problem}")
        return 1
    return 0


def cmd_run(manifest: Manifest, args: argparse.Namespace) -> int:
    app = manifest.get(args.key)
    plan = emulators.build_plan(app, manifest)
    if args.extra:
        plan.argv += list(args.extra)

    for warning in plan.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if not plan.ok:
        print(f"cannot launch '{app.key}':", file=sys.stderr)
        for problem in plan.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"==> launching {app.name} via {emulators.emulator_label(app.type)}")
    print(f"    {plan.command_line()}")
    try:
        return emulators.run(plan)
    except OSError as exc:
        print(f"failed to launch: {exc}", file=sys.stderr)
        return 1


def cmd_check(manifest: Manifest, args: argparse.Namespace) -> int:
    print("Emulators")
    for _kind, label, path in emulators.emulator_status(manifest):
        state = path if path else "NOT FOUND"
        print(f"  {label:<9} : {state}")

    print("\nApplications")
    failures = 0
    for app in manifest.apps.values():
        plan = emulators.build_plan(app, manifest)
        mark = "OK  " if plan.ok else "FAIL"
        print(f"  [{mark}] {app.key} ({emulators.emulator_label(app.type)})")
        for problem in plan.problems:
            print(f"           - {problem}")
        for warning in plan.warnings:
            print(f"           ~ {warning}")
        if not plan.ok:
            failures += 1
    print(f"\n{len(manifest.apps) - failures}/{len(manifest.apps)} ready.")
    return 1 if failures else 0


def cmd_dashboard(manifest: Manifest, args: argparse.Namespace) -> int:
    try:
        import dashboard
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"the dashboard is unavailable: {exc}", file=sys.stderr)
        print("Install Tkinter (Linux: python3-tk) or use the CLI commands.", file=sys.stderr)
        return 1
    return dashboard.main(args.manifest)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="launcher.py",
        description="Manifest-based launcher for legacy DOS/Windows software.",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="path to manifest.json (default: the one next to launcher.py)",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="list every application (default)")
    sub.add_parser("check", help="verify emulators and application files")
    sub.add_parser("dashboard", help="open the graphical app dashboard")

    p_show = sub.add_parser("show", help="print the command without running it")
    p_show.add_argument("key", help="application key from manifest.json")

    p_run = sub.add_parser("run", help="launch an application")
    p_run.add_argument("key", help="application key from manifest.json")
    p_run.add_argument("extra", nargs=argparse.REMAINDER, help="extra arguments")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "list"

    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 2

    handlers = {
        "list": cmd_list,
        "show": cmd_show,
        "run": cmd_run,
        "check": cmd_check,
        "dashboard": cmd_dashboard,
    }
    return handlers[command](manifest, args)


if __name__ == "__main__":
    raise SystemExit(main())
