# Where to find media (ISOs, Encarta, era software)

This project ships **no** software: you supply the installation media and the
period content (see [LICENSE](../LICENSE)). This page is a map of where the
1993–2003 catalogue lives today and, more importantly, *how to feed it to the
capsule* without hitting the traps this container has.

> **Legality, honestly.** Windows 95/98/ME/2000/XP left support years ago and
> have not been sold for a long time. The archives below host them as
> *preservation* material, product keys included, and they are the de-facto
> libraries the retro-computing community uses; whether that is covered by your
> local law is your call. If you still have a retail CD, an MSDN/Technet
> subscription copy, or a volume-licence ISO from work, that is the cleanest
> source — and a volume licence avoids XP's activation dance.
> The *fully legal* alternatives are listed under
> [Games](#games) and [Shareware & freeware](#shareware--freeware).

> **A note on the flags below.** This page grew out of the project's first
> iteration, which booted Windows inside a Docker/QEMU container. Only the
> *sources* it lists are timeless; anything that mentions `ISO_PATH`,
> `EXTRA_ISOS`, `EXTRA_QEMU_ARGS`, `DISK_SIZE`, `GUEST_OS`, `VGA_TYPE`,
> `CPU_CORES`, `NIC_MODEL`, `BOOT_ORDER`, `host_share/`, `install_apps.bat`,
> `scripts/reset.bat` or "the guest / the container" describes that removed
> setup. The current workflow is
> [How media reaches the capsule](#how-media-reaches-the-capsule), and the worked
> multi-disc example is the *Worked example: Encarta 2005* section of
> [the README](../README.md).

## How media reaches the capsule

There is no share, no boot ISO and no container: media are copied into the title's
own folder under `data/`, and the manifest entry points at whatever ends up
running them.

| Kind of media | What to do | Notes |
| ------------- | ---------- | ----- |
| Files a title runs as-is (DOS games, loose Win9x apps) | Copy the folder to `data/games/<key>/` or `data/apps/<key>/` and point `path_relative_to_data` at it | See [`data/README.md`](../data/README.md) |
| An installer (`setup.exe`, `.msi`) | Keep the media in `media/`, unpack it to `extracted/`, merge the discs into `source/`, install into `program/`, and register the installer as a second manifest entry | The multi-disc recipe below |
| A CD that is *checked at runtime* | Unpack it and `subst` it onto a drive letter, or install the title's full/content-pack option so the disc is never needed | A disc check wants the original volume label |
| A disc image bigger than you need to keep | Keep it out of `data/`, or delete the ISOs once installed | `data/` is git-ignored either way |

### Extracting a disc image

A plain `.iso` (ISO9660/Joliet) unpacks with the `tar` that Windows 10/11 and
Linux already ship - no extra tool, and long file names survive:

```bash
tar -xf media/L05EDXRCD1.iso -C extracted/disc1    # Linux / macOS
tar -xf media\L05EDXRCD1.iso -C extracted\disc1     # Windows (bsdtar)
```

For `.bin`/`.cue`, CloneCD (`.ccd`/`.img`) or Alcohol (`.mds`) images, use a tool
that understands the format (`bchunk`, `7z`). Converting a *protected* disc
(SafeDisc/SecuRom, roughly 1997-2006) to a plain ISO throws away the very bytes the
disc check looks for, so for those: install a no-CD patch, or keep the original
image and let a drive-letter emulator serve it.

### Multi-disc sets: merge the discs, install once

Extract every disc into `extracted/disc1`..`disc4`, then merge them all into
`source/`. Windows Installer resolves each media row through the MSI's
`Media.Source` column, and many packages leave that column **empty** - which means
"look for disc 2/3/4 in the same folder as the `.msi`". One merged folder therefore
removes every prompt, and the merge costs nothing:

```powershell
# Windows: hard links; the later discs only repeat a few byte-identical files
New-Item -ItemType HardLink -Path "source\CONTENT\X.EIT" -Target "extracted\disc2\CONTENT\X.EIT"
```
```bash
# Linux / macOS
cp -l extracted/disc2/* source/
```

Encarta 2005 (four CDs, `L05EDXRC`) is the worked case: 594 files in `source/`, a
2 GB content pack copied into `program/` by `ADDLOCAL=ALL`, and two manifest
entries - one to install, one to run. Every trap it exposed is written up in
[known-issues.md](known-issues.md) and in
[`data/apps/encarta_2005/NOTES.md`](../data/apps/encarta_2005/NOTES.md), including
the `REBOOT=ReallySuppress` that stops `msiexec` restarting the machine.

## Operating systems

| Source | What it has |
| ------ | ----------- |
| **WinWorldPC** (<https://winworldpc.com>) | The single best first stop: DOS 6.22, Win 3.1/95 (incl. OSR2.x), 98/98 SE, ME, NT 4, 2000, XP (Home/Pro, SP0–SP3, volume licence), plus Office, Plus! packs and era utilities. Every download lists checksums and install notes, and keys are published with the discs. |
| **Internet Archive** (<https://archive.org>) | Search the `Software Library` for "Windows 98 Second Edition", "Windows 95 OSR2", "Windows XP Professional SP3"… Item descriptions usually carry the product key; prefer items with a checksum file and several mirrors. |
| **Vetusware** (<https://vetusware.com>) | Large legacy OS + application library (free account). Good for the *application* era: Office 97, Works, Publisher, Encarta-adjacent CDs. |
| **betasarchive.org** / BetaWiki | Pre-release Windows builds, if you want the capsule to feel genuinely "1995 in development". Fun, unstable, not for daily use. |

Verify what you downloaded: WinWorld prints MD5/SHA1, archive.org items often ship
a `checksums.md5`, and [Redump](http://redump.org) `.dat` files cover
disc-exact copies. The Wayback Machine still holds Microsoft's own old
hash lists for MSDN/volume media.

### Which Windows, for which mood

| Goal | Install | Why |
| ---- | ------- | --- |
| The true 1995 feel | **Windows 95 OSR2** | 256 MB RAM / 2 GB disk; DOS-mode games, no USB, IE3/4, Netscape 3 |
| **Recommended sweet spot** | **Windows 98 SE** | DOS *and* Windows games, DirectX 8.1, IE5.5, drivers for AC97/USB, Encarta 98/99. Keep RAM ≤ 512 MB: 98 SE gets unstable above that. |
| Encarta 2000+ and late games | **Windows 2000 Pro (SP4)** | NT stability, USB mass storage, Encarta Reference Library 2001–2003 |
| Run everything up to 2005 | **Windows XP SP3** | The last Windows with decent DOS-game support. |

Practical notes:

Practical notes:

- **Size the disk at creation.** Decide before you install: a full games/Encarta
  library wants 12–20 GB, a 95/98-era build is happy with 2–4 GB.
- **Install the OS first**, then bring the content in. Budget real time for it on
  9x-era media - it is an hour of clicking, not a five-minute wizard.
- **Non-bootable 95/98 upgrade discs** exist (the OEM/retail "full" versions boot;
  upgrade media often does not). Boot from a floppy image and run setup from there.
- Reinstalling later: hold a key at the boot prompt (or change the boot order) so
  the CD wins over the installed system.

### What each of the two can and cannot run

| Era / type of software | Windows 98 SE | Windows XP SP3 |
| ---------------------- | ------------- | -------------- |
| 1981–1995 DOS games | **Native DOS, real Sound Blaster, VESA modes — best case** | NTVDM only: no sound-card access, poor VESA support → most titles need DOSBox-X (or VDMSound for simple ones) *inside* the guest |
| 1995–2000 Windows games & apps (Win32) | ✅ | ✅ (rare 16-bit installers may want compatibility mode) |
| Windows 3.x-era / 16-bit apps, DOS utilities | ✅ natively | ✗ mostly (NTVDM is limited) |
| 2000–2008 software (Office XP/2003/2007, Photoshop, .NET 2.0, IE7/8, WMP 11) | ✗ | ✅ |
| 2001–2008 games, and disc DRM (SafeDisc/SecuROM 2000–2006) | ✗ — those DRM versions refuse 9x | ✅ |
| Encarta | '94–'99 (+ 2000 with patience) | 2000–2003, plus '94–'99 |
| USB mass storage | needs a driver; no generic support | ✅ built in |
| NTFS, disks over 137 GB | ✗ FAT32 only | ✅ |
| Comfortable RAM | ≤ 512 MB | 1024–2048 MB |

**Bottom line.** XP SP3 wins on *nominal* range (about 1995–2008) and is the
only one of the two that can run the 2000+ catalogue; Windows 98 SE owns
everything before 1995 and is the only one that runs the DOS library **natively
with working sound**. For this capsule, a **games-first** shelf is better served
by 98 SE, while a **software-first** shelf (Encarta 2002+, Office, browsers,
utilities) belongs on XP with DOSBox-X added for the DOS side. None of that
constrains the *host*: the capsule runs the emulators natively, which is exactly
what the 2001–2008 3D titles and the later Encarta sets need.

Two notes for either choice:

- **Windows 98 SE is a uniprocessor OS** - a second CPU is simply unused, so do
  not size a machine around it.
- **Give 98 SE a real display driver.** Out of the box it offers a generic 2D
  driver at low colour depth; the Cirrus driver it ships usually reaches a better
  resolution and colour depth. A 3D-era title is better served by the capsule's
  native route than by a 2D-only virtual adapter either way.

Both systems can coexist on one host (a VM alongside, or a second machine) if you
would rather not choose.

## Encarta and the encyclopedia shelf

All of these are **CD-ROM products**, which is the main practical constraint:
feed them as ISOs (see above) rather than as loose files in the share.

| Title | Notes |
| ----- | ----- |
| Encarta '94 / '95 / '96 / '97 / '98 (Deluxe) | The *classic* Encarta: low-res video, the **MindMaze** quiz game. 98 Deluxe shipped on 2 CDs. Happiest on Windows 95/98. |
| Encarta Encyclopedia 99 (2 CDs) / Deluxe 2000 | Prettier UI, wants IE5+ / Media Player / DirectX. 2000 still runs on 98 SE, better on 2000/XP. |
| Encarta Reference Library 2001 / 2002 / 2003 | The DVD/CD-ROM era: Windows 2000/XP, DirectX 8+, Media Player 7+. |
| Encarta Africana, Encarta Kids, Encarta World English Dictionary | Same installer family, same era shelf. |

Install tips:

- Choose the **full installation** when offered — it copies the media into the
  install folder, so the disc is not needed at runtime. Encarta 2005 in this capsule
  was installed exactly that way: the `CHD` ("copiar en el disco duro") feature via
  `ADDLOCAL=ALL` adds 1.29 GB of content and no disc is ever requested.
- The 2005 set is **four CDs**, and its MSI looks for discs 2–4 in the *same folder
  as the `.msi`*, so merge them before installing — see
  [How media reaches the capsule](#how-media-reaches-the-capsule) and
  [`data/apps/encarta_2005/NOTES.md`](../data/apps/encarta_2005/NOTES.md) for the
  exact commands, including the `REBOOT=ReallySuppress` that stops the installer
  rebooting the machine at the end.
- If a setup *insists* on the original disc (volume label / CD check), unpack it
  and hand the folder a drive letter:
  `subst E: "<...>\extracted\disc2"`. A plain folder has no ISO9660 label, but the
  substituted letter gets the files to the installer regardless.
- Reading Encarta's tens of thousands of files straight off an image is slow. That
  is why the content pack is copied to disk during the install — a one-time cost,
  after which the title starts instantly.

Neighbouring titles from the same shelf, all easily found in the same archives:
**Microsoft Bookshelf 98**, **Cinemania** 95/96, **Microsoft Dinosaurs**,
**Dangerous Creatures**, **Musical Instruments**, **Ancient Lands**,
**Grolier Multimedia Encyclopedia** 1998/1999, **World Book** 1998/2000,
**Compton's Interactive Encyclopedia** 1998, **Encyclopaedia Britannica**
1999/2001/2002, **Encarta World Atlas** / **3D Atlas** / **Microsoft Streets &
Trips 98/2000** (the pre-GPS era).

## Educational software

Two ways to find it: browse the **collections**, or search by the **publisher**
from the back of the box (much faster — a publisher name plus a year finds most
era titles instantly).

| Collection | Notes |
| ---------- | ----- |
| archive.org → `CD-ROM Software Library` | Tens of thousands of archived CD images: encyclopaedias, reference, edutainment, magazine cover discs. |
| archive.org → `Software Library: MS-DOS` / `K-12 Educational Software` | Flat-file titles that copy straight into `data/games/<key>/`. |
| archive.org → magazine/cover discs | PC Gamer, PC Zone, Computer Gaming World, ZDNet/CNET, "Windows 95 CD Sampler" — the way software actually travelled in the 90s. |
| Vetusware / MyAbandonware | Both have an education category; MyAbandonware tags "for kids". |
| eXoDOS / eXoWin3x | Curated packs *with manuals, screenshots and metadata* — worth mining even if you only take a few titles. |

Publisher → era titles (use these as search terms):

| Publisher | Titles |
| --------- | ------ |
| Broderbund | *Where in the World/USA/Time is Carmen Sandiego?*, *Oregon Trail*, *Kid Pix*, *Just Grandma and Me* (Living Books), *Print Shop* |
| MECC / The Learning Company | *Number Munchers*, *Word Munchers*, *Oregon Trail II/3rd ed.*, *Reader Rabbit*, *The ClueFinders*, *Zoombinis* |
| Davidson | *Math Blaster*, *Reading Blaster*, *Word Blaster* |
| Knowledge Adventure | *JumpStart* series, *3D Body Adventure* |
| Edmark | *Sammy's Science House*, *Millie's Math House*, *Thinkin' Things*, *Mighty Math* |
| Humongous Entertainment | *Putt-Putt*, *Freddi Fish*, *Pajama Sam*, *Spy Fox*, *Backyard Sports* |
| DK Multimedia | *Eyewitness*, *The Way Things Work*, *My First Amazing Dictionary*, *The Ultimate Human Body* |
| Microsoft Home | *Magic School Bus* series, *3D Movie Maker*, *Creative Writer*, *Fine Artist* — plus Encarta above |
| Scholastic / Disney / Living Books | *The Magic School Bus*, *Animated Storybook*, *Arthur's Teacher Trouble* |
| Sierra / National Geographic | *Mixed-Up Mother Goose*, *Dr. Seuss*, *EcoQuest* / *Mammals*, *Picture Atlas of the World* |

Typing and language drills of the era: *Mavis Beacon Teaches Typing*, *Typing
Instructor Deluxe*, *Mario Teaches Typing*, Hyperglot's *Learn to Speak*,
*Transparent Language*, *Berlitz Think & Talk*.

Two things you will want alongside the software:

- **Manuals**: archive.org items usually include the scanned documentation;
  [replacementdocs](https://www.replacementdocs.com) covers the games.
- **Drivers**: for 95/98, [The Retro Web](https://theretroweb.com),
  the VOGONS driver archive and PhilsComputerLab's driver packs.

## Games

| Source | Notes |
| ------ | ----- |
| archive.org → `MS-DOS Games` | ~7,000 titles, playable *in the browser* to preview them, with the files to download for your guest. |
| archive.org → `Classic PC Games`, `Software Library: Windows` | Windows-era titles, shareware compilations, cover discs. |
| MyAbandonware / Old-Games.ru / OldGamesDownload | Large DOS + Windows libraries sorted by year; OldGamesDownload ships pre-configured installers. |
| eXoDOS / eXoWin3x + Total DOS Collection | Preservation-grade and curated (full eXoDOS is ~500 GB, but single titles can be pulled out). |
| [Redump](http://redump.org) | Disc-exact images for the CD-based games — the ones that *check the CD*. |
| GOG / Steam / Zoom Platform | Paid, pre-patched, DRM-free re-releases that run on the **host**. Always check here first (see below). |

**Games that insist on the CD** (Red Alert, Warcraft II, Myst, Riven, Tomb
Raider, most 1997–2000 releases) will not accept a folder copy: mount the ISO as
described above. *Myst* and *Riven* additionally want QuickTime, usually on the
same disc.

### Check for a re-release, then check the disc format

**Search the store before you search the abandonware sites.** A surprising
number of these titles have been re-released pre-patched and DRM-free, and those
builds run on the *host* — no guest to install, no driver hunting, no 2D-only
VGA ceiling. *Submarine Titans* is the example worth remembering: GOG has sold it
since December 2019 for $4.99, and that package is the final retail 1.1.0 with
the copy protection removed. GOG is the single best source for this era
(LucasArts, Sierra, Interplay, MicroProse, Strategy First, *Warcraft I/II*,
*Diablo*); Steam and the Zoom Platform cover much of the rest.

**Then look at what kind of image you actually downloaded.** A plain ISO9660
`.iso` is the easy case - see
[How media reaches the capsule](#how-media-reaches-the-capsule). Discs from about
1997–2001 are often *protected* and circulate as `.bin`/`.cue`, CloneCD
(`.ccd`/`.img`) or Alcohol (`.mds`) instead:

- A raw `.bin` cannot simply be renamed into an ISO: a MODE1/2352 track carries 16
  bytes of sync, 4 bytes of header and 288 bytes of ECC per sector, which would be
  handed to the installer as if they were user data.
- Converting `.bin`/`.cue` → `.iso` (e.g. with `bchunk`) produces a clean
  2048-byte-sector ISO **only for unprotected discs**. SafeDisc/SecuROM hide
  their protection in exactly the bytes that conversion discards, so the
  installer or the CD check then fails. A documented case: the retail
  *Submarine Titans* disc installs from its BIN/CUE but dies with an installer
  error once it is converted to a plain ISO.
- When the disc *is* protected, the options that work are (a) keep the original
  `.bin`/`.cue` and let a drive emulator that understands the protection serve it,
  or (b) install a **no-CD patch**, which is what most preservation releases
  already ship. Many titles install happily from a converted ISO and only check
  the disc at run time - and a full/content-pack install (as done for Encarta
  2005) sidesteps the check entirely.

**Mind the minimum resolution.** Most 1997–2002 titles draw at 800×600 or more
(*Submarine Titans* quotes 800×600 up to 1280×1024 on its own box), and a plain
640×480/16-colour mode makes them refuse to start. Force a mode through the
display settings (Wine: `winecfg` → Graphics) before blaming the game.

**Watch out for audio, too.** Odd startup failures on this generation of games are
often audio rather than media: the *Submarine Titans* "Internal error" is reported
to disappear once the machine has a sound card it has a driver for (AC97 on
2000/XP, SB16 on 95/98). Test a title with and without audio before you assume a
bad disc.

## Shareware & freeware

The most legally comfortable way to fill the capsule — these were *meant* to be
copied, and they are what a 1995 desktop actually looked like:

- **Shareware episodes**: Doom, Wolfenstein 3D, Commander Keen, Duke Nukem 3D
  (episode 1), Jazz Jackrabbit, Raptor, Crystal Caves, Monster Bash, Cosmo,
  Ken's Labyrinth, Blake Stone, Epic Pinball, Jill of the Jungle.
- **Freeware / free releases**: Tyrian 2000, One Must Fall 2097, Beneath a Steel
  Sky, Ultima IV, *Arena* and *Daggerfall* (Bethesda), *Command & Conquer* Gold
  and *Red Alert* (EA gave them away), ZZT, Grand Theft Auto 1 & 2.
- **Modern re-releases** whose *original game data* you can copy into the capsule:
  GOG (LucasArts, Sierra, Interplay, MicroProse, *Warcraft I/II*, *Diablo*),
  Steam (id, 3D Realms, *Age of Empires II*, *RollerCoaster Tycoon*,
  *Zoo Tycoon*), Zoom Platform.

## The early web inside an old build

A period Internet Explorer cannot speak TLS 1.2, so today's HTTPS-only web mostly
fails on it. Use the HTTP proxies built for retro browsers:

| Service | What it does |
| ------- | ------------ |
| **ProtoWeb** (<https://protoweb.org>) | Serves archived 1990s sites to IE4/5/6 over plain HTTP — the best "surf 1998" experience. |
| **The Old Net** (<https://theoldnet.com>) | Same idea, plus Gopher/BBS gateways. |
| **oldweb.today** | Browsing archived pages in an emulated browser — handy from the *host* to pick sites. |
| **Wayback Machine** | Direct deep links (`web.archive.org/web/1998id_/…`) when a site still answers over HTTP. |
| **Flashpoint** (BlueMaxima) | The late-90s/2000s Flash game archive, for the Shockwave era. |

The archived **Encarta MSN** site (1997–2009) lives in the Wayback Machine — a
nice "same encyclopaedia, on the web" contrast for the capsule.

## Checklist before you install

- **No spaces in media filenames.** Everything travels through the manifest and a
  command line, and `data/apps/Windows 98 SE/` is more trouble than it is worth
  (the same goes for DOSBox `mount` lines).
- **Unpack before you install.** A disc image on disk is archival; an installer
  wants the *extracted* files — see
  [How media reaches the capsule](#how-media-reaches-the-capsule).
- **Merge the whole set first.** Half a set means "insert disc 2" half-way through
  a twenty-minute install.
- **Check the hashes** of anything you download before installing it on top of a
  working capsule: WinWorld prints MD5/SHA1, archive.org items usually ship a
  `checksums.md5`, and [Redump](http://redump.org) `.dat` files cover disc-exact
  copies. The Wayback Machine still holds Microsoft's own old hash lists.
- **Install into the capsule**, not into `C:\Program Files`, so the manifest entry
  keeps working when the folder moves.
- **Expect a first-run wizard.** Plenty of 2000s titles show a registration or
  "system check" wizard once; click through it rather than assuming the title
  failed. (Encarta 2005 is a case in point.)
- **Keep media out of git** — already handled: everything under `data/` and every
  `*.iso` is ignored, so `git status` stays clean and a 700 MB image never reaches
  a commit.




