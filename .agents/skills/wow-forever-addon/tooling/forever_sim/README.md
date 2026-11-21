# forever_sim

A headless WoW: Forever client for scenario tests. Real Blizzard UI code runs under LuaJIT, with the addons under
test, so the bugs the offline specs miss show up: secret values, taint, gamepad-interface taint, broken saved
states and frames covering each other. Each repo vendors this folder as `tools/forever_sim/`, byte for byte, in the
same way as `forever_tools` (`python3 tools/forever_sim/sync.py check|update|pin`).

Nothing of Blizzard's or of a third-party addon is committed. `restrictions.txt` is the one committed list: the
`restrictedapi` class of each documented function and method, derived from warcraft.wiki.gg (CC BY-SA 4.0), with the
generator beside it. `fetch.py` downloads Blizzard's UI source (Gethe/wow-ui-source at
the Forever build's revision, by commit hash) and the client's global strings, items, colours and atlas sizes
(wago.tools, at the pinned build) into `tools/.cache/forever_sim/`. The Questie, TomTom, Auctionator and Polestar
in `stubs/` are our own stand-ins, written from what those addons do in public.

```sh
python3 tools/forever_sim/fetch.py [--locale deDE]   # once; CI caches it
python3 tools/forever_sim/fetch.py --refresh-restrictions   # after the wiki's classes change; commit restrictions.txt
python3 tools/forever_sim/fetch.py --refresh-restrictions \
    --probe ~/path/SavedVariables/ForeverProbe.lua          # also merge every block the live client recorded
luajit tools/forever_sim/run.lua                     # every tests/sim/*_scenario.lua, then the exercise
luajit tools/forever_sim/run.lua -v --only=tooltip   # one scenario, with the client's errors
```

