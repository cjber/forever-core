# Atlas Forever and Hoard Forever: align with the suite requirements

Owner asked for both repos to be aligned with the rest of the WoW: Forever suite on 2026-10-26. Their READMEs and
store pages now follow WFA-10, WFA-11 and WFA-32 and are merged (atlas #1, hoard #2). This brief covers the code,
CI and asset gaps that are still open. Read `.agents/skills/wow-forever-addon/SKILL.md` (the WFA pack) first.

Both repos are private and untagged. Do not tag or release them. Open one PR per repo, keep `main` green, do not use
`-s` on commits (GitHub signs).

## atlas-forever

| Gap | Requirement | What done looks like |
|---|---|---|
| No `.sift/` | WFA-15, WFA-17 | `sift setup` vendors `.sift/` and `.agents/skills/sift-project/`; add the `sift` job to `ci.yml` running `.sift/gate.py --base origin/$BASE` and `.sift/agents.py check`, and a project profile in the Atlas words. |
| No `typecheck` job | WFA-15, WFA-18 | `typecheck` job: lua-language-server against `.luarc.json`, plus `tools/typecheck.sh` running the editorconfig, family, secret, locale and `forever_tools.sync` checks where they apply. |
| `tools/forever_tools/` absent | WFA-29 | Vendor the canonical package from `.agents/skills/wow-forever-addon/tooling/forever_tools` with its `MANIFEST.json`, and reduce `tools/changelog.py`, `tools/check_package.py` and `tools/release_check.py` to thin entry points that import it. |
| No `.github/workflows/core-shared-drift.yml` | suite convention | Copy it from `tweaks-forever` unchanged. |
| No `THIRD_PARTY.md` | WFA-31 | List the client map data (read at runtime, not shipped) and, once it exists, the icon art. `tools/check_package.py` must not fail the zip for the missing file. |
| No icon | WFA-7, WFA-8, WFA-22 | Draw `media/icon.svg` from the pack's `icon-template.svg` (single gold emblem, family palette), render it with `render_icon.py`, add `## IconTexture: Interface\AddOns\AtlasForever\media\Icon` to the TOC, then restore the centred 96 px icon line at the top of `README.md` (it is deliberately absent until the file exists). |
| No addon compartment entry | WFA-3 | `## AddonCompartmentFunc` in the TOC plus the click handler, opening the settings page (which also needs building: today there is none, and `settings.showContents`, `settings.travelButton`, `settings.windowScale` and `settings.rememberLast` are saved but unused). |
| No `docs/screenshots/` | WFA-9, WFA-25 | Needs the window first. Add `tools/screenshots.py` and `docs/screenshots/scenes.sha256` when the window lands, and the `check_screenshots.py` job. |
| `.gitattributes` | WFA-20 | Add the `docs/screenshots/scenes.sha256 linguist-generated=true` line with the screenshots in the same PR. |

## hoard-forever

| Gap | Requirement | What done looks like |
|---|---|---|
| No `.sift/` | WFA-15, WFA-17 | As atlas. There is a `.agents/skills/sift-project/SKILL.md` here, but its text is a copy of Field Guide Forever's profile: rewrite it for Hoard (gate commands, the container `pcall` rule, live roots) before `sift setup`. |
| No `typecheck` job | WFA-15, WFA-18 | As atlas. |
| `tools/forever_tools/` is partial | WFA-29 | It holds 4 modules and no `MANIFEST.json`. Vendor the full package from the canonical producer and make the three tool scripts thin entry points. |
| No `.github/workflows/core-shared-drift.yml` | suite convention | Copy from `tweaks-forever`. |
| No `## IconTexture` in the TOC | WFA-8 | The icon now exists (`media/icon-400.png`, `media/Icon.tga`, rendered from `media/icon.svg`); the TOC already declares `## IconTexture`, verify it resolves to `media\Icon`. |
| `docs/screenshots/` empty | WFA-9, WFA-25 | `README.md` and `docs/curseforge.md` already reference `docs/screenshots/window.png`, so this is the first asset to produce: `tools/screenshots.py` from the `wow-mock-screenshots` pack against the real window, plus `scenes.sha256` and the `check_screenshots.py` job. |
| Guild vault not read | product claim | `Core/Snapshots.lua` reads bags, bank and reagent bank only; `Core/Settings.lua` already offers **Cache the guild vault** and the `Guild` tab filters a `guild` kind nothing produces. Either implement the vault read (`C_GuildBank.GetGuildBankItemInfo` behind `pcall`, cached per guild) or remove the setting and the tab. The docs currently say the tab stays empty. |
| No `AGENTS.md` standards declaration | WFA-17 | `AGENTS.md` was added in the docs PR; add the `## Standards` line naming the WFA pack at a full commit SHA once `.sift` can check it. |

## Suite drift found in the same sweep (fix in their own PRs)

| Repo | Drift |
|---|---|
| legacy-forever | `stylua.toml` carries an extra `syntax = "Lua51"` line the other eight copies lack. |
| adventure-guide-forever, skillup-forever | Run `ruff check tools` with no `ruff.toml`, so they lint against ruff's defaults instead of the family config. |
| bestiary-forever, legacy-forever, tweaks-forever, atlas-forever, hoard-forever | No `.gitleaks.toml`; `secrets` therefore runs gitleaks' default rules instead of the family's allowlist. |
| field-guide-forever (private) | No `docs/curseforge.md`, no `THIRD_PARTY.md`, no `typecheck` job, no rendered icon. Expected for an unpublished repo; bring it in line before it is published. |

## Gate for every PR

`stylua --check .`, `luacheck .`, every `tests/*_spec.lua` under LuaJIT, `python3 .sift/gate.py --base origin/main`,
`python3 tools/changelog.py --check`, and the packaged zip check. Say in the PR which of the WFA ids above it closes.
