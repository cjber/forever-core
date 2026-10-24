# Legacy Forever v0.9.0: store plan (CurseForge 1705879, Wago b6mzA7KP)

Apply this by hand after the v0.9.0 release workflow has uploaded the file. Everything here comes from
cjber/legacy-forever main once the PR "chore: prepare v0.9.0" has merged. The only player-facing change since
0.8.0 is #135 (translations). The 0.8.0 plan is in legacy-forever-0.8.0-store.md next to this file.

## Summary (both stores)

    Shows which of your unfinished Legacy challenges you can advance in the zone on the world map.

Unchanged, and the same as the TOC Notes line. Store copy stays English (WFA-34).

## Description (both stores)

Paste docs/curseforge.md from main. On CurseForge, add this footer:

    Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)

What changed since the 0.8.0 description: one paragraph in Usage. "It's in English and French. More translations
are welcome…" now reads "Translated into French by Brainc3ll, and into German, Spanish, Korean, Brazilian Portuguese,
Russian and Chinese by machine. French lines added since, such as the Forever addons page, are machine translated too.
Corrections are welcome as a pull request or a translation issue: Locales has the template."

check_copy.py (wow-forever-addon) passes: docs/curseforge.md has 595 prose words (limit 600) and README.md
has 1180 (limit 1200).

## Logo

media/icon-400.png (400x400), unchanged.

## Gallery, in display order

All keep: no image changed since 0.8.0. I re-rendered twice for this release, and both runs were
byte-identical to main.

| # | File | Caption | Action |
|---|------|---------|--------|
| 1 | docs/screenshots/demo.gif | Discover an area and its shading lifts as the corner's percentage goes up. Click the corner to fold it away. | keep |
| 2 | docs/screenshots/map.png | Half of Ashenvale explored: the shield's number is what's left on this map, and its menu lists it by challenge. | keep |
| 3 | docs/screenshots/continent.png | Zoom out and each zone with dungeon objectives left gets a badge. | keep |
| 4 | docs/screenshots/tracker.png | Challenges you track sit in the objective tracker under the game's own header, with live progress. | keep |
| 5 | docs/screenshots/menu.png | Tick a challenge in the menu to track it. | keep |

If the 0.8.0 plan's re-uploads weren't applied yet, apply them first: re-upload demo.gif, map.png (as a
quality-90 JPEG on CurseForge, where the limit is 2 MB) and menu.png, then delete their old copies.

## Stale images to remove

None new. Clean-up still open from 0.8.0, if not already done: unvisited.png and any duplicates.

## Store fields (optional)

On CurseForge, under "Supported languages" (or the project's language field, if it has one), the addon now
ships deDE, esES, esMX, frFR, koKR, ptBR, ruRU, zhCN and zhTW. Wago has no such field.

## Owner-only (carried over from 0.8.0, if not done)

- CurseForge Relations: Shortest Path Forever as an optional dependency (the TOC lists it in OptionalDeps); on Wago,
  the same through its dependency field.

## After applying

Check that both public pages show 0.9.0 for Forever, with the 0.9.0 notes:
- https://www.curseforge.com/wow/addons/legacy-forever/files
- https://addons.wago.io/addons/legacy-forever/versions
