# Legacy Forever v0.8.0: store plan (CurseForge 1705879, Wago b6mzA7KP)

Apply this by hand after the v0.8.0 release workflow has uploaded the file. Everything here comes from
cjber/legacy-forever main once the PR "chore: prepare v0.8.0" has merged. It comes after #125
(CurseForge link), #126/#128/#132 (shared family block and tooling), #127 (Forever addons page and
hints), #130 (credits) and #131 (the page in Legacy's own French). The 0.7.1 plan is kept in legacy-forever-0.7.1-store.md next to this file.

## Summary (both stores)

    Shows which of your unfinished Legacy challenges you can advance in the zone on the world map.

This is unchanged, and it matches the TOC Notes line. Legacy stays focused (visibility plan, section 6.4).

## Description (both stores)

Paste docs/curseforge.md from main. On CurseForge, add this footer:

    Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)

What changed since the 0.7.1 description:
- The "With my other Forever addons" list is replaced by the shared Forever family table (the block
  between the `forever-family` HTML comments; the comments don't render). One sentence after it says
  what Shortest Path, Adventure Guide and Tweaks add to Legacy.
- Every sibling link goes to CurseForge.
check_copy.py (wow-forever-addon) passes. docs/curseforge.md has 570 prose words (limit 600) and
README.md has 1155 (limit 1200; #130 added a Credits section, which is GitHub-only).

## Logo

media/icon-400.png (400x400), unchanged.

## Gallery, in display order

These are the same five images and captions as before. Three of the images were redrawn in #127,
because the map menu's last checkbox now reads "Suggest my other Forever addons". Re-upload those
three and delete the old copies.

| # | File | Caption | Action |
|---|------|---------|--------|
| 1 | docs/screenshots/demo.gif | Discover an area and its shading lifts as the corner's percentage goes up. Click the corner to fold it away. | **re-upload** (redrawn) |
| 2 | docs/screenshots/map.png | Half of Ashenvale explored: the shield's number is what's left on this map, and its menu lists it by challenge. | **re-upload** (redrawn) |
| 3 | docs/screenshots/continent.png | Zoom out and each zone with dungeon objectives left gets a badge. | keep |
| 4 | docs/screenshots/tracker.png | Challenges you track sit in the objective tracker under the game's own header, with live progress. | keep |
| 5 | docs/screenshots/menu.png | Tick a challenge in the menu to track it. | **re-upload** (redrawn) |

map.png (2.5 MB) is over CurseForge's 2 MB limit, so convert it to a quality-90 JPEG for CurseForge.
menu.png (1.1 MB) and demo.gif (0.5 MB) fit as they are. On Wago, upload in reverse display order,
because it lists the newest first.

I re-rendered the screenshots twice for this release. Both runs were byte-identical to main.

## Stale images to remove

The old uploads of the three redrawn images: "Discover an area and its shading lifts…",
"Half of Ashenvale explored…" and "Tick a challenge in the menu to track it.". The old menu still says
"Suggest companion addons". Also remove unvisited.png and any duplicates, if they're still there from
before 0.7.0.

## Owner-only

- CurseForge Relations: add Shortest Path Forever as an optional dependency. The TOC already lists it
  in OptionalDeps. On Wago, do the same through its dependency field.

## After applying

Check that both public pages show 0.8.0 for Forever, with the 0.8.0 notes:
- https://www.curseforge.com/wow/addons/legacy-forever/files
- https://addons.wago.io/addons/legacy-forever/versions
