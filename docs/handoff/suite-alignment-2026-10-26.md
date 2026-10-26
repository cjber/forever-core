# Suite alignment: every addon against the WFA requirements, and the code that should live in Forever Core

Owner asked on 2026-10-26 to extend the Atlas/Hoard README alignment to every addon, to find the other stale
things across the suite, and to move the logic that is duplicated between addons into Forever Core. This brief is
the whole sweep. Read it with `boundaries.md` (ownership, §5 the shared-code rule) and the WFA pack in
`.agents/skills/wow-forever-addon/SKILL.md`.

Repos in scope (all under `cjber`, addon folder in brackets, all Interface 16001, `_classic_beta_`):

| repo | folder | visibility | latest tag |
|---|---|---|---|
| forever-core | ForeverCore | public | v0.2.1 |
| adventure-guide-forever | AdventureGuideForever | public | v0.22.7 |
| field-guide-forever | FieldGuideForever | private | v0.3.2 |
| legacy-forever | LegacyForever | public | v0.12.6 |
| shortest-path-forever | ShortestPathForever | public | v1.22.7 |
| skillup-forever | SkillUpForever | public | v0.19.7 |
| tweaks-forever | TweaksForever | public | v0.15.7 |
| atlas-forever | AtlasForever | private | none |
| hoard-forever | HoardForever | private | none |

`docs/handoff/atlas-hoard-suite-alignment.md` already carries the first Atlas and Hoard gaps and is being worked
separately. Where this brief repeats one of them it is the same work, not a second PR: take the row here as the
current wording and skip it if the earlier PR already closed it.

Note the Field Guide repo is `cjber/field-guide-forever`, not `bestiary-forever`; `cjber/bestiary-forever`
redirects to it. forever-core's consumer lists name it correctly already.

## 1. Duplicated Lua logic to move into Forever Core

Ranked by how much drift it has already caused. Each one is a new file in core plus a vendored copy in every addon
that needs it, added to `VENDORED` in `tools/check_consumers.py` and `tools/sync_consumers.py` in the same PR, so
the gate exists before the copies do.

### 1.1 `Core/Text.lua` — case- and accent-insensitive matching (new)

Four addons each wrote their own. They do not agree:

| file | approach | lines |
|---|---|---|
| `hoard-forever/Core/Model.lua` | explicit accented-letter table (~45 lines) + lower | 45 |
| `adventure-guide-forever/Planning/Model.lua` | `lower():gsub("[\195\197][\128-\191]", FOLD)` byte-pair fold | 3 |
| `shortest-path-forever/Core/Way.lua` | strips `%s` and `%p` only, no accent fold | 3 |
| `tweaks-forever/Bags/Reagents.lua` | a function named `Fold`, but it folds a bag slot, not text — **rename it, it is not a duplicate** | — |

Ship `Core/Text.lua` with `ns.Text.Fold(text)` (accent fold + lower, returns a string) and
`ns.Text.Rank(folded, query)` for the exact/prefix/word-prefix/substring ordering Hoard and Adventure Guide both
implement. Spec it in `tests/text_spec.lua` with the accented cases each addon currently gets wrong or right.
Then: Hoard, Adventure Guide and Shortest Path read it and delete their copies. Tweaks' `Fold` is local naming
only; leave the behaviour, rename the local to `FoldSlot` so the name stops colliding.

### 1.2 `UI/SettingsPage.lua` — the settings canvas every addon hand-builds (new)

`field-guide-forever/Core/Settings.lua` (118 lines) and `hoard-forever/Core/Settings.lua` (45 lines) both hand-roll
the same thing: a `CheckButton` helper that creates the template, a `GameFontNormal` label, an optional
`tooltipText`, and an `OnClick` that writes through a getter/setter; then `Settings.RegisterCanvasLayoutCategory` +
`Settings.RegisterAddOnCategory`. The five older addons each carry their own `UI/Settings.lua`
(five different hashes) with the same shape again.

Ship `UI/SettingsPage.lua`: `ns.SettingsPage.Register(name, build)` plus `AddCheck`, `AddSlider`, `AddDropdown`,
`AddButton`, all reading strings through `ns.L`. It holds no addon's options, only the chrome — boundaries §5 keeps
each addon's settings page its own. Spec in `tests/settings_page_spec.lua` against the mock's `Settings` stub.
Consumers: all eight addons; each keeps its own rows and its own `ns.L` keys.

### 1.3 The vendored core files the three new addons never got

This is not new logic, it is the §5 files missing or stale. Current state, byte-checked against core `main`:

