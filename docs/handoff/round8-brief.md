# Round 8 brief: prominent flight path reminder, then the queued features

Read `brief.md` first (signing, trailers, PR flow, credits, locales, generated data); read `boundaries.md` for who owns
what and never move a feature across an addon boundary without editing that file and adding a change-log row in the same
round. This file is the work queue. One PR per item, in the order below, each green on its own `ci.yml`.

The owner asked for these on 2026-10-21 ("Rest are all good too we should implement all of that too in tasks"). They are
queued, not optional.

## W1. Shortest Path: make the missing flight path reminder prominent (do this first)

Today the only signal that a route walks you to a flight master you have not discovered is a parenthetical on one
tracker row: `Journey/Journey.lua:323` appends `(new flight path)` to the step text. Two more places already know the
node is unknown and draw it quietly: `UI/FlightPins.lua:222` picks `taxinode_undiscovered` for the pin and
`UI/Compass.lua:76` for the compass stop, and `Core/API.lua:406` exposes `newFlightPath` per leg. There is no banner, no
sound, no option, and no warning before you set off or when you arrive.

What to build:

- A real reminder, not a suffix. When the current plan contains a walk to an undiscovered flight master, say so where
  the player will see it: the tracker's journey header or a dedicated row above the steps, with the number of the step
  and the flight master's name (for example "Step 3: fly from Ironforge. This flight master is new, walk to it first").
- Announce it once when the plan lands (`journey search completes`) and again when the player is close to that flight
  master, the way `UI/Alert.lua` announces a boat: `RaidWarningUtil.AddMessage` on `ChatTypeInfo.RAID_WARNING`, plus
  `FlashClientIcon`, plus `PlaySoundFile(..., "Master")` only when the existing `ns.db.alertSound` is on. Reuse that
  file's per-key dedupe so a plan held for minutes does not re-announce every layout pass. Pick the game's own flight
  master sound if one exists in the Forever build's FileDataIDs; if it does not, no sound on this one and say so in the
  PR body rather than inventing a FileDataID.
- An option, default on, beside the existing alerts checkbox in `UI/Settings.lua` (`alerts` / `alertSound` are there),
  so a player can keep the tracker row and drop the banner.
- Keep the tracker row's `(new flight path)` suffix: it stays the quiet in-line marker for anyone who turned the
  reminder off.
- Nine locales for every new phrase (`deDE esES esMX frFR koKR ptBR ruRU zhCN zhTW`), machine lines marked `-- mt`, and
  `tools/check_locales.py --release` clean.
- Specifications: extend `tests/journey_spec.lua` and `tests/alert_spec.lua` (or add `tests/flight_reminder_spec.lua`)
  to cover a plan with an undiscovered master, a plan with a known one, the dedupe, the option off, and a plan whose
  unknown master is not the current step. Run every gate in the repo's `AGENTS.md` locally first.

Not in scope: changing what the planner returns, auto-discovering nodes, or anything that touches `Transport/`.

## W2. Forever Core: publish and adopt, once the repo exists

`cjber/skills`, branch `forever-core-staging`, folder `forever-core/` holds the finished ForeverCore addon (36 files,
green locally). Its `docs/handoff.md` has the publish and adoption commands. Creating `cjber/forever-core` fails with
403 for the workspace GitHub app on every route, so:

1. Run the full gate matrix on the staged tree and report the numbers (`luacheck`, `stylua --check`, every
   `tests/*_spec.lua`, the native host spec with `TRACKER_UI_ROOT=tools/.cache/tracker-ui`, `ruff`, the packager dry
   run plus `tools/check_package.py`).
2. `python3 tools/check_consumers.py --local /home/nebula/wow` must report the 7 shared files identical in all four
   consumer checkouts; if not, `tools/sync_consumers.py` and one PR per drifted repo.
3. If `cjber/forever-core` exists by the time you start, publish the staged tree to it and do the adoption PRs. If it
   does not exist, skip only the publish and the adoption PRs, and say so in your report.

## W3. SkillUp: multi-rank recipe cost and ROI, and a shopping list export

`UI/Shopping.lua` builds the list and has no export today. `UI/Tooltip.lua` already formats a single recipe's net
copper (`ns.FormatNet`, green `+` for profit, red `-` for cost). What is missing:

- A cost and ROI figure per recipe that accounts for the ranks it will carry you through (a recipe that is orange at
  150 and yellow at 175 is worth more than one that greys out after a single cast), and an ordering choice on the skill
  path: cheapest total cost, or best cost per skill point.
- Export the shopping list as text the player can paste into chat or hand to work-orders-forever: raw materials with
  counts, grouped by the tier each is needed for. Keep the existing list behaviour unchanged when no export is asked
  for.
- Specs for the rank maths (`tests/` has the model specs) and the export format. Nine locales.

## W4. Tweaks: vendor junk profiles and a repair threshold warning

- Per-item sell profile: always sell, never sell, ask. The client's own junk rule stays the default; the profile is the
  addon's own list, saved per character, with a "sell now" pass at a vendor that reports what it sold.
- A repair warning on a threshold the player sets (a percentage of durability or a copper amount), raised through the
  same banner pattern the addon already uses, and only at a vendor that can repair.
- Specs for the profile decisions and the threshold. Nine locales. Keep every tweak behind its own checkbox, as the
  boundary rules require.

## W5. Adventure Guide: rare encounter route overlays and milestone checklist cards

- A rare encounter overlay on the world map for the zone the player is in, drawn through `UI/MapCanvas.lua` and the
  `ForeverMapMarkers` registry (see `overlay-notes.md`) so there is no gamepad taint, with the same "we do not know
  where it spawns" honesty the rest of the suite keeps: no invented coordinates.
- Level milestone checklist cards: the levels and unlocks a player should care about next, as cards in the guide's own
  feed, reading Legacy's targets where Legacy is installed and using its own fallback where it is not.
- Specs, nine locales, and no navigation of its own: Shortest Path routes.

## W6. Legacy: dungeon entrance pins, cleared and uncleared

The open decision from 2026-10-21: entrance pins should show whether the instance is cleared this lockout as well as
whether it has ever been cleared. Implement both states on the pin (a cleared badge for this lockout, a dimmer badge
for all time), use exploration opacity only for entrances the character has not found, and keep the challenge badge on
top as the boundary doc says. Specs, nine locales.

## Rules that apply to every item

- The shared tracker files are vendored from Forever Core and are never edited in a consumer repo; everything addon
  specific goes through `ns.TrackerHostSettings` and `ns.L`.
- Never loosen a check, skip a spec, or hand-edit generated `Data/`.
- Report `READY <PR URL> <head sha>` per PR. Do not merge; the coordinator merges.
- Every PR lists its in-game `/reload` checks for the owner, since no agent launches the game.
