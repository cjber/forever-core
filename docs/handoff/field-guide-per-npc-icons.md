# Field Guide Forever: per-NPC species icons from each NPC's real model

Repo: cjber/bestiary-forever. Interface 16001, WoW: Forever. Branch off current `main`.
Raised by Cillian 2026-10-22: "let's see how varied we can go, as much as possible. Ideally just
directly using the actual image that shows per NPC."

## The one hard constraint, measured (do not try to work around it)

**This client ships no per-NPC 2D portrait bitmaps.** Measured on the pinned build's
`CreatureDisplayInfo-1.60.1.70450.csv`: of **14,218** display rows, `PortraitTextureFileDataID` is
non-zero in **96** and `PortraitCreatureDisplayInfoID` in **4**. So there is no "exact picture of
NPC 12345" to fetch, and `Data/Client.lua`'s `ns.ClientData.portraits` is 14,122 zeros.

`CreatureTemplate` returns **HTTP 400** on wago.tools for this build; `Creature` exists but holds only
184 rows; `NPCFaction` is 400. Do not build on any of those.

## What is actually available, and it is much better than the current 13 buckets

Every NPC's **real 3D model** is reachable, and a model is a far finer identity than a creature type:

```
CMaNGOS creature_template.ModelId1        (already cached: tools/.cache/ClassicDB_1_12_1_z2815.sql.gz)
  -> client CreatureDisplayInfo.ID          (ModelId1 IS the display id; measured 99.9% overlap,
                                            7,690 of 7,701 distinct modelids land in the client table)
  -> CreatureDisplayInfo.ModelID            (cached: CreatureDisplayInfo-1.60.1.70450.csv)
  -> CreatureModelData.FileDataID           (NEW pinned source: wago.tools db2/CreatureModelData, HTTP 200)
  -> listfile path, e.g. creature/kobold2/kobold2.m2   (NEW pinned source, see below)
```

Measured coverage against the pinned QuestieDB catalogue of **13,391** NPCs:

- **10,118** resolve all the way to a model path (**75.6%**).
- **367** distinct model stems.
- Humanoids currently share **one** bearded head; their real models are **130 distinct** stems:
  `humanmale_hd` 1087, `dwarfmale_hd` 658, `orcmale_hd` 581, `nightelffemale_hd` 371,
  `humanfemale_hd` 346, `scourgemale_hd` 311, `trollmale_hd` 307, `nightelfmale_hd` 291,
  `taurenmale_hd` 284, `goblinmale` 256, `ogre` 103, `murloc` 102, `satyr` 86, `furbolg` 84, `kobold` 55, ...
- This is the variety win. A Dwarf is a dwarf, an Ogre is an ogre, a Murloc is a murloc.

## Pinned sources to add

1. `CreatureModelData` — `https://wago.tools/db2/CreatureModelData/csv?build=1.60.1.70450` (HTTP 200, ~217 KB).
2. Listfile — `https://github.com/wowdev/wow-listfile/releases/latest/download/community-listfile.csv`,
   **pin the release tag `202610202236`**, not `latest`. It is 153 MB, so:
   - **filter on download** to lines whose path ends `.m2` and starts `creature/`, cache only that
     subset as compact JSON in `tools/.cache/` (gitignored, like the CMaNGOS dump), and record the
     source tag plus a sha256 of the full download exactly as `CMANGOS_SHA256` is recorded.
   - never commit the listfile or the subset.
3. If a pinned listfile cannot be reached, the generator must fail loudly — do not silently drop to
   type/family-only, which is the state we are leaving.

## Icon selection: one source of truth, generated

Replace the stretched-out rule tables with a single ordered **stem -> icon** table held in
`tools/gen_creature_icons.py`. The generator resolves each NPC to its icon and writes the result into
`Data/CreatureIcons.lua`; `UI/Art.lua` and `tools/mockups.py` both read that generated data. This is
deliberate: the last two rounds shipped addon and mock resolving differently, and the mock showed art
the addon would never draw. Do not duplicate the stem rules into the mock.

Budget the icon set for **maximum distinct art**. Verified present in this build (79 of 81 candidates
I probed; `spell_fire_bolt` and `spell_nature_strengthofearthtotem` are **absent** — do not use them):

- Heads/races: `inv_misc_head_human_01/02`, `dwarf_01/02`, `orc_01/02`, `troll_01/02`, `tauren_01/02`,
  `elf_01/02`, `gnome_01/02`, `undead_01/02`, `scourge_01`, `murloc_01`, `kobold_01`, `gnoll_01`,
  `centaur_01`, `quillboar_01`, `nerubian_01`, `tuskarr`, `vrykul`, `clockworkgnome_01`, `tiger_01`;
  dragons by colour: `inv_misc_head_dragon_black/blue/bronze/green/red` plus `_01`.
- Pets: `ability_hunter_pet_{cat,wolf,bear,boar,spider,raptor,crocolisk,turtle,scorpid,bat,hyena,
  tallstrider,gorilla,crab,silithid,worm,wasp,vulture,windserpent,owl,moth,chimera,rhino,devilsaur,
  corehound,dragonhawk,ravager,warpstalker,sporebat}`.
