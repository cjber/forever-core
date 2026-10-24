---
name: wow-forever-addon
description: "Standards pack for cjber's WoW: Forever addons (legacy-forever, skillup-forever, tweaks-forever, shortest-path-forever, any new one) - the numbered requirements every addon repo shares for UI look and feel, assets, README and store pages, code and performance, CI and releases. Load before building or changing an addon's UI, icon, screenshots, README, store page, CI, release process or GitHub repo settings, when debugging taint, a blocked action, in-game layout or load time, or when `sift audit` reviews an addon that declares it under `## Standards` in AGENTS.md."
---

# WoW: Forever addon standards

One family, one feel: each addon is a small, fast extension of the default Forever UI that works the
moment it is installed. These requirements are the shared contract. Each repo declares this pack in
its `AGENTS.md` under `## Standards`; `sift audit` reviews against the ids below, and a repo waives one
only in its `AGENTS.md`, with the reason.

Reference implementations: **skillup-forever** for CI and release, **tweaks-forever** for settings.
When this pack and a reference repo disagree, fix whichever is wrong in the same change.

## Requirements

### Product

- **WFA-1** Extend the base game, do not replace it. Add information or an action where the player
  already looks (a Blizzard frame, tooltip, menu, map, tracker, settings page); step aside when
  another popular addon already does the job, and say so in README under "Works alongside".
- **WFA-2** Zero setup. Every feature works out of the box: no required settings, extra downloads
  or companion installs. Data ships in the release zip (`.pkgmeta` `move-folders` for a
  load-on-demand data addon). Anything off by default is off because it acts for the player.
- **WFA-28** Game data has two sources: the installed QuestieDB (quests, NPCs, objects, spawns,
  vendors, trainers' places) and AtlasLoot (bosses, loot, recipes, drop rates), read at runtime
  through their public tables. Neither is copied into the repo or the zip: QuestieDB carries no
  licence and AtlasLoot is GPL v2. This is the one companion install WFA-2 allows; without it the
  feature says in one plain line what to install and the rest of the addon works. A dataset neither
  holds (trainer fees, transports) is a named exception in the repo's `AGENTS.md` under `## Waivers`,
  stating its source, and the player sees a live in-game value over the bundled one wherever the
  client offers it. A server-emulator dump (CMaNGOS classic-db) describes Classic Era, not Forever:
  it is never the source for a dataset QuestieDB or AtlasLoot holds.
- **WFA-3** Minimal surface. Options live in one place: a Settings > AddOns page (Blizzard's
  settings API), or a menu on the addon's own UI when every option is about that UI (Legacy Forever's
  map menu). A slash command (short form plus the full name) and an addon compartment entry
  (`## AddonCompartmentFunc`) both open it. No minimap button, no custom options window.

### UI

- **WFA-4** Looks like the retail default UI. Stock frame templates, `GameFont*` objects, atlases,
  `GameTooltip`, `MenuUtil` menus, `MapCanvasDataProviderMixin` pins, copied from the Blizzard
  source for the Forever build (Gethe/wow-ui-source, branch `forever`). Never custom-styled frames,
  fonts or colours, except that chat prefixes use the family's mint `|cff33ff99`; addon-drawn art
  only where no atlas exists, in the atlas's palette.
- **WFA-5** Objective tracker sections sit above quests with a unique negative `uiOrder`. Registry:
  Legacy Forever `0` and `-1`, SkillUp Forever `-2`, Shortest Path Forever `-3`, Adventure Guide Forever `-4`. A new addon takes the
  next free number and adds it here. Attach by hooking `ObjectiveTrackerManager:AddContainer`.
- **WFA-6** Copy talks to the player in the game's voice: short, plain, no jargon or internal names.
  After an update, tell them to `/reload`, never to restart the game.
- **WFA-26** An audio cue is the sound the game itself makes for that thing: a ship's dock bell for a
  boat, the zeppelin's horn for a zeppelin. Never a raid warning, ready check or PvP alert, which mean
  something else to a player. Find it in the Forever build's listfile on wago.tools, check it exists with
  `/api/casc/<FileDataID>?build=`, and play it with `PlaySoundFile(<FileDataID>, "Master")` beside a
  comment naming the file.
