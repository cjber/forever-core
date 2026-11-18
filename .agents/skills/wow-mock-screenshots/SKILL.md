---
name: wow-mock-screenshots
description: "Renders mock README and store screenshots for a WoW addon from the client's own art, fonts and wago.tools data with the suite renderer (tools/wowmock). Use when screenshots are missing or stale after a UI change and no in-game capture is wanted."
---

# Mock WoW screenshots from the game's own art

Screenshots taken in game go stale with every UI change and need someone at the keyboard. This skill
renders them instead: the same atlases, textures, fonts, item icons and colours the client uses, laid out
with the numbers from Blizzard's own XML/Lua, and the addon's own drawing reproduced from its source. A
render is evidence only for the state and rendering paths it actually reproduces. Compare native frames
against client captures before using them in README/store galleries; label model composites and AI concepts as previews, not in-game captures.

Never launch, focus or send input to the game client to do this.

## Pieces

| Piece | Where |
|---|---|
| Suite renderer | `tools/wowmock/wowmock.py` in this repo (README beside it); an addon's loader finds it through `FOREVER_CORE` |
| Gotchas: endpoints, BLP quirks, atlas choice, colours, fonts, widget numbers | `tools/wowmock/NOTES.md` - read before adding a widget |
| Per-addon scenes | The repo's existing `tools/screenshots.py` or `tools/mockups.py`; read its loader before running |
| Output | `docs/screenshots/*.png`, referenced from `README.md` and `docs/curseforge.md` |
| Cache | `~/.cache/wowmock/<build>/` (DB2 CSVs, files by fdid, path lookups) |
| Blizzard UI source for layout numbers | `~/drive/proj/wow/wow-handoff/blizzard-ui/Interface/AddOns` |

Use Python 3 and Pillow 12 or newer, respecting the repo's exact Pillow pin. If no pin exists, check Core's renderer requirements
before rendering and record the version used. Read `wow-retail-ui-style` (`../wow-retail-ui-style/SKILL.md`),
`docs/asset-registry.md` and `docs/ui-composition.md` before choosing art or placing widgets. Core owns the
suite renderer and composition contract; this skill owns the screenshot workflow.

The suite scene loaders default to a sibling `forever-core` checkout and import
`tools/wowmock/wowmock.py` from it. In a worktree, set the override explicitly:

```sh
FOREVER_CORE=/path/to/forever-core python3 tools/mockups.py
```

Use the repo's actual scene-script name. A missing renderer is an actionable setup error, not a
reason to fall back to a divergent copy. Existing non-suite `$WOWMOCK` loaders keep their documented
legacy setup; this suite contract does not migrate them.

## Workflow

1. **Lock the composition** before implementing a redesign: compare the complete native host and a current
   suite reference at the same scale. Show one coherent owner-reviewed panel with frame, borders, correctly
   facing tabs, cropped icons and content density. An AI concept establishes direction only. Record each
   template, host edge, resolved atlas/file/set, texcoords, border owner and draw layer per Core's composition
   contract. Check source icons at native resolution for baked bevels before adding any frame.
2. **Pick the scenes** from what the README says the addon does: one image per headline feature, showing the
   addon's own UI in the context a player sees it (a bag, a tooltip, a menu, a map, a tracker). Plain dark
   backdrop from `scene()`; never fake a 3D world.
3. **Read the addon's source** for exactly what it draws: textures, sizes, anchors, colours, text, order of
   menu entries. The mock reproduces the code, not the feature description.
4. **Read Blizzard's source** for the frames around it (XML sizes/anchors, NineSliceLayouts, font objects).
   Where a number is engine-side and not in the source, pick it by comparison with a real screenshot and
   record scene-specific assumptions in the addon scene source; reusable renderer findings belong in Core's `tools/wowmock/NOTES.md`.
5. **Use real data**: real item IDs present in the Forever build's ItemSparse, real names, real icons, real
   stats. Choose content a player of that level would actually carry. Don't invent items, quests or NPCs.
6. **Build the scene** in the repo's existing scene script with wowmock widgets. A widget only that addon draws stays
   in the repo script; anything another addon could reuse goes into Core's renderer, documented in its header,
   with what you learned added to Core's `tools/wowmock/NOTES.md`.
7. **Verify**: view each PNG with Read, then crop and enlarge regions side by side with a real in-game
   screenshot of the same kind of frame (the list is in Core's `tools/wowmock/NOTES.md`) and compare borders, colours,
   text size and baseline, spacing. Iterate until they match. State in the report any place the mock
   still deviates from the real UI. Inspect icons and borders enlarged: a correct asset name can still
   contain a baked old frame. Verify all four picture edges and the tab's open edge against its owning
   surface. Geometry and freshness checks do not establish native composition.
8. **Reproducibility**: running the repo's scene script twice must give byte-identical PNGs.
9. **Animated demo** (`docs/screenshots/demo.gif`) when a headline feature is about motion or time: a
   route settling, a countdown, a sort reordering. Render the frames from the same scene builders
   rather than screen-recording; `render_demo` in shortest-path-forever's `tools/screenshots.py` is the
   template. Render each frame at the GIF's final size (thin strokes and dashes do not survive a
   downscale), quantize every frame to one shared palette built from the first frame plus an enlarged
   crop of the small UI, with no dither, then save with `duration=100, loop=0, optimize=True`. That
   keeps text colours stable, repeated encodes byte-identical and the file under the stores' 2 MB limit.
   Six to ten seconds is enough. It leads the store gallery when it exists.
10. **Ship**: images, the script and the README/store references in the addon repo's PR, whose body shows every
   image; renderer and notes changes in a forever-core PR; changes to this workflow in this skill.

## Rules

- Always pass the build to wago.tools file downloads (`&build=`); without it you get retail art.
- Forever's own art (atlas set 1, "c60") wins where it exists; Core's `tools/wowmock/NOTES.md` explains the selection rule and
  the tooltip-centre case that proves it.
- Don't draw a mouse cursor. Place hover tooltips and menus where the client anchors them.
- Keep scenes honest: show what the addon does today, with the defaults a new player gets unless the
  image is about an option.
- Put every bar, meter and count at 0 in at least one scene. The client takes a width of 0 as unset, so a
  left-anchored fill set to 0 draws at its art's full width; the layout pass does the same, but only a
  scene with an empty state shows it.
- Keep the UI art pin separate from data-export pins. Change Core's renderer pin only with verified client
  evidence, then regenerate affected renders. A newer data export does not authorize changing UI art.
- Present a focused mobile-readable mock. Link its image on the effort's pushed GitHub branch, preferably
  at its commit SHA; do not upload to a new third-party host. Also open each generated preview with `xdg-open` when the owner's workflow requires it. Publish only the selected lockup in `docs/previews/` as the proposal, never in a store gallery.
