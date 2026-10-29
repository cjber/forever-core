# Hoard Forever: v0.1.0 build brief

Repo: `cjber/hoard-forever` (public, new). Addon folder: `HoardForever`. Interface 16001, flavour `_classic_beta_`.
Owner: Cillian Berragan (`cjber`, cjberragan@gmail.com). You implement, test and open a PR. You never merge or tag.

## Read first

1. `AGENTS.md` and `README.md` in the repo (already committed on `main`).
2. `cjber/skills`, branch `ccr-cc333990-q8ydc4-handoff`: `forever-handoff/brief.md` (shared agent rules: commits, PR
   flow), `forever-handoff/boundaries.md` (who owns what), and `wow-forever-addon/SKILL.md` (the WFA standards pack
   this repo declares in AGENTS.md).
3. The `wow-retail-ui-style` skill (`cjber/skills`, branch `ccr-cc333990-q8ydc4-handoff`,
   `wow-retail-ui-style/SKILL.md`). Its twelve rules are hard requirements for the window, not advice: templates,
   NineSlice layouts from `NineSliceLayouts.lua`, font objects, client colours, and atlases resolved against the
   pinned build `1.60.1.70124`. No hand-drawn chrome, no hex gold.
4. Reference implementation for structure and tooling: `cjber/field-guide-forever` (Field Guide Forever). Copy its
   shape, not its features.

## What Hoard Forever is

One window that answers "where is this item, and how many do I have". It searches every container a character can
see, plus the last recorded state of the account's other characters, and it never moves, sells, mails or uses
anything.

Standalone: no dependency on QuestieDB, AtlasLoot, any Forever sibling or any library. It must work with nothing else
installed, and nothing else may depend on it.

## Scope for v0.1.0

### Sources

| Source | How it is read | Notes |
|---|---|---|
| Bags | `C_Container.GetContainerNumSlots` and `GetContainerItemInfo`, containers 0..4 plus `BACKPACK_CONTAINER` | include the reagent bag when the client has one |
| Bank | bank containers from `BANK_CONTAINER` (-1) through `NUM_BANKGENERAL_SLOTS`, plus the reagent bank | only readable while the bank is open |
| Warband bank | only if the client exposes it; probe with `pcall` and hide the source when absent | never fake it |
| Guild vault | `C_GuildBank.GetGuildBankItemInfo(tab, slot)` while the vault is open, cached per guild | the cache survives the vault closing |
| Alts | the SavedVariables snapshot each character writes on container change and at logout | timestamped, keyed `Name-Realm` |

Every source is probed at runtime. A source the client or the player does not have is absent from the tabs and from
the counts, never shown as zero with an error.

### The index

- `Core/Model.lua` is pure: `Build(scan)` groups raw container records into one record per item (by `itemID`,
  link suffix, quality, icon, name), each with a `sources` list of `{ kind, character, tab, count }` and a total.
  `Query(index, text, tab)` filters and ranks. No WoW API, no I/O, no `GetTime`, so the specs drive it directly.
- Ranking: exact name, then name prefix, then word prefix, then substring; ties broken by total count then name.
  Case and accent insensitive. An empty query lists the largest stacks first.
- Token filters in the same box, documented in the README: `q:epic` (quality at least), `t:weapon` (item class),
  `ilvl:>200`. A token the parser does not recognise is treated as text, never as an error.
- Rebuild on `BAG_UPDATE_DELAYED`, `PLAYERBANKSLOTS_CHANGED`, `PLAYERBANKBAGSLOTS_CHANGED`, `GUILDBANK_UPDATE_TABS`
  and on window open. No `OnUpdate`, no polling timer, and no full rescan per keystroke: keystrokes filter the
  cached index.
- Cost: opening the window on a full account stays under 3 ms per frame and a keystroke under 1 ms. Put the
  measurement in the PR.

### The window

- `UI/Window.lua`: `PortraitFrameTemplate` (or `ButtonFrameTemplateNoPortrait` when the portrait has nothing to
  show), title "Hoard Forever", a NineSlice content well around the results, `MinimalScrollBar` on the list.
- Tab row about y = -54 with `PanelTemplates` tabs (`All`, `Bags`, `Bank`, `Alts`, `Guild`), 16 to 20 units of
  padding, title baseline 30 from the top edge, the first result row about 90 below the title, 8 units between rows,
  controls 22 to 26 units high. The client's rhythm matters more than any single number here.
- Search box: `InputBoxTemplate` with `GameFontHighlight`, 8 unit text insets, placeholder in `GameFontDisableSmall`,
  focused on open. `Esc` clears the query, then closes the window.
- `UI/Results.lua`: one row per item. The item icon from its real `IconFileDataID` in a client icon frame, the name
  in the quality colour from `ITEM_QUALITY_COLORS`, a right aligned total in `NumberFontNormalSmall`, and one line of
  source chips under it ("Bags 12", "Bank 40", "Ahri-Bank 3", "Guild tab 2: 8") in `GameFontHighlightSmall`.
  `Shift`-click inserts the item link into chat; a plain click opens a `GameTooltip` anchored to the row with the
  item's own tooltip and the per source breakdown.
