# Brief: rarity recolour instead of an added trim (cjber/bestiary-forever, Field Guide Forever)

Approved design is already merged on `main` as commit 4604a6a: the mockups in `docs/screenshots/rarity-target.png`,
`rarity-nameplates.png` and `rarity-elite.png`, drawn by `tools/rarity.py`. Those images are the acceptance criteria.

## What changes
`UI/Rarity.lua` currently draws four addon-owned white strips outside the frame art (an added trim). Replace that with a
direct recolour of the client's own brass hardware:

- `SetDesaturated(true)` then `SetVertexColor(r, g, b)` on the client's chrome textures.
- `copper` (the default tier): restore the originals - no desaturation, no tint, no added art. A common creature must
  look exactly as the client draws it.
- `silver` (0.79, 0.83, 0.88), `gold` (0.91, 0.74, 0.39), `shiny` (0.58, 0.83, 1) - the existing `COLORS` table.
- Target frame: recolour the targeting-frame chrome textures (the nine-slice pieces of `TargetFrameTextureFrame`, and
  the portrait frame art). Never tint the health/mana bar fills.
- Nameplates: recolour the plate's trough/border texture (`frame.UnitFrame.HealthBarsContainer.healthBar.bgTexture`,
  see tweaks-forever `UI/Nameplates.lua` for the plate frame shape in this build). Never tint the fill, the name text
  or the elite dragon icon.
- Restore every texture you touched before applying a new tier, so a plate reused for another unit never keeps the old
  colour. Keep a `---@type table<Texture, {r: number, g: number, b: number, desaturated: boolean}>` of originals.
- Keep the existing trigger points: `PLAYER_TARGET_CHANGED`, `NAME_PLATE_UNIT_ADDED/REMOVED`, and the `ns.OnProgress`
  sweep. Keep the `showRarityTrim` option and `Core/Model.lua`'s `Model.Tier` bands exactly as they are.

## Rules
- Follow `AGENTS.md`: Lua 5.1, tabs, `---@type`, `L["..."]` for any new string, no new globals beyond the existing
  save/API ones, `.luacheckrc` only gains real WoW API globals.
- Prove it with a spec: extend `tests/rarity_spec.lua` (or add a UI spec against `tests/wow_mock.lua`) covering the
  tier table, the copper restore, and a second unit reusing a plate.
- Run the AGENTS.md commands: `luacheck .`, `stylua --check .`, every `tests/*_spec.lua`, `python3 tools/rarity.py`
  then `python3 tools/check_screenshots.py --record` if the images change, ruff, changelog.
- No `-s`/`--signoff`. Trailers per the shared brief. No model names in commits or PR text.
- PR against `main`, then send `READY <PR URL> <head sha>`. Do not merge.

## In-game checks for the owner (list them in the PR)
1. `/reload`, target a common creature: the frame is the client's brass, unchanged.
2. Target a silver/gold/shiny species: the chrome reads in that colour with its highlights intact, bars unscathed.
3. Target a nameplate of each tier in a pull: only the plate's rim changes.
4. `/fg` > untick "Show creature rarity trim": everything returns to the client's brass.
