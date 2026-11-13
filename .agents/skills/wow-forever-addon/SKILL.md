---
name: wow-forever-addon
description: "Standards pack for cjber's WoW: Forever addons (legacy-forever, skillup-forever, tweaks-forever, shortest-path-forever, any new one) - the numbered requirements every addon repo shares for UI look and feel, assets, README and store pages, code and performance, CI and releases. Load before building or changing an addon's UI, icon, screenshots, README, store page, CI, release process or GitHub repo settings, when debugging taint, a blocked action, in-game layout or load time, or when an audit reviews an addon that declares it under `## Standards` in AGENTS.md."
---

# WoW: Forever addon standards

One family, one feel: each addon is a small, fast extension of the default Forever UI that works the
moment it is installed. These requirements are the shared contract. Each repo declares this pack in
its `AGENTS.md` under `## Standards`; an audit reviews against the ids below, and a repo waives one
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
  ForeverCore is the one required companion, and the addon's own zip ships it: declare `## Dependencies: ForeverCore`
  in the TOC, and in `.pkgmeta` download the release `tools/forever-core.txt` pins under `externals:` and place it
  with `move-folders:` `<package-as>/ForeverCore: ForeverCore`, with no `required-dependencies` entry. A store update
  can skip a required dependency, and the packager sends Wago no dependency list, so the zip carries the core. It is
  the suite's shared library, not a second addon the player has to choose. The root TOC also names that release in
  `## X-Forever-Core: <tag>`, so a player's other Forever addon can say a sibling bundles a different core. Every core
  release re-releases every addon automatically: the core sync PR moves the pin, rewrites the external and the TOC
  field, and adds a marked `CHANGELOG.md` entry, then `release-consumers.yml` dispatches each addon's own release once
  its full CI on main is green. Each addon's `Core/Require.lua` computes `ready` from feature checks of every
  post-API-1 ForeverCore member it calls, never a version comparison, and calls `ns.ForeverRequire(ready)`; the
  vendored file is never edited in a consumer.
