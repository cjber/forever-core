# Tweaks Forever: store plan (round 3 copy, family-brief section C)

CurseForge project 1708506 (authors.curseforge.com/#/projects/1708506) and Wago ZKxOWd6k
(addons.wago.io/developers/projects/ZKxOWd6k). Apply by hand once the store-copy PR is on main (or with the next
release, whose plan will extend this one). The 0.12.0 plan is kept beside this file as tweaks-forever-0.12.0-store.md.

## Summary (both stores): CHANGED

Old:

    Small quality-of-life automations and fixes that extend the default UI, stepping aside where another addon already does the job.

New (the TOC `## Notes`, word for word):

    Options to accept and turn in quests (standing down for Polestar), name rares near you, and repair and sell junk at merchants.

It leads with the three features most clearly Tweaks' own: quest automation that stands down for Polestar, rare
alerts, and merchant handling (repairs and junk). "Options to" because quest automation and rare alerts start off.

## Description (both stores)

Paste `docs/curseforge.md` from main in full, and type cjber's footer at the end on CurseForge as before:

    Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)

What changed:
- The intro leads with the same three features. "Polestar" joins the list of addons whose overlapping option greys out.
- New third bullet, **Rares and levelling** (it was **Levelling**, near the end).
- Shorter wording in Vendors, Maps, Nameplates, Sparkles, Fishing and Usage, which keeps the copy under 600 words
  (597 prose words; README 1,185 of 1,200). `check_copy.py README.md docs/curseforge.md` passes.
- The "With my other Forever addons" section is unchanged here. The TOOLING agent's sync PR swaps it for the shared
  Forever family block; paste whatever main has at the time.

## Logo (unchanged)

`media/icon-400.png`. Leave it.

## Gallery: first caption CHANGED, order unchanged

Keep the 15 images and order from tweaks-forever-0.12.0-store.md (JPEGs for the four images over 2 MB are in
tweaks-gallery/). Change only image 1's caption:

| # | File | Old caption | New caption |
|---|---|---|---|
| 1 | demo.gif | Dungeon entrances on the map, nameplates, and the junk coin in your bags. | The junk coin marks what sells with your greys at a merchant. Also dungeon entrances and nameplates. |

The README caption under the GIF says the same. CurseForge and Wago both let you edit a caption in place.

No image yet shows quest automation or a rare alert, so the caption leads with the merchant feature the GIF does show.
A scene for each (a rare alert line in chat; the quest dialog accepting itself is hard to show in a still) would be a
follow-up wow-mock-screenshots PR. If one lands, make it image 1 and move this caption to it.

## Stale images to remove

None. Every image re-rendered byte-identical; only `scenes.sha256` changed (Map/Coordinates.lua's hash).

## Owner-only (not done here)

- CurseForge Relations and Wago dependencies: Shortest Path Forever as an optional dependency (the TOC already
  declares it in `## OptionalDeps`).
