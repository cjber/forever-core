# Fix: container item click reports ADDON_ACTION_FORBIDDEN against SkillUpForever (skillup-forever #218)

Repo: /home/nebula/wow/skillup-forever (cjber/skillup-forever), branch off origin/main.

## The report (from CurseForge, player Syrberus, 2026-10-20)

```
4x [ADDON_ACTION_FORBIDDEN] AddOn 'SkillUpForever' tried to call the protected function 'UNKNOWN()'.
[!BugGrabber/BugGrabber.lua]:554: in function '?'
[C]: in function 'UseContainerItem'
[Blizzard_UIPanels_Game/Mainline/ContainerFrame.lua]:1608: in function
[C]: in function 'ContainerFrameItemButton_OnClick'
[Blizzard_UIPanels_Game/Mainline/ContainerFrame.lua]:1681: in function
Locals:
event="ADDON_ACTION_FORBIDDEN"
addonName="SkillUpForever"
addonFunc="UNKNOWN()"
```

`badAddons` names SkillUpForever, so something SkillUp Forever does has tainted the bag item button click path, and the protected `UseContainerItem` call from Blizzard's ContainerFrame is then blocked.

## Your job

1. Read AGENTS.md in the repo first and obey it, especially the taint rules (never hook or wrap Blizzard methods, no `hooksecurefunc` on Blizzard frames, no tainted closures reaching a secure handler).
2. Find the taint source. Start with `UI/Shopping.lua` (bag and bank counts, the shopping list, the Buy reagents path) and `UI/TrackerHost.lua`. Look for anything that writes into, re-parents, sets scripts on, or otherwise touches Blizzard container frames or their item buttons, or that runs addon code from an insecure path during a click.
3. Fix it minimally, in the repo's own style, without hooking any Blizzard method and without changing behaviour players rely on. If the safe fix is to stop touching something entirely, do that and say so.
4. Add a spec under `tests/` that fails without the fix and passes with it, fully mocking the container frame, the item button and the click path (the suite already mocks frames extensively - follow `tests/client.lua` and the existing tracker specs).
5. Run the full local gate from AGENTS.md and make every command pass:
   ```
   stylua --check .
   luacheck .
   tools/typecheck.sh
   for s in tests/*_spec.lua; do luajit "$s" || exit 1; done
   python3 tools/changelog.py --check
   python3 .sift/gate.py --base origin/main && python3 .sift/agents.py check
   ```
6. Commit with a conventional message referencing (#218) and PUSH the branch `fix/218-container-taint` and open a PR against main. Omit -s on every commit (GitHub auto-signs). Do NOT tag and do NOT touch CHANGELOG version numbers - the maintainer handles release prep.

Do not change the release workflow, secrets, branch protection, or any test to make a check pass. Report back the root cause you found, the files changed, the gate results and the PR number.
