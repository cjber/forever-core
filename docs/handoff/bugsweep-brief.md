# Bug sweep, 2026-10-17 (owner: "full sweep of bug reports… some fairly bad ones")

brief.md applies: signed commits, trailers, the coordinator merges, WFA-33 credit (name the reporter), and WFA-34
translations. Follow /home/user/skills/pr/SKILL.md and run the code-review skill (high). Every fix gets a spec that
fails on the old code. For each report, first open a GitHub issue ("Reported on CurseForge by <user>, <date>: …", with
the full text quoted), then fix it with `Closes #N`. Round 6 agents are also working in these repos, so use your own
worktree from fresh origin/main and merge main before READY.

## SkillUp (urgent)
1. **syrberus, 10-17: taint, 196 times.**
   - The error: `Blizzard_SharedXML/SharedTooltipTemplates.lua:208: attempt to perform arithmetic on a secret number
     value (execution tainted by 'SkillUpForever')` in `GameTooltip_InsertFrame`, called from
     `SkillUpForever/UI/Tooltip.lua:258`, from the Professions recipe list's OnEnter (a CallbackRegistry TriggerEvent).
   - **Cause:** inserting our frame into GameTooltip through Blizzard's helper runs Blizzard code on tainted, secret
     values.
   - **Fix:** stop calling GameTooltip_InsertFrame and any Blizzard tooltip layout helper with our values. Draw the
     skill-up bar as our own frame anchored to the tooltip (or plain tooltip lines), with no arithmetic on values the
     tooltip owns. Search every SkillUp tooltip path for the same pattern.
   - Comment on and credit syrberus.
2. **kurila11478, 10-17: "I had selected 'buy reagents,' but now I can no longer uncheck the box. Also, my leveling
   route isn't displaying anything anymore."**
   - Reproduce it in the harness: the setting is stuck, and the route comes out empty. Likely a saved-variable or
     migration problem (the 0.14/0.15 changes, the Forever addons setting migration), or an error that stops the route
     building.
   - Fix it, add a migration that repairs bad saved state, and add specs.
3. **ballara, 10-17: the recipe tooltip covers the reagent list. Asked to move it.**
   - Add a setting to anchor SkillUp's recipe tooltip beside the Professions window (or to the cursor) instead of over
     the reagents.
   - Keep the default behaviour unless the current default actually covers the reagents for most recipes; then pick
     the better default and say why.
- Release SkillUp 0.15.1 (bugs only) as soon as 1 and 2 merge. Item 3 can ride along if ready, otherwise 0.16.0.

## Legacy
4. **overspark, 10-17: "an option to disable drawing dungeon entrances on the map"** (other addons already draw them).
   - Add a map-menu and settings toggle, "Show dungeon and raid entrances" (on), that hides Legacy's entrance pins only.
     Zone badges and shading stay.
   - Coordinate with round 6 agent H, who is rewriting Legacy's map drawing: build on H's overlay once its PR merges,
     or keep the change small so it rebases easily.

## SPF and the shared tracker
5. **deathmvp1, 10-15: the Shortest Path journal sits behind the quest list with Questie's tracker.**
   - With Questie's own tracker, SPF attaches to the hidden or empty Blizzard tracker.
   - Detect Questie's tracker frame (read-only, feature-detected) and either attach to it, or auto-detach to a movable
     position that doesn't overlap.
   - This lives in the shared UI/TrackerHost.lua (byte-identical in SPF, AGF, SkillUp and Legacy): change it in SPF
     first, then port it byte for byte with the sha pins.
6. **AGF #203, the tracker background** (anonymous CurseForge request): an optional background behind the shared
   tracker column with an opacity slider, off by default. The same shared TrackerHost change goes in one PR with item 5.
- Credit deathmvp1 (CurseForge handle) and berserkerlxl, who diagnosed it.
