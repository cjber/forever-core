# W3: SkillUp shopping list API, text export and one buy trip

Repo: `cjber/skillup-forever` (folder `SkillUpForever`, Interface 16001).
Read `../brief.md`, `../boundaries.md`, `../round9/README.md`, then `skillup-forever/AGENTS.md`.

## Why

The shopping maths is already shipped and must not be rebuilt: `UI/Shopping.lua` has the tracker section
(`MAX_OBJECTIVES`, `RefreshTracker`), cross-profession totals (`ns.TrackedNeeds`), bags+bank counts with the
secret-number fallback (`ns.Have`), Syndicator alt counts (`ns.AltCounts`), the vendor buy button
(`MerchantPurchases`, `BuyMissing`, `Confirm`), the Auctionator list (`WriteAuctionList`, `SyncAuctionator`,
`AuctionSignature`, `ns.AuctionListName`); `UI/AuctionSearch.lua` searches a recipe's missing reagents;
`Integrations/Prices.lua` prices vendor / Auctionator / bundled / gathered; `Core/Model.lua`
(`SHOPPING_SOURCES`, `BucketItems`) buckets by gather / vendor / auction / unknown.

What is missing is the outside world: `SkillUpForever.API` v1 is only `Professions`, `Stats`, `Navigate`,
`OpenRecipes`, so nothing can read the list - not `work-orders-forever`, not another Forever addon - even though
`boundaries.md` §3 promises "export hands raw materials to work-orders-forever or a shopping list". There is also
no text export (`UI/` has no clipboard path at all) and no single trip that buys everything still missing.

## What to build, in this order, one PR per step

### PR 1 - `API.ShoppingList` (API `minor`; v1 currently has no `minor`, so add `minor = 1`)

```lua
API.ShoppingList(skillLineID?) -> {
  itemID, name?, need, have, source,          -- source: "gather" | "vendor" | "auction" | "unknown"
  copper?, priceSource?, priceAge?,           -- from Integrations/Prices.lua; nil when unpriced
  profession?, professionID?,
}[]
API.ShoppingText(skillLineID?, opts?) -> string   -- the same list as text, see PR 2
```

- With no `skillLineID`, the list is every tracked profession's, aggregated exactly as `ns.TrackedNeeds()` does
  it (`need` summed, `have` counted once). With an id, that profession alone.
- `source` must be the model's own bucket (`ns.Model.ShoppingSource`), never a second classification.
- Every number comes from the existing plan/prices. Do not recompute costs in the API file.
- Return fresh tables; empty table (not nil) when nothing is tracked. Nil is reserved for "not ready yet", the
  way `Professions()` already behaves.
- Specs: `tests/api_shopping_spec.lua` covering aggregated vs single profession, a shared reagent, a tool item, an
  unpriced item, nothing tracked, and the copy isolation.

### PR 2 - the text export

- `ns.BuildShoppingText(skillLineID?, opts)` in a new `UI/Export.lua` (or `Core/Export.lua` if it stays pure
  text): grouped by source in `ns.Model.SHOPPING_SOURCES` order, then by profession, one item per line as
  `60 x Copper Bar (auction, 1g 20s)`; a header line naming the character and the professions; `opts.plain` gives
  the machine format instead - `itemID:count` per line, nothing else - which is the work-orders handoff shape.
- **The client has no clipboard-write API.** Do not pretend otherwise: a "Copy list" button opens a small popup
  with a multi-line `EditBox` pre-filled and text pre-selected, with the hint string "Select all and copy
  (Ctrl+C)". Say it plainly in the tooltip and the changelog; do not claim one-click copy.
- `/su list [profession]` prints the human list to chat and opens the same popup, so a player without the window
  open can still get it. `/su list plain` gives the machine format.
- Nine translations for every new phrase (`deDE esES esMX frFR koKR ptBR ruRU zhCN zhTW`, `-- mt` on machine
  lines), `python3 tools/check_locales.py` clean, `python3 tools/phrases.py` regenerated if the repo's workflow
  requires it (check `AGENTS.md`).
- Specs: exact expected text for a small fixture (order, grouping, thousands of copper formatting, empty list,
  plain format), and a screenshot of the popup if it is a real frame.

### PR 3 - one buy trip

`ns.BuyTrip()` -> one `NavigateRoute("SkillUpForever", stops)` through Shortest Path, covering what the list
still lacks:

- vendor-source items: the vendors that sell them, from the data this repo already has (`Data/Vendor.lua`,
  `Integrations/Sources.lua` - do not hand-write vendor coordinates);
- auction-source items: the nearest auctioneer **only if** `HasAuctionator()` and the player's collect mode is
  auction (`ns.CollectMode()`), since a trip to an AH with no list is a wasted walk;
- training steps: the route's `plan.training` trainers, the way `TrainingSteps` already resolves them.

Stops are ordered by travel with `ShortestPathForever.API.Estimate` when present, else by straight-line distance;
each stop gets `title`, `tooltip` (what to buy there and how much) and an appropriate `kind` (`"vendor"`,
`"auction"`, `"trainer"`). Declines cleanly (returns false with a reason) when SPF is absent, in combat, or when
there is nothing missing - and then falls back to setting the game's own waypoint on the first stop. Button in the
shopping section next to the vendor buy button, plus `/su trip`.
- Specs with a fake `ShortestPathForever.API`: stop contents, ordering, the decline paths, the waypoint fallback,
  and that no stop is produced for a bucket that needs nothing.

## Boundaries

SkillUp owns profession numbers, the list and its export; Shortest Path executes travel; Tweaks owns bag and
tooltip UI - do not add lines to Blizzard tooltips, and do not move the list into another addon. The
`work-orders-forever` integration is the plain text format plus the API call, nothing more, unless that repo is
checked out and has a documented public API you can call safely - if it is not available, say so in the PR body
rather than inventing a handshake.

## Report

Gate lines per PR, proposed version and CHANGELOG entry, PR URLs with head SHAs, exactly which parts depend on
Auctionator or Syndicator being installed, and the in-game checks the owner should run. No version bump, no tag.
