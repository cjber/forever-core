# Forever addons: your checklist (2026-10-16)

Everything else is done and merged. These need you, because they need a login, a browser or the game.

## 1. Store pages (CurseForge and Wago)
Every description is `docs/curseforge.md` from main. When you paste it, delete the two `<!-- forever-family -->` marker lines.
The CurseForge footer ("Made by Cillian Berragan · …") is already at the bottom of each file.

| Addon | Description | Summary | Gallery |
|---|---|---|---|
| Shortest Path | re-paste (adds the translations line) | unchanged | five images: demo.gif, tracker.png, minimap.png, docks.png (JPEG on CF, 2.8 MB), plus AGF's map.png |
| SkillUp | re-paste (adds the translations line) | unchanged | unchanged |
| Adventure Guide | re-paste after 0.16.0 | **"Picks quests for your level and, with Shortest Path Forever, walks you to each one."** | map.png first; captions 1 and 4 per the store plan |
| Legacy | re-paste | unchanged | re-upload demo.gif, map.png (JPEG on CF) and menu.png; delete the old copies |
| Tweaks | re-paste | the new summary from the store plan | new first caption |

- **Wago:** it still showed the old Shortest Path and SkillUp descriptions after your paste. Check that both saved.
- **CurseForge Relations and Wago dependencies:** add Shortest Path Forever as an optional dependency on Adventure Guide, SkillUp, Legacy and Tweaks.
- **Moderation:** nothing to do. Confirmed public on CurseForge on the evening of 2026-10-16: SPF 1.19.0, SkillUp 0.15.0, Legacy 0.9.0, Tweaks 0.14.0, AGF 0.16.0.

The store plans, with the exact text and images, are in `/tmp/claude-0/-home-user/76bf530e-5da5-583c-877f-df32f2ad82fa/scratchpad/release/`.

## 2. GitHub
- [ ] Add your commit-signing SSH key to GitHub (Settings, then SSH and GPG keys, as a *Signing key*). Until then, commits from these sessions show "unknown key" instead of Verified.
- [ ] Add this line to `cjber/.github/.github/PULL_REQUEST_TEMPLATE.md` (this session had no push access):
  `- [ ] A reporter or requester is credited in the changelog bullet and THIRD_PARTY.md (WFA-33)`
- [ ] Add repo topics to all five repos: `world-of-warcraft`, `wow-addon`, `wow-forever`, `lua`.
- [ ] Pin the five repos on your profile.
- [ ] Add the `package` job to each repo's required checks.
- [ ] Delete the probe branches in cjber/skills: `ccr-cc333990-q8ydc4-probe` and `fix/probe-xyz`.
- [ ] Optional: purge the old QuestieDB-derived test files from AGF's git history (needs a force-push). They're no longer committed.

## 3. People and comments
- [ ] Skim the Wago comment pages of all five addons (they need a login). Send me any names whose report or idea we built, so I can credit them.
- [ ] Optional: create a shared Discord for bug reports and send me a permanent invite link. I'll wire it into every report window, the settings pages, the READMEs and the stores.

## 4. In game (each release PR lists its full `/reload` checks)
- **Forever addons page** in each addon's settings: it lists five rows, Copy link works, Escape closes the window, and the buttons fit.
- **Hints:** they show only for addons you don't have, and *Suggest my other Forever addons* turns them all off.
- **SPF:** Adventure Guide's suggestions in the quest menus (with AGF 0.15.0 or later), the "What next?" footer, and the Legacy line on dungeon stops.
- **SkillUp:** the auction-house reagent search for N crafts, and that it doesn't overlap Auctionator's button or, in German or French, Create All or Track Recipe.
- **Tweaks:** no login error, rare alerts, the OpenMap step-aside, and the gamepad check for the settings page (#168).
- **Translations:** switch the client to German, French, Korean or Chinese and check that the text fits and no `%d` shows.
- **Open issues that need the game:** SPF #158, #159, #161 and #188; AGF #166; SkillUp #124; Tweaks #168.
