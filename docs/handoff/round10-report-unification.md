# Brief: unify the in-game report / issue logic into Forever Core

Owner ask (2026-10-24, #wow-addons): "Why are they different? Unify the logic for reporting and anything similar
across all add-ons. No point having it divergent. Maybe we could unify into core as well? Expand forever core for all
things where possible and sensible please."

Read first: `brief.md` (signing, trailers, PR flow, credits, locales), `boundaries.md` (ownership, §5 vendoring rule,
§8 change process), `forever-core/docs/adoption.md`, `forever-core/AGENTS.md`.

## Why they differ today (verified on main, 2026-10-24)

`UI/Report.lua` is ~574-587 lines and is copy-pasted into all five addons. Its own header claims "it copies across the
Forever addons with only its strings changed" - but it has drifted:

1. **Two lineages.**
   - adventure-guide-forever uses constant locale keys (`L.REPORT_TITLE`, `L.REPORT_HINT`, `L.ISSUE_*`) and cites
     `docs/design.md §2.24`.
   - The other four use phrase keys (`L["Legacy Forever report"]`, `L["Shortest Path report"]`, `L["SkillUp report"]`,
     `L["Tweaks Forever report"]`) and cite `cjber/adventure-guide-forever docs/report-window.md`.
   - AGF differs from each of the other four by 74-89 lines; the other four differ from each other by 32-53 lines
     (namespaces, type names, strings).
2. **A live Lua bug survives in four of five.** The focus handler is
   `edit:SetScript("OnEditFocusGained", edit.HighlightText)` in adventure-guide, legacy, skillup and tweaks - the method
   is passed directly, so the client calls `handler(self, isUserInput)` and the boolean lands in `HighlightText`'s
   `start` argument, raising "bad argument #2 ... outside of expected range" and leaving the text unselected. Only
   shortest-path-forever has the fixed closure `function(self) self:HighlightText() end`. The same bug is at the second
   site (`output:SetScript`). This is the bug fixed for `UI/ForeverFamily.lua` in adventure-guide-forever #269 / #255;
   the fix never reached Report.lua in the other four.
3. **The slash dispatch is re-implemented inline in different files**: `Core/Core.lua` (adventure-guide ~1078,
   legacy ~96, skillup ~647) and `UI/Settings.lua` (shortest-path ~578, tweaks ~149), each with its own branch
   (`command` vs `message`) and its own help lines. `/path issue` and `/tweaks issue` work but are undocumented.
4. **`tests/report_spec.lua` is duplicated** in all five (316-419 lines) and has drifted 651-696 diff lines apart.

## The home: Forever Core

`forever-core` already owns the vendored shared files (`UI/TrackerHost.lua`, `UI/TrackerLock.lua`, `UI/TrackerOrder.lua`,
`UI/TrackerQuestie.lua`, two contract specs, `tools/fetch_tracker_ui.py`), synced by `tools/sync_consumers.py` and gated
by `tools/check_consumers.py` (see `docs/adoption.md`). Reporting is the same kind of shared code: identical in every
addon, addon-specific only in its strings. Move it there.

## Work

### 1. Forever Core: `UI/Report.lua` becomes the one copy
- Take the current report/issue module as the base and make it byte-identical across consumers by reading everything
  addon specific through the namespace:
  - window title and hint via phrase-keyed `ns.L`, the way `UI/ForeverFamily.lua` does (see the `PHRASE_KEYED` note in
    adventure-guide-forever's `tools/lint_copy.py`): e.g. `L["<Addon> report"]`, the report hint phrase, `L["Bug: "]`,
    `L["Feature request: "]`, `L["Copy report"]`, `L["Copy link"]`, the issue window title/hint. adventure-guide-forever
    must switch off `L.REPORT_*` constant keys to the same phrase keys so the file needs no per-addon edit.
  - the repo slug from `## X-Website` (already done by `Report.Repo()`).
  - `ns.ReportLines`, `ns.SafeCall`, `ns.Print` as today.
- **Fix the `OnEditFocusGained` bug in the canonical copy** (closure form) so all five inherit the fix.
- Add a shared command helper so the `report` / `issue|bug|feature` branch is one function, not five copies - e.g.
  `Report.Command(command, argument) -> boolean` that handles those subcommands and returns whether it did. Each addon's
  slash handler calls it first and keeps its own other subcommands (audit, skipped, trainers, criteria, shopping, ...).
- Keep the existing type annotations and comment voice; update the file header to say it is vendored from Forever Core.

### 2. Vendor the report spec
`tests/report_spec.lua` moves to core as the contract spec and is vendored too. It must pass against the shared module
with only the strings/namespace supplied by a small harness. Extend it to cover the fixed focus handler (focus the box,
assert no error and the text selected).

### 3. Extend the vendoring tooling with per-file consumers
The tracker files go to four addons; the report files go to all five (tweaks has `UI/Report.lua` but does not draw into
the tracker). Change `tools/sync_consumers.py` and `tools/check_consumers.py` to a per-file consumer map so the tracker
set stays at four and the report set covers five, and update `docs/adoption.md` accordingly.

### 4. Fold in the other already-identical files ("anything similar")
`UI/ForeverFamily.lua` and `tests/forever_family_spec.lua` are already byte-identical in all five (hand-synced today,
pinned by a hash in the spec). Add them to the vendored set with all five consumers so they stop being a separate manual
sync. Scan the other `UI/` files for any further byte-identical-and-duplicated pair and list what you find in the PR.

### 5. Consumers: one PR per repo
For each of the five addons:
- Replace `UI/Report.lua` with the core copy (byte-identical) and `tests/report_spec.lua` with the core spec; add/adjust
  the locale phrases; switch adventure-guide-forever off its constant keys.
- Point the slash handler at the shared `Report.Command`.
- Document `/X issue` in the README command table and `docs/curseforge.md` for shortest-path-forever and tweaks-forever
  (the other three were documented on 2026-10-24).
- Run the repo's full `## Commands` gate; keep CI green.

### 6. Docs and release
- Core: update `docs/adoption.md`, `AGENTS.md`, `README.md`; bump `CHANGELOG.md` and tag a core release.
- `boundaries.md` §4 (duplicates) and §5 (shared code) + a §10 change-log row: add `UI/Report.lua` and
  `UI/ForeverFamily.lua` (and their specs) to the shared-code list.
- After core's release, the five adoption PRs; then a patch release per addon so the focus-bug fix reaches players.

## Gates
Every repo: its own `AGENTS.md` `## Commands`. Core additionally:
`python3 tools/check_consumers.py --local /home/nebula/wow` must be green once all five carry the same bytes. Never edit
a consumer's vendored copy by hand - change it in core, run `sync_consumers.py`, then one PR per consumer.

## Report back
Issue/PR table per repo, the core release tag, whether `check_consumers.py` is green, and the one-line changelog bullet
per merged PR. This is a bug fix plus a de-duplication, so no credits are owed.
