# SkillUp Forever 0.15.0: store plan

CurseForge project 1705762 (authors.curseforge.com/#/projects/1705762) and Wago aNerqn62
(addons.wago.io/developers/projects/aNerqn62). The packager uploads the file and the notes (the 0.15.0
CHANGELOG entry). Everything below is done by hand, once the v0.15.0 release run is green. The 0.14.0 plan is kept
at release/skillup-forever-0.14.0-store.md. If its description paste was never applied, this paste covers it.

## Summary (both stores, unchanged)

Required skill, colour thresholds and skill-up chance for every recipe in the Professions window.

## Description (both stores)

Paste `docs/curseforge.md` from main at the release commit, in full. On CurseForge, type cjber's footer at the
end of the textarea so React registers the change:

    Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)

What changed since the 0.14.0 paste: one line. "SkillUp is in English for now; translations are welcome as a pull
request or issue." becomes:

    Translated into German, French, Spanish, Brazilian Portuguese, Russian, Korean and Chinese (machine translated; corrections welcome through the [translation form](https://github.com/cjber/skillup-forever/issues/new?template=translation.yml)).

`check_copy.py` passes on README.md and docs/curseforge.md (590 of 600 prose words).

The release notes (published by the packager) now link the translation form. The TOC also carries localized
`## Notes-<locale>` lines, which only the in-game AddOns list reads; the store summary stays English.

## Logo (unchanged)

`media/icon-400.png` (400x400).

## Gallery (both stores, unchanged)

| # | File (docs/screenshots/) | Caption |
|---|---|---|
| 1 | demo.gif | From 48 to 60 the rows re-sort by cost per skill-up, and the bracers turn green at 55. |
| 2 | window.png | Chance and cost, right in the window's own rows. |
| 3 | tooltip.png | Colour thresholds and reagent prices for the recipe you hover. |
| 4 | route.png | The route tab from 48 to 73: what to train, what to craft and where reagents come from. |
| 5 | gear.png | The gear tab, turned on in settings: each slot shows the newest thing this character could craft for it. |
| 6 | tracker.png | Track it and the route sits beside your quests. |
| 7 | trainer.png | At the trainer, a green arrow marks the recipe that best extends or cheapens your route. |
| 8 | reagent.png | Hover a reagent to see how much your routes need. |

Every image is byte-identical to v0.14.0 (rendered twice, both runs identical): the scenes are English. Nothing to
upload or remove.

## Optional (owner)

- CurseForge's project page has a "Localization"/language field on some project types. If it shows one, tick
  German, Spanish (both), French, Korean, Portuguese (Brazil), Russian and Chinese (both). No Italian.
- Still outstanding from earlier plans, if never done: Relations (Shortest Path Forever as an optional
  dependency) on both stores, and the GitHub topics.
