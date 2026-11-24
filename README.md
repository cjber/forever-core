<p align="center"><img src="media/icon-400.png" width="96" height="96" alt="ForeverCore icon"></p>

<h1 align="center">ForeverCore</h1>

<p align="center">A library for my own addons only (Adventure Guide, Shortest Path, SkillUp and the rest). It comes with those addons and needs no setup.</p>

<p align="center">
  <a href="https://github.com/cjber/forever-core/actions/workflows/ci.yml"><img src="https://github.com/cjber/forever-core/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/cjber/forever-core/releases"><img src="https://img.shields.io/github/v/release/cjber/forever-core" alt="Latest release"></a>
</p>

**Interface:** 16001 (WoW: Forever, live client folder `_forever_`, beta `_classic_beta_`)

## What it is

ForeverCore is a library, not a feature addon. Every Forever addon declares it with `## OptionalDeps: ForeverCore`,
so the game loads the standalone library first when installed. Each addon also ships with an embedded copy. It has no settings page of its own. Your
Forever addons use it for:

- **One tracker column.** Forever addons with a tracker section add it to the same column, a frame of its own that sits to
  the left of the game's quest tracker, top edges level, and follows it when you move that tracker in Edit Mode. Drag
  any section's header to put it anywhere; Lock in the header's right-click menu keeps it there. Scale it once, and
  every addon follows. It never changes the game's quest tracker.
- **A bug report window.** Each addon's report command opens a ready-to-copy report with the version, the client
  build, the character, the place, recent errors, a performance table and a log.
- **Debug capture.** `/forever debug on` turns on the client's own chat, combat and taint logs for a report and
  `/forever debug off` puts the client's settings back, so a player can attach what the report needs without a
  developer's addon.
- **Shared tabs, settings and logs.** Addons share the world map quest log tabs, settings layout, error journal and debug log.

The column can wear an optional dark background from any section's right-click menu, drawn with the game's own tooltip
background art. It offers off, 25%, 50%, 75% or 100%, and starts off, so a player who reads the tracker fine over dark
terrain keeps the stock look.

## Addon integration

Each section belongs to the addon that provides the feature. See the suite's
[ownership boundaries](docs/handoff/boundaries.md). Addons use the shared code through `ForeverCore.Register` and the
modules on the `ForeverCore` table; see
[`docs/adoption.md`](docs/adoption.md). The shape every addon's own public API follows is in
[`docs/api-conventions.md`](docs/api-conventions.md).
A third-party addon reads the members it may rely on, and the suite's published APIs, in [`docs/api.md`](docs/api.md).

## Install

The library comes with each Forever addon. To install the standalone library, drop the
`ForeverCore` folder in `Interface/AddOns`. `/fcore tracker` prints the column's anchors, heights and combat state, which is
the same diagnostic the addons print from their own slash commands.

## Development

The repo also owns a reusable offline UI mock renderer in [`tools/wowmock/`](tools/wowmock/README.md) and the Discord
release digest in [`tools/discord_digest.py`](tools/discord_digest.py). Every tool pin lives in `tools/toolchain.json` and is
installed by `.github/actions/toolchain` from the manifest of whichever repository calls it; a daily `bump-toolchain`
workflow moves them, and an hourly `dependabot-merge` job arms auto-merge for Dependabot's patch and minor updates in
this repo and every Forever addon, while a major waits for review.

## Credits

ForeverCore is built on the game's own UI and the work of other addon authors, listed with every player who helped in
[THIRD_PARTY.md](THIRD_PARTY.md).

<!-- forever-credits:start -->

Thanks to moshoutegong, TechnoHunter, user_efwsfml273dlvfm5, serb1tar, tommyekholm, Crypa7, Shuro, dokiz, user_vyffn82yvmu3bflh, user_8vheexbirr5v6h4a, Laddylucks, thirex, axejess, p1tu, Mirades96, silhouetteone, kowakowa93, xh43k, cotijelucie, iPulse, _spada, Darkwavez76, Naburiel, MrFIXlT, deathmvp1, berserkerlxl, Alex21xx, Torpdotorgx, dryzee, procque, Fareed, ZiiMs, Bolton_wow, hknylmz, Flangemuffler, Raynfeathyr, I3igAl, Wavebreaker90 and everyone who reported a bug or asked for a feature.

<!-- forever-credits:end -->

## Licence

GPL-3.0-or-later. See `LICENSE`.