An installed cache whose `atlas.lua` predates the current schema is rebuilt from the client tables by the same
`fetch.py` command. With `--offline` it names the missing table instead of reading the stale keys.

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
taint reached), on any protected call refused because of a field the addon wrote, and on any stranded wait: a frame
or `EventRegistry` callback the addon registered for `PLAYER_LOGIN` or `VARIABLES_LOADED` after that event fired,
which never calls back (a file a wrapped ForeverCore runs after login does this; `ns.AfterEvents` is the fix).
`allowErrors`, `allowGamepadTaint` and `allowStrandedWaits` options turn those checks off for a scenario that
asserts on them itself. After the declared
scenarios, and whether or not `tests/sim` holds any, the runner runs `sim:exercise()` for the repository's addon.
An addon whose TOC names ForeverCore in `## OptionalDeps` or `## Dependencies` gets that checkout loaded for the
exercise, from `$FOREVER_CORE` or the sibling `../forever-core`, so the addon's UI is really built and the exercise
means something; the walk still covers only the repository's own widgets.

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
| `sim:pressBinding(key)` | dispatches a CLICK override as hardware input; priority overrides win, and the latest set wins within one priority class (the simulator's choice for ordering between owners) |
| `sim:pressEscape()` | Escape through the client's `ToggleGameMenu` as a hardware input, so its registered handlers run |
| `sim:event(name, ...)`, `sim:advance(seconds)` | client events; timers, animations, OnUpdate, OnSizeChanged |
| `sim:setGamepad(true)`, `sim:gamepadNavigate()`, `sim:bindingSetChange()` | the gamepad interface (with `INPUT_DEVICE_INTERFACE_TRANSITION` on a change), one secure pass of its navigation, and a binding-set change through the client's `InputBindingManager` |
| `sim:stub("Questie", options)` | a third-party stand-in, loaded with the addons |
| `sim:slashCommands(addon)` | the slash commands `addon` registered, as their first aliases, sorted |
| `sim:slash("/cmd rest")` | a typed slash command as the chat box runs it: aliases match in any case, the handler gets the remainder as fresh input |
| `sim:putInBag(bag, slot, itemID, count)` | a bag slot's contents (`nil` itemID empties it), then BAG_UPDATE(bag) and BAG_UPDATE_DELAYED; the backpack is bag 0 with 16 slots. With the merchant open, `C_Container.UseContainerItem` sells the slot |
| `sim:openQuestReward(questID, { title, text, choices, rewards, money, xp })`, `sim:completeQuestReward(choice)`, `sim:closeQuestReward()` | the quest giver's reward panel: QuestFrame shows and QUEST_COMPLETE draws it through the client's QuestInfo; each of `choices` and `rewards` is an item ID or `{ itemID, count }`. Completing puts the chosen item, the fixed rewards and the money in the player's bags and purse |
| `sim:reload()` | a fresh client with the same options, addons and stubs, logged in with what `/reload` would have saved |
| `sim:exercise{ ... }` | every surface twice (gamepad interface off then on): commands in and out of combat, Professions with every side tab and a recipe, trainer, merchant tabs, bags, character tabs, tracker, quest log, world map, Escape, and a target, soft-interact and binding-set change after each; the addon's own buttons are hovered, clicked and left after every command and every surface that opens; then the same after a reload |
| `sim:exerciseWidgets(addons)` | every shown Button the named addons' own code created (menu rows and check boxes included): OnEnter, a left click, OnLeave, once each and in the current combat state, with frames a click opens walked in the same pass |
| `Sim.new{ locale = "deDE" }` | another client locale (fetch it first) |
| `sim:expectNoErrors(addon)`, `sim:expectError(text)`, `sim:takeErrors()` | the client's error list |
| `sim:strandedWaits(addon)`, `sim:expectNoStrandedWaits(addon)` | waits registered for a once-only loading event after it fired, with the addon line that registered each |
| `sim:gamepadTaint(addon)`, `sim:expectNoGamepadTaint(addon)` | secure reads of fields the addon wrote, with the writer line, the addon line the taint entered from, and the reader line; distinct causes are listed once with a count |
| `sim:noisy{ seed, itemsPerFrame, failPercent, bagPercent, merchantPercent }`, `sim:noisy(false)` | a noisy client: every frame, seeded GET_ITEM_INFO_RECEIVED and ITEM_DATA_LOAD_RESULT pairs for random item IDs with some loads failed, BAG_UPDATE churn then BAG_UPDATE_DELAYED, and MERCHANT_UPDATE while the merchant is open; a requested load of a known item fails at the same rate; `sim.noise.fired` counts what it raised. A consumer spec runs it with `sim.work` to assert its work per event stays flat |
| `sim.work.reset()`, `sim.work.paths[label]`, `sim.work.measure(label, f, ...)` | the work counter: every event is measured under its own name, and `measure` wraps any other path (a tooltip, a click, a callback), returning that run's `{ handlers, apiCalls }` and then `f`'s results; each `paths` entry holds `runs`, `handlers`, `apiCalls`, `maxHandlers` and `maxApiCalls` |
| `sim:rect(frame)`, `sim:overlap(a, b)`, `sim:expectNoOverlap(a, b)`, `sim:expectOnScreen(frame)` | layout |

`sim.world` holds what the client reports: `player`, `units` (target, mouseover...), `group`, `professions`,
`items`, `spells`, `maps`, `waypoint`, `achievements`. `sim.impl["C_Namespace.Function"] = function(...) end`
answers any API directly; the documented rules (below) still apply to what it returns.

An addon repo needs no scenario file for the shared exercise: the runner runs it after the declared scenarios.
`sim:exercise` logs in, runs each registered addon's slash commands twice (a toggle opens then closes) and the
scenario's own `commands`, opens Professions with every side tab and a selected recipe, the trainer, merchant
tabs, bags, character tabs, the objective tracker, the quest log and the world map, and fires a target change,
a soft-interact change and a binding-set change after each. After every command and every surface that opens, it
hovers, left-clicks and leaves every shown Button the addon's own code created (a check box and a menu row are
Buttons too), once each and in the current combat state; a click that opens new frames is walked in the same
pass. It does that with the gamepad interface off and then on, repeats the commands and map in combat, then
reloads and runs both interfaces again. It fails on an error either client caused; pass `addons`, `commands`,
`savedVariables` or `allowErrors` to narrow or widen it.

An addon that needs its own options declares the exercise, and the runner uses that instead of its automatic one:

```lua
scenario("every surface with my own commands", function(sim)
	sim:exercise{ commands = { "/myaddon reset" }, savedVariables = "tests/sim/fixtures/settings.lua" }
end)
```

## What it models

- **API**: every `C_*` namespace, global function, Enum and Constants table comes from
  `Blizzard_APIDocumentationGenerated`, with the documented arguments, return shapes and flags. Functions
  Blizzard's own Lua calls that the documentation omits exist; the ones the pinned annotations type answer with
  those returns (`undocumented_returns.lua`, from `gen_undocumented_returns.py`). Every widget method the
  documentation lists exists on its widget type.
