# SkillUp Forever 0.13.0: store plan

CurseForge project 1705762 (authors.curseforge.com/#/projects/1705762) and Wago aNerqn62
(addons.wago.io/developers/projects/aNerqn62). The packager uploads the file and the notes. Everything below is by
hand, after the v0.13.0 release run is green.

If the 0.12.0 store changes (description paste, five replaced images, trainer caption) haven't been applied yet,
apply this plan instead; it includes them.

## Round 3 (Forever family): next description paste

Apply with the next release's paste, not before: paste `docs/curseforge.md` from main once both of these have
merged, so the store never shows the half-way state.

- SkillUp's family-copy PR (branch `ccr-cc333990-q8ydc4-family-copy`): under *With my other Forever addons*, the
  sentences that say what a sibling adds to SkillUp now stand on their own. With Shortest Path Forever, clicking
  a trainer or vendor in the route plans the trip there, and SkillUp picks the nearest by travel time. Adventure Guide Forever shows each profession's next steps in its Professions tab. A
  tracked route shares one tracker column with their sections and Legacy Forever's.
- The TOOLING sync PR for SkillUp: the shared Forever family block (between `<!-- forever-family:start -->` and
  `<!-- forever-family:end -->`, heading "My other Forever addons") replaces the "With my other Forever addons"
  heading and its "All optional:" list of Legacy and Tweaks; the integration paragraph then follows the block's
  table. The Prices and Usage sections were trimmed in the same PR to fit WFA-11's 600 words (597 after the sync).

Summary, logo and gallery: unchanged by this round. If the hints PR lands before the release, the release plan
adds nothing to the gallery for it (a tooltip line, no new scene).

### Owner-only, by hand (not in any PR)

- CurseForge Relations for project 1705762: add Shortest Path Forever as an optional dependency. It is the only
  Forever addon in the TOC's `## OptionalDeps` (with Auctionator, TomTom, Syndicator, Questie and AtlasLoot,
  which can also be added if they have CurseForge projects).
- Wago aNerqn62: the same optional dependency in its dependency field.
- GitHub topics on cjber/skillup-forever: `world-of-warcraft`, `wow-addon`, `wow-forever`, `lua`.

## Summary (both stores, unchanged)

Required skill, colour thresholds and skill-up chance for every recipe in the Professions window.

## Description (both stores)

Paste `docs/curseforge.md` from main at the release commit, in full. On CurseForge, type cjber's footer at the
end of the textarea so React registers the change:

    Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)

What changed since the 0.12.0 paste: the Shopping lists bullet ends with "At the auction house, search a recipe's
reagents for as many crafts as you choose." (#143). `check_copy.py` passes on README.md, docs/curseforge.md and
docs/route.md.

## Logo (unchanged)

`media/icon-400.png` (400x400).

## Gallery (both stores, unchanged from the 0.12.0 plan)

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

Every image is byte-identical to v0.12.0, so nothing new to upload if the 0.12.0 gallery changes were applied.
If not, replace demo.gif, window.png, route.png, tracker.png and reagent.png (stale since 0.11.0), keep gear.png,
tooltip.png and trainer.png, and set trainer.png's caption as above. On Wago, upload in reverse order.

## Not in the gallery

No scene shows the auction-house reagent bar (it needs the auction house open), the gathering-node tooltip,
`/su report` or a quest rank step. A screenshot of the bar would need an auction house scene in the harness; a
possible follow-up.
