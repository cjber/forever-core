# Changelog

## Unreleased

- **Simulator helpers pass consumer multi-value lint.** Explicit single-value argument counts preserve vararg behaviour when the simulator is vendored into an addon.

- **Native panel composition has one lockup and one chrome owner.** The shared guidance now records
  native edge ownership for map and portrait frames, source-backed side rails and top/bottom tabs, clipped artwork
  and unframed versus beveled icons, so addon mockups do not approve impossible tab placement or
  nested borders.
- **Peer-statistic readers coexist with the source addon.** A read-only subscription observes validated reports without replacing another addon's sender or relaying its messages. Aggregate counts and encounter difficulties have explicit subject schemas.
- **Peer sharing tolerates inaccessible roster names.** The transport checks both name and realm before building a group signature.
- **Buttons use the Forever gold border.** Shared buttons and previews use the set-1 red-button atlas. The shared asset checker rejects legacy loose chrome and templates that select it, including references inside art helpers.
- **Linting works in cached checkouts.** The multi-value scanner applies directory exclusions inside its requested root, so a parent cache directory cannot hide every Lua file.
- **Combat transitions have regression coverage.** Specs check combat and lockdown during and after events, including player and other-unit loss-of-control data.
- **Multiline mock text follows client alignment.** Each line now aligns independently within centered and right-justified text boxes, including the widest-line constraint.
- **Reports deduplicate BugGrabber errors consistently.** Long caught errors no longer repeat in the BugGrabber section, and its heading is omitted when every entry is already listed.
- **Shared checks validate consumer identity and renderer coverage.** Worktree drift checks normalize GitHub remotes and reject unknown consumers, while asset checks include every active gallery renderer.

## 0.4.6 - 2026-11-03

- **Addons share one peer-statistics transport.** The shared module validates and bounds guild and group rows, ranks cumulative totals and observed first completions, and cancels sends and hides peers immediately when sharing is switched off.
- **Simulator loading respects excluded game types.** Startup bootstrap files, explicit addon loads and partial loads all honour the Forever client's addon restrictions.

## 0.4.5 - 2026-11-03

- **Profession scenarios complete their page transitions.** The test client loads startup bootstrap files and the casting bar, supplies the skipped action-bar and micro-menu calls, and keeps native constants readable during addon-triggered calls.
- **Core's dead-code check works in feature worktrees.** It identifies the shared-source repository by its TOC rather than its folder name.

## 0.4.4 - 2026-11-03

- **Mock menus keep their transparent corners.** The renderer no longer paints an opaque rectangle behind the rounded native menu artwork, so map previews have no dark square around the popup.

## 0.4.3 - 2026-11-03

- **The suite's tools ignore fixture TOCs that never ship.** TOC runtime discovery walked every `.toc` under
  a consumer, including the ones `tools/` and `tests/` keep for their own fixtures, so a vendored simulator
  could report a runtime file the packager never ships. Explicit tools and tests roots are now excluded while
  nested child-addon TOCs outside those roots are still found, with a regression covering the simulator's
  Auctionator stubs. Nothing changes in game.
- **Release help and changelog ordering work again.** `tools/changelog.py --help` answered with a traceback
  instead of usage, and version headings were compared as text, so 0.10.0 sorted below 0.9.0 when the tool
  checked which tags still need an entry. Both are fixed; entries are ordered numerically.

## 0.4.2 - 2026-11-03

- **Vendoring keeps the exec bit.** `forever_tools/sync.py update` and `forever_sim/sync.py update` copied with
  `shutil.copyfile`, which never carries the file mode, so a vendored script with a shebang landed as 100644 and
  ruff failed the consumer with EXE001. Both copy through a helper that carries the source mode across. Nothing
  changes in game.

## 0.4.1 - 2026-10-27

- **The suite's newest-build lookup now sees Forever's own product key.** wago.tools publishes Forever under
  `wowf` as well as the older `wow_classic_beta` list, and `forever_tools.latest_build` read only the latter, so
  the addons' daily data refresh kept reporting the previous build (1.60.1.70532) after 1.60.1.70630 shipped.
  It now reads both products and takes the highest 1.6x build. Nothing changes in game.

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