- **WFA-28** Game data has two sources: the installed QuestieDB (quests, NPCs, objects, spawns,
  vendors, trainers' places) and AtlasLoot (bosses, loot, recipes, drop rates), read at runtime
  through their public tables. Neither is copied into the repo or the zip: QuestieDB carries no
  licence and AtlasLoot is GPL v2. This is the one data companion WFA-2 allows (ForeverCore is the required library,
  not a data companion); without it the
  feature says in one plain line what to install and the rest of the addon works. A dataset neither
  holds (trainer fees, transports) is a named exception in the repo's `AGENTS.md` under `## Waivers`,
  stating its source, and the player sees a live in-game value over the bundled one wherever the
  client offers it. A server-emulator dump (CMaNGOS classic-db) describes Classic Era, not Forever:
  it is never the source for a dataset QuestieDB or AtlasLoot holds. `.pkgmeta` lists the CurseForge
  slug of every TOC `OptionalDeps` folder under `optional-dependencies` (QuestieDB is `questiedb`,
  AtlasLoot's Forever build `atlasloot-forever`): the TOC line only orders loading, and the store
  relation is what makes the CurseForge app offer the data addon. Wrong or missing data in either is
  fixed upstream, by a report or PR to that project (Questie's in-game debug offer already collects
  missing quest, NPC and loot data), not by an override table in the addon, which drifts from what
  every other addon reads.
- **WFA-3** Minimal surface. Options live in one place: a Settings > AddOns page (Blizzard's
  settings API), or a menu on the addon's own UI when every option is about that UI (Legacy Forever's
  map menu). A slash command (short form plus the full name) and an addon compartment entry
  (`## AddonCompartmentFunc`) both open it. No minimap button, no custom options window. Slash words are the addon's
  own: a word the client's GlobalStrings define, such as `/ma` for main assist, is run by the chat box before any
  addon command, so `tools/check_slash_words.py` (vendored, checked against `tools/client_slash_words.txt`) fails a
  collision and `sim:slash` refuses one.

### UI

- **WFA-4** Looks like the retail default UI. For design and mockups, read
  [wow-retail-ui-style](../wow-retail-ui-style/SKILL.md) and its asset registry first: native host
  integration, compact content spacing, edge ownership and the host's approved surfaces are part
  of the match. The canonical composition contract is [ui-composition.md](../../../docs/ui-composition.md).
  Buttons use `SharedButton*Template` and the set-1 `128-RedButton` family. Every addon CI runs
  `python3 -m tools.forever_tools.assets`: the shared blacklist covers runtime and renderer art,
  including legacy loose chrome, inherited templates, and the profession crafting progress bar
  atlases (`Profession-ProgressBar-BG`/`-frame`, which read as the crafting cast bar). Art helpers
  and `art-ok` do not waive it.
  Contact sheets are discovery aids, not asset allowlists. Stock frame templates, `GameFont*` objects, atlases,
  `GameTooltip`, `MenuUtil` menus, `MapCanvasDataProviderMixin` pins, copied from the Blizzard
  source for the Forever build (Gethe/wow-ui-source, branch `forever`). Never custom-styled frames,
  fonts or colours, except that chat prefixes use the family's mint `|cff33ff99`; addon-drawn art
  only where no atlas exists, in the atlas's palette.
- **WFA-5** Objective tracker sections sit above quests with a unique negative `uiOrder`. Registry:
  Legacy Forever `0` and `-1`, SkillUp Forever `-2`, Shortest Path Forever `-3`, Adventure Guide Forever `-4`, Kiln Forever `-5`. A new addon takes the
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
  native shape and comment the native size. File icons are square; account for any texcoord crop. Never
  resize an asset non-uniformly: only nine-slice and three-slice pieces, bar fills, colour textures and masks
  stretch, and only along the axis the client's own template stretches them. Each repo's `AGENTS.md`
  carries this rule under Rules and its gate runs `tools/lint_art.py` (`forever_tools.art`): art is set only in
  the repo's art helper file, or on a line that says why its shape is right (`art-ok: reason`). A texture reused
  for a file icon after an atlas keeps the atlas's crop: reset its texcoords first.
- **WFA-36** A menu or dropdown built from a list scrolls. Blizzard's Menu API never clamps a submenu to the
  screen and a dropdown's root only flips sideways, so a list that grows runs off the bottom. A description (root or
  submenu) that gets entries in a loop, or is handed to a helper in a loop, calls `SetScrollMode(extent)` on itself
  in the same function: 20 rows of 20 px (`SetScrollMode(400)`) unless the repo already names its extent. A loop that
  stays short by construction (a constant table of a few options) says why on its `for` line or the line above:
  `-- menu-scroll-ok: <reason>`. `UIDropDownMenu_AddButton` cannot scroll, so a list goes through the Menu API.
  `tools/check_menu_scroll.py`, vendored from forever-core, runs in the required `core-shared` job of every repo;
  where a spec stubs the menu, it asserts the extent too.

### Assets

- **WFA-7** One icon family. `media/icon.svg` starts from [icon-template.svg](icon-template.svg):
  gold rounded frame, warm-brown radial background, a single centred emblem in the gold palette
  with the template's drop shadow and outline. Colour inside the emblem only where it carries
  meaning (difficulty colours, a tick). No scenes or alternative backgrounds.
- **WFA-8** Icon files are rendered, not hand-exported: `python3 <this skill>/render_icon.py`
  writes `media/icon-400.png` (README, store logo) and `media/Icon.tga` (64 px). The TOC uses
  `## IconTexture: Interface\AddOns\<Addon>\media\Icon`, and so does every child addon the zip
  ships (load-on-demand data or map addons), pointing at the parent's icon, so none shows a `?`.
  Every in-game identity surface (minimap button, Professions or side tab, window portrait, leaderboard tab,
  addon compartment) reads the one `## X-Forever-Icon: Interface\Icons\<name>` value from the TOC with
  `C_AddOns.GetAddOnMetadata(addonName, "X-Forever-Icon")`; `forever_tools.identity`, run by the assets
  check, fails a TOC that omits it, a value the pinned build does not have, or a repeat in shipped Lua.
- **WFA-9** Screenshots come from `tools/screenshots.py` via the `wow-mock-screenshots` skill, one
  per headline feature, regenerated in the same PR as any UI change they show. README, store page
  and store gallery use the same files from `docs/screenshots/`. `docs/screenshots/scenes.sha256` records each
  image's hash beside its scene dump's (`forever_tools.screens`); CI recomputes the dumps headlessly
  (`tools/check_screenshots.py`) and fails when a dump moved but its image did not.
  Every PR body shows every image in `docs/screenshots/`, linked at the head commit's SHA: the changed
  ones in full under `## Screenshots`, the rest in `<details>` blocks.
  A screenshot is evidence only after its whole-panel composition, native tab edge and icon chrome
  ownership meet the rules in [ui-composition.md](../../../docs/ui-composition.md).

