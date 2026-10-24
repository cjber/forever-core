# Shared ForeverFamily.lua: propagate the #269 OnEditFocusGained fix to the other four addons

## Why

Issue cjber/shortest-path-forever#269 reported a caught Lua error in the "Forever addons" link box:

```
bad argument #2 to '?' (outside of expected range -2147483648 to 2147483647 - Usage: self:HighlightText([start, stop]))
```

The defect: `edit:SetScript("OnEditFocusGained", edit.HighlightText)` passes the method itself, and the client
calls an `OnEditFocusGained` handler as `handler(self, isUserInput)`, so the boolean lands in `HighlightText`'s
`start` argument.

It is fixed and released in shortest-path-forever v1.22.4 (commit 69ab701, merged as a323ea2). The file
`UI/ForeverFamily.lua` is byte-identical across all five addons and its own header says a change there is made in
shortest-path-forever first, then copied unchanged to the other four together with `tests/forever_family_spec.lua`
and its new pin. That copy has not been done, so the other four still raise the same error.

## What to do

For each of these four repos — the local clones are under `/home/nebula/wow/` and are clean on `main`:

- `adventure-guide-forever`
- `legacy-forever`
- `skillup-forever`
- `tweaks-forever`

1. Read that repo's `AGENTS.md` and follow its Commands section exactly.
2. Copy the two files unchanged from the shortest-path-forever clone at
   `/home/nebula/wow/shortest-path-forever` (on `main`, at v1.22.4):
   - `UI/ForeverFamily.lua` -> `<repo>/UI/ForeverFamily.lua`
   - `tests/forever_family_spec.lua` -> `<repo>/tests/forever_family_spec.lua`
   The spec already carries `PENDING`… see below — verify with:
   `sha256sum <repo>/UI/ForeverFamily.lua` must equal `3beb18e13af61d99bee0c680d6d66b4afd34a52e463de4a0f90f291b6c1aa2f3`.
   The spec's `local PINNED` already holds that hash, so it passes as copied.
3. Run the repo's full local gate: `luacheck .`, `stylua --check .`, and
   `for s in tests/*_spec.lua; do luajit "$s" || exit 1; done`,
   plus `python3 tools/changelog.py --check` and (where the repo has it) `python3 tools/check_generated.py --offline`.
   All must pass before a PR.
4. CHANGELOG: add a patch-entry heading under `## [Unreleased]` — an `## [x.y.z] - <UTC date>` heading with one
   bold-lead bullet describing the fix, in that repo's voice. Next patch version per repo:
   adventure-guide-forever 0.22.3, legacy-forever 0.12.4, skillup-forever 0.19.3, tweaks-forever 0.15.5.
   Suggested bullet (adapt the wording per repo, keep it one paragraph):
   "**The Forever addons link box selects its address without a Lua error.** Focusing the read-only box handed
   the client's own `isUserInput` flag to `HighlightText` as its start argument, so it raised *bad argument #2 to
   '?' (outside of expected range ...)* and left the address unselected. It now selects the whole address the way
   the game asks (#269)."
5. In-addon "what's new" must move with the version or CI fails the release:
   - adventure-guide-forever: `Locales/enUS.lua`'s `WHATS_NEW` must OPEN WITH the first bold-lead text of the new
     CHANGELOG entry (tests/locales_spec.lua captures it as `%- %*%*(.-)%.?%*%*`). Then
     `python3 tools/phrases.py > Locales/phrases.txt` and update the `L["WHATS_NEW"]` line in every
     `Locales/<locale>.lua`, marking each machine translation with a `-- mt` comment line above it (WFA-34).
   - tweaks-forever: `UI/WhatsNew.lua`'s `ns.WHATS_NEW_VERSION` must equal the new version and `ns.WHATS_NEW`
     should be the new headline.
   - legacy-forever and skillup-forever: `ns.WHATS_NEW` in `Core/Core.lua` is `L["<headline>"]` — update it to the
     new release's headline so the chat line matches the release; add the English line to `Locales/enUS.lua` /
     `Locales/phrases.txt` as those repos do for `WHATS_NEW`.
6. Commit (no `-s`, no sign-off flag — GitHub signs automatically), push a branch named
   `fix/forever-family-focus-highlight`, open a PR against `main` whose body says `Fixes #269` and names the
   propagation, and report the PR number/URL plus the head SHA back. Do not tag or release; the coordinator
   merges and cuts the release.

## Boundaries

- Do not change `## Interface` (still 16001) or the TOC `## Version: @project-version@` placeholder.
- Do not touch the vendored `tweaks-forever/LibAHTab` files.
- If any repo's `UI/ForeverFamily.lua` differs from shortest-path's for a reason other than this fix, stop and
  report the diff instead of overwriting.
- One PR per repo.
