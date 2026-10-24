# Legacy Forever v0.7.1: store plan (CurseForge 1705879, Wago b6mzA7KP)

Apply by hand after the v0.7.1 release workflow has uploaded the file. Everything here comes from
cjber/legacy-forever main once PR #123 "chore: prepare v0.7.1" has merged. This is a patch release.
The store copy, logo and gallery are unchanged from 0.7.0, so the only job is to confirm the stores
still match the 0.7.0 plan (kept in legacy-forever-0.7.0-store.md next to this file).

## Summary (both stores)

Shows which of your unfinished Legacy challenges you can advance in the zone on the world map.

Unchanged, and the same as the TOC Notes line.

## Description (both stores)

docs/curseforge.md has not changed since 0.7.0. If the stores already show the 0.7.0 description,
leave it alone. Otherwise paste docs/curseforge.md from main and add this footer on CurseForge:

    Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)

check_copy.py (wow-forever-addon) passes on docs/curseforge.md and README.md.

## Logo

media/icon-400.png (400x400), unchanged.

## Gallery, in display order (unchanged)

I re-rendered the screenshots twice for this release. Both runs were byte-identical to main, and no
image has changed since 2026-10-09 (#97).

| # | File | Caption |
|---|------|---------|
| 1 | docs/screenshots/demo.gif | Discover an area and its shading lifts as the corner's percentage goes up. Click the corner to fold it away. |
| 2 | docs/screenshots/map.png | Half of Ashenvale explored: the shield's number is what's left on this map, and its menu lists it by challenge. |
| 3 | docs/screenshots/continent.png | Zoom out and each zone with dungeon objectives left gets a badge. |
| 4 | docs/screenshots/tracker.png | Challenges you track sit in the objective tracker under the game's own header, with live progress. |
| 5 | docs/screenshots/menu.png | Tick a challenge in the menu to track it. |

map.png (2.5 MB) and continent.png (2.8 MB) are over CurseForge's 2 MB limit. If you have to
re-upload them, convert them to quality-90 JPEGs first.

## Stale images to remove

None are new in this release. If the 0.7.0 gallery clean-up wasn't done, do it now: remove any image
that isn't one of the five above, any duplicate of them, and unvisited.png.

## After applying

Check that both public pages show 0.7.1 for Forever, with the 0.7.1 notes:
- https://www.curseforge.com/wow/addons/legacy-forever/files
- https://addons.wago.io/addons/legacy-forever/versions

## Round 3 (Forever family visibility), for the next release's store paste

#125 (CurseForge link) and #126 (tooling sync, shared family block) have merged; the hints PR is #127.
Apply with the next release, not before.

- Summary: unchanged (Legacy stays focused; plan section 6.4).
- Description: paste docs/curseforge.md from main. Since #126 the "With my other Forever addons" list
  is the shared "My other Forever addons" table (between the `forever-family` markers, which CurseForge
  and Wago don't render), followed by one sentence on what Shortest Path, Adventure Guide and Tweaks
  add to Legacy.
- The README's map pins link to Shortest Path Forever now goes to CurseForge, not GitHub (#125). The
  store description already linked CurseForge.
- Owner-only (not done by any agent): CurseForge Relations, add Shortest Path Forever as an optional
  dependency (the TOC already declares it in OptionalDeps); on Wago, the same through its dependency field.
- Gallery: #127 redraws demo.gif, map.png and menu.png (the map menu's last checkbox now reads
  *Suggest my other Forever addons*). The release store plan will list them for re-upload.
- Logo: unchanged.
