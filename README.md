<p align="center"><img src="media/icon-400.png" width="96" height="96" alt="Forever Core icon"></p>

<h1 align="center">Forever Core</h1>

<p align="center">A library: the shared code every Forever addon needs. CurseForge and Wago install it alongside any Forever addon, and there is nothing to set up.</p>

<p align="center">
  <a href="https://github.com/cjber/forever-core/actions/workflows/ci.yml"><img src="https://github.com/cjber/forever-core/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/cjber/forever-core/releases"><img src="https://img.shields.io/github/v/release/cjber/forever-core" alt="Latest release"></a>
</p>

**Interface:** 16001 (WoW: Forever, live client folder `_forever_`, beta `_classic_beta_`)

## What it is

Forever Core is a library, not a feature addon. Every Forever addon requires it with `## Dependencies: ForeverCore`,
so the game loads it first and exactly one copy of each shared file runs. It has no settings page of its own. Your
Forever addons use it for:

- **One tracker column.** Every Forever addon adds its section to the same objective tracker. Scale it, lock it or
  drag it once, and every addon follows.
- **A bug report window.** Each addon's report command opens a ready-to-copy report with the version, the client
  build, the character, the place, recent errors and a log.
- **Forever Leaderboards.** Each addon can add its board to one shared window, opened from that addon, with weekly and
  all-time standings and a line on the unit tooltip.
- **The common chrome.** The minimap button, the quest log side tabs, the settings page drawing, the error journal and
  the debug log are shared once.

The column can wear an optional dark background from any section's right-click menu, drawn with the game's own tooltip
background art. It offers off, 25%, 50%, 75% or 100%, and starts off, so a player who reads the tracker fine over dark
terrain keeps the stock look.

## What it does not do

It draws no quest, route, profession or challenge sections of its own. Sections belong to the addon that owns the
feature: see the suite's ownership boundaries in `docs/handoff/boundaries.md`. Its shared code is added to an addon
through `ForeverCore.Register` and the modules on the `ForeverCore` table; see [`docs/adoption.md`](docs/adoption.md).
The shape every addon's own public API follows is in
[`docs/api-conventions.md`](docs/api-conventions.md).
A third-party addon reads the members it may rely on, and the suite's published APIs, in [`docs/api.md`](docs/api.md).

## Install

Players never install it by hand: CurseForge and Wago install it as a required dependency of every Forever addon. For a manual install, drop the
`ForeverCore` folder in `Interface/AddOns`. `/fcore` prints the column's anchors, heights and combat state, which is
the same diagnostic the addons print from their own slash commands.

## Development

The repo also owns a reusable offline UI mock renderer in [`tools/wowmock/`](tools/wowmock/README.md) and the Discord
release digest in [`tools/discord_digest.py`](tools/discord_digest.py).

## Credits

Forever Core is built on the game's own UI and the work of other addon authors, listed with every player who helped in
[THIRD_PARTY.md](THIRD_PARTY.md).

<!-- forever-credits:start -->

Thanks to iPulse, _spada, Darkwavez76, Naburiel, MrFIXlT, deathmvp1, berserkerlxl, Alex21xx, Torpdotorgx, dryzee, procque, Fareed and everyone who reported a bug or asked for a feature.

<!-- forever-credits:end -->

## Licence

GPL-3.0-or-later. See `LICENSE`.