### Docs

- **WFA-10** README shape: centred 96 px icon, `<h1 align="center">`, one-line pitch, CI, release
  and CurseForge downloads badges (`img.shields.io/curseforge/dt/<X-Curse-Project-ID>`, linked to the
  store page; ForeverCore itself has none, as every addon pulls it in); then Features, Install, Usage
  (slash commands), optional sections for how the numbers or data work, Works alongside, Development, Credits, Licence. Under 1,200 words: a feature is one
  bullet led by a bold name, at most ~60 words; depth moves to `docs/`. `## Credits` is a short paragraph that
  thanks, by name and with a link, the data sources, the addons whose ideas a feature took (even when no code was
  copied, saying so), translators and the people who reported bugs or asked for features (GitHub handles and named
  CurseForge users; a generic thanks for the rest). THIRD_PARTY.md (WFA-31) holds the full list. The WFA-32 family block is not
  counted; `check_copy.py --words` gives the count every repo uses.
- **WFA-11** `docs/curseforge.md` is the store description and follows [store-page.md](store-page.md): the pitch,
  the sponsor sentence with the Discord, Sponsors and Ko-fi button row under it, three to six captioned
  screenshots, Features, Usage, the source and AI lines; under 1,000 words; no Install or Development sections. `forever_tools.store_page` fails CI on a page
  that leaves a part out. It is pasted into CurseForge by hand after it changes; Wago carries a fixed stub (`wow-addon-publish`). The WFA-32 block is
  not counted here either.
- **WFA-23** The addon fits the game's own UI. Show this in the lead image, against the stock UI
  where the change is subtle. Copy leads with what the addon does and how to use it; it does not
  need a slogan about its appearance. See [voice.md](voice.md).
- **WFA-24** Store copy, README and posts use short, factual sentences and British spelling.
  No invented teams, credits, personal experiences or origin stories. Remove preambles and
  filler; retain useful instructions and real limitations. [voice.md](voice.md) is the rule set;
  `python3 <this skill>/check_copy.py docs/curseforge.md README.md` must pass before a store paste or post.
- **WFA-25** No two screenshots (images under `docs/screenshots/`) stacked without words between
  them, in the README or the store page. Badges and support buttons are not screenshots. Each
  image, or row of images in one `<p>`, gets a line under it saying what to look at in plain words,
  not a copy of its alt text. `check_copy.py` flags a stacked pair. Two things that belong side by side
  are one image, composed in `tools/screenshots.py` as one `scene()` with both widgets as layers.
- **WFA-12** `CHANGELOG.md` follows Keep a Changelog with prose: `## [Unreleased]` on top,
  `## [x.y.z] - YYYY-MM-DD`, bullets led by a bold sentence then why it matters, in player terms.
  A version that changes a public API puts those notes under an optional `### For addon authors` subsection
  after the player bullets, so players read their changes first; the release notes carry it as written.
  A feature release, one that raises the major or minor over the newest tag, names its hero at the top of
  its section with `<!-- discord-image: docs/screenshots/<file>.png -->`: one of the repo's own rendered
  screenshots that shows the new feature, at its native size. `tools/changelog.py --check x.y.z` fails a
  feature release without one.

### Code and performance

- **WFA-13** Fast in both senses: time to a result and per-frame cost. Benchmark the short and long
  case before and after a change to a hot path; no frame over 3 ms; no idle `OnUpdate` or timers;
  bounded work per event. A one-off job the player is waiting on (a catalogue built at login) may take
  a larger slice, measured in game: 2 s of work at 1 ms a frame is 40 s of empty UI at 60 fps.
