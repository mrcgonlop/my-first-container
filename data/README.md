# `data/` — where the capsule content lives

Every application listed in `manifest.json` points at a folder *inside* this
directory, using the `path_relative_to_data` field. Keep the layout tidy:

```
data/
├── games/                 # interactive software
│   ├── submarine_titans/  #   SubTitan.exe + its data files
│   ├── doom/              #   DOOM.EXE, DOOM1.WAD, (optional) dosbox.conf
│   └── wolf3d/
└── apps/                  # productivity / reference software
    ├── encarta_2000/      #   Encarta.exe + its data
    └── encarta_2005/      #   the 4-CD set: media|extracted|source|program + NOTES.md
```

## Rules of thumb

- **One folder per title.** An entry's `command` is resolved *inside* its
  folder, so `"command": "DOOM.EXE"` means `data/games/doom/DOOM.EXE`.
- **`command` may point deeper than the root.** Forward slashes work, so a title
  installed into a sub-folder is simply
  `"command": "program/Biblioteca de Consulta Encarta 2005/Encarta.exe"`. When the
  program loads its data relative to itself, set `working_dir` to that same
  sub-folder - see [docs/configuration.md](../docs/configuration.md).
- **Relative paths only.** Use forward slashes (`games/doom`); the launcher
  normalises them for Windows.
- **No spaces in filenames** for DOS entries — DOSBox and DOS itself handle
  them poorly.
- **Optional per-app files** (e.g. a hand-tuned `dosbox.conf`, a `README.txt`
  you like) live next to the game and are referenced from the manifest.

## Titles that ship on discs

A title that has to be *installed* gets a few working folders of its own next to
the running program. `data/apps/encarta_2005/` is the reference implementation
(see its `NOTES.md`); the shape is:

```
data/apps/encarta_2005/
├── media/       # the ISOs, exactly as downloaded            (git-ignored)
├── extracted/   # one folder per disc, unpacked              (git-ignored)
├── source/      # all discs merged = the installer's source  (git-ignored)
├── program/     # where the installer put the software; the entry runs from here
├── install.cmd  # the installer, kept here so the entry stays relative
└── NOTES.md     # findings worth keeping: flags, traps, layout   (tracked!)
```

- **Everything heavy stays git-ignored** (`data/` is ignored apart from READMEs
  and `.gitkeep`), but `NOTES.md` is the kind of small text file worth tracking:
  it records *why* an install command looks the way it does.
- **Install into `program/`**, never into `C:\Program Files`: the manifest entry
  then keeps working after the capsule is copied elsewhere.
- **Merging multi-disc sets is the normal case.** Installers look for the later
  discs beside the `.msi`/`setup.exe`, so extracting every disc into one `source/`
  folder removes the "insert disc 2" prompts. Hard links make that free:

  ```powershell
  New-Item -ItemType HardLink -Path "source\<file>" -Target "extracted\disc2\<file>"
  ```

Everything under `data/` is ignored by git: the capsule ships the *structure*
and the *manifest*, never the copyrighted content. Only this README and the
`.gitkeep` placeholders are tracked.
