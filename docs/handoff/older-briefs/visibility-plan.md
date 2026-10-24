# Forever addons: visibility and cross-linking plan

2026-10-16. This is a plan only, with no code. Every in-game item becomes its own issue and PR once you approve it.

## 1. Where things stand

| Addon | CurseForge downloads | Links to the others on its store page | Mentions the others in game |
|---|---|---|---|
| Shortest Path Forever | **32.2K** | "With my other Forever addons", at the bottom | none |
| SkillUp Forever | **24.6K** | buried in an "All optional" paragraph | none |
| Adventure Guide Forever | 2.5K | "With my other Forever addons", at the bottom | yes: "Install Shortest Path Forever for walked routes…", "Install Legacy Forever…", "Install Tweaks Forever…" |
| Legacy Forever | 2.4K | one paragraph; one link goes to GitHub, not CurseForge | a grey tooltip line on pins suggesting Shortest Path, with a setting to turn it off |
| Tweaks Forever | 2.0K | one sentence at the end of "Works alongside" | none |

What the numbers say:
- About 57K of the 64K total downloads come from two addons, Shortest Path and SkillUp. The other three each have about 2K.
- Adventure Guide is the natural partner of Shortest Path. One decides where to go next, the other gets you there. But only about 1 in 13 Shortest Path downloads also gets Adventure Guide.
- The two big addons are the funnel, and they currently say nothing about the others in game. Their store pages mention them only at the very bottom.
- Legacy's grey tooltip line is the right pattern to copy. It shows up exactly where the other addon would help, it's quiet, and it has a setting.

## 2. Rules every change follows

1. **Shown where it helps, never at login.** A hint appears at the moment the other addon would do the job: a menu, a tooltip, or an empty state. There are no popups and no chat lines at login, and the update line stays about this addon only.
2. **Only when it's missing, at most once a session, and off with one setting.** Hints show only when the other addon isn't installed. Each addon gets one setting, *Suggest my other Forever addons*. If a hint is dismissed, it stays away for the account.
3. **Plain wording.** Each hint says what you'd get, in the voice.md style and with no marketing. For example: "Adventure Guide Forever suggests quests for your level." Every hint goes through Locales.
4. **No network, no taint, nothing in combat.** A hint is a grey line, or a menu entry that copies a link. It never opens a browser or calls a protected function.
5. **A hint never blocks or weakens the feature.** An addon still works fully on its own.

## 3. In game, by addon (sorted by reach)