- **WFA-14** Saved variables never assume a key: every default is declared in one place (a
  `DEFAULTS` table, or the feature registry's `default =`), and a missing key reads as its default,
  so a new option and an old save file always agree.
- **WFA-38** Never touch Blizzard's Lua state. Forever runs its UI through secure delegates, so a hook, a field
  write or a first call from addon code into a Blizzard object makes Blizzard's own code fail or be blocked later,
  often only in combat, and the error names this addon. Blizzard allows hooks in general; this rule is ours,
  because on this client they break.
  - Allowed: events; `HookScript`; `EventRegistry` or an object's own `RegisterCallback`;
    `TooltipDataProcessor`; `hooksecurefunc("GlobalFunction", …)`; our own frames and textures, which may be
    parented or anchored to a Blizzard frame; engine calls on a Blizzard widget (points, size, alpha, shown)
    after Blizzard has laid it out.
  - Never: `hooksecurefunc(object, "Method", …)`; a replaced method; a field written on a Blizzard table; a
    call to a Blizzard object's Lua methods (`frame:UpdateIcon()`); Blizzard layout or lazy-cache functions; the
    map openers (`ToggleWorldMap`, `OpenWorldMap`: use `C_Map.OpenWorldMap`).
  - To restyle a Blizzard element, draw our own on top and hide theirs with alpha: a texture of ours parented to
    the frame, their texture at alpha 0, both refreshed from events. Blizzard does not reset alpha it never set.
  - The gate is `forever_sim`, not a list: every table field read and write in Blizzard's and the addon's Lua is
    instrumented, a field written by addon code carries that addon's taint, and a secure read of it taints
    execution and reports the field, the writer and the reader at the refused call. WFA-35's scenario runs it
    with the gamepad interface off and on over every panel, and `tests/sim/taint_gate_spec.lua` proves the
    known-bad shapes fail. There is no `taint-ok` exception.
- **WFA-35** New UI work adds a scenario to `tests/sim/`, the [forever_sim](tooling/forever_sim/README.md) suite (real
  Blizzard UI under LuaJIT, vendored as `tools/forever_sim/` the same way as `forever_tools`). The scenario walks
  the player's way to the feature and adds the states that have broken before: combat, a secret tooltip, the
  gamepad interface, Questie's tracker, an old saved file. A fix for a reported error comes with a scenario that
  fails on the release the error was reported against.

### Build, CI and release

- **WFA-15** CI covers at least the skillup-forever baseline: actions pinned to full SHAs with a
  version comment, `persist-credentials: false`, `permissions: contents: read`; luacheck, every
  `tests/*_spec.lua` under LuaJIT (a glob, so a new spec cannot be left out; `python3 -m
  tools.forever_tools.specs` runs them in parallel and names every failure), StyLua `--check`,
  lua-language-server, ruff for the Python tools, actionlint and zizmor, and gitleaks over the full
  history. Every pull-request workflow cancels a PR's superseded runs (top-level `concurrency` grouped on
  the PR number, `cancel-in-progress` only for `pull_request`, so `main` keeps a run per commit) and every
  job sets `timeout-minutes`. Extra checks (shellcheck) are welcome. Downloaded binaries are pinned by sha256. LuaJIT,
  luacheck, LuaLS, StyLua and gitleaks come from `cjber/forever-core/.github/actions/toolchain@<sha>` at the commit
  the repo's other core tooling comes from, never from apt, curl or a tool action: `with: tools: lua luals stylua
  gitleaks` names what the job needs, and the action reads the vendored `tools/toolchain.json` from the job's own
  checkout (its `manifest` input defaults to it), so every version comes from that one file. A job
  named `project-rules` runs `tools/changelog.py --check` and the repo's own rules, the ones no linter covers, as
  one stdlib script, `tools/repo_rules.py` (the merge base from `--base "origin/$BASE"` where a rule reads it). A
  hit is exempt only where the rule says so, with a `rule-ignore: <id> - <reason>` marker. Sloppatrol is a patrol,
  not a gate: a repo it patrols keeps `.sloppatrol/sloppatrol.yml`, whose checks are the fast CI checks plus the
  rules script, and `.sloppatrol/instructions.md`, its live roots; nothing else under `.sloppatrol/` is tracked.
  Dependabot updates `github-actions` daily with a one-day cooldown, grouped per ecosystem, and the vendored
  `tools/pyproject.toml`'s `uv` group holds the Python tools, which run as
  `uv run --project tools --frozen --group dev <tool>`. Core's hourly `dependabot-merge` job arms squash auto-merge for
  a patch or minor update in every addon; a major waits for review under the `major` label. Every other pin sits in the
  vendored `tools/toolchain.json`, which core's daily `bump-toolchain` workflow moves; a major it proposes also waits
  for review.
  A `package` job runs the pinned BigWigs packager
  with `args: -d -z` (no upload) and `tools/check_package.py` (`forever_tools.package`) on its output: every file a
  TOC or XML loads and every `Interface\AddOns\<addon>\` path is in the zip, no `tests`, `tools`, `types`, `docs`,
  `ruff.toml`, `stylua.toml` or dot file (`.agents`, `.luacheckrc`) ships, every packaged folder ships a licence file (LICENSE, LICENCE, COPYING or UNLICENSE), THIRD_PARTY.md
  and the WFA-10 and WFA-31 credits sections ship with text under them, and the smoke spec passes on the packaged
  folder. `tools/doctor.py`
  (`forever_tools.doctor`) checks a machine against every pin in the vendored `tools/toolchain.json` and
  `tools/pyproject.toml` and prints a fix for each problem; AGENTS.md lists it under Commands.
- **WFA-16** Releases: a signed `v*` tag runs `release.yml` (BigWigs packager, pinned) with this
  version's CHANGELOG entry as notes (`tools/changelog.py`), uploading to GitHub, CurseForge and
  Wago; the TOC carries `X-Curse-Project-ID` and `X-Wago-ID`. Setup is in `wow-addon-publish`.
  Release prep starts by translating every phrase added since the last tag into each shipped locale (WFA-34):
  `tools/check_locales.py` lists each locale's coverage, and `--release` fails until every shipped locale is back at
  100%.
- **WFA-17** Every repo has a lean `AGENTS.md` declaring this pack by its link on forever-core `main`, never a
  commit SHA, so every repo reads the latest standards. Headless specs pass on builds that are broken in game, so a change
  to anything the player sees or to combat behaviour is verified live in game before it merges, and
  the PR says what was checked. Agents run that check themselves in the headless client
  ([in-game.md](in-game.md), whose hard rules bound every session: interface only, short, human pace); [debugging.md](debugging.md) covers taint, profiling and reading
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
  The client-call lint is one: every published addon runs the vendored `tools/lint_client_calls.py`
  (`forever_tools.client_calls`) from its own `tools/typecheck.sh`, refusing a call of a client function the Forever
  client does not have, which type-checks against the retail annotations and then fails in game.
- **WFA-30** Values the client may return as secrets (unit GUIDs and names, tooltip unit data) are read
  through the repo's one helper, `ns.Readable` (the value, or nil when it is secret), and every tooltip hook
  returns first when `ns.Usable(tooltip)` is false (nil or forbidden). Both live in a small file with no other
  addon state (Adventure Guide Forever's `Core/Secret.lua`), so it copies across the family as is. `tools/lint_secret.py` (`forever_tools.readable`) runs in `typecheck.sh`
  and refuses an unguarded read unless its line says why it is safe (`-- secret-ok: reason`).
- **WFA-37** Only what the client defines loads. A font object (`CreateFontString`'s third argument,
  `SetFontObject` and its button forms, XML `inherits=`, `font=` and `style=`) is one the Forever client's UI defines
  or the addon defines itself: the client has `GameFontNormalLarge` but no `GameFontLarge`, and a missing one errors
  on every login. A settings page title uses `GameFontHighlightHuge`, as Blizzard's own pages do. A TOC never lists
  `Bindings.xml`: the client loads it by itself, and listed it logs one warning per binding. `tools/check_client_load.py`
  and its font list `tools/blizzard_fonts.txt`, vendored from forever-core, run in the required `core-shared` job of
  every repo.
- **WFA-31** `THIRD_PARTY.md` lists every input: what it is, where its pin lives (the constant in `tools/`, never
  a copied value that a data refresh would leave stale), its licence, and whether it ships in the zip or is
  build-only. An embedded library (LibStub and the like) ships with its licence and is credited there; every
  `move-folders` folder ships a licence file of its own (public-domain code such as LibStub carries it in its
  header). Media made for the addon (icons, textures) is named as the addon's own, with the script that draws it. Its
  credits are two Markdown tables, each `| Who | What | Notes |`: `## Players` names each player who reported a bug,
  asked for a feature, translated the addon or changed its code, and `## Inspired by` names each addon or project an
  idea came from. One row is one shipped contribution (one report fixed, one idea built, one translation, one code
  change): a player with five shipped items has five rows with the same `Who`, in table order, never one row whose
  `What` joins several with a semicolon. The `What` cell is the short outcome line a player reads in game, roughly
  eight words and no channel or issue number: "A darker tracker background", not "Asked on CurseForge for ...". Where
  they asked, the channel (CurseForge, Discord), and the issue number go in `Notes`, which never reaches the game.
  `Who` and `What` are what the in-game Thanks page shows, so a link in `Who` keeps only its visible text.
  `tools/forever_tools/credits.py` reads exactly those two sections into `Data/Credits.lua` for
  `ForeverCore.Credits`; a missing section is an empty list, and nothing is inferred from a row's words. The same run
  keeps one sentence, "Thanks to A, B and everyone who reported a bug or asked for a feature.", between
  `<!-- forever-credits:start -->` and `<!-- forever-credits:end -->` in README.md's `## Credits` and in
  docs/curseforge.md, naming every `## Players` name once, in rank order (most rows first, then table order); a store
  page without the markers is left alone,
  while `--check` fails a README without them. Add `Data\Credits.lua` to the TOC and pass `ns.Credits` to
  `ForeverCore.Credits.Register` once the addon loads, so the in-game Thanks page shows it; `Line(addonTitle)` gives
  the addon's own settings page its short thanks.
  `tools/check_package.py` fails a zip without THIRD_PARTY.md, one of those credit sections or README's `## Credits`.
