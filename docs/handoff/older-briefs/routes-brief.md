# Round 5: community routes in Adventure Guide (owner request 2026-10-17)

Owner: "support community routes in adventure guide, see how Polestar does it. Not only RXP support but any route
someone might want. Maybe pair with Polestar as a dep?"

brief.md and release-brief.md apply. That includes the WFA-33 credit rule, translations at release (WFA-34 and WFA-16),
signed commits and the coordinator merging.

## What Polestar has (read from fitzforge/polestar at 2e90286, GPL-3.0; read only, copy no code)
- **Guide packs:** any author writes plain-text `.guide` files. Polestar's toolchain compiles them into a separate addon
  that calls `Polestar.RegisterPack{...}` and `Polestar.RegisterGuide{...}` (docs/PACK_FORMAT.md, GUIDE_PACKS.md,
  GUIDE_FORMAT.md). Each guide is `{ id, pack, title, faction, races, classes, minLevel, maxLevel, category, zone, next,
  steps = { { title, note, only, goals = { { t = "accept"|"turnin"|"kill"|"collect"|"goto"|..., quest, npc, map, x, y,
  ... } } } } }`, with x and y in the 0-100 range.
- **Read side** (docs/ARCHITECTURE.md, "The guide registry" and "Engine"):
  - `Polestar.Guides.Packs()`, `Pack(id)`, `PackShown(id)`, `List()`, `Get(id)`, `Suggestions()`, `Suggest()`.
  - `Polestar.Engine.GetGuide()`, `SetGuide(id)`, `GetStepIndex()`, `GetStepView(i)`, `GetLiveStep()`, `Skip()`,
    `GetWaypoint()`, `GetProgress()`.
  - The message bus `Polestar.On(msg, fn)` / `Off`, with GUIDES_REGISTERED, PACKS_CHANGED, GUIDE_CHANGED,
    STEP_CHANGED, STEP_UPDATED, WAYPOINT_CHANGED and GUIDE_COMPLETED.
  - Only `Polestar.Nav.API` is explicitly labelled "public, for other addons", with a version number. The Guides and
    Engine surface is documented but has no version, so it may move.
- Polestar already hands travel off to Shortest Path Forever (Nav/Handoff.lua) and uses code adapted from SPF with
  permission. Fitz is friendly and may use our code.

## Design (coordinator decision)
Adventure Guide gets **route sources**. One internal provider interface, with RestedXP moved onto it, plus a Polestar
provider. AGF stays the front end: journey cards, steps, tracker section and map pins, with SPF for travel.
1. **A provider interface** (internal, in AGF): `id`, `title`, `Available()`, `List()` (guides with title, level range,
   faction or race fit, author, pack and licence), `Start(id)`, `Current()`, `StepView()`, `Skip()`, plus change
   events. Move the existing RestedXP integration onto it with no behaviour change, covered by its specs.
2. **A Polestar provider** (optional dependency `Polestar`). Feature-detect every call; never require Polestar.
   - **Where guides come from:** list Polestar's guides and every shown community pack, with the author, pack and
     licence on each.
   - **Following a guide:** Polestar's Engine decides step completion. AGF reads the step view and draws it in its own
     UI, and routes travel through SPF.
   - **Starting a guide:** an AGF card for a Polestar guide calls `Polestar.Engine.SetGuide(id)`.
   - **Display ownership:** a one-time prompt, the same pattern as RestedXP: "keep Polestar's window, or follow its
     guides in Adventure Guide". There is a setting to switch later. Never show both guide windows or both arrows
     fighting: when AGF owns display, rely on Polestar's own options or documented hooks to quiet its window and
     arrow, and if there's no clean way, say so and leave Polestar's UI alone.
   - **Contract spec:** stub Polestar's documented API at a pinned SHA, the way AGF pins SPF_SHA in
     tests/contract_spec.lua, so a Polestar API change is caught in review.
3. **Credits:** "Community routes come from Polestar guide packs; each guide shows its author." Each pack's author
   and licence show in AGF's UI. No pack content is bundled.
4. **Not in this round:** AGF's own authoring format. Polestar's toolchain already gives authors a compiler, lint and
   playtest; pointing authors there is better than a second format. Say this in the README.
5. **Visibility:** in the README and store copy, a short "Community routes (with Polestar)" bullet; add Polestar to
   OptionalDeps.

## Outward
Draft (don't post) an issue for the owner to open on fitzforge/polestar. It asks Fitz to declare the Guides and Engine
read API, and the message names above, public and versioned (like `Nav.API.version`), and lists exactly which calls AGF
uses. Put it in the scratchpad.

## Done means
Specs for the provider interface, the RestedXP regression and the Polestar provider (stubbed), plus the full gate,
translations for any new phrases (all 9 locales, check_locales --release), code-review (high), PR(s) with in-game checks,
then release prep for AGF 0.17.0.
