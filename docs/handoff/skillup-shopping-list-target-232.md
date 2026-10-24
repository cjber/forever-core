# SkillUp Forever: show the skill target in the shopping list window (#232)

## Why

CurseForge, Sogu, 2026-10-23 17:38: "Any way we can get shopping list to reach certain skill points, instead of just 300?"

The planning behaviour is already right: `ns.db.routeTargets[skillLine]` holds a per-profession target, set from the Target box in `UI/Route.lua` (`page.Target`, committed by `CommitTarget`, shown as `Skill  %d/%d     Target`), and `Core/Plan.lua`'s `RouteTarget` reads it (default `base + 25`, clamped to the last rank a trainer, book or quest teaches). `ns.PlanRoute` plans to it and `ns.RouteReagents` / `ns.TrackedNeeds` build the shopping list from that plan, so the list is already for the chosen target rather than for the cap.

The gap is that the shopping list window never says so: `UI/ShoppingList.lua` shows `Gather` / `Vendor` / `Auction house` headings and rows of `Name (Profession)` with no skill level at all, so a player reads it as one "everything to 300" plan.

Tracking issue: cjber/skillup-forever#232.

## What to do

Target version: **0.19.4** (patch), tag `v0.19.4`, Interface stays 16001.

1. `Core/API.lua`, `API.ShoppingList(skillLineID)`: each per-profession record already carries `profession`, `skillLine`, `items`, `total`, `unpriced`. Add `target` = the plan's target in base skill (`entry.plan.target`). Additive only: no field renamed or removed. Bump `API.minor` by one (currently `minor = 2`) and add a line to the public API doc block in that file saying what `target` is.
2. `UI/ShoppingList.lua`, `Refresh()`: show the target. Preferred shape, and the one to mock: each row's name becomes `Name (Profession to N)` (one new localizable format string), and add one summary line under the window title listing every tracked profession with its target, because the window groups by source, not profession. If the summary line crowds the header on a 620x500 frame, keep only the per-row target and say so in the PR body.
3. Optional and only if it fits cleanly beside the title: the same Target EditBox the route page uses, committing through `ns.TargetChanged` / `ns.db.routeTargets` then `ns.Changed("target")` exactly as `CommitTarget` does, so both pages always agree. If it needs layout work that risks the header, leave it out and note it.
4. Localization (WFA-34): regenerate `Locales/phrases.txt` with `python3 tools/phrases.py`, add the new English string(s) to `Locales/enUS.lua`, and add each other locale's line marked with a `-- mt` comment above it. Do not hand-write translations without the marker.
5. Specs, run from the repo root with luajit:
   - the API record carries `target` equal to the plan target for a tracked profession with a saved `routeTargets` value different from the default;
   - the shopping list window's rendered text contains that target for two tracked professions with different targets.
   Follow the existing synthetic client in `tests/client.lua` (`tests/shopping_list_spec.lua` already sets `routeTargets = { [197] = 60, [164] = 60 }`; use different values per profession so the assertion is meaningful). No real client, no QuestieDB/AtlasLoot data copied in.
6. CHANGELOG: add `## [0.19.4] - 2026-10-23` under `## [Unreleased]` with one bold-lead bullet in the repo's voice, e.g. "**The shopping list says which skill level it is buying for.** The list already followed each profession's route target, but the window never showed it, so it read as one plan to 300; every row and the header now name the target, and the target can be changed from the list (#232)."
7. `ns.WHATS_NEW` in `Core/Core.lua` must move with the version: point it at the new release's headline, add the English line to `Locales/enUS.lua` and `Locales/phrases.txt` as that repo does for `WHATS_NEW`.

## Gate

Run the full Commands section of `AGENTS.md` in `cjber/skillup-forever`: `stylua --check .`, `ruff format --check tools && ruff check tools`, `luacheck .`, `tools/typecheck.sh`, every `tests/*_spec.lua` under luajit, `python3 tools/changelog.py --check`, `python3 tools/check_generated.py`, `python3 tools/check_screenshots.py`, `.sift/gate.py --base origin/main` and `.sift/agents.py check`. All must pass before the PR.

## Deliverable

One PR against `main` on `cjber/skillup-forever` from branch `feat/shopping-list-target`, body starting `Fixes #232`, describing the shape chosen in step 2 and any part of step 3 left out and why. Commits without `-s` or any sign-off flag. Report the PR number and URL back. Do not tag, do not release, do not merge: the maintainer merges on green CI and cuts v0.19.4.
