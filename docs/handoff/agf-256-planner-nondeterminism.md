# AGF #256: fix the planner rebuild nondeterminism on QuestieDB v1.0.7

Repo: cjber/adventure-guide-forever. Branch from current origin/main (20720be).
Supersedes the diagnosis in forever-handoff/agf-256-refresh-questiedb-1.0.7.md (keep that task, add this root cause).

## Repro (verified)

```sh
git worktree add --detach /tmp/agf-fix main && cd /tmp/agf-fix
python3 tools/refresh_pins.py            # QUESTIEDB_TAG v1.0.6 -> v1.0.7
python3 tools/gen_quests.py && python3 tools/diff_forever.py && \
python3 tools/gen_zoneart.py && python3 tools/gen_corpus.py && \
python3 tools/catalogue_revision.py --write
luajit tests/laps_spec.lua               # 531776 checks, 2 failed
```
Both failures are the Stability invariant `Keys(third, key) == Keys(again, key)`
(`again = Plan(..., last=first)`, `third = Plan(..., last=again)`):
- seed 4, character 56 (level 10 at 1426:0.8628:0.4881)
- seed 12, character 42 (level 21 at 1413:0.3526:0.2788)

Reproduce one alone with `AGF_LAPS_SEED=4 luajit tests/laps_spec.lua` (add a temporary
`CHARACTERS=56` cap and `SEEDS={4}` to iterate in ~13 s instead of 4 min).

## Root cause (confirmed with instrumentation)

The rebuild does not reach a fixed point: the route oscillates 10 -> 8 -> 10 steps for
seed 4 char 56, because `Planning/Laps.lua` `Verify()` over-reserves quest-log capacity.

`Verify` walks the re-committed steps simulating the client log (`cap = player.logMax`,
`left` = slots held). For a **new** pickup it requires `left + owed < cap`, where
`owed` counts the committed pickups (`lap.picked`, i.e. the previous route's
`order.picked`) still ahead in the step list. For a committed pickup it only requires
`left < cap`.

`lap.picked` is every town pickup of the previous route. A route with `logMax = 4`
legitimately picks up 7 quests, because hand-ins along the way free slots. So
`#picked (7) > cap (4)`, and the reservation "leave room for all 7 committed pickups at
once" is unsatisfiable — every new pickup is rejected, the towns empty, and `Verify`
drops those steps.

Trace of the three builds (`VERIFY-HEAD n=<steps> count=<log> cap=<logMax> pickedN=<#picked> owed0=<initial owed>`):

```
first  (last=nil):    walk 30 -> commit 26 -> route 10, order 26
again  (last=first):  VERIFY-HEAD n=30 count=0 cap=4 pickedN=7 owed0=7  -> route 8,  order 8
third  (last=again):  VERIFY-HEAD n=30 count=0 cap=4 pickedN=6 owed0=6  -> route 10, order 28
```

The collapsed `again` route commits the smaller `picked` set (6), so `third`'s
reservation is satisfiable and the route grows back to 10 — a period-2 cycle. `first`
(no committed order, `picked={}`) and `third` both reach 10; only the middle rebuild
shrinks. That is exactly the "rebuild with nothing changed keeps the route" invariant
failing.

The committed order for `first` holds 26 idents (10 route steps + 16 steps past
`Model.MAX_STEPS`, which `MergeLapVisits` deliberately keeps). That is by design and is
not itself the bug; the bug is the capacity reservation in `Verify`.

## What to fix

Fix the reservation in `Planning/Laps.lua` `Verify()` so a committed route that is
walkable stays walkable on rebuild. The reservation must not require room for more
committed pickups than the log can hold at once: it has to account for the committed
hand-ins ahead that free slots (e.g. reserve only the peak excess of committed pickups
over committed hand-ins still ahead, instead of the raw count), so new pickups in held
steps are not rejected when the committed pickups ahead will not coexist.

Constraints:
- Do NOT loosen, skip or delete the stability check, and do NOT touch `tests/golden/`.
- Keep the QuestieDB pin at v1.0.7 (`tools/gen_corpus.py` QUESTIEDB_TAG/SHA256) and the
  regenerated `Data/` from the repo's own generators. Never hand-edit generated data.
- Preserve the committed-order semantics of docs/design.md §4.3.

## Gate (all must pass locally with v1.0.7)

```sh
luacheck .
for s in tests/*_spec.lua; do luajit "$s" || exit 1; done     # laps_spec included (~4 min)
luajit -joff tests/plan_bench.lua
python3 tools/check_generated.py --offline
stylua 2.5.2 --check .
ruff format --check tools && ruff check tools
python3 tools/changelog.py --check
# generator unit tests
python3 tools/gen_corpus_test.py && python3 tools/gen_quests_test.py && \
python3 tools/gen_zoneart_test.py && python3 tools/diff_forever_test.py && \
python3 tools/catalogue_revision_test.py && python3 tools/refresh_pins_test.py && \
python3 tools/check_generated_test.py
```

## Deliverable

ONE PR to cjber/adventure-guide-forever main carrying the v1.0.7 pin bump, the
regenerated `Data/`, the `Planning/Laps.lua` fix and a `CHANGELOG.md` **Unreleased**
line. Commit without `-s`. Report the PR number, the root-cause explanation and the
exact local gate output. Do not merge.

---

## Deeper findings (run #88, 2026-10-24) - fix NOT yet landed

The oscillation is driven from the walk, not (only) the Verify reservation. For seed 4
char 56 the three builds differ as:

```
first  (last=nil):    route 10 steps, ends ... 136:2 138
again  (last=first):  route 8  steps, ends ... area:98321:4   (136:2 and 138 dropped)
third  (last=again):  route 10 steps, ends ... 136:2 801
```

