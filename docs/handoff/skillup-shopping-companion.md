# SkillUp: material shopping list companion (bill of materials, copy export, one buy trip, API minor 2)

Repo: cjber/skillup-forever. Branch from fresh `origin/main`. Read the repo's `AGENTS.md` first and obey it.
Do not bump the version, do not tag, do not run the Release workflow. The maintainer does release prep.

The owner asked for the "Skill Up material shopping list companion" (idea 3 of the suite deep dive). Most of
it already ships: the tracker's missing-reagent section, per-profession Auctionator lists, the vendor buy
button, alt counts through Syndicator, prices with age, and the recursive craft cost. Do not rebuild any of
that. This PR adds the four things that are genuinely missing, nothing else.

## 1. Read API: `SkillUpForever.API.ShoppingList(skillLineID?)`

`Core/API.lua` builds `local API = { version = 1 }` (line 360). Add `minor = 2` and
`API.ShoppingList(skillLineID)`. With no argument it covers every tracked profession; with a skill line ID,
just that one.

Return a copy (never the cache), built from the same data the tracker uses (`ns.TrackedNeeds()` and
`ns.RouteReagents(plan)`), one row per item per profession:

```lua
{
  profession = "Tailoring",       -- the plan's profession name, or nil when the skill line is not a route
  skillLine = 197,
  items = {
    {
      itemID = 2592,              -- the item's ID
      need = 24,                  -- the route's total for this profession
      have = 6,                   -- bags plus bank, ns.Have
      missing = 18,               -- max(need - have, 0)
      source = "vendor",          -- gather | vendor | auction | unknown, as Model.ShoppingSource gives
      price = 120,                -- copper per unit from ns.Price, nil when unknown
      priceAge = 3,               -- days since Auctionator saw it, nil for vendor and gather prices
      cost = 2160,                -- missing * price, nil when the price is unknown
      alt = { { name = "Altname", count = 12 } }, -- ns.AltCounts, may be empty
    },
  },
  total = 2160,                   -- copper for every priced missing item in this profession
  unpriced = 2,                   -- number of missing items with no known price
}
```

Order is deterministic across calls: professions by name, then the source bucket order in
`ns.Model.SHOPPING_SOURCES` (gather, vendor, auction, unknown), then itemID. Keep it stable so the window and
the copied text never shuffle between refreshes. Document the shape in `types/API.lua`, keep
`types/Namespace.lua` in step, and add an "For addon authors" bullet in the CHANGELOG's Unreleased section.

This is the contract `work-orders-forever` will consume, so names and nil semantics matter more than breadth.

## 2. Standalone window: `UI/ShoppingList.lua`

A player can only see the shopping list today by opening a profession, or while one is tracked. Add one
window, opened from chat without a profession open. Follow `UI/Report.lua` for the frame: `PortraitFrameTemplate`,
`UISpecialFrames` for Escape, `SetToplevel`, clamped to screen, movable, the addon's own icon in the portrait
through `ns.Art`, and an `InsetFrameTemplate` body. Match the native client look, per the `wow-retail-ui-style`
skill at `~/wow/skills/wow-retail-ui-style` (read it before drawing): no invented chrome, no stretched art, no
overlapping or clipped text.

Content, grouped by source with a heading per bucket that has rows ("Gather", "Vendor", "Auction house",
"Unknown"), rows showing icon, item name, need, have, missing, alts ("on Altname" for the largest holder), unit
price and line cost. Footer: the total cost of everything still missing, plus "N items have no price yet" when
that is non-zero. Empty state: one centred line saying there is nothing to buy and why (no tracked profession,
or nothing missing).

Two buttons in the footer:

- **Copy list**: open the same read-only, pre-selected, multi-line `EditBox` dialog that `UI/Report.lua` uses
  (`Select` calls `SetFocus` then `HighlightText`, `OnTextChanged` restores the text) with the plain text from
  item 3. WoW has no clipboard API, so the dialog must tell the player to press Ctrl+C, exactly as the report
  window does.
- **Plan buy trip**: calls item 4. When Shortest Path is missing, keep the button visible but disabled with a
  tooltip explaining that the trip needs Shortest Path Forever.

Register with `ns.WhenStale("shoppingList", Refresh)` so it follows skill, tracking, merchant, prices and bag
changes through `ns.Changed`. Render only after `PLAYER_ENTERING_WORLD` and `VARIABLES_LOADED`, deferred one
frame, like the rest of the suite. Never hook a Blizzard method or reparent a Blizzard frame.

