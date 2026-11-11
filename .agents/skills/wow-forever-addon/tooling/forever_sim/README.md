# forever_sim

A headless WoW: Forever client for scenario tests. Real Blizzard UI code runs under LuaJIT, with the addons under
test, so the bugs the offline specs miss show up: secret values, taint, gamepad-interface taint, broken saved
states and frames covering each other. Each repo vendors this folder as `tools/forever_sim/`, byte for byte, in the
same way as `forever_tools` (`python3 tools/forever_sim/sync.py check|update|pin`).

Nothing of Blizzard's or of a third-party addon is committed. `restrictions.txt` is the one committed list: the
`restrictedapi` class of each documented function and method, derived from warcraft.wiki.gg (CC BY-SA 4.0), with the
generator beside it. `fetch.py` downloads Blizzard's UI source (Gethe/wow-ui-source at
the Forever build's revision, by commit hash) and the client's global strings, colours and atlas sizes
(wago.tools, at the pinned build) into `tools/.cache/forever_sim/`. The Questie, TomTom, Auctionator and Polestar
in `stubs/` are our own stand-ins, written from what those addons do in public.

```sh
python3 tools/forever_sim/fetch.py [--locale deDE]   # once; CI caches it
python3 tools/forever_sim/fetch.py --refresh-restrictions   # after the wiki's classes change; commit restrictions.txt
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
taint reached), and on any protected call refused because of a field the addon wrote. `allowErrors` and
`allowGamepadTaint` options turn those checks off for a scenario that asserts on them itself.

## Steps and checks

| Call | Does |
|---|---|
| `sim:login{ savedVariables = path or table }` | every addon loads with its saved variables, then VARIABLES_LOADED, PLAYER_LOGIN, PLAYER_ENTERING_WORLD |
| `sim:savedState()` | what `/reload` would write, for replaying into a new client |
| `sim:openProfessions(skillLineID)`, `sim:recipeRows()`, `sim:hoverRecipe(i or name)` | the real Professions window from `sim.world.professions` |
| `sim:openWorldMap(mapID)`, `sim:zoomMap(n)`, `sim:panMap(dx, dy)`, `sim:closeWorldMap()` | the real world map |
| `sim:enterCombat()`, `sim:leaveCombat()` | PLAYER_REGEN_*; combat lockdown and in-combat secrets |
| `sim:joinGroup{ ... }`, `sim:leaveGroup()` | party members and GROUP_ROSTER_UPDATE |
| `sim:hover(frame)`, `sim:leave()`, `sim:click(frame)`, `sim:hoverUnit(unit)` | input, as fresh secure dispatches; a click is a hardware input |
| `sim:pressEscape()` | Escape through the client's `ToggleGameMenu` as a hardware input, so its registered handlers run |
| `sim:event(name, ...)`, `sim:advance(seconds)` | client events; timers, animations, OnUpdate, OnSizeChanged |
| `sim:setGamepad(true)`, `sim:gamepadNavigate()`, `sim:bindingSetChange()` | the gamepad interface (with `INPUT_DEVICE_INTERFACE_TRANSITION` on a change), one secure pass of its navigation, and a binding-set change through the client's `InputBindingManager` |
| `sim:stub("Questie", options)` | a third-party stand-in, loaded with the addons |
| `sim:slashCommands(addon)` | the slash commands `addon` registered, as their first aliases, sorted |
| `sim:slash("/cmd rest")` | a typed slash command as the chat box runs it: aliases match in any case, the handler gets the remainder as fresh input |
| `sim:reload()` | a fresh client with the same options, addons and stubs, logged in with what `/reload` would have saved |
| `sim:exercise{ ... }` | every surface twice (gamepad interface off then on): commands in and out of combat, Professions with every side tab and a recipe, trainer, merchant tabs, bags, character tabs, tracker, quest log, world map, Escape, and a target, soft-interact and binding-set change after each; then the same after a reload |
| `Sim.new{ locale = "deDE" }` | another client locale (fetch it first) |
| `sim:expectNoErrors(addon)`, `sim:expectError(text)`, `sim:takeErrors()` | the client's error list |
| `sim:gamepadTaint(addon)`, `sim:expectNoGamepadTaint(addon)` | secure reads of fields the addon wrote, with the writer line, the addon line the taint entered from, and the reader line; distinct causes are listed once with a count |
| `sim:rect(frame)`, `sim:overlap(a, b)`, `sim:expectNoOverlap(a, b)`, `sim:expectOnScreen(frame)` | layout |

`sim.world` holds what the client reports: `player`, `units` (target, mouseover...), `group`, `professions`,
`items`, `spells`, `maps`, `waypoint`, `achievements`. `sim.impl["C_Namespace.Function"] = function(...) end`
answers any API directly; the documented rules (below) still apply to what it returns.

An addon repo exercises its own surfaces with one shared step, in `tests/sim/exercise_scenario.lua`:

```lua
scenario("every surface, in and out of combat and across a reload", function(sim) sim:exercise() end)
```

`sim:exercise` logs in, runs each registered addon's slash commands twice (a toggle opens then closes) and the
scenario's own `commands`, opens Professions with every side tab and a selected recipe, the trainer, merchant
tabs, bags, character tabs, the objective tracker, the quest log and the world map, and fires a target change,
a soft-interact change and a binding-set change after each. It does that with the gamepad interface off and then
on, repeats the commands and map in combat, then reloads and runs both interfaces again. It fails on an error
either client caused; pass `addons`, `commands`, `savedVariables` or `allowErrors` to narrow or widen it.

## What it models

- **API**: every `C_*` namespace, global function, Enum and Constants table comes from
  `Blizzard_APIDocumentationGenerated`, with the documented arguments, return shapes and flags. Functions
  Blizzard's own Lua calls that the documentation omits exist and answer nothing. Every widget method the
  documentation lists exists on its widget type.
- **Scripts**: each widget type supports the scripts the client's annotations give it
  (`script_types.lua`, generated by `gen_script_types.py` from the pinned Ketho/vscode-wow-api copy), inherited
  along the widget hierarchy. `SetScript` and `HookScript` raise the client's
  `Cannot assign script handler for '...'` error for any other script, and `HasScript` answers from the same set;
  script names match in any case.
- **Taint**: every table field read and write in Blizzard's and the addon's Lua is instrumented at load with a
  real Lua 5.1 parser (line numbers kept, Blizzard's rewritten source cached per build). A field written while
  addon code runs carries that addon's taint, including a field a table constructor names; a secure read of it
  taints execution, and the next protected call is refused with the field, the writer's addon and file:line, and
  the Blizzard file:line of the read. Method
  calls, `rawget`, `rawset`, `next`, `pairs`, `ipairs` and the table-mutating library functions follow the same
  slot rule. The boundaries match the client: a C API's synchronous Lua runs in the caller's taint, and only an
  engine boundary it really has (an event it fires, a callback it defers to the next frame) is modelled in that
  native; `securecall`, `securecallfunction` and `secureexecuterange` keep a tainted caller tainted and restore a
  secure caller afterwards; client-dispatched events, timers, OnUpdate and scripts keep the taint of what set them
  (an addon handler still taints its own body); and a `hooksecurefunc` or `HookScript` post-hook runs isolated from
  its caller. A frame's script is not a table slot, so secure code reading an OnMouseUp does not taint itself,
  though running the script does. A documented function or widget method with `HasRestrictions` raises
  ADDON_ACTION_BLOCKED for a tainted caller by its classes in `restrictions.txt` (beside `docs.lua`, generated by
  `fetch.py --refresh-restrictions`): `nocombat` in combat, `hwevent` outside a hardware input, `always` at any
  time, and an `untagged` name keeps the combat-only rule. A name can carry more than one class (a tag of
  `protected,hwevent` is `always,hwevent`), and the call is refused when any of them applies. Only `protected` is
  `always`: a tag the sim cannot model (`noscript`, which blocks `/run` and `loadstring` rather than addon file code,
  `secureframe`, `restrictedframe`, or a state such as an instance) stays untagged. A name observed to differ from
  the wiki is overridden beside the global and widget rules, with the issue that saw it.
- **Secret values**: the documented `SecretReturns` and `SecretWhen*` rules (combat, unit restrictions, maps)
  return secrets. Tainted code that does arithmetic, comparisons, `#`, indexing or calls on a secret gets the client's
  error, naming the addon. Widget aspects work too: a secret argument adds the documented aspect, and getters on a region
  with that aspect, or anchored to one, return secrets.
- **Gamepad-interface taint**: the gamepad UI is booted (`Blizzard_GamepadSharedUtility`,
  `Blizzard_GamepadActionBars`, `Blizzard_GamepadSmartNavigation`), so `UpdateInteractIcons` runs on a target
  change, a soft-interact change and a binding-set change and makes its protected call as in the client. Any
  field an addon wrote that secure Blizzard code reads is reported with the writer, the reader and the field.

## Limits

- Layout is our own anchor solver: no text measurement (a character is half the font height wide), no clamping,
  strata draw order or hit testing.
- Functions the documentation leaves out answer by their name: counts 0, predicates false, the rest nil.
  Placeholders that Blizzard code reads for undocumented enums, constants, CVars and LE_* values are listed in
  `sim.gaps`.
- FrameXML proper, action bars, unit frames, chat and the shop are not booted (`loader.lua` SKIP_DEPS); a scenario
  can load one by name. The gamepad action bars and the action-button templates they inherit are booted.
- `secret == x` is always false, and a secret used as a table key is not caught.
- Units, recipes, items and maps are scenario data, not the game's databases.
- A client boots in about 2-4 s of CPU time. A suite belongs in its own CI job, not the fast gate.
