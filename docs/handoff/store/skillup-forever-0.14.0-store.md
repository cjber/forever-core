# SkillUp Forever 0.14.0: store plan

CurseForge project 1705762 (authors.curseforge.com/#/projects/1705762) and Wago aNerqn62
(addons.wago.io/developers/projects/aNerqn62). The packager uploads the file and the notes (the 0.14.0
CHANGELOG entry). Everything below is by hand, after the v0.14.0 release run is green. The 0.13.0 plan is kept
at release/skillup-forever-0.13.0-store.md; if its changes were never applied, this plan includes them
(description paste) and its gallery table still holds.

## Summary (both stores, unchanged)

Required skill, colour thresholds and skill-up chance for every recipe in the Professions window.

## Description (both stores)

Paste `docs/curseforge.md` from main at the release commit, in full. On CurseForge, type cjber's footer at the
end of the textarea so React registers the change:

    Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)

What changed since the 0.13.0 paste:
- The "With my other Forever addons" list is gone. The shared family block (between the
  `<!-- forever-family:start/end -->` markers, heading "The Forever addons") replaces it:
  a sentence and a five-row table, each name linked to its CurseForge page. The HTML comment markers don't
  render on CurseForge or Wago; leave them in the paste so the next paste diff stays clean.
- After the block, one paragraph says what the others add to SkillUp: Shortest Path's trip and travel-time
  pick, Adventure Guide's Professions tab, the shared tracker column with Legacy.
- Prices and Usage are trimmed (same content, fewer words); the settings line says "Forever addon hints".
- `check_copy.py` passes on README.md and docs/curseforge.md (586 of 600 prose words) and `check_family.py`
  passes.

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

Every image is byte-identical to v0.13.0 (rendered twice, identical). Nothing to upload or remove. No scene
shows the Forever addons page or a hint line (a settings canvas and a tooltip line); not worth a gallery slot.

## Owner-only, by hand (not in any PR)

- CurseForge Relations for 1705762: Shortest Path Forever as an optional dependency (the only Forever addon in
  the TOC's `## OptionalDeps`; Auctionator, TomTom, Syndicator, Questie and AtlasLoot can be added too).
- Wago aNerqn62: the same optional dependency.
- GitHub topics on cjber/skillup-forever: `world-of-warcraft`, `wow-addon`, `wow-forever`, `lua`.