| file | field-guide | atlas | hoard |
|---|---|---|---|
| `Core/SafeCall.lua` | **stale** (own older copy) | **stale** (own older copy) | **missing** |
| `UI/Report.lua` | missing | missing | missing |
| `tests/report_spec.lua` | missing | missing | missing |
| `UI/ForeverFamily.lua` | missing | missing | missing |
| `tests/forever_family_spec.lua` | missing | missing | missing |
| `Core/MicroButton.lua` | current | — | — |
| tracker files | n/a (no column) | n/a | n/a |

Do it the §5 way: nothing changes in core; run `tools/sync_consumers.py` against each checkout and open one PR per
repo. Both stale `SafeCall.lua` copies predate the current comment and the `MAX_ERRORS = 5` cap, so replacing them
changes behaviour — say so in each PR and in the CHANGELOG. `UI/Report.lua` brings `/report`; each addon supplies
`ns.ReportLines` and its own `ns.Art`, so the new repos need those two small pieces before `/report` will print.

### 1.4 The Python wrappers are nine hand-edited copies of the same thing

`tools/changelog.py`, `tools/check_package.py`, `tools/release_check.py`, `tools/check_locales.py`,
`tools/check_editorconfig.py`, `tools/lint_secret.py`, `tools/check_copy.py`, `tools/check_family.py` are thin
wrappers over `forever_tools`. `check_package.py` alone exists in nine different versions (19, 19, 23, 29, 32, 33,
33, 42, 73 lines). `check_locales.py` and `check_editorconfig.py` are already identical everywhere — those two are
the shape the rest should take.

