# Tweaks Forever 0.12.0: store plan

CurseForge project 1708506 (authors.curseforge.com/#/projects/1708506) and Wago ZKxOWd6k
(addons.wago.io/developers/projects/ZKxOWd6k). The packager uploads the file and notes. Everything
below is done by hand, after the v0.12.0 release run is green and the release PR (#189) is on main.

## Summary (both stores, unchanged)

Small quality-of-life automations and fixes that extend the default UI, stepping aside where another addon already does the job.

This is the TOC `## Notes`. If the store summary already says this, leave it.

## Description (both stores)

Paste `docs/curseforge.md` from main at the release commit, in full. On CurseForge, type cjber's footer at the end
of the textarea so React registers the change:

    Made by Cillian Berragan · [cillian.dev](https://cillian.dev/) · [GitHub](https://github.com/cjber) · [Twitter](https://twitter.com/cjberragan)

What changed since the 0.11.5 paste:
- Vendors: adds "Hold Shift as a merchant opens to skip both." (#184)
- Maps: the blue tint is now "on the world and zone maps" (#185). Dropped "; click one to travel there". The Shortest Path line below still says it.
- Quests and camps: adds quest levels in quest dialogs (#180) and keys for your nearest quest's item and target (#188).
- New bullet, **Levelling**: XP per hour and time to level, plus optional rare alerts (#186, #187).
- Shorter: the sparkles bullet, the Automation line ("All off by default."), the intro's second sentence, the
  Legacy/SkillUp/Adventure Guide lines, "All optional:", and the translations and "Bug reports and ideas are welcome" lines.
  This brings the copy back under the 600-word limit (597 words of prose).

`check_copy.py docs/curseforge.md README.md` passes on the release branch.

## Logo (unchanged)

`media/icon-400.png` (400x400). The icon hasn't changed, so leave it.

## Gallery (both stores), in this order

| # | File (docs/screenshots/) | Upload as | Caption |
|---|---|---|---|
| 1 | demo.gif | demo.gif (1.4 MB) | Dungeon entrances on the map, nameplates, and the junk coin in your bags. |
| 2 | dungeonmap.png | gallery/dungeonmap.jpg | Inside a dungeon the map opens on its own floor, with the legend beside it and a button for each floor. |
| 3 | dungeons.png | gallery/dungeons.jpg | Every dungeon and raid entrance, with retail's icons. Blackrock Mountain lists all four. |
| 4 | nameplates.png | nameplates.png | Nameplates in retail's own frame, with your target outlined and a quest icon on what you still need. |
| 5 | tooltips.png | tooltips.png | Unit tooltips with the health bar inside, in the retail game's own bar and frame. |
| 6 | editmode.png | editmode.png | Move and scale Blizzard windows from a tab in Edit Mode. |
| 7 | zonelevels.png | gallery/zonelevels.jpg | Each zone's level range on the world map, coloured like quest levels, with your and the cursor's coordinates. |
| 8 | exploration.png | gallery/exploration.jpg | Reveal unexplored areas: what you haven't found yet is tinted blue. |
| 9 | gear.png | gear.png | A bag item's gear groups, named in its tooltip in their colours. |
| 10 | menu.png | menu.png | Ctrl+Right-click a bag item to put it in a gear group. |
| 11 | junk.png | junk.png | Alt+Right-click marks an item as junk; it sells with your greys. |
| 12 | spellreach.png | spellreach.png | Spell reach icons on enemy nameplates: full colour in reach, red out of it. |
| 13 | quests.png | quests.png | Abandon quests: pick the ones to drop, with one confirmation. |
| 14 | camp.png | camp.png | The Campfire Nearby buff says where the fire is and what each benefit is doing for you. |
| 15 | campsite.png | campsite.png | A camp's tooltip says what sitting nearby gives you. |

CurseForge refuses images of 2 MB or more. Four PNGs are larger (dungeons 2.8 MB, zonelevels 2.8 MB, exploration
2.5 MB, dungeonmap 1.3 MB). JPEGs at quality 90 of all four are ready in
`/tmp/claude-0/-home-user/76bf530e-5da5-583c-877f-df32f2ad82fa/scratchpad/release/tweaks-gallery/`. Upload those
on both stores so the two galleries match. Everything else goes up as the committed file.
On Wago, upload in reverse order (campsite.png first, demo.gif last), because Wago shows the newest first.

## Stale images to remove

Since v0.11.5, four images were re-rendered. Each world map scene now shows the coordinates line that 0.12.0
turns on by default: demo.gif, dungeons.png, zonelevels.png and exploration.png. The other eleven are
byte-identical to the 0.11.5 files.

- **Replace** the gallery entries for those four with the new files. Wago's edit page can't swap an image, so upload
  the new one first, then delete the old one.
- **Keep** the entries for the other eleven if they're already there with these captions. Fix a caption in place if it differs.
- Delete any duplicate, or any older entry that isn't in the fifteen-image list above.

## Not in the gallery yet

No scene exists yet for the 0.12.0 additions that aren't on the map: the XP per hour tooltip, the best-reward coin,
the `/tweaks report` window, quest levels in dialogs and the item/object quest tooltips. One image each would
be a follow-up PR (wow-mock-screenshots), not part of this release.