### Shortest Path → Adventure Guide (the biggest win)
- **Quest menu.** Shift-click and the quest-choice menu are where players pick a goal by hand. When Adventure Guide is missing, add one grey entry, "Suggest quests for my level: Adventure Guide Forever". Clicking it opens a small copy box with the CurseForge address. Reuse the existing `/path report` window.
- **Tracker after arrival.** When you arrive and nothing else is planned, add a one-line grey footer under the finished journey: "What next? Adventure Guide Forever plans quests for your level." It shows once a session.
- **Dungeon and raid entrances** (Shortest Path's portal and entrance pins). When Legacy Forever is missing, add a grey tooltip line, "Legacy Forever shows the Legacy challenges this counts toward". It shows only on the dungeons Legacy has data for.

### SkillUp → Shortest Path and Adventure Guide
- **Route rows for trainers and vendors.** With Shortest Path missing, SkillUp falls back to the nearest place in a straight line. Add a grey line on the row's tooltip: "With Shortest Path Forever this picks the nearest by travel time and walks you there." That's true, and it's the value the player gets.
- **The quest steps added in 0.12.0** (Artisan quests). With Adventure Guide missing, add a grey line: "Adventure Guide Forever can plan this quest chain."

### Adventure Guide (already does this; tidy it up)
- Move its three "Install …" lines onto the shared setting and the once-a-session rule, so all five addons behave the same.
- Add a SkillUp hint on profession-trainer stops: "SkillUp Forever plans the cheapest route to your next profession rank."

### Legacy
- Keep the Shortest Path tooltip line.
- Add an Adventure Guide line on zone completion: "Adventure Guide Forever routes the quests left in this zone." Zone completion counts quests, and Adventure Guide plans them.

### Tweaks
- On its settings page, add a short **Works with** block that lists the other four, each with one line and installed or not. That's the obvious place in a settings-only addon.
- The dungeon-entrance click already plans with Shortest Path. When Shortest Path is missing, the entrance tooltip says "With Shortest Path Forever, click to plan the way there."

### Shared, in all five addons: a "Forever addons" settings page
- Each addon gets one small sub-page under its settings that lists the five addons. Each row has its icon, one plain line, its status (*on*, *installed but off*, or *not installed*), and a **Copy link** button.
- Build it once as a shared Lua file, like TrackerHost, that is byte-identical in every repo and checked by `sync.py`. Then the wording and the list stay in step, and a sixth addon is a one-line change.
- This page also carries the global *Suggest my other Forever addons* setting.

## 4. Store pages (CurseForge and Wago)

These are copy and gallery changes only. You'd apply them by hand, like the release store plans.

- **One shared "Forever family" block.** Every description gets the same five-row table near the top, under the first screenshot and not at the very bottom. Each row has the icon, the name, a link, and "with this addon: …" saying what it adds to *this* one. Today two pages have a list at the bottom and three bury it in prose.
- **Shortest Path page:**
  - Add a gallery image of an Adventure Guide journey running through Shortest Path, captioned "With Adventure Guide Forever: quests for your level, routed stop by stop".
  - It has only 3 gallery images now, so there's room.
- **Adventure Guide page:**
  - **Summary line:** lead with the pairing and the outcome, not the mechanism. For example: "Picks quests for your level and, with Shortest Path Forever, walks you to each one."
  - **First gallery image:** the map with the route.
- **SkillUp page:** replace the "All optional" paragraph with the family block. SkillUp has the second-biggest audience, and today its cross-links are the hardest to find.
- **Tweaks:**
  - The summary sounds generic ("game settings for…"). Lead with the three most-used features instead.
  - Rename the gallery's first caption to match.
- **Legacy:** fix the GitHub link so it points to CurseForge, and add the family block.
- **CurseForge "Relations" tab:** add each real optional dependency that the TOCs already declare.
  - Adventure Guide, SkillUp, Legacy and Tweaks each list **Shortest Path** as an optional dependency.
  - Adventure Guide also lists the others.
  - This shows on every page, CurseForge's search uses it, and it matches what the code already does.
- **Wago:** the same descriptions. Use Wago's dependency field the same way.

## 5. GitHub

- **README "Works with" section:** a shared five-row table at the same place in every README, just under the screenshots. Add it to the forever_tools copy check so it can't drift.
- **Topics on all five repos:** `world-of-warcraft`, `wow-addon`, `wow-forever`, `lua`.
- **A profile README** (`cjber/cjber`) listing the five, and pin the five repos on your profile.
- Make sure each issue form names the addon's own `/… report` command (done in round 1) and links the family page.

## 6. Rethinking some addons (for you to decide)

1. **Adventure Guide's name.** "Adventure Guide" is Blizzard's name for the dungeon journal. A player scanning a list may think it's a loot or boss journal. Options:
   - (a) Keep the name and make the summary and first image unmistakably about quests. This is cheap, and I recommend starting here.
   - (b) Add a subtitle in the store title, "Adventure Guide Forever: Quest Routes".
   - (c) Rename it later if (a) doesn't move downloads. Renaming costs search ranking and existing links, so I don't recommend it yet.
2. **An Adventure Guide option inside Shortest Path.** Instead of only a hint, Shortest Path's quest menu could show Adventure Guide's top three suggestions when Adventure Guide is installed. The API already exists. This makes the pair feel like one product while staying two addons, which keeps #166's load time apart. It's medium effort; do it after section 3.
3. **Tweaks' scope.** It's a broad bundle with a generic name, and it overlaps OpenMap and Leatrix for maps. Lead its page with what's unique to Forever (quest automation that respects Polestar, rare alerts, merchant handling). Leave the map features to step aside, as they already do.
4. **Legacy stays focused.** Its audience is people chasing Legacy points. Point it out where those players already are, on dungeon pins in Shortest Path and zone completion in Adventure Guide, instead of broadening the addon.

## 7. Measuring it

- **Baseline today:** Shortest Path 32,267, SkillUp 24.6K, Adventure Guide 2,549, Legacy 2.4K, Tweaks 2.0K.
- Each week, record CurseForge downloads and the files-page ratio of Adventure Guide to Shortest Path. Also record GitHub traffic referrers per repo; the owner can see these under Insights → Traffic.
- **Target:** a meaningful rise in Adventure Guide and Legacy downloads relative to Shortest Path within 4–6 weeks of the in-game hints shipping.
- **What's not measured in game:** no telemetry is added. The addons have no network access, and that stays true.

## 8. Order and effort

| Phase | Work | Effort | Who |
|---|---|---|---|
| 1 | Store pages: the family block, summaries, Relations, the Shortest Path gallery image; plus GitHub topics, profile, README table | small | I draft, you apply in the stores |
| 2 | The shared "Forever addons" settings page and setting, as a shared Lua file synced like TrackerHost | medium | one PR per repo |
| 3 | The hints where they help: Shortest Path quest menu and arrival footer, SkillUp route tooltip, Legacy and Tweaks lines, Adventure Guide's existing lines moved onto the shared rule | medium | one PR per repo, with specs; off with the shared setting |
| 4 | Adventure Guide suggestions inside Shortest Path's quest menu (6.2) | medium | Shortest Path and Adventure Guide, using the existing API |
| 5 | Review the numbers at 4–6 weeks; decide on Adventure Guide's subtitle or rename (6.1) | — | you |

## 9. Decisions I need from you

1. The global setting: should *Suggest my other Forever addons* be on by default? I recommend yes, since each hint is quiet, shown only where it helps, and at most once a session.
2. Is the arrival-footer hint in Shortest Path's tracker acceptable? It's the most visible one.
3. Adventure Guide's name: option (a) now, revisit later? Or a subtitle now?
4. Should Shortest Path show Adventure Guide's suggestions in its own menu (6.2)?