Add `forever_tools/wrappers.py` with one emitter per wrapper and a `python3 -m forever_tools.wrappers --check`
mode, then generate all eight into every repo so each is byte-identical. Keep the per-repo differences that are
data (a repo's own ignore list) in the repo's config, not in the wrapper.

## 2. Stale and missing suite files, per repo

Evidence is the file's absence or a differing hash against the canonical copy this table names.

### 2.1 field-guide-forever — the furthest behind

- **`media/` does not exist at all** while `FieldGuideForever.toc:7` declares
  `## IconTexture: Interface\AddOns\FieldGuideForever\media\Icon`. The packaged addon asks for an icon it does not
  ship; WFA-7/WFA-8 want `media/icon.svg` rendered to `icon-400.png` + `Icon.tga` by `render_icon.py`.
- No `.gitleaks.toml` (the `secrets` job runs gitleaks with the default config only).
- No `THIRD_PARTY.md` (WFA-31).
- No `docs/curseforge.md` (WFA-11).
- No `Locales/phrases.txt`, no `tools/check_locales.py`, and only `Locales/enUS.lua` — WFA-34 asks for deDE, esES,
  esMX, frFR, itIT, koKR, ptBR, ruRU, zhCN, zhTW, less any the client lacks. The five published addons all ship
  10 locale files; check whether the client offers itIT.
- `tools/forever_tools/` holds 4 of the 23 files and no `MANIFEST.json` — the vendored package is not installed,
  only four modules were copied by hand.
- `README.md` is not WFA-10 shape: it opens `# Field Guide Forever` with no centred icon, no badges, no family
  block. Rewrite it in the same shape as Atlas and Hoard.
- `.sift/` has no `ledger/` or `reports/` directories; the other five have them.

### 2.2 atlas-forever

- `tools/forever_tools/` is current except `editorconfig.py` and `sync.py` (2 of 23 differ from canonical).
- `Locales/` has `enUS.lua` + `phrases.txt` only; no other locale files (WFA-34).
- No `docs/screenshots/` and no capture tooling (WFA-9).
- `.sift/` has `sgconfig.yml` + `scripts/` but no `script-tests/`, `ledger/` or `reports/` (skillup is the same).
- No `refresh-data.yml` / `retry-refresh.yml`. Atlas reads the client's own instance data, so confirm this is
  deliberate before adding either (WFA-19 applies only where a repo has a data source to refresh).
- `README.md` badges use absolute `github.com/cjber/atlas-forever/...` URLs on a private repo. Same defect the
  Hoard icon had (raw URLs 404 on a private repo): switch the badge links and icon to relative paths.

### 2.3 hoard-forever

- `tools/forever_tools/` current except `editorconfig.py` and `sync.py`, and **`MANIFEST.json` still points at
  `github.com/cjber/skills` revision `09cc65d`** — the package moved to forever-core on 2026-10-24. Re-vendor.
- `Locales/` has `enUS.lua` + `phrases.txt` only (WFA-34).
- `docs/screenshots/` is empty; `docs/curseforge.md` referenced a `window.png` that never existed. Fixed in #4 by
  removing the image; the page needs a real capture before WFA-9 is met.
- `.sift/` has an empty `scripts/` and no `script-tests/`, `ledger/` or `reports/`.
- No `refresh-data.yml` (Hoard reads containers, so probably deliberate — confirm).

### 2.4 The six established repos — smaller, but real

| repo | finding |
|---|---|
| forever-core | no `.editorconfig` (every addon has one); no `THIRD_PARTY.md`; README is not WFA-10 shape and there is no `docs/curseforge.md` — decide whether core is published as a page at all before adding either |
| legacy-forever | `stylua.toml` carries an extra `syntax = "Lua51"` line the other eight do not; no `.gitleaks.toml` |
| tweaks-forever | no `.gitleaks.toml` |
| adventure-guide-forever | runs `ruff` in `check` with **no `ruff.toml`**, so it lints at ruff's defaults (88 cols, no rule selection) instead of the suite's 120/`E,F,I,UP,B`. The canonical `ruff.toml` passes on its `tools/` unchanged — verified. |
| skillup-forever | same missing `ruff.toml`. The canonical config reports one `I001` in `tools/screenshots.py`, so fix that import block in the same PR. |
| shortest-path-forever | only repo with `bake-*` jobs (correct, it is the nav-data repo); no drift otherwise |

### 2.5 CI job names are not the same in every repo (WFA-18)

The ruleset requires checks by exact name, so a renamed job is a merge that silently stops being gated.

| repo | jobs |
|---|---|
| adventure-guide-forever | check, typecheck, **generated-data**, sift, workflows, secrets, package |
| legacy-forever | check, typecheck, **generated**, sift, workflows, secrets, package |
| skillup-forever | check, typecheck, **generated**, sift, workflows, secrets, package |
| shortest-path-forever | check, typecheck, **generated**, sift, workflows, secrets, package, bake-provenance, bake-native |
| tweaks-forever | check, typecheck, **generated**, **python**, sift, workflows, secrets, package |
| field-guide-forever | check, **python**, **changelog**, sift, workflows, secrets, package — **no typecheck** |
| atlas-forever | check, typecheck, **python**, **changelog**, sift, workflows, secrets, package |
| hoard-forever | check, typecheck, **python**, **changelog**, sift, workflows, secrets, package |

Pick one name for the generated-data job (`generated` is the majority) and one decision for `python` and
`changelog` (present or absent, consistently), then rename the job and its required check together. Field Guide
gaining `typecheck` is the one that changes what is tested, so that PR says so.

## 3. Forever Core's own gate is out of date

`tools/check_consumers.py` and `tools/sync_consumers.py` still describe the suite as it was before round 9:

- `ALL_CONSUMERS` is the five original addons. `atlas-forever` and `hoard-forever` are absent from both lists, so
  their `SafeCall.lua` drift is invisible to the gate.
- `PRIVATE_CONSUMERS = ("field-guide-forever",)` is correct, but the Field Guide side
  (`tools/check_core_shared.py`) only compares `Core/MicroButton.lua` and its spec. Widen that list as the new
  vendored files land.
- `VENDORED` needs `UI/SettingsPage.lua`, `Core/Text.lua` and their specs once §1.1 and §1.2 exist.

Do this in the same PR that adds the new core files, otherwise the copies drift from day one.

## 4. Work order

One PR per repo, in this sequence, each with its CHANGELOG entry:

1. **forever-core** — `Core/Text.lua` + spec, `UI/SettingsPage.lua` + spec, the `forever_tools/wrappers.py`
   emitter, and the updated `VENDORED`/consumer lists. No addon behaviour changes here.
2. **adventure-guide-forever**, **shortest-path-forever**, **hoard-forever** — adopt `Core/Text.lua`; delete the
   local fold; rename Tweaks' local `Fold` to `FoldSlot` in the Tweaks PR.
3. **all eight** — adopt `UI/SettingsPage.lua` for the panel chrome only.
4. **field-guide-forever**, **atlas-forever**, **hoard-forever** — the §5 vendoring (`SafeCall`, `Report`,
   `ForeverFamily` + specs), their `MANIFEST.json` re-vendored from forever-core, and `check_core_shared.py`
   widened to the new file list.
5. **field-guide-forever** — `media/` from `icon.svg` via `render_icon.py`, `THIRD_PARTY.md`,
   `docs/curseforge.md`, the WFA-10 README, `Locales/phrases.txt` + `check_locales.py` + the locale files.
6. **every repo** — the `ruff.toml`, `.gitleaks.toml`, `.editorconfig` and `stylua.toml` one-liners from §2.4.
7. **every repo** — the CI job-name consolidation from §2.5, one PR per repo, job and required check renamed
   together.

Rules that apply to all of it: no `-s` on commits (GitHub signs them), no tags and no releases from this brief,
`luacheck` + `stylua` + the specs green locally before the PR, `check_copy.py` clean on any page you touch, and
each PR names what it changed in behaviour (the `SafeCall` replacement and Field Guide's new `typecheck` do).
