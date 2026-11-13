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
`ForeverCore.APIKit.minor` is the kit's own version and rises only when the kit adds a member:

- minor 1: `Hub` and `NotReady`.
- minor 2: `Invalid`, `Publish` and `Addons`.

An addon that uses a minor 2 member keeps working with an older core by checking it first:
`if (ForeverCore.APIKit.minor or 1) >= 2 and ForeverCore.APIKit.Addons then ... end`.

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
| `"invalid"` | the argument is wrong, so asking again with the same argument cannot help |

`"invalid"` is an error answer, not a not-ready one, and it is the one reason `NotReady` does not take. A read that
refuses its argument returns it through `APIKit.Invalid()`, so the answer is typed and the reason is spelled once:

```lua
function API.Stop(step)
	if type(step) ~= "number" then
		return APIKit.Invalid()
	end
	return ns.Model.Stop(step)
end
```

A read's signature names both answers, `nil, ForeverCoreAPIAnswer`, which is `ForeverCoreAPIReason` or
`ForeverCoreAPIInvalid`. Only a read that can answer `"invalid"` widens it; a read with no argument keeps
`ForeverCoreAPIReason`.

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

## Discovery

An addon hands core its public API table once at load with `APIKit.Publish(addonName, api)`. The name must be a
non-empty string and the table must hold an integer `version`; anything else is a programming error, raised at the
calling line. Publishing the same name again replaces that entry, so a second call never duplicates it.

```lua
APIKit.Publish("SomeAddonForever", API)
```

`APIKit.Addons()` returns a fresh list, sorted by name, of `{ name, version, minor, api }` for every published addon.
`version` and `minor` are read from the api table at call time, `minor` is 0 when the table has none, and `api` is the
addon's own table rather than a copy, because it is the callable API:

```lua
for _, entry in ipairs(APIKit.Addons()) do
	if entry.version >= 1 and type(entry.api.Stats) == "function" then
		local rows = entry.api.Stats()
	end
end
```

A published API is still a read: its hub is subscribed to and its reads answer as the rest of this document says.

## Reads, places and rows

A read returns a fresh table on every call. A caller may keep it or change it; it is never the addon's own table.

A place is a `map` field holding a uiMapID and `x`, `y` normalized from 0 to 1. A place with no known position leaves
`x` and `y` nil rather than guessing.

`Stats()` returns rows with `addon`, `metric`, `subject`, `value` and `eventUnix`. Adventure Guide's
[`docs/api.md`](https://github.com/cjber/adventure-guide-forever/blob/main/docs/api.md) is the reference for that
shape.

## What every addon carries

- `docs/api.md`: every published member with its arguments and result, the change keys, and the minor history.
- `types/API.lua`: LuaLS declarations for the API table and the tables it returns.
- A contract spec, `tests/api_spec.lua`, that loads the TOC and checks each documented answer.
- A `### For addon authors` section under `## [Unreleased]` in `CHANGELOG.md` for every API change.
- `APIKit.Publish(addonName, API)` once at load, so `APIKit.Addons()` finds the addon's own table.
- `python3 tools/check_api_docs.py` in the gate: it fails when `Core/API.lua` publishes a name that `docs/api.md`
  does not mention as `Name(`, or a `minor` that the history does not mention.