- **WFA-32** README.md and docs/curseforge.md each carry the family block, "The Forever addons", once,
  between `<!-- forever-family:start -->` and `<!-- forever-family:end -->`, in place of any hand-written list of
  the other addons. The table has three columns: the addon linked to its CurseForge page, what it does, and an
  Issues link to `https://github.com/cjber/<repo>/issues`. A line under the table says bug reports, feature
  requests and pull requests are welcome on each addon's GitHub, and that everyone whose report or idea ships is
  thanked by name on the Thanks page in game, in the store page and in the changelog, unless they ask not to be. The
  text is
  `forever_tools.family` and never edited in a repo: `tools/check_family.py` runs in `typecheck.sh` and fails on any
  difference (`--fix` rewrites it after a sync, `--print` gives it to place). Prose outside the block says only what
  a sibling really adds to this addon. ForeverCore is the shared library the addons require, so the table gives it no
  row.
- **WFA-33** A player who reported a bug we fix, asked for a feature we build, translated the addon or changed its
  code is credited by name in the same PR, whether they wrote on GitHub or in store comments: the changelog bullet
  ends "thanks to X for the report" (or "for the idea"), and THIRD_PARTY.md's `## Players` table gains a row for what
  came of it, one row per shipped contribution (WFA-31). When the reporter has a GitHub account, the fixing commit
  also carries `Co-authored-by: <login> <<id>+<login>@users.noreply.github.com>` (the id from
  `gh api users/<login> --jq .id`), so GitHub shows them as a contributor; a store or Discord reporter gets the
  changelog and `## Players` credit only. Use the handle they posted under; an anonymous store handle (`user_` and
  random characters) gets the table's generic thanks instead. Praise, and requests that weren't built, are not
  credited. The addons' author, cjber, is never credited: not in a changelog bullet, THIRD_PARTY.md, release notes,
  README, store copy or the in-game Thanks page. Only other players are credited. A player who asks not to be named,
  in any issue, store comment or Discord, is removed from every addon's `## Players` table, the README and store
  thanks blocks (regenerate them) and the changelog lines that thank them (replace the name with "a player"), and
  their name is added to `credits_opt_out.txt` in forever-core so no later sweep re-adds them; `credits.py` fails
  while a `THIRD_PARTY.md` row names one. The org PR template (`cjber/.github`) carries the checklist line
  `- [ ] A reporter or requester is credited in the changelog bullet and THIRD_PARTY.md (WFA-33)`.
- **WFA-33a** An issue filed from a CurseForge comment carries one line of its own, `CurseForge thread <id> (<addon>)`,
  so ForeverCore's `docs/handoff/cfwatch.py` can read which thread waits on the fix: `--unanswered` marks that thread as
  waiting on the issue and its state, and `--due` lists it with the release once every linked issue is fixed and shipped,
  unless the owner has already replied after that release.
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
