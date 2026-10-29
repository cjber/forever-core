# Field Guide: run the generated-data gate in CI

Repo: `cjber/field-guide-forever` (addon name Field Guide Forever). Branch: `ci/generated-data-gate`.

## The gap

`AGENTS.md` > Commands lists `python3 tools/check_generated.py` as part of the local gate, and every
sibling addon (adventure-guide-forever, legacy-forever, shortest-path-forever, skillup-forever,
tweaks-forever) runs that same gate as a CI job. Field Guide does not: `.github/workflows/ci.yml` has
`deadcode`, `check`, `python`, `sift`, `changelog`, gitleaks and package jobs, but no generated-data job.

It was removed, correctly at the time, in `a3ddd8e` ("ci: check what this addon actually has") because the
scaffolded workflow called tooling that did not exist in the repo yet. Since then `tools/gen_zones.py`,
`tools/gen_creature_icons.py` and `tools/check_generated.py` have all landed, so the two shipped data files
(`Data/Client.lua`, `Data/CreatureIcons.lua`) are generated, hand-edit forbidden, and currently enforced by
nothing on push or PR.

## What to change

1. `tools/check_generated.py`
   - Add an opt-in `--offline` flag, default off, matching the sibling repos' `check_generated.py`
     (`adventure-guide-forever/tools/check_generated.py` line ~50 is the reference).
   - Pass the mode through to BOTH generator invocations (`tools/gen_zones.py` and
     `tools/gen_creature_icons.py`) instead of hardcoding `--offline`.
   - Keep everything else exactly as it is: the two-run byte-stability assertion, the "is stale;
     regenerate it with ..." SystemExit messages, and the final pinned-listfile icon coverage check.

2. `.github/workflows/ci.yml`
   - Add a `generated-data` job modelled on `adventure-guide-forever`'s:
     checkout with `persist-credentials: false`, then `actions/cache` with `path: tools/.cache`,
     `key: regeneration-${{ runner.os }}-${{ hashFiles('tools/gen_*.py') }}`,
     `restore-keys: regeneration-${{ runner.os }}-`, then `run: python3 tools/check_generated.py`.
   - Reuse the pinned action SHAs already present in this repo's `ci.yml`
     (`actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1`, `actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9`).
   - Give it `timeout-minutes: 20`, like the siblings.

## Constraints

- Do not change any file under `Data/`, `release.yml` or any other workflow. No new Python dependencies.
- Keep `ruff check tools` and `ruff format --check tools` and `ty` green.
- Commit without `-s`.

## Verification required (report the exact commands and output)

1. Cold cache, proving the new default works in CI where `tools/.cache` starts empty: move
   `tools/.cache` aside, then `python3 tools/check_generated.py`. It must download the pinned sources,
   verify their sha256 pins, and print both "Generated client data is fresh and byte-stable." and
   "Generated creature icon data is fresh and byte-stable." plus the listfile line.
2. Warm cache, offline mode: `python3 tools/check_generated.py --offline` on the now-populated cache.
3. Confirm `git status --porcelain` shows no change under `Data/` after both runs.
4. Run the rest of the `AGENTS.md` Commands gate: `stylua --check .`, `luacheck .`, the `tests/*_spec.lua`
   loop with `luajit`, `python3 tools/check_core_shared.py`, `python3 tools/visual_audit.py`,
   `python3 tools/check_screenshots.py`, `python3 tools/changelog.py --check`, and the sift gate.
5. Lint the workflow with actionlint.

## Deliverable

One PR titled `ci: run the generated-data gate on every push and PR`. Body must say why the job was absent
(reference `a3ddd8e`) and why it is safe now, and include the verification output above.

CI and tooling only: no version bump, no CHANGELOG entry, no release.
