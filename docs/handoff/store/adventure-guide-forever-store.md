# Adventure Guide Forever v0.14.0: store plan

Apply by hand on CurseForge (project 1711538, https://authors.curseforge.com/#/projects/1711538) and
Wago (rNkgPlNa, https://addons.wago.io/developers/projects/rNkgPlNa) after the release is published.
All files are from `main` at the release commit (paths relative to the repo root).

## Summary (both stores)

Quest journeys and RestedXP guides in the map and objective tracker.

(Unchanged; matches the TOC `## Notes`.)

## Description (both stores)

Paste `docs/curseforge.md` from main in full. On CurseForge, keep the footer:
`Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)`

What changed in it since v0.13.0:
- The Next spot bullet became "Where to do objectives": a place with mobs 3 or more levels above you gives way
  to a lower one on its map, and Next spot cycles a step's spots, even where you stand.
- One line after the companion list: an empty shared tracker column leaves your quests where Edit Mode or your UI
  addon put them.
- The RestedXP bullet reads "Read RestedXP's instructions" and drops the travel note, "All optional. Each one adds
  something to the guide:" became "All optional:", and the What to do next bullet drops "Expand a header to see
  more" (the panel caption covers it).

`check_copy.py` passes; 599 words (limit 600).

## Logo

`media/icon-400.png` (unchanged; no re-upload needed).

## Gallery (unchanged order and files)

| # | File | Caption |
|---|------|---------|
| 1 | `docs/screenshots/demo.gif` | Choose a journey and follow its route. |
| 2 | `docs/screenshots/panel.png` | Choose a journey without leaving the world map's quest log. |
| 3 | `docs/screenshots/map.png` | Pick one and Shortest Path Forever walks you to each stop in turn. |
| 4 | `docs/screenshots/tracker.png` | Your journey heads the tracker, with action icons for the current stop and up to two upcoming stops. |
| 5 | `docs/screenshots/restedxp.png` | Follow a RestedXP guide in the Adventure tab, with its engine handling progress. |
| 6 | `docs/screenshots/loot.png` | Right-click a dungeon card to browse AtlasLoot bosses and their drops with native item tooltips. |
| 7 | `docs/screenshots/search.png` | Search puts the best match first, with each quest's requirements under it. |

## Replace or remove

Nothing. Every image re-rendered byte-identical at build 1.60.1.70425 (only `docs/screenshots/manifest.txt`
records the new build), so the gallery set from v0.13.0 stays as it is. If v0.13.0's plan wasn't applied yet,
apply that one's replacements; the files are the same.

## Not in the gallery

chosen.png, guide_setup.png, menu.png, panel_four.png, panel_overflow.png, story_complete.png and tooltip.png are
rendered for README/test coverage; story_complete.png is in the README only.

---

# v0.14.1 addendum

Description: paste `docs/curseforge.md` from main again after v0.14.1 (598 words). The only change since v0.14.0
is in the "Where to do objectives" bullet: "*Next spot* picks another camp, even where you stand." Summary, logo and
gallery are unchanged (screenshots byte-identical).

---

# Round 3 (Forever family visibility): summary and first image

Owner decision (a): the name stays; the summary and first gallery image make it plainly about quests. Apply once
the store-copy PR (and the tooling family-block PR #191) have merged; the release store plan supersedes this if the
release ships first.

## Summary (both stores)

Picks quests for your level and, with Shortest Path Forever, walks you to each one.

(Same text as the TOC `## Notes`.)

## Description (both stores)

Paste `docs/curseforge.md` from main in full. Its first paragraph now leads with quests and the Shortest Path pairing,
and the map image comes first.

## Gallery (new order)

| # | File | Caption |
|---|------|---------|
| 1 | `docs/screenshots/map.png` | Each number is a stop on the route: a pickup, an objective or a hand-in. |
| 2 | `docs/screenshots/demo.gif` | Choose a journey and follow its route. |
| 3 | `docs/screenshots/panel.png` | Choose a journey without leaving the world map's quest log. |
| 4 | `docs/screenshots/tracker.png` | Your journey heads the tracker, with action icons for the current stop and up to two upcoming stops. |
| 5 | `docs/screenshots/restedxp.png` | Follow a RestedXP guide in the Adventure tab, with its engine handling progress. |
| 6 | `docs/screenshots/loot.png` | Right-click a dungeon card to browse AtlasLoot bosses and their drops with native item tooltips. |
| 7 | `docs/screenshots/search.png` | Search puts the best match first, with each quest's requirements under it. |

On CurseForge, make map.png the featured (first) image: drag it to the top of Images. On Wago, reorder the same way.
No files change, so nothing needs re-uploading; only the order and the first caption change.

---

# Adventure Guide Forever v0.15.0: store plan (supersedes the sections above)

Apply by hand on CurseForge (project 1711538, https://authors.curseforge.com/#/projects/1711538) and Wago
(rNkgPlNa, https://addons.wago.io/developers/projects/rNkgPlNa) after v0.15.0 is published. Files are from `main`
at the release commit.

## Summary (both stores)

Picks quests for your level and, with Shortest Path Forever, walks you to each one.

(Same as the TOC `## Notes`. Changed since v0.14.x: it used to read "Quest journeys and RestedXP guides in the map and
objective tracker.")

## Description (both stores)

Paste `docs/curseforge.md` from main in full (599 words, check_copy.py passes). On CurseForge keep the footer:
`Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)`

Changed since v0.14.1:
- The opening leads with quests and the Shortest Path pairing, and says the game's waypoint leads without it.
- The map with the route is the first image.
- The shared "The Forever addons" family block (between the forever-family markers) replaces the old
  "With my other Forever addons" list.
- Usage names the Forever addons settings page, which lists all five Forever addons.
- The tracker caption is shorter.

## Logo

`media/icon-400.png` (unchanged; no re-upload).

## Gallery (new order; no new files)

| # | File | Caption |
|---|------|---------|
| 1 | `docs/screenshots/map.png` | Each number is a stop on the route: a pickup, an objective or a hand-in. |
| 2 | `docs/screenshots/demo.gif` | Choose a journey and follow its route. |
| 3 | `docs/screenshots/panel.png` | Choose a journey without leaving the world map's quest log. |
| 4 | `docs/screenshots/tracker.png` | Your journey heads the tracker, with the current stop and up to two upcoming ones. |
| 5 | `docs/screenshots/restedxp.png` | Follow a RestedXP guide in the Adventure tab, with its engine handling progress. |
| 6 | `docs/screenshots/loot.png` | Right-click a dungeon card to browse AtlasLoot bosses and their drops with native item tooltips. |
| 7 | `docs/screenshots/search.png` | Search puts the best match first, with each quest's requirements under it. |

Make map.png the featured (first) image on both stores (drag it to the top). Update captions 1 and 4.

## Replace or remove

Nothing to delete: every image re-rendered byte-identical (two runs), so the files on the stores are current; only
the order and captions 1 and 4 change.

## Not in the gallery

chosen.png, guide_setup.png, menu.png, panel_four.png, panel_overflow.png, story_complete.png and tooltip.png are
rendered for README/test coverage; story_complete.png is in the README only.

## Owner-only (not done here)

CurseForge Relations and Wago dependencies (Shortest Path, SkillUp, Legacy, Tweaks as optional), per the visibility
plan.

---

# v0.17.0 addendum

Apply by hand on CurseForge (project 1711538) and Wago (rNkgPlNa) once v0.17.0 is published.

## Summary (both stores)

Unchanged. It matches the TOC `## Notes`: "Picks quests for your level and, with Shortest Path Forever, walks you to each one."

## Description (both stores)

Paste `docs/curseforge.md` from main at the release commit in full, keeping the CurseForge footer. The only change
since v0.16.1 is one new first bullet under Features, plus trims elsewhere to stay within the limit (599 words):

- **Works alongside Polestar.** While Polestar guides, the route and map marks pause; click the tracker line to take
  over, or turn this off in Route settings.

The "Search and hints" bullet and the "Installed together" and tracker-column paragraphs are shorter.
`check_copy.py` passes on README.md (1197 words) and docs/curseforge.md (599 words).

## Logo

`media/icon-400.png`. It's unchanged, so there's nothing to re-upload.

## Gallery

The files, captions and order are unchanged from the v0.14.0 plan above. Both renders were byte-identical to main at
build 1.60.1.70450, and only `docs/screenshots/manifest.txt` records the new build.

## Replace or remove

Nothing.
