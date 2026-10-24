# Shortest Path Forever v1.19.0: store plan (CurseForge 1708599, Wago b6Xy1wKp)

Apply this by hand once the v1.19.0 release workflow has uploaded the file. It all comes from
cjber/shortest-path-forever main after "chore: prepare v1.19.0" merges. This is a minor release: the addon is now
translated into the nine languages the WoW: Forever client offers besides English (#210).

## Summary (both stores)

The fastest way anywhere: walking paths, flight points, boats, zeppelins, lifts, the tram and portals, with live departure times.

Unchanged. It matches the TOC `## Notes` line. Store copy stays English (WFA-34).

## Description (both stores)

Paste docs/curseforge.md from main. The one change since 1.18.0 is a new line after the Usage list:

    Translated into German, French, Spanish, Brazilian Portuguese, Russian, Korean and Chinese (machine translated; corrections welcome through a [translation issue](https://github.com/cjber/shortest-path-forever/issues/new?template=translation.yml)).

On CurseForge, keep the footer:

    Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)

check_copy.py (wow-forever-addon) passes on docs/curseforge.md (580/600 words) and README.md (1195/1200).

## Logo

media/icon-400.png (400x400). Unchanged.

## Gallery, in display order

I rendered the screenshots twice for this release. Both runs were byte-identical to each other and to main
(the scenes are drawn in English), so the gallery is unchanged from 1.18.0's plan.

| # | File | Caption |
|---|------|---------|
| 1 | docs/screenshots/demo.gif | The route settles, the next boat counts down and the compass turns with you. |
| 2 | docs/screenshots/tracker.png | The tracker shows the trip one step at a time. |
| 3 | docs/screenshots/minimap.png | Walking breadcrumbs and the native waypoint lead to the next step. |
| 4 | docs/screenshots/docks.png | Hover a dock to see its services and destinations. |
| 5 | Adventure Guide's docs/screenshots/map.png | With Adventure Guide Forever: quests for your level, routed stop by stop |

- Image 5: https://raw.githubusercontent.com/cjber/adventure-guide-forever/main/docs/screenshots/map.png
- docks.png is 2.8 MB, over CurseForge's 2 MB limit. If you upload it again, convert it to a quality-90 JPEG first.
- Wago lists the newest image first, so upload in reverse order (5, 4, 3, 2, 1).

## Stale images to remove

None are new in this release. If 1.18.0's gallery plan hasn't been applied yet, apply it now: remove any image that
isn't one of the five above, and any duplicate of them.

## Owner-only

- CurseForge: if the project settings list supported languages, you can tick the nine locales. Nothing ships
  through CurseForge's localization system (the packager keyword is unused).