`Planning/Laps.lua` `Handable()` refuses the return visit to `town:1426:136` in the
`again` build. Instrumented (`HANDABLE town:1426:136 id=384 back=9 before=true log=false
pending=2 ranked=7 done=1 guard=true inner=true`): the hand-in for quest 384 has
`pending=2` objectives but the walk only ever works `done=1` of them, so the guard passes
and the inner check `(done or 0) ~= pending` returns false. With the return visit refused,
the log never frees a slot (`left` stays at `cap`), so every later pickup is rejected and
the route collapses. The committed order (which holds `town:1426:136<<` at rank 9) is what
makes `Handable` treat 384 as a hand-in to wait for.

### Fixes tried and REJECTED (do not repeat)

1. Drop steps past `Model.MAX_STEPS` from the committed order (move the `route[index]=nil`
   truncation in `MergeLapVisits` before the `held` map): seed 4 passes, but the full
   `tests/laps_spec.lua` goes to **531755 checks, 32 failed** (was 2). The "a step past the
   step limit stays in the order" behaviour is load-bearing.
2. `NameLapAreas`: `lap.ranked[id] = math.max(...)` instead of `math.min(...)` (the
   Handable guard bound): seed 4 unchanged (**26343 checks, 1 failed**). Not the lever.
3. Relax `Handable` to take the close when **any** hand-in is ready instead of requiring
   all: `tests/laps_spec.lua` passes (**490237 checks, 0 failed**) but it changes route
   content broadly (check count 531776 -> 490237) and **`tests/plan_golden_spec.lua` fails**
   (assertion in `tests/plan_golden_spec.lua:269`). Too broad; changes the golden routes.

### Suggested direction

Keep the committed-order semantics intact and make `Handable`/`BuildLapAnchors` stop a
hand-in whose quest the committed order never picks up or works from holding back the
return visit - i.e. detect the case the comment above `Handable` already describes ("the
last build's check gave its pickup to the log's limit") precisely, rather than loosening
the all-ready rule or dropping post-limit steps. A correct fix must leave
`tests/plan_golden_spec.lua` and the `laps_spec` check count unchanged (route content must
not move) while turning the 2 stability failures green.

### Working state left behind

`git worktree` `/tmp/agf-fix2` (detached main 20720be) holds the v1.0.7 regenerated
`Data/`, `tools/gen_corpus.py` pin v1.0.7 and `tests/.corpus`, with the relaxed-`Handable`
experiment in `Planning/Laps.lua` (revert with `git checkout -- Planning/Laps.lua`). Remove
with `git -C /home/nebula/wow/adventure-guide-forever worktree remove --force /tmp/agf-fix2`.

## CONFIRMED MECHANISM (run 90, sandbox, QuestieDB v1.0.7, seed 4 char 56)

The root cause in "What to fix" above (Verify over-reserving capacity) is NOT the seed-4 cause. Instrumented
`Planning/Laps.lua` (Verify / WalkLap / Consider / Handable) with the v1.0.7 data. The cycle is:

- **Build A** (`last=nil`): walk `W_A` places `area:384:4` and `area:412:4` as stops for quests 384/412 near
  `town:1426:136`. `Verify(A)` **rejects the pickups 384 and 412** at that town because the log cap is 4 and the
  four earlier pickups (96608, 98321, 98322, 99158) already fill it (`left=4 cap=4`, `owed=0`). Their areas are
  then orphaned (objectives neither in `log` nor picked up) and dropped: `VERIFYDROP area:384:4` / `area:412:4`.
  So A's route `R_A` (26 steps) lacks them, and the committed order `O_A = Idents(R_A)` lacks them too.
- **Build B** (`last=first`): with `O_A`, `Consider()` gives committed steps `held - 6000000`, so after
  `area:98321:4` the walk takes committed `town:1426:138` (cost 822.6) over the **new** areas 384:4/412:4. B never
  works them, so `Handable(town:1426:136)` stays false (its hands 384/412 are never done), the committed return
  visit `town:1426:136<<` is never taken, and B's walk runs on; `Verify(B)` then collapses to **8 steps**.
- **Build C** (`last=again`): `O_B` (from `R_B`) no longer pulls the walk to 138, so C's walk == A's walk again ->
  10 steps. Hence `C != B` (the failing invariant) - a period-2 cycle.

At `town:1426:136` in build A the rejection is genuine log capacity (`owed=0`), so the reservation theory does not
apply. I implemented and tested the brief's suggested fix (reserve only the peak excess of committed pickups over
committed hand-ins still ahead, instead of the raw committed-pickup count) in `Verify()`: **it did not change the
outcome** - `AGF_LAPS_SEED=4` still `1 failed`, `AGF_LAPS_SEED=12` still `1 failed`.

**Best hypothesis for a correct fix**: the committed order `O_A` must not carry a return visit
(`town:1426:136<<`) whose prerequisite areas (384:4/412:4) it does not hold; or the rebuild must not let that
unreachable committed visit re-route the walk (the walk's placement of areas for quests whose pickups the log
cannot hold, then Verify rejecting the pickup, is the inconsistency that seeds the cycle). Constraints unchanged:
keep `tests/plan_golden_spec.lua` passing and the `laps_spec` check count unchanged, do not touch `tests/golden/`.

**Rejected fixes (do not repeat)**: (1) drop steps past `Model.MAX_STEPS` from the committed order -> laps_spec
32 failed; (2) `NameLapAreas lap.ranked[id] = math.max` -> no effect; (3) relax `Handable` to any-hand-in-ready ->
laps_spec passes but `plan_golden_spec.lua:269` fails.

Fast repro: `AGF_LAPS_SEED=4 luajit tests/laps_spec.lua` (~35 s, 1 failed); `AGF_LAPS_SEED=12` (1 failed).