- **Scripts and CVars**: `client_surface.lua` holds what the Forever client itself reports, from a ForeverProbe
  dump (cjber/forever-dev): for each widget type, every script its `HasScript` accepts, and every cvar with its
  default. `SetScript` and `HookScript` raise the client's `Cannot assign script handler for '...'` error for any
  other script, an XML `<Scripts>` handler the type does not take is ignored with a warning, as FrameXML.log does,
  and `HasScript` answers from the same set; script names match in any case. Every defined cvar starts at its
  default; an undefined one reads nil and `SetCVar` on it returns false. After a client patch, refresh it with
  `gen_client_surface.py --probe ForeverProbe.lua`; `tests/sim/client_surface_spec.lua` fails when the loaded UI
  reads a cvar or uses a widget type the dump lacks.
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
  the wiki is overridden beside the global and widget rules, with the issue that saw it. A widget method is keyed by
  its documented system (`SimpleButtonAPI_SetEnabled`) or, for a block the live client recorded, by its own name
  (`SetEnabled`): `fetch.py --refresh-restrictions --probe <ForeverProbe SavedVariables>` merges every call the
  client refused into the pin, classed from the recorded event and combat state.
- **Forever's professions**: `C_TradeSkillUI.OpenRecipe` behaves as recorded live, not as retail: from a hardware
  input it closes an open Professions window (three TRADE_SKILL_CLOSE) and answers
  `OPEN_RECIPE_RESPONSE(recipeID, base, child)`, and from tainted code outside one it is refused yet still answers.
  `CraftRecipe` is refused to tainted code at any time. A profession's `childSkillLineID` (Cooking 185, child 2939)
  is reported only by recipe, with the base line as parent; `GetProfessionChildSkillLineID` is 0. A refused call's
  recorded side effects live in `sim.refusedImpl`.
- **Items**: every item ID answers from the client's own Item, ItemSparse, ItemClass and ItemSubClass rows at the
  pinned build (every `GetItemInfo` return; `items-<locale>.lua` from `fetch.py`). A name resolves only for an
  item the bags hold, as the client resolves only cached items.
  A scenario's `sim.world.items[id]` wins over the client row, for an item the build lacks or a link a spec fixes.
  Bags (`sim.world.bags`), merchant sales and quest rewards hold only items one of the two knows, so a scenario
  cannot invent an item the client would never show.
- **Work per path**: `sim.work` counts, per event and per path a spec wraps in `measure`, the handlers dispatched and
  the documented API calls tainted code made, nested paths counting in their parent too. Counts are deterministic, so
  a bench asserts an upper bound on one path's work; the in-game per-frame cost is !!DevPerf's per-event split.
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
- Functions neither the documentation nor the annotations type answer by their name: counts 0, predicates false,
  the rest nil.
  Placeholders that Blizzard code reads for undocumented enums, constants and LE_* values are listed in
  `sim.gaps`.
- FrameXML proper, action bars, unit frames, chat and the shop are not booted (`loader.lua` SKIP_DEPS); a scenario
  can load one by name. The gamepad action bars and the action-button templates they inherit are booted.
- `secret == x` is always false, and a secret used as a table key is not caught.
- Units, recipes and maps are scenario data, not the game's databases.
- `GetItemInfo`'s `isCraftingReagent` is always false (the client derives it from item flags), and items given to
  the bags never merge into an existing stack.
- A client boots in about 2-4 s of CPU time. A suite belongs in its own CI job, not the fast gate.

## Profession recipe search

`C_TradeSkillUI.GetRecipeItemNameFilter` returns the current text, initially `""`.
`SetRecipeItemNameFilter(text)` sets it immediately; nil clears it. Changed text queues
`TRADE_SKILL_LIST_UPDATE` for the next simulation tick, coalescing changes before that tick.
Setting identical text does nothing. `GetFilteredRecipeIDs` preserves recipe order and returns
literal, case-insensitive substrings of recipe names; an empty filter returns all recipes.
`GetAllRecipeIDs` is unaffected.

Evidence comes from the UI revision pinned by `fetch.py`, under the cache's `wow-ui-source/Interface/AddOns/`:
`Blizzard_ProfessionsTemplates/Blizzard_Professions.lua`, `Professions.OnRecipeListSearchTextChanged`,
compares text with `strcmputf8i`, passes ordinary text to the name setter and nil for a level search.
`Blizzard_Professions/Blizzard_ProfessionsCrafting.lua` restores the search box from the getter.
`Blizzard_Professions/Blizzard_ProfessionsFrame.lua` refreshes on the list update, and
`Blizzard_APIDocumentationGenerated/TradeSkillUIDocumentation.lua` marks that event unique,
without the synchronous flag present on adjacent events.

The pinned generated documentation does not describe the name setter's native matching algorithm.
The engine implementation is absent from the UI source, so matching output-item or reagent names
cannot be established from these inputs. The simulator deliberately searches recipe names only,
using Lua's case fold (ASCII case-insensitive; no full Unicode fold), consistent with its existing
`strcmputf8i` model and SkillUp's local recipe-search fixture. Output-item/reagent matching,
Unicode case folding and item-level filtering are not claimed as modeled. Next-tick delivery,
coalescing and unchanged-text suppression are explicit simulator choices for the asynchronous,
unique update, rather than measured native timing.
