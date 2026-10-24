# Round 3: Forever family visibility (owner-approved 2026-10-16)

The owner approved /tmp/claude-0/-home-user/76bf530e-5da5-583c-877f-df32f2ad82fa/scratchpad/visibility-plan.md in full
("do all fully"). Read it first. Their decisions on its section 9:
1. *Suggest my other Forever addons* is **on by default**.
2. The arrival footer in Shortest Path's tracker is **approved**.
3. Adventure Guide's name: **option (a)**. Keep the name; the summary and first image make it clearly about quests. Don't rename anything.
4. Shortest Path **shows Adventure Guide's suggestions** in its own quest menu (plan 6.2).

brief.md (commits, signing, PRs, attribution, the coordinator merges, strict protection) and release-brief.md still apply.
Send `READY <PR URL> <head sha>` to "main" for each PR. Never merge, push tags or trigger workflows yourself.

## Canonical names (use exactly)
| Addon | Folder / TOC | SavedVariables | CurseForge URL |
|---|---|---|---|
| Shortest Path Forever | ShortestPathForever | ShortestPathForeverDB | https://www.curseforge.com/wow/addons/shortest-path-forever |
| Adventure Guide Forever | AdventureGuideForever | AdventureGuideForeverDB | https://www.curseforge.com/wow/addons/adventure-guide-forever |
| SkillUp Forever | SkillUpForever | SkillUpForeverDB | https://www.curseforge.com/wow/addons/skillup-forever |
| Legacy Forever | LegacyForever | LegacyForeverDB | https://www.curseforge.com/wow/addons/legacy-forever |
| Tweaks Forever | TweaksForever | TweaksForeverDB | https://www.curseforge.com/wow/addons/tweaks-forever |

## Who does what
- **TOOLING agent** (cjber/skills, then one sync PR per addon): the shared store and README "Forever family" block, and its drift check.
- **SPF agent**: builds the shared Lua module `UI/ForeverFamily.lua` first (the canonical copy), then SPF's hints, then
  the Adventure Guide suggestions in SPF's quest menu (after the AGF API merges).
- **AGF, SkillUp, Legacy and Tweaks agents**: store and README copy for their own addon (section C) straight away. Then,
  once the coordinator says the SPF module has merged, port it byte-for-byte and add their hints (section B).
  The AGF agent also adds the suggestions API (section D) straight away.
- After every PR has merged, each repo agent does release prep (Phase 1 of release-brief.md, a minor bump) and sends READY.
  Then Phase 2 runs on "publish".

