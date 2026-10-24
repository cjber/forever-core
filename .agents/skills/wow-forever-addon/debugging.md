# Debugging a Forever addon in game

Reference for the failures headless specs miss. Blizzard's source for the build is Gethe/wow-ui-source,
branch `forever`; diff the build you have against the latest before blaming addon code.

## Taint and blocked actions

A blocked action is blamed on the addon whose taint the game read, often far from the call that was
blocked. Find the read, not the call.

- `/console taintLog 4`, `/reload`, reproduce, read `Logs/taint.log`. Levels: 1 blocked actions,
  2 globals, 3 upvalues, 4 table fields. Below 4 the log never names a tainted field. Set it back to 0.
- `issecurevariable(table, "key")` returns the addon that tainted a field, for example
  `/dump issecurevariable(WorldMapFrame, "mapID")`.
- Bisect an interaction between addons with `C_AddOns.DisableAddOn(name)` and `ReloadUI()`. A block
  blamed on one addon can need a second one loaded.
- Blizzard iterates map data providers through `secureexecuterange`, so registering a provider does
  not taint the others. What taints Blizzard's own code is state an addon wrote that it later reads:
  a field written by calling a Blizzard method from addon code, or a lazy cache first filled during
  an addon's call. `tools/lint_taint.py` lists the calls already known to do this; add each new one.
- A provider's inherited `RegisterEvent` goes through the map (`AddDataProviderEvent`) and writes the
  addon's taint into the event counts every provider shares. Blizzard's quest provider then runs
  tainted and its pins hit `ADDON_ACTION_BLOCKED ... SetPassThroughButtons()` in combat, blamed on the
  addon. `CVarMapCanvasDataProviderMixin` does this from `OnShow`: build on `MapCanvasDataProviderMixin`
  and listen on a frame of your own.
- The taint is planted when the map opens out of combat and the block fires on a later open in combat,
  so reproduce in that order.
- Opening or retargeting the world map from addon code (`OpenWorldMap`, `ToggleWorldMap`, `OpenQuestLog`,
  `WorldMapFrame:SetMapID`, `QuestMapFrame_ShowQuestDetails`) taints its map fields until a reload, with
  the same blocked pins in combat. `C_Map.OpenWorldMap(uiMapID)` has the game open and retarget it from
  its own code, and the map is shown before the call returns. Nothing clean brings back a collapsed quest
  sidebar or opens the quest details page.
- `issecurevariable` can read secure while the block still follows (the `OpenQuestLog` case). Count
  blocked actions over several map opens in combat; treat the field check as a hint.
- An addon's own map pins are acquired through `AcquirePin`, which calls the protected
  `SetPassThroughButtons`. HereBeDragons-Pins makes that a no-op on its pin mixin.

## Layout that only breaks live

- `UI/TrackerHost.lua` is shared by the tracker addons and the client runs whichever copy loads
  first. Change every copy before reloading, and keep them byte-identical.
- In combat the game restores `ObjectiveTrackerFrame` to its own height and addon code cannot resize
  it. Clamped to the screen, the taller frame is pushed over whatever is stacked above it.
- Other addons place buttons on the map without registering them: Krowi_WorldMapButtons (bundled with
  Questie) uses globals `Krowi_WorldMapButtons<N>` and the canvas's top-right slot, outside
  `WorldMapFrame.overlayFrames`. Test beside Questie.
- Settings rows cut long labels with an ellipsis, and a slider shows no value until its options get
  `SetLabelFormatter(MinimalSliderWithSteppersMixin.Label.Right, format)`.
- Game panels can be locked: `ToggleLegacySystemUI()` does nothing until the Legacy reward track has
  renown. Disable the entry and show the game's own locked tooltip instead of a dead button.

## Performance

- Measure in game before choosing a fix: accumulate `debugprofilestop()` around each stage and print
  the totals once, with the slice set high enough to run the job in one frame. Strip it before
  committing.
- `C_AddOnProfiler.MeasureCall(func, ...)` times one call; `C_AddOnProfiler.GetAddOnMetric(name,
  Enum.AddOnProfilerMetric.PeakTime)` and the `CountTimeOver*` metrics give a spike check after a run.
- Hot loops over provider data: key tables by number, not by concatenated strings; hoist constant
  tables out of the loop; check the clock once per batch, not per item.
- The headless clock in the specs is a stub, so a spec proves slicing and never speed.

## Reading results without a screenshot

- SavedVariables are written on `/reload`; a dump command that stores its result there can be read
  from disk.
- `/chatlog` writes chat to `Logs/WoWChatLog.txt`. `Logs/FrameXML.log` reports load failures such as
  a missing TOC file. `/console addonLoadDebugging 1` writes `Logs/AddOnLoad.log`.
- The addon namespace is not a global, so `/run` cannot reach it: print from inside the addon with a
  fixed prefix.
