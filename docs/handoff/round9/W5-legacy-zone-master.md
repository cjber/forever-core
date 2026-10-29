# W5: Legacy x Field Guide - the "Zone Master" completion row

Repo: `cjber/legacy-forever` (folder `LegacyForever`, Interface 16001).
Read `../brief.md`, `../boundaries.md`, `../round9/README.md`, then `legacy-forever/AGENTS.md`.

## Why

`boundaries.md` §3, Field Guide row: "Zone bestiary completion, creature records, rare and variant sightings |
Field Guide | Legacy may read it for a *Zone Master* style milestone". Rule 10 says Field Guide awards nothing that is
not cosmetic and does not duplicate Legacy's challenge tracking. Today Legacy has no idea a Field Guide exists,
and Field Guide's completion is invisible outside its own window, even though `FieldGuideForever.API.Progress(zoneName)`
already answers `{ zone, catalogued, total, fraction }` and `API.Zones()` lists every zone with its continent.

Legacy owns zone completion, the completion tooltip, the map shading and the tracker row; reading Field Guide for
one extra row is exactly the permitted direction, and it is a small, contained change.

## What to build

1. `Integrations/Field Guide.lua` - optional, version-checked exactly like `Integrations/Navigate.lua` checks
   Shortest Path (`FieldGuideForever.API`, `api.version == 1`, `type(api.Progress) == "function"`). It answers:
   - `Field Guide.Zone(uiMapID)` -> `{ catalogued, total, fraction, name }?`
   - `Field Guide.State()` -> `"ready" | "outdated" | "missing" | "loading"`
   Resolve `uiMapID` to a zone name through the mapping Legacy already uses for zone completion
   (`Core/ZoneCompletion.lua`, `UI/Map.lua`) - do not build a second zone table. Return `nil` for instances and
   for zones Field Guide does not catalogue.
2. A new completion category `bestiary` alongside the existing ones in `Core/ZoneCompletion.lua`: worth a
   documented share of the zone percentage (pick the weight so a fully catalogued zone reads as a sensible
   milestone, and say the number in the PR body), **counted only when Field Guide is present and ready** -
   Legacy must be identical to today when it is not (that is rule 11: every addon works alone).
3. Surfaces, all of them driven by the one category value:
   - the completion window: one row with "N of M creatures" and the same bar treatment as the other categories;
   - the zone tooltip (`Completion.AddSummary`) and the continent badge tooltip: one extra line;
   - the map shading tint: only if a category already tints today - if the tint maths is percentage-based the new
     category joins automatically, which is the preferred outcome;
   - the tracker section: one row, no new frame.
4. A setting to switch the row off (default on) in `UI/Settings.lua`, in the existing pattern, saved flat.
5. Nine locales for every new phrase (`deDE esES esMX frFR koKR ptBR ruRU zhCN zhTW`, machine lines `-- mt`),
   `python3 tools/check_locales.py` clean, `python3 tools/phrases.py > Locales/phrases.txt` if the repo's gate
   wants a regenerated template, and `python3 tools/check_screenshots.py --record` plus your own look at every
   changed PNG (completion window, tooltip, map) at full resolution.

## Specs

- `tests/bestiary_integration_spec.lua`: ready / missing / outdated / loading; zone with no catalogue entry;
  instance map id; a fraction of 0 and of 1; a caller-visible copy, never Field Guide's table.
- Zone completion: the percentage with the category present, absent, and at 0 of N; the tooltip line, including
  the "not installed" case (the line must be absent, not empty or "0 of 0").
- Tracker layout spec: the new row when ready, nothing when missing.

## Boundaries

Legacy reads Field Guide's public API and never its internals; Legacy does not track creature kills itself and
must not ask Field Guide to. Field Guide keeps its own window - no Field Guide UI is drawn from Legacy. If you think
the category weight or the tooltip wording moves a boundary, say so in the PR body; the coordinator owns
`boundaries.md`.

## Report

Gate lines, proposed version and CHANGELOG entry, PR URL with head SHA, the weight you chose and why, and the
in-game checks (with and without Field Guide installed). No version bump, no tag.
