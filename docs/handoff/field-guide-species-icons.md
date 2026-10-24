# Field Guide Forever: real creature icons instead of INV_Misc_Bone_01

Repo: cjber/bestiary-forever. Interface 16001, WoW: Forever.
Raised by Cillian 2026-10-22 after seeing the README on GitHub: every creature row and the detail
portrait still show the generic bone placeholder.

## What is actually wrong (verified on main at 28ea487)

- `docs/screenshots/field-guide.png` (Badlands / Siege Golem) renders `interface/icons/inv_misc_bone_01.blp`
  for every row in the creature list and for the detail portrait. Cropped at full resolution and inspected:
  three identical femur glyphs in the list, one in the portrait. `chaosbolt`/`fireshield`-style art is absent.
- The renderer falls back to that glyph because every mock species carries `family = "Unknown"`
  (`tools/mockups.py`, `species_icon()` → `FAMILY_ICONS.get(species["family"], FALLBACK_ICON)`,
  `FALLBACK_ICON = "interface/icons/inv_misc_bone_01.blp"`).
- The family comes from the disposable fixture's 6th column, which is QuestieDB's **`subName`** — the NPC's
  title or occupation, not a creature family. Measured over the pinned fixture (13,391 rows): 10,279 have it
  empty, and the non-empty values are "Innkeeper" (59), "Stable Master" (54), "The Argent Dawn" (53),
  "Warrior Trainer" (42), "Banker" (41). Nothing there is a creature family.
- The runtime addon has the same gap and is **not** consistent with the mock:
  `Integrations/QuestieDB.lua` sets `family = row.subName` (or "Unknown"), and `UI/Art.lua` `Art.FamilyIcon`
  falls back to `INV_Misc_QuestionMark` while the mock falls back to the bone. So the screenshots are wrong
  *and* they lie about what the addon draws.
- QuestieDB Forever exposes no creature type or family at all. Its NPC fields are: name, minLevelHealth,
  maxLevelHealth, minLevel, maxLevel, rank, spawns, waypoints, zoneID, questStarts, questEnds, factionID,
  friendlyToFaction, subName, npcFlags. Do not try to infer family from any of these.

## Where the authentic data is

The repo already generates `Data/Client.lua` from pinned wago.tools DB2 exports for build 1.60.1.70450
through `tools/gen_zones.py` + `tools/forever_tools/wago.py`, gated by `tools/check_generated.py`.
`TABLES` there already pulls `CreatureFamily` (ID, Name_lang) and `CreatureDisplayInfo`
(ID, PortraitTextureFileDataID), and the output has `ns.ClientData.families` (27 named families: Wolf, Cat,
Spider, Bear, Boar, Crocolisk, Carrion Bird, Crab, Gorilla, Raptor, Tallstrider, ...) plus
`ns.ClientData.portraits`.

What is missing is the npcID → creature type/family edge, which lives in the client's `CreatureTemplate` DB2.
Add it to `TABLES` in the same generated, pinned, checked-in way — no hand-written creature data.

Note: a first attempt with columns `("ID", "family", "type")` returned **HTTP 400** from wago.tools.
Resolve the exact column names for this build first (list the table's schema) rather than guessing; the
1.60.1 schema does not use those bare names.

Then map the resolved values onto the icons that already exist:
- creature type → the type bucket Art/FAMILY_ICONS already has (Beast, Dragonkin, Demon, Elemental, Giant,
  Undead, Humanoid, Critter, Mechanical, Aberration);
- `familyID` → the named family icons (Wolf, Cat, Spider, Bear, Boar, Crocolisk, Tallstrider, Raptor, ...).
Keep the existing name-keyword rules as the refinement on top, and keep the family lookup as the fallback.

## Size guard

`CreatureTemplate` is large. Do not ship a 200k-entry table. Store only the NPC ids the addon can meet —
non-zero type or family — encoded compactly in one generated module, and report the packaged size delta.
`.pkgmeta` already keeps `tools/` out of the package.

## Acceptance criteria

1. Siege Golem shows Mechanical art, Chicken hatches out of the bone glyph, Stonevault Rockchewer shows a
   beast glyph, Jarkal Mossmeld shows a humanoid one, in both the list and the detail portrait.
2. `INV_Misc_Bone_01` and `INV_Misc_QuestionMark` appear in **no** README screenshot.
3. Addon and mock resolve the icon through the same generated data — `Art.SpeciesIcon` and the mock's
   `species_icon` must not disagree on the fallback any more.
4. Specs: one for the generated mapping lookup, one for icon resolution across Beast / Humanoid / Mechanical /
   unmatched.
5. Re-render `docs/screenshots/` and `demo.gif`, restamp `scenes.sha256` with `tools/check_screenshots.py --record`.
6. Full local suite green: luacheck, stylua, every `tests/*_spec.lua` under luajit, ruff check + format,
   `check_generated.py`, `visual_audit.py`, `check_screenshots.py`, `changelog.py --check`,
   `.sift/gate.py --base origin/main`, `.sift/agents.py check`.
7. Open every README image and inspect it at full resolution before handoff, and step the GIF frames — the
   earlier rounds passed every automated check while the bone glyphs were plainly visible.
8. CHANGELOG entry under Unreleased. Commit without `-s`. Open a PR to main; do not merge it.

## Do not

- Do not rename the project or its tabs, do not rewrite `AGENTS.md` beyond what the icon work needs, and do
  not touch unrelated files. A previous round drifted into a rename and had to be reverted.
- Do not hand-edit a PNG; fix the renderer or the generated data and re-render.
