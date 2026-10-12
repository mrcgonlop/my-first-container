# Configuration reference — `manifest.json`

`manifest.json` is the **single source of truth** of the capsule. It has two
top-level keys: `settings` (how to find and drive the emulators) and `apps`
(one entry per title). The launcher reads it, resolves every path and hands the
entry to Wine or DOSBox-X; nothing is hard-coded in the Python.

```
manifest.json
├── settings      → emulator binaries, data folder, global Wine/DOSBox options
└── apps
    └── <key>     → one launchable title
```

Point the tools at a different file with `--manifest PATH` (CLI) or the
`TIMECAPSULE_MANIFEST` environment variable.

## `settings`

| Key                 | Default      | Meaning                                                     |
| ------------------- | ------------ | ----------------------------------------------------------- |
| `data_root`         | `"data"`     | Folder that holds the content, relative to `manifest.json`. |
| `emulators.wine`    | `"wine"`     | Wine executable (a name on `PATH`, or a path).              |
| `emulators.dosbox`  | `"dosbox-x"` | DOSBox-X executable.                                        |
| `wine.prefix`       | `""`         | Global `WINEPREFIX` used when an app does not set its own.  |
| `wine.arch`         | `""`         | Global `WINEARCH` (`win32` / `win64`).                      |
| `dosbox.extra_args` | `[]`         | Global switches appended to every DOSBox-X command line.    |

Every key is optional; the launcher fills in the defaults above.

`scripts/setup.py` installs both emulators on this machine and, with `--apply`,
writes the paths it found into `settings.emulators`. That is what you want when
a binary is *not* on `PATH`: a Flatpak export, a portable DOSBox-X ZIP, or the
`tools/bin/wine.cmd` shim used on Windows. Values may be absolute paths, or
relative to `manifest.json`.

## `apps.<key>`

`<key>` is a stable identifier (used on the CLI and as the tree key in the
dashboard). Fields common to **all** types:

| Field                   | Required  | Meaning                                                   |
| ----------------------- | --------- | --------------------------------------------------------- |
| `name`                  | no        | Display name (defaults to the key).                       |
| `type`                  | **yes**   | `wine`, `dosbox` or `native`.                             |
| `category`              | no        | Free-form grouping (`games`, `apps`, …); default `apps`.  |
| `description`           | no        | One line shown in the list and the dashboard.             |
| `path_relative_to_data` | **yes**   | Folder inside `data_root` holding the title.              |
| `command`               | see below | Executable inside that folder.                            |
| `args`                  | no        | Arguments appended to the command (quote-aware).          |
| `working_dir`           | no        | Working directory; defaults to the title's folder.        |
| `env`                   | no        | Extra env vars, e.g. `{"LANG": "en_US.UTF-8"}`.           |

### `type: "wine"` — Windows games/apps

| Field         | Meaning                                                              |
| ------------- | -------------------------------------------------------------------- |
| `command`     | **Required.** The `.exe` to run (e.g. `SubTitan.exe`).               |
| `wine_prefix` | Per-app `WINEPREFIX` (keeps conflicting titles in separate bottles). |
| `wine_arch`   | Per-app `WINEARCH` (`win32` is the common choice for 9x-era titles). |

The launcher runs `wine "<app folder>/<command>" <args>` with the working
directory set to the app folder (many 90s titles load data relative to it) and
`WINEPREFIX`/`WINEARCH` set from the app, then `settings.wine`.

### `type: "dosbox"` — DOS titles

| Field     | Meaning                                                       |
| --------- | ------------------------------------------------------------- |
| `command` | Optional program to run after mounting (e.g. `DOOM.EXE`).     |
| `args`    | Arguments for that program (e.g. `-iwad DOOM1.WAD`).          |
| `mount`   | Drive letter the folder is mounted as (default `C`).          |
| `config`  | Optional `dosbox.conf` in the app folder, passed with `-conf`.|

The launcher builds the command line dynamically, so a game's config never
contains absolute paths:

```
dosbox-x [-conf <app>/dosbox.conf] \
         -c "mount C <app folder>" -c "C:" \
         -c "DOOM.EXE -iwad DOOM1.WAD" \
         -c "exit"
```