- **WFA-27** Never stretch art. An icon, atlas or texture is drawn at its native aspect: size it from
  `C_Texture.GetAtlasInfo` and fit it inside its box, centred, never anchor or size it to a box of another
  shape. Inline markup (`CreateAtlasMarkup`, `|A`, `|T`) takes whole pixels, so pick sizes within 2% of the
  native shape and comment the native size. File icons are square; account for any texcoord crop. Only
  nine-slice pieces, bars, fills, colour textures and masks stretch by design. Each repo's `AGENTS.md`
  carries this rule under Rules and its gate runs `tools/lint_art.py` (`forever_tools.art`): art is set only in
  the repo's art helper file, or on a line that says why its shape is right (`art-ok: reason`). A texture reused
  for a file icon after an atlas keeps the atlas's crop: reset its texcoords first.

### Assets

- **WFA-7** One icon family. `media/icon.svg` starts from [icon-template.svg](icon-template.svg):
  gold rounded frame, warm-brown radial background, a single centred emblem in the gold palette
  with the template's drop shadow and outline. Colour inside the emblem only where it carries
  meaning (difficulty colours, a tick). No scenes or alternative backgrounds.
- **WFA-8** Icon files are rendered, not hand-exported: `python3 <this skill>/render_icon.py`
  writes `media/icon-400.png` (README, store logo) and `media/Icon.tga` (64 px). The TOC uses
  `## IconTexture: Interface\AddOns\<Addon>\media\Icon`, and so does every child addon the zip
  ships (load-on-demand data or map addons), pointing at the parent's icon, so none shows a `?`.
- **WFA-9** Screenshots come from `tools/screenshots.py` via the `wow-mock-screenshots` skill, one
  per headline feature, regenerated in the same PR as any UI change they show. README, store page
  and store gallery use the same files from `docs/screenshots/`. `docs/screenshots/scenes.sha256` records each
  image's hash beside its scene dump's (`forever_tools.screens`); CI recomputes the dumps headlessly
  (`tools/check_screenshots.py`) and fails when a dump moved but its image did not.

### Docs

- **WFA-10** README shape: centred 96 px icon, `<h1 align="center">`, one-line pitch, CI and
  release badges; then Features, Install, Usage (slash commands), optional sections for how the
  numbers or data work, Works alongside, Development, Credits, Licence. Under 1,200 words: a feature is one
  bullet led by a bold name, at most ~60 words; depth moves to `docs/`. `## Credits` is a short paragraph that
  thanks, by name and with a link, the data sources, the addons whose ideas a feature took (even when no code was
  copied, saying so), translators and the people who reported bugs or asked for features (GitHub handles and named
  CurseForge users; a generic thanks for the rest). THIRD_PARTY.md (WFA-31) holds the full list. The WFA-32 family block is not
  counted; `check_copy.py --words` gives the count every repo uses.
- **WFA-11** `docs/curseforge.md` is the store description: the pitch, the headline screenshots,
  Features, Usage, a source/licence line; under 600 words; no Install or Development sections. It
  is pasted into CurseForge and Wago by hand after it changes (`wow-addon-publish`). The WFA-32 block is
  not counted here either.
- **WFA-23** The addon fits the game's own UI. Show this in the lead image, against the stock UI
  where the change is subtle. Copy leads with what the addon does and how to use it; it does not
  need a slogan about its appearance. See [voice.md](voice.md).
- **WFA-24** Store copy, README and posts use short, factual sentences and British spelling.
  No invented teams, credits, personal experiences or origin stories. Remove preambles and
  filler; retain useful instructions and real limitations. [voice.md](voice.md) is the rule set;
  `python3 <this skill>/check_copy.py docs/curseforge.md README.md` must pass before a store paste or post.
- **WFA-25** No two images stacked without words between them, in the README or the store page. Each
  image, or row of images in one `<p>`, gets a line under it saying what to look at in plain words,
  not a copy of its alt text. `check_copy.py` flags a stacked pair. Two things that belong side by side
  are one image, composed in `tools/screenshots.py` as one `scene()` with both widgets as layers.
- **WFA-12** `CHANGELOG.md` follows Keep a Changelog with prose: `## [Unreleased]` on top,
  `## [x.y.z] - YYYY-MM-DD`, bullets led by a bold sentence then why it matters, in player terms.
  A version that changes a public API puts those notes under an optional `### For addon authors` subsection
  after the player bullets, so players read their changes first; the release notes carry it as written.

### Code and performance

- **WFA-13** Fast in both senses: time to a result and per-frame cost. Benchmark the short and long
  case before and after a change to a hot path; no frame over 3 ms; no idle `OnUpdate` or timers;
  bounded work per event. A one-off job the player is waiting on (a catalogue built at login) may take
  a larger slice, measured in game: 2 s of work at 1 ms a frame is 40 s of empty UI at 60 fps.
