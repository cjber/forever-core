# Depending on ForeverCore

ForeverCore is a standalone addon every Forever addon requires. It loads once, before its consumers, and owns the
shared runtime: the tracker column, the report and issue windows, the error journal and debug log, Forever
Leaderboards, the minimap button, the quest log side tabs, the settings-page chrome and the family page.

Nothing is vendored any more. An addon no longer carries a copy of a shared file, so there is exactly one copy of each
in the game and a fix reaches players with ForeverCore's next release.

## The dependency

In the addon's TOC:

```toc
## Dependencies: ForeverCore
```

In `.pkgmeta`, so the stores install ForeverCore with the addon:

```yaml
required-dependencies:
  - ForeverCore
```

CurseForge and Wago resolve the project from the addon's own store page, so a player installing any Forever addon gets
ForeverCore without choosing it. CurseForge is the published description and gallery; Wago is an upload mirror with a
fixed stub pointing at CurseForge. The addon must not list ForeverCore in `OptionalDeps`, and it must not ship its own
copy of a core file.

## Asking for per-addon services

Some services keep state for each addon: the error journal, the debug log ring, the report window and the map markers.
Register once, at or after the addon's `ADDON_LOADED`, and keep the returned context:

```lua
local core = ForeverCore.Register("SkillUpForever", {
	title = L["SkillUp Forever"], -- the report window's title
	lines = function()            -- the addon's own report lines
		return { "Route: " .. tostring(route) }
	end,
	db = SkillUpForeverDB,        -- optional; attach it later with core.Attach(db)
})

core.SafeCall("route rebuild", rebuild)
core.RecordError("route rebuild", message, stack)
core.CaughtErrors()
core.CutText(text, 300)
core.Log("info", "route", "rebuilt in %d ms", elapsed)
core.LogLines(50)
core.DebugEnabled()
core.DebugCommand(argument)
core.Report.Command("report")
core.Report.Show(text)
core.Report.Compose("bug")
core.MapCanvas.Pool(map, mixin, { marker = "route" })
```

`Register` is idempotent: the same addon name returns the same context. Saved variables load after the files, so
`spec.db` is optional; call `core.Attach(db)` from `ADDON_LOADED`. The journal lives under `db.errors` and the log ring
under `db.log`.

One global error handler serves every registered addon. It attributes an error to the addon whose
`AddOns/<addonName>/` folder its message or stack names, and the same for `ADDON_ACTION_BLOCKED` and
`ADDON_ACTION_FORBIDDEN`. ForeverCore registers itself, so its own errors land in its journal too. The debug switch is
one state for the character, shared by every registered addon.

## The tracker

`ForeverCore.TrackerSection.Create(name, mixin, opts)` builds a section from `ObjectiveTrackerModuleTemplate`, mixes
the addon in, sets `order`, `lineTemplate` and `header`, and attaches it once saved variables are loaded; `legacy` and
`legacyKey` offer and then clear the addon's old tracker table, `safeCall` binds its errors and `onUnattached` warns
when the section never joined. `TrackerSection.UpdateText(module, blocks)` rewrites existing line and header text
without another layout. `TrackerSection.Room(module, block)` measures the room left in the column, and
`TrackerSection.AddMore(block, key, count)` draws the "+N more" line. `ForeverCore.TrackerLine.SetInteractive(line,
{ onClick, tooltip })` makes a stock line clickable, and `TrackerLine.SetHeaderTooltip(module, tip)` draws a block
header's hover; `ForeverTrackerInteractiveLineTemplate` is the mouse-enabled line template both use.

`ForeverCore.TrackerHost` is the one column. Attach a section directly to it:

```lua
ForeverCore.TrackerHost.Attach(module, {
	get = function()
		return db.showTracker
	end,
	set = function(shown)
		db.showTracker = shown
	end,
	where = L["Turn it back on with /skillup, under Route and trainer."],
})
```

The optional second argument is the section's own show switch, offered as **Hide this section**. A section without one
keeps the menu it already has.

The column's settings are ForeverCore's own, in `ForeverCoreDB.trackerHost`: scale, lock, attached/detached,
background opacity and the detached position. A consumer whose old version kept its own tracker table offers it once so
players keep the layout they chose:

```lua
module.legacySettings = SkillUpForeverDB.trackerHost
ForeverCore.TrackerHost.Attach(module)
```

