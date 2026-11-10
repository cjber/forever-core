# Addon API conventions

Every Forever addon publishes its own API table as `<AddonName>.API` and documents it in its `docs/api.md`. The shape
is the same in every addon, so a caller that reads one already knows how to read the next. ForeverCore supplies the
parts that must not differ: an addon reads the kit as `ForeverCore.APIKit`.

```lua
local api = SomeAddonForever and SomeAddonForever.API
if api and api.version == 1 and type(api.Stats) == "function" then
	local rows = api.Stats()
end
```

## Versioning

`version` changes only when a published member breaks: its arguments, the shape of its result or its meaning. Every
addition keeps `version` and raises `minor`, and the addon's `docs/api.md` keeps the history, naming what each minor
added. A caller checks the member it wants before using it, because an older addon may not have it yet.
`ForeverCore.APIKit.minor` is the kit's own version and rises only when the kit adds a member.

## Not ready

A read that has nothing to answer returns `nil, reason` through `APIKit.NotReady`. `nil` alone is not enough: the
reason says whether to ask again.

```lua
local function CurrentStop()
	if not ns.DataReady() then
		return APIKit.NotReady("loading")
	end
	if not ns.Settings.ShowStops() then
		return APIKit.NotReady("disabled")
	end
	return ns.Model.Current()
end
```

| reason | meaning |
|---|---|
| `"loading"` | the addon is still building its data, so ask again later |
| `"disabled"` | the player turned the feature off |
| `"none"` | there is nothing to answer, for example no journey is chosen |

## Subscribe

A change reaches callers through `APIKit.Hub(addonName, channels, ready)`. `channels` maps each change name to a
function returning a comparable key, and the addon's `docs/api.md` names every key.

- The callback runs on the frame after a change, never in the same call as `Queue()`.
- One burst sends at most one call, however many times `Queue()` ran in the frame.
- `changes` is a fresh table each call, with only the channels that changed set to `true`
  (`{ stop = true, journey = true }`). Its keys are the ones the addon's `docs/api.md` lists, so a caller can treat the
  table as typed. Read the API again rather than replaying the change.
- Only the subscribers there when the dispatch began are called. One added by a callback waits for the next burst.
- Each callback runs under the addon's `SafeCall`, so an error in one reaches the error handler and the others still
  run.
- `Subscribe(callback)` returns an unsubscribe function that is safe to call twice.
- The first subscriber takes the current keys as its baseline, so it hears only later changes. A hub with no
  subscriber arms no timer.
- While `ready()` returns false nothing is read or sent. `ready` is optional.

```lua
local hub = APIKit.Hub("SomeAddonForever", {
	stop = function()
		return stopKey()
	end,
	disabled = function()
		return not ns.Settings.ShowStops()
	end,
}, ns.DataReady)

hub.Subscribe(function(changes)
	if changes.stop then
		ns.Tracker.Refresh()
	end
end)
ns.OnChange(hub.Queue)
```

## Reads, places and rows

A read returns a fresh table on every call. A caller may keep it or change it; it is never the addon's own table.

A place is a `map` field holding a uiMapID and `x`, `y` normalized from 0 to 1. A place with no known position leaves
`x` and `y` nil rather than guessing.

`Stats()` returns rows with `addon`, `metric`, `subject`, `value` and `eventUnix`. `Leaderboard(limit)` returns
`{ metric, scope, sharing, total, rows }`, where each row has `rank`, `name`, `value`, `eventUnix` and `self` (true on
this character's row). Adventure Guide's [`docs/api.md`](https://github.com/cjber/adventure-guide-forever/blob/main/docs/api.md)
is the reference for both shapes.

## What every addon carries

- `docs/api.md`: every published member with its arguments and result, the change keys, and the minor history.
- `types/API.lua`: LuaLS declarations for the API table and the tables it returns.
- A contract spec, `tests/api_spec.lua`, that loads the TOC and checks each documented answer.
- A `### For addon authors` section under `## [Unreleased]` in `CHANGELOG.md` for every API change.
- `python3 tools/check_api_docs.py` in the gate: it fails when `Core/API.lua` publishes a name that `docs/api.md`
  does not mention as `Name(`, or a `minor` that the history does not mention.