- Empty state: one line of `GameFontDisableSmall` naming what was searched, in the player's words.
- Footer: the result count and a one line hint. No button that acts on an item.
- The window position and size live in `HoardForeverDB.window`, clamped to the screen on load, registered in
  `UISpecialFrames` so `Esc` closes it, and it opens in combat without a protected call.

### Entry points

- `/hoard` and `/hoardforever` open the window; `/hoard <text>` opens it with that query.
- `HoardForever_OnAddonCompartmentClick` (declared in the TOC) opens it.
- `Core/Settings.lua` registers a Settings > AddOns page with the few real options: default tab, whether the guild
  vault is cached, whether alt snapshots are recorded at all, and "clear alt snapshots". No custom options window and
  no minimap button.

### Saved data

`HoardForeverDB`: `{ window = {...}, settings = {...}, chars = { ["Name-Realm"] = { bags = {...}, bank = {...},
guild = {...}, updated = <epoch> } }, schema = 1 }`. Flat and serialisable only. Every key is read through
`ns.DEFAULTS` (WFA-14). One character never overwrites another's snapshot, and a snapshot older than 30 days is
marked stale in the tab rather than silently trusted.

### Public API

`Core/API.lua` publishes a versioned read only `HoardForever` table: `HoardForever.version`,
`HoardForever.Count(itemID)` returning the total and the per source counts, and `HoardForever.Open(query)`. It
returns nil until the index is ready. Nothing else is public.

### Locales

`Locales/enUS.lua` is the source. Ship the same nine locales the suite ships (deDE, esES, esMX, frFR, koKR, ptBR,
ruRU, zhCN, zhTW), machine translations marked `-- mt`, every line a whole sentence. A missing phrase falls back to
its key.

### Assets and docs

- `media/icon.svg` from the family icon template, rendered with the skill's `render_icon.py` to `media/icon-400.png`
  and `media/Icon.tga` (64 px). Gold rounded frame, one centred emblem (a chest or a stack of crates, not a
  magnifying glass over a bag).
- `tools/screenshots.py` renders `docs/screenshots/` with `wowmock` (skill `wow-mock-screenshots` on the same
  branch): at least three scenes, `search.png` (a query with results across Bags and Bank), `alts.png` (the Alts tab
  with three characters) and `empty.png` (a query with no results). Real item IDs, names and icons from the pinned
  build, with the window drawn from the addon's own constants. Open every rendered PNG at full resolution before
  committing it and fix anything clipped, overlapping or misaligned: a green hash check does not prove the picture
  looks right.
- `README.md`: keep the current shape, add the screenshots under `## Features` with a line of text after each one,
  and stay under 1,200 words.
- `docs/curseforge.md`: the store description, under 600 words, with the same screenshots.
- `CHANGELOG.md`: keep `## [0.1.0] - 2026-10-22` and rewrite the bullets to match what actually shipped.
- `THIRD_PARTY.md`: keep it truthful. No third party code, no vendored data.

## Tests

`tests/model_spec.lua` is the important one: grouping, per source totals, ranking order, every token filter, an
unrecognised token, an empty index, and one item sitting in five sources at once. `tests/core_spec.lua` keeps the
load and defaults check. `tests/snapshots_spec.lua` covers reading a mocked container set into records and the
snapshot round trip. Specs are LuaJIT scripts through `tests/wow_mock.lua`; extend the mock where you need a
container API, and never weaken an assertion to make a spec pass.

## Gate before you open the PR

```sh
luacheck .
for spec in tests/*_spec.lua; do luajit "$spec" || exit 1; done
stylua --check .
uvx ruff@0.16.8 check tools && uvx ruff@0.16.8 format --check tools
python3 tools/changelog.py --check
printf 'Package check\n' > .release-notes.md && <packager -d -z> && python3 tools/check_package.py
```

CI must be green on your head SHA. You do not verify in game: list in the PR body the `/reload` checks the owner
should make (open with `/hoard`, search a bank item, switch tabs, `Shift`-click a row, clear alt snapshots).

## Git rules

- Branch `feat/hoard-v0.1` off `main`. Never push to `main`.
- Author `Cillian Berragan <cjberragan@gmail.com>`. Do not pass `-s`, `--signoff` or any signing flag: GitHub signs.
- Conventional commit subjects, and no model names anywhere.
- Open the PR against `main` with a body saying what changed, how you tested it, the in game checks left for the
  owner, and the frame cost measurement. Do not merge it.

## Report back

Send `READY <PR URL> <head sha>` to the channel when CI is green, plus one line on anything you left out and why. If
the client API you need does not exist in this build, say which source you disabled and how the UI reports it.
