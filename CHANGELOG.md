# Changelog

## Unreleased

## 0.4.0 - 2026-10-26

- **Draw the mock context menu's backing surface opaque.** `common-dropdown-bg`'s atlas centre is translucent, so a
  menu composited straight over a scene let the list underneath show through its rows; the renderer now fills the
  panel behind the atlas art. `docs/handoff/mock-migration.md` records the migration state for the consumer addons.


- **Give offline UI mocks one shared renderer.** `tools/wowmock/` now owns the MIT-licensed BLP decoder, client
  asset cache, atlas and font lookup, native widget drawing, and frame compositing used by addon screenshots.
  Addons keep their own scenes and can import this library through `FOREVER_CORE`; Core's asset-sheet tool no longer
  reaches into Field Guide for the renderer.

## 0.3.0 - 2026-10-26

- **Put text matching and settings-page chrome in Forever Core, for the addons to vendor.** `Core/Text.lua` folds case
  and Latin accents (`ELEPHANT`, `Sao Tome`, `AEgir`, `Strasse`) and ranks a match as exact, prefix, word start or
  substring, replacing the four addons' own copies that disagreed; `UI/SettingsPage.lua` is the settings canvas every
  addon hand-built (`Register` plus `AddCheck`, `AddSlider`, `AddDropdown` and `AddButton`), drawing labels through the
  addon's own `ns.L`. Neither file holds an addon's options. The consumer registry lists both files, and their specs,
  before the copies land: nothing changes in game until the addons' own PRs adopt them.

## 0.2.1 - 2026-10-26

- **The consumer drift check no longer fails on a repo it cannot read.** Field Guide Forever is private, so
  unauthenticated raw reads of its copies returned 404 and the registry reported two files as drifted when they were
  byte-identical. It moves to a documented private-consumer list that is named in the success output, and Field Guide
  gates those same copies from its own repo. The boundaries doc records the split.
## 0.2.0 - 2026-10-25

- **Add shared micro-menu buttons** with Blizzard's native button template and placement refresh handling.
- **The consumer registry names Field Guide Forever's repo as it is now called.** `bestiary-forever` became
  `field-guide-forever` on 24 October, so the vendored micro button copies are read from the current name.

## 0.1.2 - 2026-10-24

- Move shared error capture into `Core/SafeCall.lua`, vendor it to all five consumers, and add scheduled core-authoritative drift checks.

## 0.1.1 - 2026-10-24

- **Unify report and link UI** in Forever Core, fix report text selection, and map vendored files to their consumers.

## 0.1.0

- **The shared tracker column becomes a repo of its own.** `UI/TrackerHost.lua`, `UI/TrackerLock.lua`,
  `UI/TrackerOrder.lua` and `UI/TrackerQuestie.lua` move here as the single source, with the specs that pin them
  (`tests/tracker_host_spec.lua` against Blizzard's own tracker source, and the lock, order and Questie specs). The
  four addons that draw sections vendor these files at the same paths, so nothing changes in game until an addon
  moves to a new core version.
- **ForeverCore is installable on its own.** `Core.lua` keeps the column's settings in `ForeverCoreDB`, `Expose.lua`
  publishes `ForeverCore` and `/fcore`, and the TOC lists the five Forever addons as `OptionalDeps` so an addon that
  already owns the column loads first and core adopts it rather than starting a second one.
- **Drift is a gate now.** `tools/check_consumers.py` fails when any consumer's copy differs from this repo, and
  `tools/sync_consumers.py` is the one command that moves a fix out to them.