## A. The shared module `UI/ForeverFamily.lua` (the SPF agent writes it; the others port it byte-identical)
Model it on `UI/TrackerHost.lua`: one file, byte-identical in all five repos, first copy loaded wins through a global
(`ForeverFamily`), with `ns.Family` set to it. Add a spec in each repo that pins its sha256, the way
`tests/tracker_host_spec.lua` does, plus behaviour specs (in SPF's copy of the spec; the others copy the spec too).
It provides:
- `Family.ADDONS`: the five addons in the table's order: name, folder and URL, plus a one-line, plain-voice
  description of what each does, run through L[].
- `Family.State(folder)` → `"on"` | `"off"` (installed but disabled) | `"missing"`. Use `C_AddOns` with nil-safe
  fallbacks. Never assume a value isn't secret.
- `Family.Hint(db, key, folder)` → true when a hint for `folder` may show: `db.suggestFamily ~= false` (on by default),
  `Family.State(folder) == "missing"` (no hint for an addon that's installed but switched off: the player chose that),
  and `not (db.familyDismissed and db.familyDismissed[key])`. Passive surfaces (tooltip lines, a greyed menu entry)
  call this on each show. Active surfaces (the tracker footer) also call `Family.Once(key)`, which is true at most once a
  session.
- `Family.ShowLink(db, key, folder)`: a small movable popup with the addon's name and line, its CurseForge URL in a
  selected EditBox (Ctrl+C), the text "Copy the address, then open it in your browser.", Close (Escape closes too), and
  "Don't suggest this again", which sets `db.familyDismissed[key] = true`. Build it lazily, and never open it in combat.
- `Family.CreatePanel(parent, db)`: the content of a "Forever addons" settings sub-page. It has one row per addon:
  icon (`Interface\AddOns\<folder>\media\icon` when installed, else a neutral built-in icon), name, line, a state
  label ("On", "Installed, turned off", "Not installed"), and **Copy link** (→ ShowLink). The current addon's row
  says "This addon". Each addon wires this into its own settings as a sub-category, with its own checkbox
  *Suggest my other Forever addons* (`db.suggestFamily`, default on). Text: "Show a quiet line where one of my
  other Forever addons would help. Only for addons you don't have."
- Nothing protected, no hooks on Blizzard methods, nothing in combat, no network. Every string through L[].
  The taint, art, readable and multi-value lints pass. Regenerate phrases in every repo.
- Wording follows voice.md: plain, no marketing ("best", "ultimate", exclamation marks).

## B. Hints (each behind `Family.Hint`; tooltip and menu lines are grey)
- **SPF**
  - In the quest-choice and Shift-click menu, with AGF missing: a greyed entry
    "Suggest quests for my level: Adventure Guide Forever" → ShowLink. With AGF on, show its suggestions instead (D).
  - Tracker arrival footer: with nothing more planned after arrival and AGF missing, one grey line under the finished
    journey: "What next? Adventure Guide Forever suggests quests for your level." Use `Family.Once`; clicking it → ShowLink.
  - On dungeon and raid entrance tooltips, with Legacy missing: "Legacy Forever shows the Legacy challenges this counts
    toward." Only on instances Legacy has data for; if SPF can't know that, use all dungeons and raids, and say so in the PR.
- **SkillUp**
  - On the tooltips of trainer and vendor route rows, with SPF missing: "With Shortest Path Forever, this picks the nearest
    by travel time and leads you there."
  - On the Artisan quest steps, with AGF missing: "Adventure Guide Forever can plan this quest chain."
- **AGF**
  - Move its existing "Install …" lines (Shortest Path, Legacy, Tweaks) onto `Family.Hint` and the shared setting.
    Keep the "Enable …" lines (installed-but-off) as they are; they explain a missing feature, not a suggestion.
  - On profession-trainer stops, with SkillUp missing: "SkillUp Forever plans the cheapest route to your next profession rank."
- **Legacy**
  - Keep the Shortest Path tooltip line, but move its own setting onto `db.suggestFamily`. Migrate the old setting:
    if the player had turned it off, turn `suggestFamily` off once.
  - In the zone completion tooltip, with AGF missing: "Adventure Guide Forever routes the quests left in this zone."
- **Tweaks**
  - On dungeon entrance tooltips, with SPF missing: "With Shortest Path Forever, click to plan the way there."
  - Add the "Forever addons" sub-page (it is the Works with block).
- **Every addon** gets the "Forever addons" settings sub-page and the checkbox. The checkbox goes on that sub-page.

Every hint needs specs: shown when missing and on; hidden when installed, off, disabled or dismissed; Once for the footer.

## C. Store and README copy (each repo agent, its own addon)
- The TOOLING agent owns the shared family block between `<!-- forever-family:start -->` and `<!-- forever-family:end -->`
  in README.md and docs/curseforge.md. Don't edit inside the markers. You may remove your old "With my other Forever addons"
  or "All optional" sibling prose once the sync PR has landed the block (coordinate in your PR; the tooling sync PR
  inserts the block where that prose was).
- Outside the block, add one sentence per sibling that really integrates with yours, saying what it adds to *this*
  addon, where that isn't already said.
- **AGF**
  - Summary (store plan, and the TOC `## Notes` if it's worded the same) leads with quests and the pairing, e.g.
    "Picks quests for your level and, with Shortest Path Forever, walks you to each one."
  - The first gallery image is the map with the route. Update the store plan.
- **SPF**
  - Add a gallery scene of an Adventure Guide journey running through Shortest Path, if the mock-screenshot harness can
    render one (AGF has tools/screenshots_spf.py, so check whether SPF can do the reverse). Caption:
    "With Adventure Guide Forever: quests for your level, routed stop by stop".
  - If the harness can't render it, say so and list it in the store plan.
- **SkillUp**: replace the "All optional" sibling sentence with the shared block (via tooling) and keep the Auctionator,
  TomTom and Questie sentence.
- **Tweaks**: the summary leads with the three features most clearly its own (quest automation that respects Polestar,
  rare alerts, merchant handling). Update the gallery's first caption to match.
- **Legacy**: the GitHub link to Shortest Path becomes its CurseForge link. Use the shared block.
- Keep within each repo's copy limits (check_copy.py). Trim elsewhere if needed; don't drop content the old prose carried
  that isn't in the block.

## D. Adventure Guide suggestions in Shortest Path's menu
- **AGF** (straight away): add `API.Suggestions(limit)` to Core/API.lua. It returns up to `limit` (cap 5) of the guide's
  current top suggestions as plain tables `{ id, title, level, kind, map, x, y }`, using data already computed (no new
  planning on call; return what the panel would show). Also add `API.StartSuggestion(id)`, which starts it exactly as
  choosing it in AGF's own UI does (AGF then guides through SPF as usual). Bump the API minor, document it under
  "For addon authors", and add specs.
- **SPF** (after the AGF API PR merges): with AGF on and `API.Suggestions` present (feature-detect, no version pin),
  the quest menu shows a titled section "Adventure Guide suggests" with up to 3 rows, `[level] title`. Clicking one calls
  `StartSuggestion(id)`. Nothing shows when it returns nothing. Add a spec with an AGF stub. Never call it in combat if
  the menu path is protected.

## E. Owner-only (don't attempt; list in your report if relevant)
CurseForge Relations, Wago dependencies, GitHub repo topics, pinned repos, applying store copy and galleries.