`-c "exit"` closes DOSBox-X when the game quits. A `config` that is declared
but missing is only a warning — the launcher falls back to the generated
command line.

### `type: "native"` — host executables

`command` is **required**. Runs the program directly (useful on Windows, where
DOSBox-X and some apps run natively, or for a wrapper script). No emulator is
involved.

### Worked example: a title installed from its own media

Two entries, two jobs - one to *put the software in place*, one to run it. This is
how `encarta_2005` works, and it is the pattern to copy for any disc-based title
(replace the `wine` half with the real Wine binary on Linux):

```jsonc
"encarta_2005_setup": {
  "name": "Encarta 2005 (setup)",
  "type": "wine",                                    // the shim runs the .cmd
  "category": "apps",
  "command": "install.cmd",                          // installer kept in the title folder
  "path_relative_to_data": "apps/encarta_2005",
  "description": "Installs the 4 CDs into data/apps/encarta_2005/program"
},
"encarta_2005": {
  "name": "Microsoft Encarta 2005",
  "type": "wine",
  "category": "apps",
  "command": "program/Biblioteca de Consulta Encarta 2005/Encarta.exe",
  "path_relative_to_data": "apps/encarta_2005",
  "working_dir": "apps/encarta_2005/program/Biblioteca de Consulta Encarta 2005",
  "description": "Reference encyclopedia, 4-CD set - run the setup entry once first"
}
```

Three things this shows:

- **`command` may point into a sub-folder** of the title folder, not just a file
  at its root. It is resolved with `path_relative_to_data`, and forward slashes
  work on every platform.
- **`working_dir` matters when a title loads its data relative to itself.**
  `Encarta.exe` opens `DATADLX.AKC`, `CG.XML` and `ENCSPLSH.INI` from the current
  directory, so the entry points `working_dir` at the installed folder rather than
  leaving the default (the title folder, one level up).
- **An installer is just another entry.** Keeping the installer *inside* the title
  folder means the entry stays relative and the whole capsule can be moved; the
  setup entry is listed like any other app, so `check` reports whether it is ready
  too. It is skipped automatically if the media are absent - `check` says the
  installer's folder is missing, and the run entry is unaffected.

## Worked examples

```jsonc
{
  "settings": {
    "emulators": { "wine": "/usr/bin/wine", "dosbox": "dosbox-x" },
    "wine": { "prefix": "~/.wine-timecapsule", "arch": "win32" }
  },
  "apps": {
    // A Win95 RTS kept in its own Wine bottle.
    "submarine_titans": {
      "name": "Submarine Titans",
      "type": "wine",
      "category": "games",
      "command": "SubTitan.exe",
      "path_relative_to_data": "games/submarine_titans",
      "wine_arch": "win32",
      "description": "Real-time strategy game (Win95)"
    },
    // A DOS game: folder mounted as C:, launched from the command line.
    "doom_dos": {
      "name": "Doom (DOS)",
      "type": "dosbox",
      "category": "games",
      "path_relative_to_data": "games/doom",
      "mount": "C",
      "command": "DOOM.EXE",
      "args": "-iwad DOOM1.WAD",
      "description": "Classic FPS (DOS)"
    }
  }
}
```

## Adding a title

1. Drop the files into `data/<category>/<key>/`.
2. Add an entry to `apps` (or run the scaffolder):

   ```bash
   python scripts/new_app.py my_game --name "My Game" --type wine \
       --category games --command MYGAME.EXE --description "Win95 puzzler"
   ```

3. Verify: `python launcher.py check`, then `python launcher.py run my_game`.

## Diagnostics

| Command                         | What it does                                                     |
| ------------------------------- | ---------------------------------------------------------------- |
| `python launcher.py`            | Lists every app, grouped by category.                            |
| `python launcher.py check`      | Finds the emulators and every app's files; exits ≠ 0 on a problem.|
| `python launcher.py show <key>` | Prints the exact command without running it.                     |
| `python launcher.py run <key>`  | Launches the title.                                              |

