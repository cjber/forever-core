# ForeverCore API

ForeverCore is the shared library every Forever addon requires. This page is the part of it a third-party addon may
rely on: the `ForeverCore` global, its interface version and the members below. Anything not named here is internal to
the Forever addons and may change between releases without a version bump (see
[Internal members](#internal-members)).

Every addon in the suite publishes its own API the same way; [`docs/api-conventions.md`](api-conventions.md) is that
convention and the next read after this page.

## `ForeverCore.API`

```lua
ForeverCore.API -- integer
```

The interface version of the table below. It is `1` today. It changes only when a member a third-party addon may
rely on breaks: its arguments, the shape of its result or its meaning. Additions keep it and raise a member's own
`minor` instead. Refuse to run against a core older than the members you call:

```lua
if ForeverCore == nil or (ForeverCore.API or 0) < 1 then
	return
end
```

`ForeverCore` itself exists only once the client has loaded ForeverCore, which `## Dependencies: ForeverCore` in your
TOC guarantees before your files run.

## `ForeverCore.APIKit`

```lua
ForeverCore.APIKit.minor -- integer
ForeverCore.APIKit.Hub(addonName, channels, ready?) --> ForeverCoreAPIHub
ForeverCore.APIKit.NotReady(reason) --> nil, reason
ForeverCore.APIKit.Invalid() --> nil, "invalid"
ForeverCore.APIKit.Publish(addonName, api)
ForeverCore.APIKit.Addons() --> ForeverCoreAPIEntry[]
```

`minor` is the kit's own version: it rises with each member the kit adds, and each member arrived in a named minor.
It is `2` today. Check a member added in minor 2 before you use it, so the same code still runs on an older core:
`if (ForeverCore.APIKit.minor or 1) >= 2 then ... end`.

- `Hub(addonName, channels, ready?)` builds the hub an addon publishes for its own API. `channels` maps each change
  name to a function returning a comparable key, and the optional `ready` returns false while the addon is still
  working. It returns `{ Subscribe, Queue }`: `Subscribe(callback)` calls `callback(changes)` on the frame after a
  channel changes and returns an unsubscribe function that is safe to call twice, and `Queue()` asks for one dispatch
  on the next frame. Only the changed channels are set to `true` in the fresh `changes` table, and each callback runs
  under the addon's `SafeCall`. (minor 1)
- `NotReady(reason)` is the not-ready answer a read gives: `nil, reason` for `"loading"` (the addon is still building
  its data), `"disabled"` (the player turned the feature off) or `"none"` (there is nothing to answer). (minor 1)
- `Invalid()` is the error answer a read gives for a wrong argument: `nil, "invalid"`. Asking again with the same
  argument cannot help, so it is not a not-ready reason and `NotReady` does not take it. (minor 2)
- `Publish(addonName, api)` hands core an addon's public API table once at load. `addonName` must be a non-empty
  string and `api` must be a table with an integer `version`; anything else is a programming error, raised at the
  calling line. Publishing the same name again replaces that entry. (minor 2)
- `Addons()` returns a fresh list, sorted by name, of `{ name, version, minor, api }` for every published addon.
  `version` and `minor` are read from the api table at call time (`minor` is 0 when it has none), and `api` is the
  addon's own table rather than a copy, because it is the callable API. (minor 2)

## `ForeverCore.OpenMap`

```lua
ForeverCore.OpenMap(mapID?) --> boolean
```

Opens the client's world map, at `mapID` when one is given and at the player's own map otherwise (`0` and `nil` both
mean the player's map). It invokes the client's `C_Map.OpenWorldMap` through `securecallfunction`. Returns true when
the request was dispatched. It returns false, and
opens nothing, in combat, on a build without `securecallfunction`, or when the client function is missing, so you
can say why nothing opened. Call this instead of `C_Map.OpenWorldMap`.

## `ForeverCore.OpenSettingsPanel`

```lua
ForeverCore.OpenSettingsPanel(categoryID?, element?) --> boolean
```

Opens the client's settings panel, at `categoryID` and `element` when given. It runs the client's restricted
`SettingsPanel.OpenToCategory` through `securecallfunction`, preserving the client's taint boundary: true when the
client opened it, and false in combat or when the panel's secure method is missing. Call this instead of opening
the settings panel directly.

## `ForeverCore.Credits`

```lua
ForeverCore.Credits.minor -- integer
ForeverCore.Credits.Register(addonTitle, credits)
ForeverCore.Credits.Line(addonTitle) --> string?
ForeverCore.Credits.Players() --> ForeverCreditRow[]
ForeverCore.Credits.Inspired() --> ForeverCreditRow[]
ForeverCore.Credits.Open(addonTitle?) --> boolean
```

`minor` is `1` today and rises with each member this module adds. It arrived as minor 1 with `Register`, `Line` and
`Open`, the three members a Forever addon calls.

- `Register(addonTitle, credits)` hands core one addon's credits, the table its generated `Data/Credits.lua` sets as
  `ns.Credits`: `{ players = { { name, what }, ... }, inspired = { ... } }`. `addonTitle` is the name players see in
  game; registering the same title again replaces that addon's list. An addon registers under its `Family.ADDONS`
  name (the row whose `folder` is its own), the same string the shared page filters to, so its Thanks row and its
  lines name it the same way. `ForeverCore.Family.ADDONS` is the exposed list of `{ name, folder, url, line }` rows
  if an addon needs to look its own up, though passing the literal title is enough. A missing or malformed entry is
  left out rather than raised. It returns false for a title that is not a non-empty string.
- `Line(addonTitle)` is the short line an addon's own settings page shows: its top three players by their number of
  contributions to that addon, then a count of the rest, such as `Thanks to Brainc3ll, Alex and 2 more`. It returns nil
  when that addon has registered no players, so the page can hide the row.
- `Players()` and `Inspired()` return the merged lists the page draws: one row per exact player name or project, each
  `{ name, count, helped = { { addon = addonTitle, what = what }, ... } }`. One `helped` item is one contribution, so
  a player's generated rows all stay; `count` is how many the row carries. Players rank by `count` descending, then
  name case-insensitively; **Inspired by** stays alphabetical.
- `Open(addonTitle?)` shows the **Thanks** page: one compact row per player with the addons they helped, its count
  after the name when above one, and a short **Inspired by** group below. Hovering a row shows every contribution,
  grouped by identical `what`, each line led by the addons in gold. A dropdown at the top
  of the page filters to one registered addon, where each row shows that addon's `what` after the name and **Inspired
  by** lists only that addon's entries. Called with no argument it reopens on the filter the page already shows, so a
  choice survives closing and reopening; called with an addon title it filters to that addon; called with an explicit
  nil it shows every addon. An addon's own Forever addons page has a Thanks row that passes its `Family.ADDONS` name,
  so it opens filtered to that addon; ForeverCore's own page, and any folder with no row, pass nil and open **All
  addons**. It returns false only when the client cannot build the window.

Every Forever addon writes its `Data/Credits.lua` from `THIRD_PARTY.md`'s `## Players` and `## Inspired by` tables
with `python3 tools/forever_tools/credits.py`; the same run keeps the one-sentence thanks in README.md's `## Credits`
and in docs/curseforge.md, and `--check` fails when either the file or a block is stale. The addon's author is never
listed (WFA-33).

## `ForeverCore.ContextMenu`

```lua
ForeverCore.ContextMenu(owner, generator) --> ForeverMenuDescription
```

Opens the suite's one context menu beside `owner`. `generator` fills the menu the way `MenuUtil.CreateContextMenu`
takes it, `generator(owner, root)`, with `root:CreateButton(text, action)`, `CreateTitle(text)`, `CreateDivider()`,
`CreateCheckbox(text, selected, action)`, `CreateRadio(text, selected, action, data)`, `SetEnabled(enabled)` and
`SetTooltip(tooltip)`. An entry that calls `CreateButton` on itself makes a submenu, and `SetScrollMode(extent)` makes
a long menu scroll past that many pixels. Returns the root description, a `ForeverMenuDescription`. The menu is drawn
in ForeverCore's own frames because the client's menu can assert on this build and taints the gamepad interface's
focus; use this rather than `MenuUtil.CreateContextMenu`.

## `ForeverCore.ProfessionTabs`

```lua
ForeverCore.ProfessionTabs.minor -- integer
ForeverCore.ProfessionTabs.Register(key, spec) --> ForeverProfessionTab
ForeverCore.ProfessionTabs.SetMinWidth(key, width)
ForeverCore.ProfessionTabs.Select(key)
ForeverCore.ProfessionTabs.ShowNative()
ForeverCore.ProfessionTabs.Selected() --> string?
```

`minor` is the module's own version: it rises with each member the module adds. It is `1` today, the minor that adds
`SetMinWidth`. Check that member before you use it: `if (ForeverCore.ProfessionTabs.minor or 0) >= 1 then ... end`.

- `Register(key, spec)` adds a side tab to the Professions window under the client's own tabs, in registration order.
  `spec` is `{ icon, tooltip, page, minWidth?, onSelect?, safeCall? }`; `page` is your page and `minWidth` raises the
  shared custom-page width, which is at least 850 units. Native pages use Camelot's 673-unit layout. Selecting a tab shows only its page and unchecks the
  client's tabs; a client tab or page takes the window back. A key that is not a non-empty string, or one that is
  already registered, is a programming error raised at the calling line.
- `SetMinWidth(key, width)` changes the `minWidth` of a registration that is already made, then recomputes and enforces
  the shared custom-page width. `nil` clears that request, retaining the 850-unit minimum. In combat the change waits
  for combat to end with the rest of the module's frame work. An unknown key is a programming error raised at the
  calling line. (minor 1)
- `Select(key)` shows that tab's page and checks its tab; `ShowNative()` hands the window back to the client;
  `Selected()` returns the selected key, or `nil` when the client's own page is showing.

## Listing and subscribing to addon APIs

Every Forever addon that follows [`docs/api-conventions.md`](api-conventions.md) publishes its API table, so one loop
lists the whole suite:

```lua
for _, entry in ipairs(ForeverCore.APIKit.Addons()) do
	print(entry.name, entry.version, entry.minor)
end
```

An entry's `api` is the addon's own table, so subscribe through it, checking the member you want first:

```lua
local unsubscribe
for _, entry in ipairs(ForeverCore.APIKit.Addons()) do
	if type(entry.api.Subscribe) == "function" then
		unsubscribe = entry.api.Subscribe(function(changes)
			print(entry.name, "changed")
		end)
		break
	end
end
```

If one answered, `unsubscribe()` later stops it, and is safe to call twice. Reading a published API is the same as
reading any other, with the answers `docs/api-conventions.md` describes.

## Internal members

These are on the `ForeverCore` table for the Forever addons themselves. They are not a contract for a third-party
addon and may change between releases without raising `ForeverCore.API`: `Register`, `name`, `TrackerHost`,
`TrackerSection`, `TrackerLine`, `TrackerLock`, `TrackerOrder`, `TrackerQuestie`, `TrackerEqot`, `TrackerQuests`,
`QuestLogTabs`, `PeerStats`, `Leaderboards`, `LeaderboardsData`, `MinimapButton`, `SettingsPage`, `Text`,
`QuestOrder`, `Family` and `Credits`. [`docs/adoption.md`](adoption.md) describes them for the addons that own a
tracker section or a window; a third-party addon builds its own from `APIKit` and `ContextMenu` instead.
