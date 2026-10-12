# Known issues & workarounds

The capsule deliberately runs on **real hardware**, not inside a VM: Wine
translates Direct3D to the host's OpenGL/Vulkan and DOSBox-X can hand a title a
3dfx Voodoo, so games get genuine GPU acceleration. That also means the usual
Wine/DOSBox-X rough edges apply. This page lists the ones you are most likely
to hit.

## The right environment (please read first)

| Platform              | Recommended setup                                                |
| --------------------- | ---------------------------------------------------------------- |
| Linux (native)        | Best case: Wine + DOSBox-X straight from the distribution.        |
| Windows 10/11         | DOSBox-X natively; Win32 titles natively through the `tools/bin/wine.cmd` shim; **real Wine via WSL2** only when a title refuses (WSLg gives display+GPU).|
| macOS (Intel/Apple)   | Wine + DOSBox-X via Homebrew. `setup.py` does not cover macOS.    |

On Windows, do **not** expect Wine to run on the Windows side — it needs a
Unix-like environment. `python scripts/setup.py --wsl` walks through the WSL2
route; Wine-type entries that stay on the Windows side run through the shim
described at the end of this page.

## "Emulator not found"

`python launcher.py check` reports which binaries are missing.

- Install them: `python scripts/setup.py` -- it covers Linux and Windows on
  x86_64 or ARM64, and knows about apt/dnf/pacman/zypper/apk, Flatpak, winget
  and portable ZIPs. Add `--check` to see what it would do first.
- If a binary lives outside `PATH`, give the absolute path in
  `settings.emulators.wine` / `settings.emulators.dosbox` - the Windows case just
  below is the one that catches everyone.

### The binary is installed but nothing finds it

On Windows, `winget install DOSBox-X.DOSBox-X` puts the binary in
`C:\DOSBox-X\dosbox-x.exe` and does **not** add it to `PATH`, so `python
launcher.py check` reports `DOSBox-X : NOT FOUND` even though it is installed and
runs fine by hand. Either add that folder to `PATH`, or point the manifest
straight at the file:

```jsonc
"settings": { "emulators": { "dosbox": "C:/DOSBox-X/dosbox-x.exe" } }
```

Forward slashes are fine, and `"tools/bin/wine.cmd"` is the Windows default for
`emulators.wine` - a relative path, resolved from the manifest's own folder.
- Flatpak builds have no `dosbox-x` command of their own. `setup.py` links them
  into `~/.local/bin`; by hand it is:

  ```bash
  ln -sf ~/.local/share/flatpak/exports/bin/com.dosbox_x.DOSBox-X ~/.local/bin/dosbox-x
  ```

  or put that export path directly into `settings.emulators.dosbox`.

## Wine

### ARM64 Linux needs an emulation layer *inside* Wine

An ARM64 build of Wine runs ARM64 Windows binaries, which is not what 9x-era
software is. `python scripts/setup.py` therefore offers **Hangover** (Wine plus
FEX/Box64) on aarch64 Debian/Ubuntu: it emulates x86 and x86_64 code while the
rest of Wine, and everything Unix, stays native. Use `--no-hangover` to decline
the ~300 MB download and install it yourself later.

### A window opens but stays black, or DirectX fails

Older titles frequently rely on redistributables that are not part of Wine:

```bash
winetricks d3dx9 vcrun6 vcrun2005 gdiplus
```

`d3dx9` covers most 2000s Direct3D 8/9 games, `vcrun6` the Visual C++ 6 runtime
that 90s software shipped.

### Forcing a 32-bit bottle

Windows 95/98-era software is usually 32-bit and some installers are 16-bit:

```jsonc
"wine_arch": "win32"
```

or globally, `"settings": { "wine": { "arch": "win32" } }`. The prefix is
created on first launch, so changing `arch` on an existing prefix makes Wine
refuse to start — delete the old prefix or point `wine_prefix` somewhere new.

### Software rendering / no 3D

Check that the host itself exposes 3D:

```bash
glxinfo -B | grep -i renderer     # OpenGL
vulkaninfo --summary | head       # Vulkan (needed by DXVK)
```

On WSL2 the GPU is passed through by WSLg; make sure your WSL kernel and GPU
drivers are current, and keep the capsule's `data/` inside the Linux file
system (`~/`) rather than `/mnt/c`, which is much slower and can break file
locking.

For Direct3D 8/9 titles that stutter or refuse to start:

```bash
DXVK_HUD=fps wine "<game>.exe"     # DXVK translates D3D9 → Vulkan
```

Wine ≥ 9 embeds DXVK/vkd3d builds for many setups; `winetricks dxvk` installs
them into a prefix when it does not.

### "The game asks for the CD"

Mount the image and point a Wine drive letter at the device or the mount point:

```bash
sudo mount -o loop,ro game.iso /mnt/cdrom
winecfg     # Drives → add D: → /mnt/cdrom
```

### Audio crackles or is missing

Check that the host session uses PipeWire/PulseAudio, then try the ALSA path:

```bash
WINEDLLOVERRIDES=winepulse.dll=d wine "<game>.exe"
```

## DOSBox-X

### 3dfx / Glide games report "no 3dfx card"

Glide emulation needs a video config that the capsule intentionally does not
generate. Add `dosbox.conf` next to the title and reference it from the
manifest:

```ini
[glide]
glide = true
voodoo = true
```

```jsonc
"config": "dosbox.conf"
```

Glide output uses the host GPU, so it will not work over a plain remote/headless
X session without a GL-capable display.

