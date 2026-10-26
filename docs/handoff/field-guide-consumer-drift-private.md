# Fix: the Consumer drift gate is red because Field Guide is a private repo

**Round:** 2026-10-26. forever-core's `Consumer drift` workflow (`drift.yml`, cron `30 7 * * *`) failed on
2026-10-26T07:55:56Z (run 40288839972). It is the first run since `355369f` added `field-guide-forever` to
`MICRO_CONSUMERS`, and it fails on exactly the two Field Guide entries:

```
field-guide-forever: Core/MicroButton.lua: could not be read: HTTP Error 404: Not Found
field-guide-forever: tests/micro_button_spec.lua: could not be read: HTTP Error 404: Not Found
```

The copies themselves are **not** drifted. Verified locally against `~/wow/bestiary-forever` at `33ee66c`:
`Core/MicroButton.lua` is `f93c59a57ece` on both sides and `tests/micro_button_spec.lua` is `5f636c1b52c9` on both
sides, byte identical to forever-core `355369f`.

The cause is direction, not content: `tools/check_consumers.py` fetches every consumer copy through
**unauthenticated** `raw.githubusercontent.com`. `cjber/field-guide-forever` (local dir `bestiary-forever`) is a
**private** repo, so that URL returns 404 for anyone without a token, and the script reports an unreadable file as
drift. The other four consumers are public, so they still read fine.

A token would fix it, but that means a new secret, which is out of scope. The design already has the answer: Forever
Core is public and Field Guide is private, so the check has to run **from Field Guide**, where core's bytes are
readable and its own copies are local. That is how the five public consumers already work
(`.github/workflows/core-shared-drift.yml` + `tools/check_core_shared.py`), and Field Guide is the only consumer
missing that pair.

## Task 1 - give field-guide-forever its own core drift gate

Work in `cjber/field-guide-forever` (local clone `~/wow/bestiary-forever`), fresh from `origin/main`.

1. Add `tools/check_core_shared.py`, modelled on `adventure-guide-forever`'s file of the same name, but for Field
   Guide's paths only: `Core/MicroButton.lua` and `tests/micro_button_spec.lua`. It reads
   `https://raw.githubusercontent.com/cjber/forever-core/main/<path>` (public, no token), compares to
   `Path.cwd() / path` byte for byte, and exits non-zero naming every mismatch with both short hashes. Same shape and
   same message style as the adventure-guide script, ruff clean for `.16.8` (`check` and `format --check`).
2. Add `.github/workflows/core-shared-drift.yml`: byte-for-byte the adventure-guide file (same name
   `Forever Core drift`, `on: schedule - cron "30 7 * * *"` plus `workflow_dispatch`, `permissions: contents: read`,
   pinned `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1` with `persist-credentials: false`,
   one step running `python3 tools/check_core_shared.py`). It must pass the repo's own `actionlint` and
   `zizmor --offline .github` CI job, so copy the pinned action and the comments rather than paraphrasing.
3. Add `python3 tools/check_core_shared.py` to the `## Commands` block in `AGENTS.md` next to the other gates, so the
   local gate and CI agree, and note in one sentence that the file is the Field Guide side of the suite's core drift
   gate (private repo, so it checks itself against public core).

Do not touch `Core/MicroButton.lua`, `tests/micro_button_spec.lua`, `Data/` or any generated file: the copies are
already correct.

## Task 2 - stop forever-core failing on a repo it cannot read

Work in `cjber/forever-core`, fresh from `origin/main`.

1. In `tools/check_consumers.py`, move `field-guide-forever` out of `MICRO_CONSUMERS` into a new documented
   `PRIVATE_CONSUMERS = ("field-guide-forever",)` constant. Leave it out of the remote comparison loop (it cannot be
   read without a token) and print, as part of the success output, one line naming the private consumer and saying it
   is gated from its own repo by `core-shared-drift.yml`. Exit status stays 0 when every readable copy matches and
   non-zero on any mismatch, exactly as now. Extend the module docstring with one sentence explaining the split:
   public consumers are compared from here, the private one compares itself against public core.
2. Leave `MICRO_CONSUMERS` correct for `adventure-guide-forever` (still compared from here) and leave
   `tools/sync_consumers.py` alone: it works on local checkouts and must keep syncing Field Guide.
3. In `docs/handoff/boundaries.md` section 5, extend the existing Field Guide bullet (the one about `bestiary-forever`
   joining the micro-button consumer list) with: Field Guide is private, so forever-core cannot read it over
   unauthenticated raw; it runs its own `tools/check_core_shared.py` from `.github/workflows/core-shared-drift.yml`
   against public core main, and `tools/check_consumers.py` lists it as a private consumer instead of fetching it.

## Gates

- forever-core: `luacheck .`, `stylua --check .`, `pipx run ruff==0.16.8 check tools`,
  `pipx run ruff==0.16.8 format --check tools`, and `python3 tools/check_consumers.py` must pass locally with no
  network error (it should now print the private-consumer line and exit 0).
- field-guide-forever: the full `## Commands` block from its `AGENTS.md`, including `stylua --check .`, `luacheck .`,
  `for spec in tests/*_spec.lua; do luajit "$spec" || exit 1; done`, `python3 tools/check_generated.py`,
  `python3 tools/visual_audit.py`, `python3 tools/check_screenshots.py`, `python3 tools/changelog.py --check`,
  `python3 .sift/gate.py --base origin/main`, `python3 .sift/agents.py check`,
  `uvx ruff@0.16.8 check tools && uvx ruff@0.16.8 format --check tools`, and run
  `python3 tools/check_core_shared.py` to confirm it exits 0 today.
- One PR per repo. Conventional commit subjects, no `-s` flag, no model names anywhere. In each PR body list the
  in-game `/reload` check the owner should do (for these two PRs: none needed, no runtime code changes - say so).
