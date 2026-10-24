# Fix: shared tracker drift - own the section parent in spf, agf and legacy
Brief also pushed to cjber/skills, branch ccr-cc333990-q8ydc4-handoff, forever-handoff/tracker-drift-container.md

## What is wrong

The suite contract says these five files must be byte-identical on main across
shortest-path-forever, adventure-guide-forever, skillup-forever and legacy-forever
(`tools/check_shared_tracker.py`, workflow "Shared tracker drift", runs daily 07:30):

    UI/TrackerHost.lua
    UI/TrackerQuestie.lua
    tools/fetch_tracker_ui.py
    tests/tracker_host_spec.lua
    tests/tracker_questie_spec.lua

Right now two of them have drifted, and the daily workflow has been red since 2026-10-20:

- `UI/TrackerHost.lua`: skillup has an addon-owned `Module:SetContainer`; spf, agf and legacy do not.
- `tests/tracker_questie_spec.lua`: skillup stubs `module.SetParent` in its tracker spec; the other three do not.

This is a real bug, not just a hash mismatch. skillup fixed it on 2026-10-21 in commit `8fba0d1`
("fix(tracker): own the section parent instead of calling Blizzard SetContainer (#218)"), because
calling Blizzard's native `ObjectiveTrackerModuleMixin:SetContainer` registers our section with
Blizzard's tracker manager and taints the protected bag/objective click path (#218, ADDON_ACTION_FORBIDDEN
on UseContainerItem). skillup's `TrackerHost` keeps `module:SetContainer(host)` in `api.Attach`, but now
that resolves to the addon-owned method below, which only stores the container and reparents our own frame:

```lua
local Module = {}
function Module:SetContainer(container)
	self.parentContainer = container
	self:SetParent(container)
end
```

spf, agf and legacy still have no such method, so every attach goes through Blizzard's tainted path.

## Your job

For each of these three repos, working from fresh `origin/main`, on a branch named
`fix/shared-tracker-container`:

- shortest-path-forever (main 4c5e585)
- adventure-guide-forever (main 1b66d6a)
- legacy-forever (main 9d70f9f)

1. Read the repo's AGENTS.md first and obey it, especially the taint rules.
2. Bring these four files to the exact content skillup-forever has on its main (they differ only in the
   tracker-container change; take skillup's version wholesale and confirm with a diff that nothing else moves):
   - `UI/TrackerHost.lua` (adds `Module:SetContainer`)
   - `tests/tracker_questie_spec.lua` (adds the `module.SetParent` stub)
   - `tests/tracker_geometry_spec.lua` (same stub - not in the shared list, but the spec needs it once
     `Module:SetContainer` calls `self:SetParent`)
   - `tests/tracker_host_harness.lua` (its mock `m:SetContainer` must call
     `env.ObjectiveTrackerManager:SetModuleContainer(self, container)` so a regression back to the native
     path is caught)
3. Add `tests/container_item_click_spec.lua` exactly as skillup has it - the mocked bag-click regression
   spec that fails if the host ever registers the section with Blizzard's manager again.
4. Run the repo's full local gate from AGENTS.md and make every command pass, at minimum:
   ```
   stylua --check .
   luacheck .
   tools/typecheck.sh
   for s in tests/*_spec.lua; do luajit "$s" || exit 1; done
   python3 tools/changelog.py --check
   python3 .sift/gate.py --base origin/main && python3 .sift/agents.py check
   ```
5. Commit with a conventional message (`fix(tracker): own the section parent instead of calling Blizzard SetContainer`)
   and PUSH each branch, then open a PR against main in each repo. Omit `-s` on every commit.
   Do NOT tag, do NOT touch CHANGELOG version numbers or TOC versions - the maintainer handles release prep.
6. After all three PRs are pushed, run `python3 tools/check_shared_tracker.py` from a fresh
   shortest-path-forever clone: it compares main, so it should still fail until the PRs merge. Instead,
   verify each PR head produces the identical sha256 for all five shared files:
   `curl -s https://raw.githubusercontent.com/cjber/<repo>/<branch>/<path> | sha256sum` and compare
   against `https://raw.githubusercontent.com/cjber/skillup-forever/main/<path>`. All four must match.

Do not change release workflows, secrets, branch protection, screenshot baselines, generated data,
or any test to make a check pass. Report back: the PR number per repo, the gate results, and the
five sha256 comparisons.
