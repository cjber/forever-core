# Shortest Path #271, part 2: never fight another waypoint addon for the native user waypoint

Repo: `cjber/shortest-path-forever`. Issue: #271 (read it and its triage comment first).

Scope: **part 2 only**. Part 1 of #271, an in-world destination pin, is NOT in scope and #271 must
stay open after this work.

## The prerequisite the triage comment asked for, now done

Waypoint UI (the addon overspark runs beside us) is public and readable, so there is no guessing left:

- Source: `github.com/Adaptvx/Waypoint-UI`, GPLv3. It ships a `Forever` flavour for 1.60.1,
  current release 1.7.4, CurseForge project 1275146.
- It draws its own world-space pin **and** drives the client's native user waypoint. In
  `Code/MapPin/MapPin.lua` it caches `C_Map.SetUserWaypoint`, `C_Map.ClearUserWaypoint`,
  `C_Map.HasUserWaypoint`, `C_Map.GetUserWaypoint`, compares with
  `USER_WAYPOINT_TOLERANCE = 0.0005`, and validates its session:
  `MapPinUtil.ValidateUserNavigationState` calls `MapPin.ClearUserNavigation(true)` when the
  highest-priority super-tracking type is `UserWaypoint` but `MapPin.IsUserNavigationTracked()`
  is false. Its `USER_WAYPOINT_UPDATED` handler drops its navigation when no user waypoint exists.
- It exposes a public global for other addons, `WaypointUIAPI` (root `API.lua`):
  `WaypointUIAPI.Navigation` with `IsUserNavigationTracked()`, `IsUserNavigationFlagged(flag)`,
  `IsPathStepWaypointTracked()`, `ClearDestination()`, `ClearUserNavigation(preserveWaypoint?, suppressAdvance?)`,
  `NewUserNavigation(options)`, `NewPin(options)`, `GetUserNavigation()`, `GetPin(id)`,
  `GetAllPins()`, `ClearPin(id)`, `ClearAllPins()`; plus `WaypointUIAPI.OpenSettingsUI()`.
  `NewUserNavigation` options keys: `name, mapID, x, y, flags, iconTexture, r, g, b,
  requestRecolor, iconType, suppressAudio, stripCoordinates`.

So both addons write the one client user waypoint and both treat a waypoint that is not theirs as
foreign. `Journey/JourneyGuide.lua` already owns the native waypoint while it guides
(`guide.expectedWaypoint`, `ns.charDB.guideWaypoint`, `StopGuide` restoring
`previous.previousWaypoint`, `OwnsWaypoint` stopping guidance when the waypoint changes). With
Waypoint UI loaded, each one's write ends the other's: last writer wins. That is the report.

## What to change

Rule: one writer at a time, and Shortest Path yields.

1. **Detect Waypoint UI lazily**, at the point of use and not at load (it may load after us):
   `C_AddOns.IsAddOnLoaded("WaypointUI")` and `_G.WaypointUIAPI` with a
   `Navigation.IsUserNavigationTracked` function.
2. **Do not touch the native waypoint while Waypoint UI is tracking one.** In
   `Journey/JourneyGuide.lua`, when the detection above holds, the guide must not call
   `C_Map.SetUserWaypoint`, `C_Map.ClearUserWaypoint` or `C_SuperTrack.SetSuperTrackedUserWaypoint`.
   Everything that does not need the native waypoint keeps working: arrow, compass, tracker,
   `UI/StopPin.lua`, `UI/MinimapPins.lua`, the map drawing.
3. **Hand the destination over instead of fighting.** When a journey starts or its bend changes
   while Waypoint UI is tracking, call
   `WaypointUIAPI.Navigation.NewUserNavigation({ name = <same title the guide uses>, mapID = uiMap, x = x, y = y })`
   inside `ns.SafeCall`, so a renamed or absent member can never raise. We keep steering the player;
   we just do not need to own the marker.
4. **Ownership must not mistake Waypoint UI for the player.** `OwnsWaypoint()` / `StopGuide()`
   currently end guidance when the native waypoint changes. A change made by Waypoint UI while we
   guide must not stop our journey; only a player-made change does. Use the existing
   `guide.writing` flag for our own writes and treat an active
   `WaypointUIAPI.Navigation.GetUserNavigation()` as Waypoint UI's.

   Do not introduce a setting for this, and do not hide Waypoint UI's pin.
5. **No-op when Waypoint UI is absent.** With it not installed, behaviour is byte-for-byte what it
   is today and every existing spec must pass unchanged.

## Tests

`tests/waypoint_ui.lua` already boots a fresh addon against Blizzard's real waypoint provider and a
native provider, with no client. Extend it with a Waypoint UI fake: `_G.WaypointUIAPI` with
`Navigation.IsUserNavigationTracked/GetUserNavigation/NewUserNavigation/ClearUserNavigation`, plus
`C_AddOns.IsAddOnLoaded("WaypointUI")` returning true. New cases:

- (a) journey starts while Waypoint UI tracks a navigation: Shortest Path never calls
  `SetUserWaypoint` or `ClearUserWaypoint`, calls `NewUserNavigation` once with the same
  destination, and still reports `ns.IsJourneyGuided()` true;
- (b) Waypoint UI replaces the user waypoint mid-journey: the journey survives (no `StopGuide`),
  no `ClearUserWaypoint`, no `charDB.guideWaypoint` left behind;
- (c) Waypoint UI absent: existing behaviour, existing cases unchanged;
- (d) API present but a member missing or raising: `ns.SafeCall` swallows it, nothing errors and
  guidance continues;
- (e) a player-made waypoint change with Waypoint UI loaded still ends guidance.

## Gate before the PR

Follow `AGENTS.md` Commands exactly:

```sh
stylua --check .
luacheck .
for s in tests/*_spec.lua; do luajit "$s" || exit 1; done
python3 tools/changelog.py --check
python3 .sift/gate.py --base origin/main && python3 .sift/agents.py check
```

Plus `tests/ui.sh` if the UI harness is touched, and a `## [Unreleased]` `CHANGELOG.md` entry in the
house style (prose, bold lead, issue reference `(#271)`), written in the terms a player would
notice: with Waypoint UI installed the two addons no longer clear each other's pin.

## Branch and PR

Branch `fix/271-waypoint-ui-coexistence` off `origin/main`. Commit without `-s`. Open the PR against
`main` with a body that links #271, states the two facts above (Waypoint UI drives the native
waypoint; it exposes `WaypointUIAPI.Navigation`), says what changed, lists the new spec cases and
pastes the gate output. Do not close #271.