Open it with `/su shopping` and `/su shop` (add both to the existing `Slash` in `Core/Core.lua`), and add a
"Shopping list" button beside the existing shopping controls on the route page (the block around
`UI/Route.lua:929`).

Add the file to `SkillUpForever.toc` in load order (after `UI/Shopping.lua`) or it never runs.

## 3. Plain text export: `ns.ShoppingText(skillLineID?)`

Player-facing text, no markup, no em or en dashes. One header line naming the professions covered, then the
items grouped by source, then the total. Example:

```
SkillUp Forever shopping list
Tailoring
Vendor
18 x Linen Cloth - 1s 20c each - 21s 60c
Auction house
4 x Coarse Thread - 40c each, price seen 3 days ago - 1s 60c
Unknown
2 x Fine Thread - price unknown
Total for priced items: 23s 20c
```

Rules: only rows with `missing > 0`; names come from `C_Item.GetItemNameByID` with the existing
`item %d` fallback and a `RequestLoadItemDataByID` call when the name is not cached; money through the
`ns.FormatNet`/`ns.Model.RoundMoney` path the rest of the UI uses; every phrase through `ns.L`. Long lists are
not truncated: the copy dialog scrolls.

## 4. One buy trip: `ns.ShoppingTrip(skillLineID?)`

Everything still missing becomes a single Shortest Path route, in the order the player should visit:

1. One stop per vendor NPC that sells missing vendor-sourced items, nearest first. Use the data already read:
   `ns.NearestVendor(itemID, true)` (Integrations/Sources.lua:454) and `ns.NPCLocation(npcID)` for map, x, y
   and name. Group items by vendor so a vendor appears once, with the items it covers in the stop title or
   tooltip.
2. The auction house, only if the catalogue can already name a real auctioneer with a map position for the
   player's side. Do not invent one, do not bundle a table of auctioneer IDs: if the catalogue cannot name one,
   omit this stop and say so in the PR body.
3. The profession's trainer when the plan's next step is a training step (`ns.NearestTrainer(profession, cap, true)`).

Then call `ShortestPathForever.API.NavigateRoute("SkillUpForever", stops)` (stop fields: `map`, `x`, `y`,
`title`, `kind = "vendor"|"auction"|"trainer"`). Refuse cleanly with a chat line when the API or its
`NavigateRoute` is absent, and fall back to `ns.SetWaypoint` for the first vendor so the player is not stuck.
Cap the stops at the API's limit and say in the PR what that limit is. Do not add a second routing engine and
do not draw anything yourself: Shortest Path owns the route.

## 5. Tests (`tests/shopping_list_spec.lua`)

Cover at least:

- two tracked professions sharing a reagent: needs sum, professions stay separate;
- have counts reduce missing and never go below zero;
- source buckets and their order, and itemID order inside a bucket;
- vendor, auction and unknown prices, plus `priceAge` from Auctionator's age;
- totals exclude unpriced items and `unpriced` counts them;
- the API returns a fresh copy each call (mutating a row must not change the next answer);
- `ns.ShoppingText` output: header, grouping, money formatting, "price unknown", no truncation;
- `ns.ShoppingTrip`: stop order, one stop per vendor, trainer appended only for a training step, the
  no-Shortest-Path fallback, and refusal when the plan has nothing missing.

Follow `tests/client.lua` and the existing `shopping_spec.lua`/`api_spec.lua` for the stub client. Anything the
harness cannot reach (the window, the copy dialog, the buttons) belongs in the PR's In-game checks section as
concrete `/reload` steps, not in a fake test.

## 6. Screenshot and store copy

Add a shopping-window scene to `tools/screenshots.py` (follow the existing scenes; every number must come from
the repo's own data and Lua), generate it, put it in the README beside the route and tracker images, and look
at the PNG before you finish: no overlap, no clipping, no stretched art, native client look. Run
`python3 tools/check_screenshots.py --record` after.

## Gate and PR

Run every command in the repo's `AGENTS.md` `## Commands` block and make each one pass (stylua, ruff, luacheck,
typecheck, all specs, changelog check, generated check, screenshots check, sift gate and agents check). No
skipped or loosened tests.

Branch `ccr-cc333990-q8ydc4-shopping-companion`, conventional commits, omit `-s` (GitHub signs), push, open
one PR against main using the repo template, list the `/reload` checks, and report the PR number, the files
changed and the gate results. Add one `[Unreleased]` CHANGELOG bullet in the owner's voice, bold lead, no em or
en dashes anywhere.
