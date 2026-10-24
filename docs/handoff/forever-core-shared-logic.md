# Complete the Forever Core extraction: SafeCall into core, and make the drift gate real

**Round:** 2026-10-24. Owner asked whether Forever Core now holds *all* the shared logic and whether the latest
releases ship divergent copies of it. Audit findings below; this brief is the cleanup.

Read `forever-handoff/boundaries.md` §5 first: it is the authority and it already says "Shared code is vendored from
Forever Core, never re-implemented per addon". The vendoring model (byte-identical copies, no dependency to install)
is deliberate and stays. Do **not** turn Forever Core into a `RequiredDeps` / `.pkgmeta` external: that is the friction
the model exists to avoid.

## What the audit found

1. `forever-core` (v0.1.1) already owns and vendors, byte-identical, into its consumers:
   - tracker column: `UI/TrackerHost.lua`, `UI/TrackerLock.lua`, `UI/TrackerOrder.lua`, `UI/TrackerQuestie.lua`
     (into the four tracker consumers: adventure-guide, legacy, shortest-path, skillup), plus their specs and
     `tools/fetch_tracker_ui.py`;
   - `UI/Report.lua` + `tests/report_spec.lua` and `UI/ForeverFamily.lua` + `tests/forever_family_spec.lua`
     (into all five consumers).
   `tools/check_consumers.py --local ~/wow` passes (52 copies match) and every latest release tag carries those exact
   bytes. So no consumer ships a **divergent** copy of those files.
2. **Gap A — `Core/SafeCall.lua` is still five hand-maintained copies, not core-owned.** It is the error-capture
   plumbing the shared report depends on (`ns.SafeCall`, `ns.RecordError`, `ns.CaughtErrors`, `ns.CutText`). All five
   addons ship it, its body is identical, and only the namespace line, the `---@class *CaughtError` name and the
   comment differ. It is not in core, and not in `VENDORED`. Core's own `UI/Report.lua` calls `ns.SafeCall` /
   `ns.CutText` / `ns.CaughtErrors`, which core itself does not define.
3. **Gap B — the drift gate is not wired, so nothing actually enforces "no divergence".** Core's `ci.yml` never runs
   `tools/check_consumers.py`. No consumer repo references `forever-core` at all (`git grep` is empty). Only
   shortest-path has any shared-code workflow, and it is the *old* `tools/check_shared_tracker.py` that compares the
   four consumers **to each other**, covers only five tracker files, and omits `UI/Report.lua`, `UI/ForeverFamily.lua`
   and `Core/SafeCall.lua`. The handoff's "point each consumer at the core as the authority" step was never done.

## Task 1 — move `Core/SafeCall.lua` into Forever Core

Make Forever Core the single source of truth for it, exactly like `UI/Report.lua`:

1. Add `Core/SafeCall.lua` to the `forever-core` repo at that path (core is the one repo allowed the consumer's
   layout). Generalise it so one file is valid in every addon, reading everything addon specific through the
   namespace:
   - `local _, ns = ...` (the form the other shared files use);
   - a neutral `---@class ForeverCaughtError` (not `AGFCaughtError` / `LegacyCaughtError` / …);
   - a comment with no addon name and no slash command (say "the Forever addons" / "the report window").
   Behaviour must be unchanged: identical `MAX_ERRORS`/`MAX_MESSAGE`/`STACK_LINES`, identical `Cut`/`RecordError`/
   `CaughtErrors`/`SafeCall`, the same `geterrorhandler()` hand-off, the same `ns.CutText` export.
2. Add a spec for it in `forever-core/tests/` (model it on the consumer `tests/core_spec.lua` / `tests/report_spec.lua`
   stubs) and make sure core's own `luacheck`, `stylua` and specs still pass. If `forever-core/tests/report_spec.lua`
   currently stubs `ns.SafeCall`, have it load the real `Core/SafeCall.lua` instead.
3. Add `Core/SafeCall.lua` to `VENDORED` in **both** `tools/check_consumers.py` and `tools/sync_consumers.py`, mapped
   to `ALL_CONSUMERS` (all five addons ship it). Add its spec to `VENDORED` too if the spec is shared; if the spec is
   addon specific, keep it per addon and only vendor the module.
4. Update `forever-core/AGENTS.md`, `docs/adoption.md` and `README.md` so the shared-file table lists `Core/SafeCall.lua`,
   and add a `CHANGELOG.md` entry (new version, e.g. 0.1.2).

## Task 2 — make the drift gate real

1. In `forever-core`, add a `drift` job (new `.github/workflows/drift.yml`, `on: schedule` + `workflow_dispatch`,
   `contents: read`) that runs `python3 tools/check_consumers.py`. Do **not** run it on push: consumers adopt at their
   own pace, so a core push that is ahead of them must not fail core's CI.
2. In each of the five consumers, add a scheduled core-authoritative drift check (reuse the shape of
   shortest-path's `.github/workflows/shared-tracker.yml`): a script that compares that repo's own copies of every
   `VENDORED` path against `https://raw.githubusercontent.com/cjber/forever-core/main/<path>` and fails on any byte
   difference. Replace shortest-path's stale four-way `tools/check_shared_tracker.py` with this one, so it checks
   against core and covers the report, family and SafeCall files too.
3. Leave every TOC load order, the `ForeverTrackerHost` global, `ns.TrackerHostSettings`, the `OptionalDeps`, and every
   existing spec otherwise unchanged.

## Task 3 — sync, PR, merge, release

1. `python3 tools/sync_consumers.py ~/wow` from `forever-core` to write the new `Core/SafeCall.lua` (and any other
   changed shared bytes) into each consumer checkout.
2. Run each repo's own gates (luacheck, stylua, specs, package check, ruff). One PR per consumer with all the shared
   files in it; let that repo's CI be the gate. Merge green PRs to main.
3. Release `forever-core` (tag after its main CI run is green), then cut a patch release of each consumer so the
   core-owned `Core/SafeCall.lua` reaches players.
4. Acceptance: `python3 tools/check_consumers.py` in `forever-core` reports every mapped copy matching; each consumer's
   drift workflow exists and passes; `forever-core` released; each consumer released with the byte-identical
   `Core/SafeCall.lua`.

## Constraints

- Commit signing is automatic on GitHub: never pass `-s` / `--signoff` / manual signing flags.
- End every commit with the project's `Co-Authored-By` and `Claude-Session` trailers. Never put a model name in
  commits, PRs or code.
- Do not change the vendoring model. Do not add a dependency. Do not remove the `OptionalDeps` from `ForeverCore.toc`.
- One source of truth: change shared files in `forever-core` first, never in a consumer.
