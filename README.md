# Time Capsule — a manifest-driven retro software dashboard

Run **DOS and Windows 95/98/XP software directly on your own machine**, through
Wine and DOSBox-X, so legacy games and applications get **real GPU and 3D
acceleration** instead of the 2D-only adapter a virtual machine would give them.

A single JSON file — [`manifest.json`](manifest.json) — is the "app index" of
the capsule. Drop a title's files into `data/`, describe it in the manifest, and
it appears in the CLI and in the graphical dashboard.

```bash
python launcher.py list          # what is in the capsule
python launcher.py check         # are the emulators and files present?
python launcher.py run doom_dos  # play
python dashboard.py              # or browse it graphically
```

## 🧭 Design

```
┌──────────────────────────────────────────────────────────────────────┐
│ HOST  (your operating system — the GPU is yours, natively)           │
│                                                                      │
│   manifest.json ──▶ launcher.py / dashboard.py                       │
│                          │  resolves paths, builds a command line    │
│                          ├──▶ wine  ──▶ Windows 95/98/XP titles       │
│                          │            (D3D → OpenGL/Vulkan on the GPU)│
│                          └──▶ dosbox-x ──▶ DOS titles                 │
│                                        (incl. 3dfx Voodoo emulation) │
│   data/  ◀── the content: games/, apps/, disc images                 │
└──────────────────────────────────────────────────────────────────────┘
```

- **`manifest.json`** — the source of truth: emulator settings plus one entry
  per application (`wine`, `dosbox` or `native`).
- **`timecapsule/`** — the Python package: `manifest.py` (parsing/validation)
  and `emulators.py` (turns an entry into a concrete command line).
- **`launcher.py`** — the command-line interface (`list`, `show`, `run`,
  `check`).
- **`dashboard.py`** — a Tkinter window with a searchable, categorised list,
  details pane and live process output.
- **`data/`** — the content folder, kept out of git.

Nothing about a title is hard-coded: absolute paths are resolved at launch time
and DOSBox-X configs are generated on the fly, so the capsule is portable
between machines.

## ✨ Features

| Feature | How it works here |
| ------- | ----------------- |
| **Real 3D** | Wine translates Direct3D to the host's OpenGL/Vulkan; DOSBox-X can expose a 3dfx Voodoo. No virtualised display adapter. |
| **Manifest driven** | Add a title by editing JSON — no Python changes. |
| **Two front ends** | A scriptable CLI and a Tkinter dashboard (categories, search, launch, live log). |
| **Per-title isolation** | Each entry can set its own `WINEPREFIX`, `WINEARCH`, working directory and environment. |
| **Portable configs** | DOSBox-X is driven with `mount`/`-c` lines, never baked-in absolute paths. |
| **Honest diagnostics** | `launcher.py check` verifies the emulators *and* every file an entry needs, and exits non-zero on a problem. |
| **Content stays local** | `data/` is git-ignored; the repository ships structure, not copyrighted files. |

## 📋 Requirements

- **Python 3.8+** (Tkinter only for the dashboard; the CLI never imports it)
- **Wine** — for `type: "wine"` entries
- **DOSBox-X** — for `type: "dosbox"` entries (`dosbox-x`, *not* plain DOSBox)