### "Illegal command" after mounting

The command name must exist **inside** the mounted folder and DOS-style names
are case-insensitive but whitespace-free. Check with
`python launcher.py show <key>` — the printed `-c` lines are exactly what
DOSBox-X will execute.

### Fullscreen / window size

Either set it in the app's `dosbox.conf`, or add a global switch:

```jsonc
"dosbox": { "extra_args": ["-fullscreen"] }
```

### Autoexec lines that re-open a menu

Some installers leave an autoexec that returns to the DOS prompt. Since the
launcher appends its own `-c` block last, your manifest `command` wins — set
`command` to the game's executable rather than relying on the config's
`[autoexec]` section.

## The tools themselves

### `ModuleNotFoundError: No module named 'tkinter'`

The dashboard needs Tkinter, which some minimal Linux installs omit:

```bash
sudo apt install python3-tk       # Debian/Ubuntu
sudo dnf install python3-tkinter  # Fedora
```

The `launcher.py` CLI never imports Tkinter, so `list`/`show`/`run`/`check`
keep working without it.

### The dashboard opens but shows no applications

It reads the manifest named on the command line, or the one found by walking up
from the working directory, or `$TIMECAPSULE_MANIFEST`. Print the resolved path
with `python launcher.py check` and compare it with the file you edited.

### Everything is listed as "Setup needed"

That label only means *the files are not in place yet* — a missing title folder
or a missing `command`. Copy the application into `data/<category>/<key>/` as
described in `data/README.md`, then reload the dashboard.

### Windows: "wine isn't recognised"

There is no Wine on the Windows side, and none is needed: Windows runs Win32
software itself, and on ARM64 it emulates x86/x64. `python scripts/setup.py
--apply` writes a pass-through shim at `tools/bin/wine.cmd` and points
`settings.emulators.wine` at it, so `type: "wine"` entries work unchanged.

Real Wine is only needed for the occasional title that refuses to run natively.
For that, use WSL2 (`python scripts/setup.py --wsl`) and keep the capsule's
content inside the Linux file system rather than under `/mnt/c`.

## Installing period software on Windows

These are the ones that actually bit us while putting Encarta 2005 in place; the
recorded details live in `data/apps/encarta_2005/NOTES.md`.

### The installer rebooted my machine

Symptoms: the install looks complete, then Windows restarts by itself; a wrapper
script reports an obscure failure code.

**Cause.** A Microsoft Installer package can *schedule a reboot* for its final
step. With `/qn` (silent) or `/qb` (basic UI) and no `REBOOT` property, `msiexec`
honours that scheduling **without asking**, and returns

| Code | Meaning |
| ---- | ------- |
| `0`    | Success. |
| `1641` | **Success** - and a reboot was initiated. |
| `3010` | **Success** - and a reboot is still required. |
| `1603` | Fatal error during installation (the real failure code). |

`1641` and `3010` are *success* codes, which is why a naive
`if not "%ERRORLEVEL%"=="0"` prints "[error]" on a perfectly good install.

**Fix.** Add `REBOOT=ReallySuppress` to the command line to forbid the restart
outright, and treat `1641`/`3010` as success in any wrapper:

```bat
msiexec /i "<pkg>.msi" INSTALLDIR="<capsule>\program" ADDLOCAL=ALL REBOOT=ReallySuppress /qb /l*v install.log
```

**After an interrupted install, just run it again.** Windows Installer is
transactional: it rolls back the failed attempt before starting the new one, so
there is nothing to clean up by hand. Confirm nothing is half-finished with
`Test-Path HKLM:\SOFTWARE\Microsoft\Windows\Installer\InProgress` (it should be
`False`) and check the tail of `install.log` for the returned code.

### A multi-disc installer keeps asking for the next disc

Most 90s/2000s sets ship one `setup.exe`/`.msi` plus three or four content CDs.
Windows Installer resolves every disc through the MSI's `Media.Source` column; in
many packages (Encarta 2005 included) that column is **empty for all rows**, which
means "look for disc 2, 3 and 4 in the same folder as the `.msi`".

- Extract **every** disc and merge them into one folder next to the installer
  (`data/apps/<key>/source/`). Discs repeat a handful of byte-identical files, so
  merging is lossless - use hard links to keep it free of extra disk usage:

  ```powershell
  New-Item -ItemType HardLink -Path "source\<file>" -Target "extracted\disc2\<file>"
  ```

- Installing from the merged folder removes every "insert disc 2" prompt. If a
  title still insists on a labelled original disc, hand its extracted folders
  drive letters with `subst E: "<capsule>\extracted\disc2"` and so on.
- Prefer the installer's **full / "copy to hard disk"** option. It is usually the
  largest feature, and skipping it (or skipping `ADDLOCAL=ALL`) is why a title
  keeps demanding a CD after a successful install.
- Per-machine packages (`ALLUSERS=1`) raise a **UAC prompt**; the launcher shim
  (`tools/bin/wine.cmd`) waits for the installer to finish, so a setup entry is
  fine to click from the dashboard. Verbose logging (`/l*v install.log`) next to
  the installer costs nothing and answers most questions later.

### The installer finished but nothing needs the disc - or still does

Re-run `python launcher.py check`. If the *run* entry is ready, the program is in
place; if the program then asks for a CD, the content pack was not installed (see
above). To start over: `msiexec /x {ProductCode}` (the product code is in
`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall`, or just use
Add/Remove Programs).