- **WFA-14** Saved variables never assume a key: every default is declared in one place (a
  `DEFAULTS` table, or the feature registry's `default =`), and a missing key reads as its default,
  so a new option and an old save file always agree.
- **WFA-35** New UI work adds a scenario to `tests/sim/`, the [forever_sim](tooling/forever_sim/README.md) suite (real
  Blizzard UI under LuaJIT, vendored as `tools/forever_sim/` the same way as `forever_tools`). The scenario walks
  the player's way to the feature and adds the states that have broken before: combat, a secret tooltip, the
  gamepad interface, Questie's tracker, an old saved file. A fix for a reported error comes with a scenario that
  fails on the release the error was reported against.

### Build, CI and release

- **WFA-15** CI covers at least the skillup-forever baseline: actions pinned to full SHAs with a
  version comment, `persist-credentials: false`, `permissions: contents: read`; luacheck, every
  `tests/*_spec.lua` under LuaJIT (a glob, so a new spec cannot be left out), StyLua `--check`,
  lua-language-server, ruff for the Python tools, actionlint and zizmor, and gitleaks over the full
  history. Extra checks (shellcheck) are welcome. Downloaded binaries are pinned by sha256. A job
  named `sift` runs the vendored `python3 .sift/gate.py --base "origin/$BASE"` and
  `python3 .sift/agents.py check`; `sift setup` vendors both and `sift update` refreshes them.
  Dependabot updates `github-actions` monthly, grouped. A `package` job runs the pinned BigWigs packager
  with `args: -d -z` (no upload) and `tools/check_package.py` (`forever_tools.package`) on its output: every file a
  TOC or XML loads and every `Interface\AddOns\<addon>\` path is in the zip, no `tests`, `tools`, `types` or
  `.agents` ships, every packaged folder ships a licence file (LICENSE, LICENCE, COPYING or UNLICENSE), THIRD_PARTY.md
  and the WFA-10 and WFA-31 credits sections ship with text under them, and the smoke spec passes on the packaged
  folder. `tools/doctor.py`
  (`forever_tools.doctor`) checks a machine against every pin in `ci.yml` and `typecheck.sh` and prints a fix for
  each problem; AGENTS.md lists it under Commands.
- **WFA-16** Releases: a signed `v*` tag runs `release.yml` (BigWigs packager, pinned) with this
  version's CHANGELOG entry as notes (`tools/changelog.py`), uploading to GitHub, CurseForge and
  Wago; the TOC carries `X-Curse-Project-ID` and `X-Wago-ID`. Setup is in `wow-addon-publish`.
  Release prep starts by translating every phrase added since the last tag into each shipped locale (WFA-34):
  `tools/check_locales.py` lists each locale's coverage, and `--release` fails until every shipped locale is back at
  100%.
- **WFA-17** Every repo has a lean `AGENTS.md` passing `python3 .sift/agents.py check`, declaring
  this pack at a full commit SHA. Headless specs pass on builds that are broken in game, so a change
  to anything the player sees or to combat behaviour is verified live in game before it merges, and
  the PR says what was checked. [debugging.md](debugging.md) covers taint, profiling and reading
  results out of the client.

### Repository

- **WFA-18** CI job names are the same in every repo, because the ruleset (WFA-21) requires checks
  by exact name: `check` (luacheck, StyLua, the specs), `typecheck` (lua-language-server),
  `secrets` (gitleaks), `workflows` (actionlint, zizmor), and `python` (ruff) only when
  the Python tooling is big enough to earn its own job. Rename a job and its required check
  together.
- **WFA-19** `refresh-data.yml`, where a repo has one, dispatches `ci.yml` on the branch it opens
  (`gh workflow run ci.yml --ref <branch>`, `actions: write`; `ci.yml` accepts
  `workflow_dispatch`), so the new data is tested at once. A PR opened with `GITHUB_TOKEN` gets
  its `pull_request` CI only as runs awaiting approval, and a dispatched run never counts toward
  required checks: approve those runs from the PR's merge box before merging.
- **WFA-20** `.gitattributes` normalises text to LF and marks generated data files
  `linguist-generated`, so their diffs collapse in review. `.editorconfig` is the family template
  (`forever_tools.editorconfig`, `.luacheckrc` and `.pkgmeta` included), checked against `stylua.toml` and
  `ruff.toml` in `typecheck.sh`. Community health files (contributing,
  security policy, issue and PR templates) are inherited from `cjber/.github`; a repo carries its
  own copy only to override one.
- **WFA-21** `main` is protected by one ruleset: force-push and deletion blocked; changes land by
  PR with 0 required approvals and all review threads resolved; the WFA-18 checks required by
  exact job name, not strict (a branch need not be up to date); signed commits; linear history;
  squash the only merge method. Repository admins bypass it. A private repo on the free plan
  cannot have rulesets; add it when the repo goes public.
- **WFA-22** Repo settings: delete branch on merge; wiki and projects off; Dependabot alerts and
  security updates on; private vulnerability reporting on (public repos only); Actions may create
  pull requests (for WFA-19); Actions require full-SHA pinning; topics `wow-addon`,
  `world-of-warcraft`, `wow-forever`, `lua` plus one or two for what the addon does.
- **WFA-29** The Python tooling every addon shares (changelog and release checks, TOC and XML
  traversal, the Lua lexer with its taint and multi-value lints, strict DB2 CSV parsing, atomic
  writes, the generated-data gate and its semantic report) is [tooling/](tooling/README.md): one
  producer here, vendored byte for byte into each repo as `tools/forever_tools/` and pinned by
  `MANIFEST.json`. Edit it here, never in a repo; `python3 tools/forever_tools/sync.py check` runs
  in `typecheck.sh`. A repo's own `tools/` keeps only thin entry points and its generators.
- **WFA-30** Values the client may return as secrets (unit GUIDs and names, tooltip unit data) are read
  through the repo's one helper, `ns.Readable` (the value, or nil when it is secret), and every tooltip hook
  returns first when `ns.Usable(tooltip)` is false (nil or forbidden). Both live in a small file with no other
  addon state (Adventure Guide Forever's `Core/Secret.lua`), so it copies across the family as is. `tools/lint_secret.py` (`forever_tools.readable`) runs in `typecheck.sh`
  and refuses an unguarded read unless its line says why it is safe (`-- secret-ok: reason`).
- **WFA-31** `THIRD_PARTY.md` lists every input: what it is, where its pin lives (the constant in `tools/`, never
  a copied value that a data refresh would leave stale), its licence, and whether it ships in the zip or is
  build-only. An embedded library (LibStub and the like) ships with its licence and is credited there; every
  `move-folders` folder ships a licence file of its own (public-domain code such as LibStub carries it in its
  header). Media made for the addon (icons, textures) is named as the addon's own, with the script that draws it. Its `## Ideas and contributors` table names each addon an idea came
  from (with the issue numbers), each translator and each reporter. `tools/check_package.py` fails a zip without
  THIRD_PARTY.md, that section or README's `## Credits`.
- **WFA-32** README.md and docs/curseforge.md each carry the family block, "The Forever addons", once,
  between `<!-- forever-family:start -->` and `<!-- forever-family:end -->`, in place of any hand-written list of
  the other addons. The text is `forever_tools.family` and never edited in a repo: `tools/check_family.py` runs in
  `typecheck.sh` and fails on any difference (`--fix` rewrites it after a sync, `--print` gives it to place). Prose
  outside the block says only what a sibling really adds to this addon.
- **WFA-33** A player who reported a bug we fix, or asked for a feature we build, is credited by name in the same PR,
  whether they wrote on GitHub or in store comments: the changelog bullet ends "thanks to X for the report" (or "for
  the idea"), and THIRD_PARTY.md's `## Ideas and contributors` table gains or extends their row with what came of it.
  Use the handle they posted under; an anonymous store handle (`user_` and random characters) gets the table's
  generic thanks instead. Praise, and requests that weren't built, are not credited. The org PR template
  (`cjber/.github`) carries the checklist line `- [ ] A reporter or requester is credited in the changelog bullet and
  THIRD_PARTY.md (WFA-33)`.
- **WFA-34** Every addon ships in the client languages the Forever client offers besides English (deDE, esES,
  esMX, frFR, itIT, koKR, ptBR, ruRU, zhCN and zhTW, less any the client lacks), one `Locales/<locale>.lua` each,
  loaded by the TOC after `Locales\enUS.lua` and keyed exactly as `Locales/phrases.txt`. A human translation wins:
  keep each human line and fill only the gaps, and never overwrite one with a machine line. A machine-translated file
  starts with `-- Machine translated (<date>); corrections welcome: <the repo's translation issue form>`, and in a
  file that mixes the two each machine line ends `-- mt`. Use the client's own GlobalStrings terms; never change
  placeholders, colour, texture, atlas or link escapes, newlines, slash commands or addon names. Store and README
  copy stay English, with one line naming the languages and the translation form. `tools/check_locales.py`
  (`forever_tools.locales`) runs in `typecheck.sh`: it fails on an unknown key, a file LuaJIT can't parse or the TOC
  doesn't load, and a placeholder or escape that differs from English, and prints each locale's coverage (a gap falls
  back to English, so it never fails).