| Platform | Notes |
| -------- | ----- |
| **Linux** | Best supported. `python scripts/setup.py` installs both emulators. |
| **Windows** | DOSBox-X runs natively (winget installs it to `C:\DOSBox-X\`, which is *not* on `PATH` - see [known-issues.md](docs/known-issues.md#the-binary-is-installed-but-nothing-finds-it)). `type: "wine"` entries run natively too, through the `tools/bin/wine.cmd` shim that `setup.py --apply` writes: Windows already runs its own Win32 software, and on ARM64 it emulates x86/x64. Use `--wsl` only for the rare title that refuses to run on Windows itself. Installers (`msiexec`) also run natively and raise a UAC prompt. |
| **macOS** | Not covered by `setup.py`: Homebrew can supply DOSBox-X; Wine support is the weakest here. |

### Installing the emulators

`python scripts/setup.py` targets the four hosts this project supports — Linux
and Windows, on x86_64 or ARM64 — and uses whatever the machine already has: the
distribution's package manager (`apt`, `dnf`, `pacman`, `zypper`, `apk`),
Flatpak, winget, or the projects' portable downloads. On Windows it also writes
a `tools/bin/wine.cmd` shim, because Windows runs Win32 software itself.

| Flag | Effect |
| ---- | ------ |
| `--check` | Report what is installed; change nothing. |
| `--dry-run` | Print the route that *would* be used. |
| `--apply` | Write the binaries it found into `manifest.json`. |
| `--only` | Set up one emulator only: `all`, `wine` or `dosbox`. |
| `--wsl` | (Windows) Put real Wine inside WSL2 instead. |
| `--portable` | (Windows) Prefer portable ZIPs over installers. |
| `--no-hangover` | (ARM64 Linux) Skip the ~300 MB Hangover download. |

## 🚀 Quick start

```bash
git clone <your-fork> time-capsule
cd time-capsule

# 1. Install the emulators (Linux or Windows, x86_64 or ARM64)
python scripts/setup.py --apply
#    ./scripts/setup.sh is the same on Linux, scripts\setup.bat on Windows

# 2. See what the capsule knows about
python launcher.py list
python launcher.py check        # verifies emulators + files

# 3. Add your content, then launch
python launcher.py run submarine_titans
```

Ship files into `data/games/<key>/` (or `data/apps/<key>/`) matching the
`path_relative_to_data` in the manifest — see [`data/README.md`](data/README.md).

## 🖥️ The dashboard

```bash
python dashboard.py                 # add --manifest PATH for another index
```

The window shows every application grouped by category, with a filter box, a
details pane (type, emulator, problems) and an output pane that streams the
launched process's stdout. Entries whose files are missing are listed in red and
cannot be launched; **Reload** re-reads the manifest after you edit it, and
**Check** prints the same diagnostics as the CLI.

### Four ways to open it

| Platform / taste | Command |
| ---------------- | ------- |
| Any, directly | `python dashboard.py` |
| Any, through the CLI | `python launcher.py dashboard` |
| Windows, double-clickable | `scripts\dashboard.bat` (finds `py` or `python` on its own) |
| Linux / macOS | `./scripts/dashboard.sh` (or `python3 dashboard.py`) |

All of them accept `--manifest PATH` if you keep a second index (for example one
manifest per collection). Nothing else is needed: the dashboard reads
`manifest.json`, resolves every path and builds the same command lines the CLI
would print.

### What the window gives you

| Control | What it does |
| ------- | ------------ |
| **Search** | Filters as you type, matching an entry's name, key and description. |
| **Category** | `All` or a single category (`games`, `apps`, ...). |
| **Reload** | Re-reads `manifest.json` - use it after adding a title or editing an entry. |
| **Check** | Prints the CLI's diagnostics (emulators plus every file an entry needs) into the output pane. |
| **Details** | Name, emulator, category, description, and any problem or warning for the selected entry. |
| **Launch** | Runs the selected entry (double-clicking a row does the same) and streams its output below. |
| **Output** | The live log: the exact command line, the pid, and whatever the program prints. |

Red rows are entries whose files are missing: the details pane names exactly what
is absent and **Launch** stays disabled until it is in place. That is all
`Setup needed` means - never that an entry is broken.

## 📁 Repository layout

```
.
├── manifest.json              # the app index: settings + apps
├── launcher.py                # CLI: list / show / run / check / dashboard
├── dashboard.py               # Tkinter front end
├── timecapsule/
│   ├── manifest.py            # parsing, validation, path resolution
│   └── emulators.py           # LaunchPlan + Wine / DOSBox-X / native builders
├── data/                      # content (git-ignored, structure tracked)
│   ├── README.md
│   ├── games/<key>/           # e.g. games/doom/DOOM.EXE, DOOM1.WAD
│   └── apps/<key>/            # e.g. apps/encarta_2000/Encarta.exe
├── scripts/
│   ├── setup.py / .sh / .bat  # install Wine + DOSBox-X
│   ├── run.sh / .bat          # wrapper for launcher.py
│   ├── dashboard.sh / .bat    # wrapper for dashboard.py
│   └── new_app.py             # scaffold a folder + manifest entry
├── tools/                     # emulators setup.py placed here (git-ignored)
└── docs/
    ├── configuration.md       # full manifest.json reference
    ├── known-issues.md        # Wine / DOSBox-X troubleshooting
    └── media-sources.md       # where content comes from
```

## ➕ Adding a title

1. Copy the title's folder into `data/games/<key>/` or `data/apps/<key>/`.
2. Register it — either run the scaffolder:

   ```bash
   python scripts/new_app.py my_game --name "My Game" --type wine \
       --category games --command MYGAME.EXE --description "Win95 puzzler"
   ```

   or add an entry to `manifest.json` by hand:

   ```jsonc
   "my_game": {
     "name": "My Game",
     "type": "wine",                 // wine | dosbox | native
     "category": "games",
     "command": "MYGAME.EXE",
     "args": "",
     "path_relative_to_data": "games/my_game",
     "description": "Win95 puzzler"
   }
   ```

3. Verify with `python launcher.py check`, then launch it.

DOS entries need no `dosbox.conf`: the launcher mounts the folder and runs the
command. Supply `"config": "dosbox.conf"` only when you want to tune video,
sound or Glide yourself.

## 🛠️ Commands

| Command | Purpose |
| ------- | ------- |
| `python launcher.py` | List every application, grouped by category. |
| `python launcher.py list` | Same, with emulator, category and readiness. |
| `python launcher.py show <key>` | Print the exact command line without running it. |
| `python launcher.py run <key> [-- args]` | Launch the title (extra args are appended). |
| `python launcher.py check` | Verify emulators and files; exits non-zero on failure. |
| `python launcher.py dashboard` | Open the graphical front end. |
| `python dashboard.py` | The graphical front end directly. |
| `python scripts/setup.py [--check]` | Install (or just report) Wine + DOSBox-X for this host. |

All commands accept `--manifest PATH`; `$TIMECAPSULE_MANIFEST` does the same.

### The same commands as wrappers

Handy for shortcuts, scheduled tasks and bookmarks:

| Wrapper | Equivalent | Notes |
| ------- | ---------- | ----- |
| `scripts\run.bat <args>` | `python launcher.py <args>` | Picks `py` or `python`, then runs from the repository root. |
| `scripts\dashboard.bat` | `python dashboard.py` | Double-clickable; extra arguments pass through. |
| `./scripts/run.sh <args>` | `python3 launcher.py <args>` | Uses `$PYTHON` if you export one. |
| `./scripts/dashboard.sh` | `python3 dashboard.py` | |
| `scripts\setup.bat` / `./scripts/setup.sh` | `python scripts/setup.py` | Installs or repairs the emulators. |

## 📚 Documentation

- **[docs/configuration.md](docs/configuration.md)** — every `manifest.json`
  field, with worked examples.
- **[docs/known-issues.md](docs/known-issues.md)** — Wine black windows, missing
  DirectX runtimes, Glide/3dfx, audio, multi-disc installers, `msiexec` reboot
  surprises, Tkinter, WSL2 tips.
- **[docs/media-sources.md](docs/media-sources.md)** — CD/ISO/floppy images, where
  to find them, and how to feed them to the capsule.
- **[data/README.md](data/README.md)** — the content layout, including titles that
  have to be installed from their own discs.
- **`data/apps/encarta_2005/NOTES.md`** — the full write-up of the four-CD
  Encarta 2005 install: MSI flags, disc merge, verification.

## 🧾 History

The first iteration of this repository booted Windows inside a Docker container
running QEMU, reachable over VNC. That gave perfect isolation but only a
software-emulated graphics adapter — poor for anything 3D. The project has since
been re-centred on running the emulators **on the host** behind a manifest and a
dashboard, which is what gives you the real GPU. The Docker/QEMU scaffolding,
the `host_share/` drop zone and the old `start`/`stop`/`reset`/`vm` scripts have
been removed as part of that refactor.

## 📜 License & legal

See [LICENSE](LICENSE). This project ships **no** Microsoft, DOS or game files —
only tooling, placeholders and documentation. Supply your own legally obtained
media.

## 🧪 Worked example: Encarta 2005 from four CDs, no disc prompts

`data/apps/encarta_2005/` is the reference case for a *disc-based* title, and its
[NOTES.md](data/apps/encarta_2005/NOTES.md) records every finding. The shape of it:

1. **Extract the four ISOs** into one folder per disc:

   ```powershell
   tar -xf data\apps\encarta_2005\media\L05EDXRCD1.iso -C data\apps\encarta_2005\extracted\disc1
   ```

2. **Merge them into a single install source.** This package's MSI leaves the
   `Media.Source` column empty for all four media rows, so Windows Installer looks
   for disc 2, 3 and 4 *in the same folder as the `.msi`*. Hard links make the
   merge free (the three later discs repeat 29 byte-identical files, so nothing is
   overwritten): `data/apps/encarta_2005/source/` is 594 files at ~0 extra bytes.

3. **Install into the capsule** with the manifest entry **Encarta 2005 (setup)**
   (it runs `install.cmd`, which is `msiexec` with `INSTALLDIR=...\program`,
   `ADDLOCAL=ALL` for the 2 GB "copiar en el disco duro" content pack, and
   `REBOOT=ReallySuppress`):

   ```bat
   msiexec /i source\L05EDXRC.MSI INSTALLDIR=program ADDLOCAL=ALL ^
           INSTALLIE=0 SUPPRESSWMP=1 SUPPRESSSHORTCUT=1 REBOOT=ReallySuppress /qb
   ```

4. **Run it** from the dashboard entry **Microsoft Encarta 2005**. Because the
   content pack is on disk, no disc is ever requested.

Two traps worth knowing before you repeat this with another title:

- Without `REBOOT=ReallySuppress` the package *restarts the machine* when it
  finishes, and it returns **1641** (= success, reboot initiated), which a naive
  `ERRORLEVEL` check reads as a failure. See
  [known-issues.md](docs/known-issues.md#the-installer-rebooted-my-machine).
- `ADDLOCAL=ALL` is what allows a disc-free run; a plain install that skips the
  content pack keeps asking for the CDs. If a title only installs from its discs,
  `subst` the extracted folders onto drive letters instead.

Afterwards `python launcher.py check` reports both Encarta entries as ready, and
removing it again is just the registered product's uninstaller
(`msiexec /x {054500C0-64A6-4248-A026-9745C1E9E159}`).

