# AGF 256: data refresh blocked - QuestieDB v1.0.7 breaks laps_spec stability

Repo: cjber/adventure-guide-forever. Branch from current origin/main (20720be).

## What happened

The scheduled `Refresh game data` workflow (2026-10-24 06:07Z) moved the QuestieDB pin
`v1.0.6 -> v1.0.7`, regenerated `Data/` and then failed the spec step. The retry re-run
failed the same way, so it filed issue cjber/adventure-guide-forever#256 ("Data refresh
failed"). Until this passes, the bundled data stays pinned to v1.0.6 and the refresh PR
can never open.

## Reproduced locally (verified)

```
git worktree add --detach /tmp/agf-repro main
cd /tmp/agf-repro
python3 tools/refresh_pins.py            # prints: QUESTIEDB_TAG v1.0.6 -> v1.0.7
python3 tools/gen_quests.py && python3 tools/diff_forever.py && \
python3 tools/gen_zoneart.py && python3 tools/gen_corpus.py && \
python3 tools/catalogue_revision.py --write
luajit tests/laps_spec.lua
```

Result: `laps_spec: 531776 checks, 2 failed`, both stability failures:

```
  seed 4, character 56 (level 10 at 1426:0.8628:0.4881): a rebuild with nothing changed keeps the route
  seed 12, character 42 (level 21 at 1413:0.3526:0.2788): a rebuild with nothing changed keeps the route
```

The check is in `tests/laps_spec.lua` `Stability`: `Keys(third, key) == Keys(again, key)`
where `again = Plan(..., last=first)` and `third = Plan(..., last=again)`. So a second
rebuild with nothing changed changes the route - a real planner nondeterminism the new
data exposes. Reproduce just these two with `AGF_LAPS_SEED=4` / `AGF_LAPS_SEED=12`.

The workflow log showed a different first symptom in CI (`Planning/Journeys.lua:862:
attempt to yield across C-call boundary` in the same laps_spec). Treat that as a second
face of the same failing run: the CI refresh failed on laps_spec with the v1.0.7 data.

## The fix

- Diagnose the nondeterminism in the planner (`Planning/Journeys.lua`, `Planning/Plan.lua`,
  or an ordering that iterates a hash table). Do NOT loosen or delete the check, and do
  NOT touch the golden routes to hide it - the check is an invariant, not a golden value.
- Keep the QuestieDB pin at v1.0.7 (`tools/gen_corpus.py` QUESTIEDB_TAG/SHA256) and the
  regenerated `Data/` from the repo's own generators. Never hand-edit generated data.
- Gate: `luacheck .`, every `tests/*_spec.lua` under `luajit`, `luajit -joff
  tests/plan_bench.lua`, `python3 tools/check_generated.py --offline`, stylua 2.5.2
  `--check .`, ruff on `tools/`, and the generator unit tests. All must pass with v1.0.7.

## Deliverable

One PR to cjber/adventure-guide-forever main that carries the pin bump, the regenerated
`Data/`, the planner fix and a `CHANGELOG.md` Unreleased line. Commit without `-s`.
Report the PR number, the failing-check explanation, and the exact local gate results.
