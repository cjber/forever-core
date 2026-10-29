# WoW: Forever mock migration

## Goal

Every addon README scene is rendered with the shared `tools/wowmock/wowmock.py` from `cjber/forever-core`, selected through `FOREVER_CORE`. Addon scene scripts retain ownership of feature data and composition; Core owns WoW client art decoding, asset lookup and reusable widgets. Do not copy the renderer into consumers or keep a second private renderer.

## Consumers and scope

One PR per consumer repository: Adventure Guide, Legacy, Shortest Path, SkillUp, Tweaks, Field Guide (the `field-guide-forever` checkout), Hoard and Atlas. Each PR must point all screenshot imports at `$FOREVER_CORE/tools/wowmock`, remove private renderer copies and stale `WOWMOCK` instructions, render README scenes for every shipped user-facing feature, refresh scene hashes/manifests, and update the README gallery and local regeneration instructions. Atlas and Hoard currently have no shipped window, so their README must say no feature mock is applicable until a player-facing surface ships; do not fabricate a UI.

## Shared renderer correction

Blizzard MenuStyle1 uses `common-dropdown-bg` at alpha 0.925. Its atlas center is translucent, so compositing alone lets underlying rows show through. The offline composite must model the effective opaque menu surface while retaining the stock border. Implement this in `wowmock.context_menu`, then regenerate every consumer scene that includes a context menu and inspect the output at full resolution.

## Consumer procedure

1. Set `FOREVER_CORE` to the local forever-core checkout. Import from `Path(FOREVER_CORE) / "tools" / "wowmock"`; do not fall back to a personal skill checkout.
2. Preserve addon-specific scene composition, data and feature coverage. Delete private duplicate renderer implementations after callers use shared primitives.
3. Compare README feature bullets with scenes. Every shipped UI feature must appear in at least one README scene; non-UI APIs and state-only behavior do not require invented visuals.
4. Render scenes, refresh deterministic hashes, open every README image and audit clipping, overlap, text contrast and row alignment.
5. Run the repo's full documented quality gate and screenshot freshness checks. Open one PR for that repo, wait for green CI, and record URL and head SHA.

## Completion checklist

- [ ] Shared context menu backdrop corrected and its scenes regenerated.
- [ ] Adventure Guide, Legacy, Shortest Path, SkillUp, Tweaks, Field Guide, Hoard and Atlas each migrated and reviewed.
- [ ] One green PR per consumer; record links and head SHAs below.

## PRs

| Addon | PR | Head SHA | CI |
|---|---|---|---|
| Adventure Guide | pending | pending | pending |
| Legacy | pending | pending | pending |
| Shortest Path | pending | pending | pending |
| SkillUp | pending | pending | pending |
| Tweaks | pending | pending | pending |
| Field Guide | pending | pending | pending |
| Hoard | pending | pending | pending |
| Atlas | pending | pending | pending |