- Demons: `spell_shadow_metamorphosis`. Undead: `spell_shadow_raisedead`.
- Elementals by kind: `spell_fire_immolation`, `spell_frost_summonwaterelemental`,
  `spell_nature_lightning`, `spell_nature_earthquake`.
- Constructs/mechanical: `inv_misc_gear_01`. Giants: `ability_warrior_savageblow`.
  Ooze/aberration: `ability_creature_poison_01`.
- Mounts: `ability_mount_{ridinghorse,gryphon_01,wyvern_01,kodo_01,raptor,mechastrider,warhippogryph}`.
- Naga: `inv_misc_nagamale` (verified present; `inv_misc_head_naga` is not).
- **Verified absent — do not reference:** `inv_misc_head_{goblin,ogre,harpy,satyr,wendigo,basilisk,naga,troglodyte,
  yeti,gorilla,wolf,bear}`, `ability_hunter_pet_dryad`, `spell_fire_bolt`,
  `spell_nature_strengthofearthtotem`. Goblin/ogre/troglodyte/wendigo/harpy/satyr therefore fall back
  to a type icon unless another authentic fit exists — that is acceptable, a wrong head is worse than
  a neutral one.
- **Any icon path you emit must be checked against the pinned listfile at generation time and the
  generator must fail if one is missing.** No placeholder may ever ship.

My first-pass rules already cover 9,014 of the 10,118 resolvable NPCs with 39 distinct icons; push the
table to cover the remaining stems. Largest uncovered stems, all real art available:
`invisiblestalker` 146 (no art — leave to type fallback), `satyr`, `troglodyte`, `harpy`, `nagamale`,
`siren`, `basilisk`, `wendigo`, `lostone`, `lobstrok`, `thunderlizard`, `kodobeast`, `gryphon`,
`wyvern`, `lasher`, `wisp`, `forceofnature`, `hippogryph`, `ridinghorse`, `salamandermale`, `dryad`,
`gargoyle`, `keeperofthegrove`, `frenzy`, `bogbeast`, `slime`, `ghost`, `skeleton`.

## Resolution order (addon and mock, identical)

1. generated per-NPC model icon (the real creature),
2. the existing name-keyword refinement in `Art.SPECIES_ICONS` (keep it; it is good),
3. creature family icon,
4. creature type icon,
5. `Art.GENERIC_CREATURE_ICON`.

## Size

Pack the icon index into the same integer as type/family so one line per NPC is kept, e.g.
`packed = iconIndex * 1048576 + type * 65536 + family` (type max 11, family max 27, iconIndex well
under 256). Report the packaged size delta against the current 194,344-byte `Data/CreatureIcons.lua`;
raise `MAX_PACKAGED_BYTES`/`MAX_RECORDS` only with the measured number in the comment. Keep `Get`
backwards-compatible for type/family callers.

## Acceptance criteria

1. At least **8 distinct races** of humanoid render with distinct art in the README (human, dwarf, orc,
   troll, tauren, night elf, gnome, scourge at minimum), plus ogre, murloc, kobold as themselves.
2. A spec asserts icon resolution for: a human NPC, a dwarf NPC, an orc NPC, a murloc, a kobold, a
   mechanical, and an unmapped NPC — driven by real npcIDs.
3. A spec asserts `Data/CreatureIcons.lua` is byte-stable and that every icon path in it exists in the
   pinned listfile.
4. `INV_Misc_Bone_01` and `INV_Misc_QuestionMark` appear in **no** README screenshot.
5. Re-render `docs/screenshots/` and `demo.gif`; `tools/check_screenshots.py --record`.
6. Full local suite green: luacheck, stylua, every `tests/*_spec.lua` under luajit, ruff check +
   format, `check_generated.py`, `visual_audit.py`, `check_screenshots.py`, `changelog.py --check`,
   `.sift/gate.py --base origin/main`, `.sift/agents.py check`.
7. Open every README image at full resolution and inspect it, and step the GIF frames. Automated gates
   passed in earlier rounds while placeholder glyphs were plainly visible.
8. CHANGELOG under Unreleased. Commit **without `-s`**. PR to main, do not merge it.

## Do not

- Do not rename the project or its tabs; do not rewrite `AGENTS.md` beyond what this needs.
- Do not hand-edit a PNG. Fix the generator and re-render.
- Do not add a network dependency to CI: generation is cached/offline, exactly like `gen_zones.py`.

## Out of scope here — propose, do not build

The genuinely literal "actual image per NPC" in-game is a `PlayerModel` widget driven by
`PlayerModel:SetCreature(creatureDisplayID)` in the detail pane: it renders the real 3D model, and we
can resolve a displayID for 10,118 of 13,391 NPCs. That is the truest answer to Cillian's ask, but it
needs a live client to verify and the Python mock cannot render 3D, so shipping it now would put the
addon and the README out of step again — the exact fault we are fixing. Note it at the end of the PR
description as a follow-up; build the 2D icon work above.
