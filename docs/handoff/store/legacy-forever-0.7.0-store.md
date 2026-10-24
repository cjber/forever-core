# Legacy Forever v0.7.0: store plan (CurseForge 1705879, Wago b6mzA7KP)

Apply by hand after the v0.7.0 release workflow has uploaded the file. Everything below is from
cjber/legacy-forever main once PR "chore: prepare v0.7.0" has merged.

## Summary (both stores)

Shows which of your unfinished Legacy challenges you can advance in the zone on the world map.

(Unchanged; same as the TOC Notes line.)

## Description (both stores)

Paste docs/curseforge.md from main, then add the footer on CurseForge:

    Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)

What changed since the 0.6.21 description:
- The /lf report line now links the wrong objective issue form:
  https://github.com/cjber/legacy-forever/issues/new?template=wrong_objective.yml
- The translations line links the translation issue form:
  https://github.com/cjber/legacy-forever/issues/new?template=translation.yml
check_copy.py (wow-forever-addon at ceffa4d) passes on docs/curseforge.md and README.md; about 597 prose words (limit 600).

## Logo

media/icon-400.png (400x400). Unchanged. Re-upload only if the store shows something else.

## Gallery, in display order

The screenshots were re-rendered twice for this release and are byte-identical to what is on main
(last changed 2026-10-09 in #97). docs/screenshots/scenes.sha256 is current.

| # | File | Caption |
|---|------|---------|
| 1 | docs/screenshots/demo.gif | Discover an area and its shading lifts as the corner's percentage goes up. Click the corner to fold it away. |
| 2 | docs/screenshots/map.png | Half of Ashenvale explored: the shield's number is what's left on this map, and its menu lists it by challenge. |
| 3 | docs/screenshots/continent.png | Zoom out and each zone with dungeon objectives left gets a badge. |
| 4 | docs/screenshots/tracker.png | Challenges you track sit in the objective tracker under the game's own header, with live progress. |
| 5 | docs/screenshots/menu.png | Tick a challenge in the menu to track it. |

Sizes: map.png 2.5 MB and continent.png 2.8 MB are over CurseForge's 2 MB limit. Convert those two to
quality-90 JPEGs in a temp folder before uploading (the gif is 464 KB; tracker and menu PNGs are under 2 MB).
Wago lists the newest first, so upload there in reverse order (5 to 1), one image per submit, caption before submit.

## Stale images to remove

No image changed in this release. Compare each store's gallery with the five above and delete:
- any image that is not one of these five, such as a map or tracker shot uploaded before 2026-10-09
  (compare it with the current file: the tracker shot was redrawn in #97);
- duplicates of any of the five;
- docs/screenshots/unvisited.png if it was ever uploaded: it illustrates docs/zone-completion.md, not the store page.

/lf report has no screenshot: it is a support window, not a headline feature (WFA-9), so the gallery does not gain one.

## After applying

Save, reopen and check captions and order on both stores. Check the public pages show 0.7.0 for Forever:
- https://www.curseforge.com/wow/addons/legacy-forever/files
- https://addons.wago.io/addons/legacy-forever/versions
