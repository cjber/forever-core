# Fix: login takes too long, the saved QuestieDB catalogue is parsed at load (adventure-guide-forever #166)

Repo: /home/nebula/wow/adventure-guide-forever (cjber/adventure-guide-forever), branch off origin/main.

## The reports
CurseForge, adventure-guide-forever: jechten 2026-10-01 "takes forever to load", user_epti4zkxgks94zs0 2026-10-02 "seems slow", Jechten "takes forever to load. seems off a bit", Naburiel "load time". GitHub issue #166 carries the audit.

## What the 2026-10-13 audit found (do not redo it)
- Load-time Lua work is already small: the QuestieDB catalogue is cached per character and adopted at PLAYER_LOGIN, cold builds are sliced at 2 ms a frame, a harness login makes 68 frames and one plan.
- The likely cost is the client parsing the large per-character saved catalogue (about 2 MB in the test corpus) before any addon code runs. Frame budgets cannot see it.
- Under 1 ms: `Geometry.Apply` re-queries about 110 map, zone and instance entries on each `ns.Data` swap, and `tests/geometry_spec.lua` asserts that it does.

## Your job
1. Read AGENTS.md first and obey it, including the taint rules and the rule that generated Data files are never hand-edited.
2. Work in `Integrations/QuestieSource.lua` (the catalogue cache, `CACHE_REVISION`, the adopt-at-login path) and `Core/` as needed.
3. Shrink the saved form so the client parses less at login, without losing the ability to adopt it whole:
   - drop fields that are cheap to rebuild from the bundled geometry or the addon metadata;
   - prefer a compact encoding over Lua table literals if it measurably shrinks the serialised size;
   - keep a version/shape marker so an old or truncated save is rejected and rebuilt (the existing `CACHE_REVISION` and shape check already do this: keep that behaviour exact, and bump the revision if the shape changes so existing players rebuild once).
4. Add a spec under `tests/` that measures the serialised size of the saved catalogue for a fixture and fails if it grows past a documented budget, plus a spec that an old-shape save is rejected and rebuilt rather than adopted.
5. Prove the win with a number: report the serialised byte size before and after for the same fixture. A change with no measurable size reduction is not worth merging; say so if that is what you find.
6. Do not change any Blizzard behaviour, any public API shape, or any test to make a check pass. `tests/plan_bench.lua` must stay within its budget.

## Gate (from AGENTS.md - run all of it)
```
stylua --check .
ruff format --check tools && ruff check tools
luacheck .
python3 tools/gen_corpus.py
tools/typecheck.sh
for s in tests/*_spec.lua; do luajit "$s" || exit 1; done
luajit -joff tests/plan_bench.lua
python3 tools/check_generated.py --offline
python3 tools/changelog.py --check
python3 .sift/gate.py --base origin/main && python3 .sift/agents.py check
```
Add a CHANGELOG.md bullet under `[Unreleased]` in the repo's prose style, credited to the reporters (jechten, Jechten, Naburiel) where it fits. Do NOT bump the version in a heading and do not tag: the maintainer does release prep.

## Commit and PR
Commit with a conventional message referencing (#166), omit -s on every commit, push branch `fix/166-login-catalogue-size`, open a PR against main.

Report back: the root cause, what you shrank and the before/after byte numbers, files changed, gate results, and the PR number/URL.
