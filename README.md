<p align="center"><img src="media/icon-400.png" width="96" height="96" alt="Forever Core icon"></p>

<h1 align="center">Forever Core</h1>

<p align="center">The shared library every Forever addon needs: one tracker column, its Lock switch, the report window and the suite's shared UI.</p>

<p align="center">
  <a href="https://github.com/cjber/forever-core/actions/workflows/ci.yml"><img src="https://github.com/cjber/forever-core/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/cjber/forever-core/releases"><img src="https://img.shields.io/github/v/release/cjber/forever-core" alt="Latest release"></a>
</p>

**Interface:** 16001 (WoW: Forever, live client folder `_forever_`, beta `_classic_beta_`)

## What it is for

Every Forever addon requires ForeverCore with `## Dependencies: ForeverCore`, so the game loads it first and exactly one
copy of each shared file runs. A tracker scale, lock or position set in one addon is the same column in all of them,
and a fix released here reaches every addon without a second pull request.

The column can wear an optional dark background from any section's right-click menu, drawn with the game's own tooltip
background art. It offers off, 25%, 50%, 75% or 100%, and starts off, so a player who reads the tracker fine over dark
terrain keeps the stock look.

## What it does not do

It draws no quest, route, profession or challenge sections of its own. Sections belong to the addon that owns the
feature: see the suite's ownership boundaries in `docs/handoff/boundaries.md`. Its shared code is added to an addon
through `ForeverCore.Register` and the modules on the `ForeverCore` table; see [`docs/adoption.md`](docs/adoption.md).
The shape every addon's own public API follows is in
[`docs/api-conventions.md`](docs/api-conventions.md).

## Install

Players never install it by hand: CurseForge, Wago and every Forever addon bring it in. For a manual install, drop the
`ForeverCore` folder in `Interface/AddOns`. `/fcore` prints the column's anchors, heights and combat state, which is
the same diagnostic the addons print from their own slash commands.

## Development

The repo also owns a reusable offline UI mock renderer in [`tools/wowmock/`](tools/wowmock/README.md) and the Discord
release digest in [`tools/discord_digest.py`](tools/discord_digest.py).

## Licence

GPL-3.0-or-later. See `LICENSE`.
