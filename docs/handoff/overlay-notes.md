# Overlay notes: gamepad-safe map drawing (S2, SPF)

Reference implementation: `cjber/shortest-path-forever`, branch `ccr-cc333990-q8ydc4-map-overlay`,
file `UI/MapCanvas.lua`, with spec `tests/map_canvas_spec.lua`. Copy the approach. Don't copy Polestar's code.

## Why (the taint path, from Blizzard source at the pinned build)
- `MapCanvasMixin:AcquirePin` called from addon code writes `map.pinPools[template]` (a pool made in tainted code) and
  registers the pin. Under the gamepad UI, `MapCanvasMixin:OnUpdate -> UpdateGamepadCursor` runs
  `ExecuteOnAllPins` over `pinPools` every frame, puts pins in `map.currentPoIPins` and calls their
  `OnMouseEnter`. `OnHide` calls `ExitMapPin` on them. That makes the addon's values part of secure code.
- `AddDataProvider` puts the provider in `map.dataProviders`, which `secureexecuterange` walks on show, hide and events.
- `MapCanvasPinMixin:SetPosition -> map:SetPinPosition` writes `map.pinsToNudge`, so no `MapCanvasPinMixin` either.
- `map:AddOverlayFrame` writes `map.overlayFrames` (H's point 1). It's the same kind of table write, so don't use it.

## Frame strategy
- One "view" per map frame: `host = CreateFrame("Frame")` **with no parent**, then `host:SetParent(map:GetCanvas())`,
  `host:SetAllPoints(canvas)`, `EnableMouse(false)`. (The gamepad interface follows `CreateFrame` calls whose parent
  sits in an open window, so every frame of ours is made parentless and then reparented.)
- Under the host, a `layer` frame (made the same way) holds every pin. Combat hides the layer, not each pin.
- Pins come from our own pools (`MapCanvas.Pool(map, key, mixin, {template, frameType, marker})`), made parentless,
  then `SetParent(layer)`, with the mixin applied in Lua (`Mixin(pin, mixin)`). XML templates hold **art only**: no
  `mixin=` and no inheriting `BaseMapPoiPinTemplate`, `FlightPointPinTemplate`, `MapPinPingTemplate` and so on (their
  OnLoad and mixins reach the map). Rebuild the art you need (Texture plus HIGHLIGHT-layer HighlightTexture, glows).
  A `QuestPOIFrame` widget is fine as a frame type (`CreateFrame("QuestPOIFrame", nil, nil, template)`).
- No `owningMap`, `pinTemplate` or `dataProvider` fields on our frames (the map reads `focus.owningMap` on the mouse focus).

## Refresh trigger (H's point 3): no provider, no hook, no EventRegistry
- The host's `OnUpdate` runs only while the map is shown (the client skips hidden frames), so it isn't an idle
  OnUpdate. Each frame it does a handful of **reads** and fires what changed:
  `show` (first frame after opening), `map` (`GetMapID` changed), `size` (canvas width/height), `scale`
  (`GetCanvasScale`, `GetCanvasZoomPercent`, `GetGlobalPinScale`), and `hide` (the host's `OnHide`).
- That replaces `RefreshAllData` (show/map), `OnCanvasScaleChanged` and `OnCanvasSizeChanged`. A hidden map is never
  read (`GetCanvasScale` before the first show has no zoom levels).
- Rejected: `hooksecurefunc(WorldMapFrame, "OnMapChanged"/"SetMapID")` (hooks a Blizzard object method, which the
  family AGENTS.md forbids), `EventRegistry:RegisterCallback("MapCanvas.MapSet"/"WorldMapOnShow")` (writes into
  Blizzard's callback tables), and `WorldMapFrame:HookScript("OnShow")` (allowed but unnecessary, since our own child frame's
  OnShow/OnHide already fire with the map).
- Reads that are safe (they return a field or compute without writing): `GetMapID`, `GetCanvas`, `GetCanvasScale`,
  `GetCanvasZoomPercent`, `GetGlobalPinScale`, `IsVisible`, `GetPinFrameLevelsManager():GetValidFrameLevel(type, i)`,
  `EnumeratePinsByTemplate` (read of Blizzard's own pins, e.g. dedupe against native pins), canvas `GetWidth/GetHeight`.

## Canvas anchoring, zoom and scale (MapCanvasPinMixin's maths, done locally)
- Position (map fractions x, y): `pin:ClearAllPoints(); pin:SetPoint("CENTER", canvas, "TOPLEFT", w*x/s, -h*y/s)`
  where `s = pin:GetScale()`, w/h = canvas size.
- Scale with limits `(factor, start, end)`:
  `scale = Lerp(start, end, Saturate(factor*zoomPercent)) / canvasScale`, times `GetGlobalPinScale()` unless the
  pin ignores the global pin scale. No limits + ignore-global = "grows with terrain" (scale 1 relative to the canvas):
  use that for full-canvas line/area frames (size = canvas size, positioned at 0.5, 0.5).
- On every `show`/`map`/`size`/`scale`, re-apply scale + position to every active pin, then call the pin's own
  `OnCanvasScaleChanged`/`OnCanvasSizeChanged` hooks.
- Frame level: `pin:SetFrameLevel(map:GetPinFrameLevelsManager():GetValidFrameLevel("PIN_FRAME_LEVEL_X", index))`.

## Clicks and tooltips
- Pins take the mouse with `EnableMouse(true)` and **only** `OnEnter`/`OnLeave` scripts. Never `OnClick`,
  `OnMouseDown`, `OnMouseUp` or `OnDoubleClick` scripts, and never a `Button`: the gamepad navigation reads those as
  buttons of the window it scans.
- Click = press and release over the hovered pin, from one addon frame registered for `GLOBAL_MOUSE_DOWN`/`GLOBAL_MOUSE_UP`
  (registered only while a map view is shown). Down: remember the hovered pin if `pin:IsMouseOver()`. Up: same pin,
  same button, still `IsVisible()` and `IsMouseOver()`, then dispatch.
- Dispatch: if the pin passes the button through, nothing happens. Otherwise click filters run first (Shift-click to plan
  a journey), then `pin:OnMouseClickAction(button)`.
- Right button to zoom out: `pin:SetPassThroughButtons("RightButton")` unless the pin wants its right click
  (`SetPassThroughButtons()` to clear). Above-zone flight points: `SetPropagateMouseClicks(true)` (stock behaviour).
- Super-tracking (flight points): call `C_SuperTrack.SetSuperTrackedMapPin` / `ClearAllSuperTracked` yourself and
  listen for the `SUPER_TRACKING_CHANGED` event on your own frame (not `EventRegistry "Supertracking.OnChanged"`).
- Gamepad: if the gamepad UI is on (`C_InputInterfaceStyle.GetCurrentStyle() == Enum.InputDeviceInterfaceType.Gamepad`,
  read at map show), on each view frame find the nearest mouse-taking pin within 12 units of the
  `SoftCursor:GetRect()` centre (compare in screen space: `GetCenter()*GetEffectiveScale()`). Enter or leave it
  (`SetHighlightLocked(true/false)` + `OnMouseEnter/OnMouseLeave`). Tooltips follow the map cursor. Clicks stay with the
  mouse: we don't act on the gamepad's A.
- Map hide/release always leaves the hovered pin (tooltip hidden).
- Shift-click on **Blizzard's** pins/canvas: SPF keeps `AddCanvasClickHandler` / `AddGlobalPinMouseActionHandler`.
  Those registries are Blizzard's addon-facing `MapCanvasSecureUtil.CreateHandlerRegistry`: closure tables, not
  map fields, and each handler is called through `securecallfunction`. If your addon doesn't need clicks on Blizzard's
  pins, don't register them; a `GLOBAL_MOUSE_DOWN` watcher works for "observe only".

## Overlay frames (H's point 1: AddOverlayFrame replacement)
- Make your frame parentless, `SetParent(WorldMapFrame)` (or `WorldMapFrame.BorderFrame` / `.ScrollContainer` to
  match the stock overlay's layer), then anchor it with `SetPoint` relative to the map frame. Anchors follow the map,
  so no hooks are needed. Refresh its contents from the view's `show`/`map` notifications (what `overlayFrames`'
  `Refresh` got from `OnMapChanged`). Raise with `SetFrameLevel(WorldMapFrame.BorderFrame:GetFrameLevel() + n)` if needed.

## BattlefieldMapFrame (H's point 4)
- Same view code: `MapCanvas.Watch(BattlefieldMapFrame)` once it exists. It's load-on-demand, so watch on
  `ADDON_LOADED` with `"Blizzard_BattlefieldMap"` (or at init if `BattlefieldMapFrame` already exists). Its pin scale
  and alpha differ. Read `map:GetGlobalPinScale()` per view, and `map:GetGlobalAlpha()` if you mirror its opacity.

## Cross-addon markers (H's point 2): `ForeverMapMarkers`
- A shared global registry: one function per addon, under its folder name.
- **Publish a copy; never write a field into the existing table.** The family taint lint (`taint-blizzard-write`) treats
  `ForeverMapMarkers.X = fn` as a write into a table someone else owns. SPF's CI failed on exactly that. The idiom:
  ```lua
  local markers = {}
  for name, fn in pairs(ForeverMapMarkers or {}) do markers[name] = fn end
  markers.TweaksForever = function(map) return {...} end
  ForeverMapMarkers = markers
  ```
  Readers look the global up each time (never cache the table), since a later addon replaces it.
- A function takes the map frame (WorldMapFrame) and returns `{ {x=, y=, kind=}... }`: fractions on `map:GetMapID()` for
  **shown** markers, in a fresh table each call. It returns `{}` for a map it doesn't draw on, while the map is closed,
  and in combat (layer hidden). It never errors. SPF's kinds: `dock`, `portal`, `flight`, `stop`.
- Consumers (Tweaks' `DungeonEntrances.Settle`): replace `EnumeratePinsByTemplate(otherAddonTemplate)` with
  `for _, list in pairs(ForeverMapMarkers or {}) do for _, m in ipairs(list(WorldMapFrame)) do ... end end`
  (keep `EnumeratePinsByTemplate("FlightPointPinTemplate")` for Blizzard's own pins). Add `ForeverMapMarkers` to
  `.luacheckrc` globals and to your types file.

## Specs (copy `tests/map_canvas_spec.lua`)
- Freeze the fixture map before the addon's Init: `setmetatable(WorldMapFrame, {__index = old, __newindex = error})`.
  Snapshot every value reachable from WorldMapFrame (3 deep) before, run everything, then compare (catches changed
  existing keys such as `dataProviders` entries).
- The fixture `AddDataProvider` asserts after addon load, `RemoveDataProvider` always errors, and `AcquirePin` /
  `RemoveAllPinsByTemplate` assert the template isn't the addon's.
- Wrap `CreateFrame` to record parents: nothing is made with the canvas, or any frame of ours on the map, as its
  parent. The canvas has exactly one child of ours (the host).
- No pin has `OnClick`/`OnMouseDown`/`OnMouseUp`/`OnDoubleClick` scripts or `owningMap`/`pinTemplate` fields.
- Behaviour: scale and anchor numbers at two zooms and after a canvas resize. Hover shows and hides the tooltip.
  GLOBAL_MOUSE press and release clicks. A right button passes through. A press that leaves the pin is no click.
  Shift-click plans to the pin. Gamepad SoftCursor hover enters and leaves the nearest pin. Combat hides the layer and
  acquires nothing. Markers listed, and empty in combat or on a map you don't draw on.
- Test harness: the canvas stub must be a frame whose `IsVisible` follows the map and whose `GetEffectiveScale` is the
  canvas scale. Drive the view with `ns.MapCanvas.Update(map)` (the OnUpdate), and fire the host's OnHide when the map
  closes. Loops that run "every visible frame's OnUpdate" should use `IsVisible`, not `IsShown`.
