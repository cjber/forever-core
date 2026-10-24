# Tweaks Forever 0.13.0: store plan

CurseForge project 1708506 (authors.curseforge.com/#/projects/1708506) and Wago ZKxOWd6k
(addons.wago.io/developers/projects/ZKxOWd6k). The packager uploads the file and the 0.13.0 notes. Do the rest by hand
after the v0.13.0 release run is green. The earlier round-3 copy plan is kept beside this file as
tweaks-forever-round3-copy-store.md, and the 0.12.0 gallery plan as tweaks-forever-0.12.0-store.md.

## Summary (both stores): CHANGED

Old:

    Small quality-of-life automations and fixes that extend the default UI, stepping aside where another addon already does the job.

New (the TOC `## Notes`, word for word):

    Options to accept and turn in quests (standing down for Polestar), name rares near you, and repair and sell junk at merchants.

## Description (both stores): CHANGED

Paste `docs/curseforge.md` from main at the release commit, in full. On CurseForge, type cjber's footer at the end of
the textarea so React registers the change:

    Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)

What changed since the 0.12.1 paste:
- The intro leads with quest automation (standing down for Polestar), rare alerts and merchants. Polestar joins the
  "greys out" list, and so does OpenMap.
- A **Rares and levelling** bullet moves up to third (it was **Levelling**, near the end).
- **Also** adds "a page listing my five Forever addons".
- The hand-written "With my other Forever addons" list is now the shared family block, titled "The Forever addons" (five-row table), with
  a sentence each after it on what Shortest Path, Adventure Guide and Legacy add to Tweaks. The block is between
  `<!-- forever-family:start -->` and `<!-- forever-family:end -->`. CurseForge and Wago show HTML comments as
  nothing, so paste them as they are.
- Shorter wording elsewhere: 590 prose words of 600. `check_copy.py README.md docs/curseforge.md` passes.

## Logo (unchanged)

`media/icon-400.png`. Leave it.

## Gallery: first caption CHANGED, order unchanged

Keep the same 15 images and order as tweaks-forever-0.12.0-store.md. The four PNGs over 2 MB go up as the JPEGs in
`tweaks-gallery/` (dungeonmap, dungeons, zonelevels, exploration), as before. Change only image 1's caption:

| # | File | Old caption | New caption |
|---|---|---|---|
| 1 | demo.gif | Dungeon entrances on the map, nameplates, and the junk coin in your bags. | The junk coin marks what sells with your greys at a merchant. Also dungeon entrances and nameplates. |

Both stores let you edit a caption in place. On Wago, if you upload anything, upload in reverse order (newest shows first).

No image shows quest automation, a rare alert or the Forever addons page yet. A scene for each would be a follow-up
wow-mock-screenshots PR. If one lands, make it image 1 and move this caption to it.

## Stale images to remove

None. All 15 images re-rendered twice for 0.13.0, byte-identical to each other and to the committed (0.12.1) files.

## Owner-only

- CurseForge Relations and Wago dependencies: Shortest Path Forever as an optional dependency (the TOC already lists it
  in `## OptionalDeps`).
