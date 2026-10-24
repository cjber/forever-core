# forever_sim

A headless WoW: Forever client for scenario tests. Real Blizzard UI code runs under LuaJIT, with the addons under
test, so the bugs the offline specs miss show up: secret values, taint, gamepad-interface taint, broken saved
states and frames covering each other. Each repo vendors this folder as `tools/forever_sim/`, byte for byte, in the
same way as `forever_tools` (`python3 tools/forever_sim/sync.py check|update|pin`).

Nothing of Blizzard's or of a third-party addon is committed. `fetch.py` downloads Blizzard's UI source (Gethe/wow-ui-source at
the Forever build's revision, by commit hash) and the client's global strings, colours and atlas sizes
(wago.tools, at the pinned build) into `tools/.cache/forever_sim/`. The Questie, TomTom, Auctionator and Polestar
in `stubs/` are our own stand-ins, written from what those addons do in public.

```sh
python3 tools/forever_sim/fetch.py [--locale deDE]   # once; CI caches it
luajit tools/forever_sim/run.lua                     # every tests/sim/*_scenario.lua
luajit tools/forever_sim/run.lua -v --only=tooltip   # one scenario, with the client's errors
```

## A scenario

```lua
scenario("hovering a recipe after a unit tooltip", { stubs = { Questie = {} } }, function(sim)
	sim.world.professions = { { skillLineID = 164, name = "Blacksmithing", skill = 30, max = 75,
		categories = { { id = 1, name = "Materials" } },
		recipes = { { id = 2660, name = "Rough Sharpening Stone", category = 1, itemID = 2862 } } } }
	sim:login({ savedVariables = "tests/sim/fixtures/old_settings.lua" })
	sim:openProfessions()
	sim:hoverRecipe(1)
	sim:enterCombat()
	sim:hoverUnit({ name = "Defias Bandit", level = 12, friendly = false })
end)
```

The runner registers the repository's addon (its TOC), runs each scenario on a fresh client and fails it on an
error in the scenario, on any client error the addon caused (raised in its code, or in Blizzard code its
taint reached), and on any gamepad-interface taint it left. `allowErrors` and `allowGamepadTaint` options turn those
checks off for a scenario that asserts on them itself.

## Steps and checks

| Call | Does |
|---|---|
| `sim:login{ savedVariables = path or table }` | every addon loads with its saved variables, then VARIABLES_LOADED, PLAYER_LOGIN, PLAYER_ENTERING_WORLD |
| `sim:savedState()` | what `/reload` would write, for replaying into a new client |
| `sim:openProfessions(skillLineID)`, `sim:recipeRows()`, `sim:hoverRecipe(i or name)` | the real Professions window from `sim.world.professions` |
| `sim:openWorldMap(mapID)`, `sim:zoomMap(n)`, `sim:panMap(dx, dy)`, `sim:closeWorldMap()` | the real world map |
| `sim:enterCombat()`, `sim:leaveCombat()` | PLAYER_REGEN_*; combat lockdown and in-combat secrets |
| `sim:joinGroup{ ... }`, `sim:leaveGroup()` | party members and GROUP_ROSTER_UPDATE |
| `sim:hover(frame)`, `sim:leave()`, `sim:click(frame)`, `sim:hoverUnit(unit)` | input, as fresh secure dispatches |
| `sim:event(name, ...)`, `sim:advance(seconds)` | client events; timers, animations, OnUpdate, OnSizeChanged |
| `sim:setGamepad(true)`, `sim:gamepadNavigate()` | the gamepad interface, and one secure pass of its navigation |
| `sim:stub("Questie", options)` | a third-party stand-in, loaded with the addons |
| `Sim.new{ locale = "deDE" }` | another client locale (fetch it first) |
| `sim:expectNoErrors(addon)`, `sim:expectError(text)`, `sim:takeErrors()` | the client's error list |
| `sim:gamepadTaint(addon)`, `sim:expectNoGamepadTaint(addon)` | addon writes into the tables the gamepad UI walks |
| `sim:rect(frame)`, `sim:overlap(a, b)`, `sim:expectNoOverlap(a, b)`, `sim:expectOnScreen(frame)` | layout |

`sim.world` holds what the client reports: `player`, `units` (target, mouseover...), `group`, `professions`,
`items`, `spells`, `maps`, `waypoint`. `sim.impl["C_Namespace.Function"] = function(...) end` answers any API
directly; the documented rules (below) still apply to what it returns.

## What it models

- **API**: every `C_*` namespace, global function, Enum and Constants table comes from
  `Blizzard_APIDocumentationGenerated`, with the documented arguments, return shapes and flags. Functions
  Blizzard's own Lua calls that the documentation omits exist and answer nothing. Every widget method the
  documentation lists exists on its widget type.
- **Taint**: addon code is instrumented when it loads (each function reports its addon as it runs; line numbers are kept),
  globals and Blizzard table fields record their writer, `securecall`, `securecallfunction`,
  `secureexecuterange`, `hooksecurefunc` and `HookScript` isolate taint as in game, and protected functions
  and protected frames in combat raise ADDON_ACTION_BLOCKED for tainted callers.
- **Secret values**: the documented `SecretReturns` and `SecretWhen*` rules (combat, unit restrictions, maps)
  return secrets. Tainted code that does arithmetic, comparisons, `#`, indexing or calls on a secret gets the client's
  error, naming the addon. Widget aspects work too: a secret argument adds the documented aspect, and getters on a region
  with that aspect, or anchored to one, return secrets.
- **Gamepad-interface taint**: map data providers, pin pools and overlay frames, the tracker's containers and modules,
  and the input binding stack are watched. Each addon write is reported with the addon and where it ran.

## Limits

- Layout is our own anchor solver: no text measurement (a character is half the font height wide), no clamping,
  strata draw order or hit testing.
- Functions the documentation leaves out answer by their name: counts 0, predicates false, the rest nil.
  Placeholders that Blizzard code reads for undocumented enums, constants, CVars and LE_* values are listed in
  `sim.gaps`.
- FrameXML proper, action bars, unit frames, chat and the shop are not booted (`loader.lua` SKIP_DEPS); a scenario
  can load one by name.
- Table-field taint is tracked for the watched gamepad tables only. `secret == x` is always false, and a secret used
  as a table key is not caught.
- Units, recipes, items and maps are scenario data, not the game's databases.
- A client boots in about 7-9 s of CPU time. A suite belongs in its own CI job, not the fast gate.
