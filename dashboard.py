#!/usr/bin/env python3
"""Time Capsule -- graphical app dashboard.

A small Tkinter front-end over the same manifest-driven launcher that
``launcher.py`` uses. It lists every entry in ``manifest.json``, groups it by
category, shows whether the required emulator and files are present, and
launches the selected application in the background while streaming the
emulator's output into a log pane.

Tkinter ships with the official Python builds; on Linux install it with
``sudo apt install python3-tk`` (Debian/Ubuntu) if it is missing.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from timecapsule import emulators
from timecapsule.manifest import Manifest, ManifestError, load_manifest

# Reuse the labels defined by the emulator layer (single source of truth).
EMULATOR_LABEL = emulators.EMULATOR_LABELS


class Dashboard:
    """The dashboard window."""

    def __init__(self, root: tk.Tk, manifest: Manifest) -> None:
        self.root = root
        self.manifest = manifest
        self.plan_by_key: dict[str, emulators.LaunchPlan] = {}
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.filter_var = tk.StringVar()
        self.category_var = tk.StringVar(value="All")

        self._build_ui()
        self.refresh()
        self._pump_log()

    # -- UI construction ---------------------------------------------------
    def _build_ui(self) -> None:
        self.root.title("Time Capsule -- App Dashboard")
        self.root.geometry("1000x640")
        self.root.minsize(780, 500)

        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        # Toolbar ---------------------------------------------------------
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="Search:").pack(side="left")
        search = ttk.Entry(toolbar, textvariable=self.filter_var)
        search.pack(side="left", fill="x", expand=True, padx=(4, 10))
        search.bind("<KeyRelease>", lambda _event: self.refresh())

        ttk.Label(toolbar, text="Category:").pack(side="left")
        self.category_box = ttk.Combobox(
            toolbar, textvariable=self.category_var, state="readonly", width=12
        )
        self.category_box.pack(side="left", padx=(4, 10))
        self.category_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())

        ttk.Button(toolbar, text="Reload", command=self.reload).pack(side="left")
        ttk.Button(toolbar, text="Check", command=self.check).pack(side="left", padx=(6, 0))

        # Split pane ------------------------------------------------------
        paned = ttk.Panedwindow(outer, orient="horizontal")
        paned.pack(fill="both", expand=True, pady=(10, 0))
        left = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=3)
        paned.add(right, weight=2)

        # Application list ------------------------------------------------
        columns = ("type", "category", "status")
        self.tree = ttk.Treeview(
            left, columns=columns, show="tree headings", selectmode="browse"
        )
        self.tree.heading("#0", text="Application")
        self.tree.column("#0", width=240, anchor="w")
        self.tree.heading("type", text="Type")
        self.tree.column("type", width=80, anchor="center")
        self.tree.heading("category", text="Category")
        self.tree.column("category", width=90, anchor="center")
        self.tree.heading("status", text="Status")
        self.tree.column("status", width=100, anchor="center")
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_details())
        self.tree.bind("<Double-1>", lambda _event: self.launch())
        self.tree.tag_configure("missing", foreground="#b00020")

        # Details panel ---------------------------------------------------
        details = ttk.LabelFrame(right, text="Details", padding=10)
        details.pack(fill="x")
        self.name_var = tk.StringVar(value="Select an application")
        self.meta_var = tk.StringVar(value="")
        self.desc_var = tk.StringVar(value="")
        self.problem_var = tk.StringVar(value="")
        ttk.Label(details, textvariable=self.name_var, font=("", 12, "bold")).pack(anchor="w")
        ttk.Label(details, textvariable=self.meta_var, foreground="#666").pack(anchor="w", pady=(2, 6))
        ttk.Label(details, textvariable=self.desc_var, wraplength=360, justify="left").pack(anchor="w")
        ttk.Label(
            details, textvariable=self.problem_var, foreground="#b00020",
            wraplength=360, justify="left",
        ).pack(anchor="w", pady=(6, 0))
        self.launch_btn = ttk.Button(details, text="Launch", command=self.launch, state="disabled")
        self.launch_btn.pack(anchor="e", pady=(10, 0))

        # Log panel -------------------------------------------------------
        log_frame = ttk.LabelFrame(right, text="Output", padding=6)
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.log = tk.Text(
            log_frame, height=14, wrap="word", state="disabled",
            background="#101418", foreground="#d0d6dd", insertbackground="#d0d6dd",
        )
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

    # -- Populating the list ----------------------------------------------
    def refresh(self) -> None:
        query = self.filter_var.get().strip().lower()
        selected_category = self.category_var.get()
        self.tree.delete(*self.tree.get_children())
        self.plan_by_key.clear()

        categories = self.manifest.categories()
        self.category_box["values"] = ["All"] + categories

        for category in categories:
            if selected_category not in ("All", category):
                continue
            apps = [a for a in self.manifest.apps.values() if a.category == category]
            if query:
                apps = [
                    a for a in apps
                    if query in a.name.lower()
                    or query in a.key.lower()
                    or query in (a.description or "").lower()
                ]
            if not apps:
                continue
            parent = self.tree.insert("", "end", text=category.upper(), open=True, values=("", "", ""))
            for app in apps:
                plan = emulators.build_plan(app, self.manifest)
                self.plan_by_key[app.key] = plan
                status = "Ready" if plan.ok else "Setup needed"
                tags = () if plan.ok else ("missing",)
                self.tree.insert(
                    parent, "end", iid=app.key, text=app.name, tags=tags,
                    values=(EMULATOR_LABEL.get(app.type, app.type), app.category, status),
                )
        self._show_details()

    def _selected_key(self) -> Optional[str]:
        selection = self.tree.selection()
        if not selection:
            return None
        key = selection[0]
        return key if key in self.manifest.apps else None

    def _show_details(self) -> None:
        key = self._selected_key()
        if key is None:
            self.name_var.set("Select an application")
            self.meta_var.set("")
            self.desc_var.set("")
            self.problem_var.set("")
            self.launch_btn.configure(state="disabled")
            return

        app = self.manifest.apps[key]
        plan = self.plan_by_key.get(key)
        self.name_var.set(app.name)
        self.meta_var.set(f"{EMULATOR_LABEL.get(app.type, app.type)}  |  {app.category}")
        self.desc_var.set(app.description or "(no description)")

        notes = []
        if plan is not None:
            notes += [f"! {problem}" for problem in plan.problems]
            notes += [f"~ {warning}" for warning in plan.warnings]
        self.problem_var.set("\n".join(notes))
        self.launch_btn.configure(state="disabled" if (plan and not plan.ok) else "normal")

    # -- Launching ---------------------------------------------------------
    def launch(self) -> None:
        key = self._selected_key()
        if key is None:
            return
        app = self.manifest.apps[key]
        plan = emulators.build_plan(app, self.manifest)
        if not plan.ok:
            messagebox.showwarning("Cannot launch", "\n".join(plan.problems))
            return

        label = EMULATOR_LABEL.get(app.type, app.type)
        self.log_line(f"\n==> Launching {app.name} ({label})")
        self.log_line(f"    {plan.command_line()}")
        self.launch_btn.configure(state="disabled")
        threading.Thread(target=self._run_plan, args=(plan,), daemon=True).start()

    def _run_plan(self, plan: emulators.LaunchPlan) -> None:
        try:
            process = emulators.spawn(plan)
        except OSError as exc:
            self.log_queue.put(f"[error] could not start emulator: {exc}")
            self.log_queue.put("__DONE__")
            return

        self.log_queue.put(f"[pid {process.pid}] started")
        if process.stdout is not None:
            for line in process.stdout:
                self.log_queue.put(line.rstrip("\n"))
        code = process.wait()
        self.log_queue.put(f"[pid {process.pid}] exited with code {code}")
        self.log_queue.put("__DONE__")

    def _pump_log(self) -> None:
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if item == "__DONE__":
                if self._selected_key() is not None:
                    self._show_details()
                continue
            self.log_line(item)
        self.root.after(120, self._pump_log)

    def log_line(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # -- Buttons -----------------------------------------------------------
    def reload(self) -> None:
        try:
            self.manifest = load_manifest(self.manifest.path)
        except ManifestError as exc:
            messagebox.showerror("Manifest error", str(exc))
            return
        self.refresh()
        self.log_line("Manifest reloaded.")

    def check(self) -> None:
        self.log_line("\n== Emulator check")
        for _kind, label, path in emulators.emulator_status(self.manifest):
            if path:
                self.log_line(f"   {label}: found at {path}")
            else:
                self.log_line(f"   {label}: NOT FOUND")
        self.log_line("== Application check")
        for app in self.manifest.apps.values():
            plan = emulators.build_plan(app, self.manifest)
            self.log_line(f"   [{'OK' if plan.ok else '!!'}] {app.key}")
            for problem in plan.problems:
                self.log_line(f"        - {problem}")
            for warning in plan.warnings:
                self.log_line(f"        ~ {warning}")


def main(manifest_path: Optional[str] = None) -> int:
    """Entry point: open the dashboard window."""
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.2)
    except tk.TclError:
        pass

    try:
        manifest = load_manifest(manifest_path)
    except ManifestError as exc:
        root.withdraw()
        messagebox.showerror("Manifest error", str(exc))
        root.destroy()
        return 1

    Dashboard(root, manifest)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