While `ForeverCoreDB.trackerHost.migrated` is not true, the first `legacySettings` offered is copied into ForeverCoreDB
(fields of the right shape only) and marked migrated. Later offers are ignored, so the first addon to attach decides
for the client and one column's settings move every section together.

## Other modules

- `ForeverCore.Leaderboards:Register(key, spec)` registers one board; `Core/LeaderboardsData.lua` supplies overall
  points, standings and the unit tooltip. `ForeverCore.PeerStats.New(config)` and `PeerStats.Listen(owner, config)`
  are the transport behind those boards.
- `ForeverCore.MinimapButton.Create(spec)` draws the addon's minimap button on the one shared ring. Pass `spec.safeCall`
  (the `SafeCall` from `ForeverCore.Register`) so its click and refresh failures land in the addon's own journal.
- `ForeverCore.ContextMenu(owner, generator)` opens the suite's own context menu, with the same generator shape as
  `MenuUtil.CreateContextMenu`.
- `ForeverCore.QuestLogTabs.Register(key, spec)` adds a panel tab to the world map's quest log. A `spec.safeCall` keeps
  the panel's `shown` callback in the addon's journal.
- `ForeverCore.ProfessionTabs.Register(key, spec)` adds a side tab to the Professions window, under the client's own
  tabs and in registration order. `spec` is `{ icon, tooltip, page, minWidth?, onSelect?, safeCall? }`; `page` is the
  addon's page and `minWidth` raises the one width the window keeps for every profession and tab. A page whose needed
  width changes after it registered calls `SetMinWidth(key, width)` (nil clears it), which recomputes and enforces that
  width, waiting for combat to end when it is in combat. Selecting a tab shows only its page and unchecks the client's
  tabs; a client tab or page takes the window back. `Select(key)`, `ShowNative()` and `Selected()` drive and read the
  same state.
- `ForeverCore.SettingsPage.Register(name, build, L, safeCall)` draws a settings page with the caller's L for every
  label and the caller's `SafeCall` for its builders, getters and setters.
- `ForeverCore.Text.Fold` and `ForeverCore.Text.Rank` are the shared search fold and ranking.
- `ForeverCore.Family` draws the Forever addons page and its link windows. `Family.Register` and `Family.CreatePanel`
  take the addon's `SafeCall` as their last argument.
- `ForeverCore.OpenMap` and `ForeverCore.OpenSettingsPanel` open the client's restricted map and settings panel through
  `CreateSecureDelegate`, never in combat. `Core/OpenMap.lua` and `Core/OpenSettings.lua` are core runtime files, split
  by what each addon opens; each returns false in combat, without the delegate, or when the client function is missing,
  so the caller can say why nothing opened.

## Specs

A consumer's spec loads core the way the client does: its own files are loaded with `loadfile`, and core is either
required before them or stubbed with the one module the spec exercises. A spec that needs the real core loads
`ForeverCore.toc`'s files in order into one fake client, registers its own addon with `ForeverCore.Register`, and then
runs the addon's files. `tests/api_spec.lua` in this repo is the worked example.

A consumer's `tests/forever_core.lua` reads that TOC with the shared reader in its vendored
`tools/forever_sim/toc.lua`: `local Toc = dofile("tools/forever_sim/toc.lua")`, then
`Toc.files(directory, "ForeverCore.toc")`. Each entry is `{ path, kind }`: `loadfile` the `kind == "lua"` entries, and
register the `Toc.templates(entry.path)` of each `kind == "xml"` entry before loading that XML's scripts. The reader
expands an XML file into its `Script` and `Include` children in the client's order, so `UI/TrackerSection.xml` and any
later XML file need no special case in the loader.

## Changing a shared file

1. Change it here. Both specs, `luacheck` and `stylua` must pass.
2. Bump `CHANGELOG.md`; raise `ForeverCore.API` only for a breaking change to the table or `Register`.
3. Release ForeverCore. The stores carry it to players with the addons that require it.
4. Consumers pick up behaviour changes with no file copy. `tools/sync_consumers.py` copies only the development
   tooling in `tools/check_core_shared.py`'s `VENDORED`.
5. A changed store description in an addon's `docs/curseforge.md` reaches CurseForge through
   `tools/sync_curseforge.py`, which skips descriptions that did not change and checks every word, link and image URL it
   publishes. Wago keeps its fixed stub and is not described again.
