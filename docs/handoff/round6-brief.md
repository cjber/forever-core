# Round 6: Polestar-inspired improvements (owner: "implement all of these fully", 2026-10-17)

brief.md and release-brief.md apply: signed commits with the personal email, the trailers, no model names, the
coordinator merges, strict protection, WFA-33 credits, and WFA-34 translations for every new phrase in all 9 locales
(check_locales --release). Never merge, push tags or trigger workflows. Send `READY <PR URL> <head sha>` to "main".

## Process for every PR
- **PR workflow:** follow /home/user/skills/pr/SKILL.md. Where it calls for a Codex arm and no Codex is available here,
  say so in the PR and do the extra Claude review pass it asks for instead.
- **Reviews:** run /home/user/skills/review/SKILL.md and the `code-review` skill (high), then /home/user/skills/simplify
  on your diff. Fix real findings.
- **End-to-end tests:** the game can't run here, so test as end to end as the repo allows:
  - new specs for every behaviour;
  - the repo's harness and smoke specs (AGF's smoke spec, SPF's route goldens, plan bench and nav QA);
  - screenshots re-rendered twice to be byte-identical, with any changed image inspected;
  - `tools/check_package.py` on a locally built package with the pinned packager;
  - the full `## Commands` gate.
  - List the in-game `/reload` checks in the PR body.
- **No copying:** Polestar's code (GPL-3.0, at /tmp/claude-0/-home-user/76bf530e-5da5-583c-877f-df32f2ad82fa/scratchpad/ext/ps)
  is for reading the idea only. Write our own code. Credit the idea in THIRD_PARTY.md's Ideas table and in the changelog
  where a feature follows another addon: Ding! by Yendi for level-aware walks, and Polestar for the others.
- **Worktrees:** branch from fresh origin/main in your own worktree under /home/user/wt/r6-<slug>. Several agents work
  in the same repo, so merge origin/main before READY and resolve CHANGELOG/Locales conflicts with the repo tooling.

## Work items
**SPF**
- **S1, planner costs (agent A):**
  - (a) Walks avoid zones far above your level. A zone's lowest level ≥ 4 above yours costs heavily, and the walk is
    re-planned on level-up. Use zone level ranges SPF can bundle legitimately (the Warcraft Wiki data AGF and Tweaks
    already credit, or the client's own tables). Add the setting "Avoid zones far above my level" (on), with a tracker
    or tooltip note when a route detours. Credit the idea to Ding! by Yendi.
  - (b) Route styles: Fastest, Balanced (default) and Roads. Use our own ground classes in SPF's baker (road, steep,
    water edge) and our own cost profiles; re-bake through the documented generator, never by hand.
  - (c) Walks avoid the other faction's towns, with a "Hostile town: X" warning when unavoidable.
  - (d) Arrival at cave and mine mouths by subzone, as SPF already does for dungeon doors.
  - Update goldens only where the new costs explain the change, and list every golden change.
- **S2, gamepad-safe map drawing (agent B):** draw SPF's world-map and minimap content as SPF's own overlay frames on
  the map canvas, without `AddDataProvider` or `AcquirePin`. Keep every pin's behaviour: clicks, tooltips, Shift-click
  and scaling. Prove nothing of Blizzard's map tables is written, with a spec. Goal: fix SPF #158's gamepad taint.
  Comment on #158 with what changed and leave it open for the in-game A/B.
- **S3, TomTom and Polestar compatibility (agent T, small):**
  - With Polestar's TomTom stand-in or its `/way` claimed, SPF's stand-in, `/way` and Follow TomTom must not be
    blocked or double-handled. Test the load orders with stubs.
  - Make sure SPF's public API meanings that Polestar relies on (`Subscribe`, `Active`, `CurrentStop`, `Ended`,
    `Cancel`, `NavigateRoute` options) are pinned by a contract spec so they can't drift.
  - Document both in docs.

**AGF**
- **A1, quest safety (agent D):**
  - (a) Warn before taking a quest that closes another: chat names what you'd lose, using AGF's existing exclusive
    groups, once per quest, with a setting.
  - (b) Each step says when it needs a group ("Elite: group advised", "Dungeon: X", "Group of N"), from data AGF
    already has.
- **A2, where to go (agent E):**
  - (a) Kill and collect objectives prefer normal mobs over elites, and the main camp (densest cluster) over lone
    spawns, built on 0.14's level weighting.
  - (b) Cave and mine objectives arrive by subzone, leading to the mouth first.
  - (c) Quest items that expire: when a timed quest item is in the bags, its turn-in moves up the route.
- **A3, party (agent F):** when grouped, favour quests that party members share or can share. Use addon messages only
  if cheap and safe, otherwise the party's visible quest data. It's on by default, with a setting. It must stay
  dynamic, never a fixed order.
- **A4, gamepad-safe map drawing (agent G):** the same as S2, for AGF's UI/Pins.lua.

**Tweaks and Legacy**
- **H, gamepad-safe map drawing (agent H):** check Tweaks' and Legacy's map modules for `AddDataProvider`,
  `AcquirePin` and map table writes. Port the overlay approach where found, with specs. Comment on Tweaks #168.

## After the merges
Release prep for SPF 1.20.0 and AGF 0.18.0, plus Tweaks and Legacy patch releases if H changed them. Each repo's last
agent to finish does its release prep, and the coordinator says which.
