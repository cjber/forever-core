# AGENTS.md

ForeverCore is the shared library under the WoW: Forever addon suite (Interface 16001). It is its own addon,
`ForeverCore`, and every Forever addon requires it with `## Dependencies: ForeverCore`. It owns the one objective-tracker
column the suite docks into, the grip and Lock switch that move it, the section order that stacks them, the Questie and
EQOT bridges that keep the column out from under another tracker's quest list, the report and issue windows, the error
journal and debug log, the minimap button, the world map quest log tabs, the settings-page chrome and the Forever
addons page. It is GPL-3.0-or-later.

## The two rules that matter

1. **This repo is the only copy of the shared runtime.** Nothing here is addon specific. Runtime files load once, from
   ForeverCore, and a consumer reads them through the `ForeverCore` table and `ForeverCore.Register`. Never copy a
   runtime file into a consumer, and never bend one toward a single addon: everything addon specific arrives through
   `Register` or the module API. Kiln Forever keeps its addon under `addon/KilnForever/`; `CONSUMER_ROOT` in
   `tools/check_core_shared.py` records that folder for the development tooling the consumers still receive.
2. **The shared files keep their consumer-visible paths.** Suite convention is flat Lua at a consumer repo's root; this
   repo keeps `UI/TrackerHost.lua`, `Core/SafeCall.lua` and the rest at the paths consumers name in their docs and
   specs, so a consumer's `loadfile("UI/TrackerHost.lua")` still finds core's own source when its spec loads it here.

## Commands

```sh
luacheck .
stylua --check .
python3 .agents/skills/wow-forever-addon/tooling/forever_tools/specs.py   # every spec, in parallel
python3 tools/fetch_tracker_ui.py && TRACKER_UI_ROOT=tools/.cache/tracker-ui luajit tests/tracker_host_spec.lua
bash tools/typecheck.sh                   # LuaLS and the WoW API annotations at tools/toolchain.json's pins
python3 tools/check_consumers.py          # every consumer's tooling, ForeverCore pin and packaging match this repo
python3 tools/check_client_load.py        # every font object exists in the client; no TOC lists Bindings.xml (WFA-37)
python3 tools/check_menu_scroll.py        # a menu built from a list scrolls (WFA-36)
python3 tools/check_core_name.py          # the shared addon is ForeverCore, one word, in every text file
python3 tools/check_api_docs.py           # docs/api.md names every published API function and its minor
python3 tools/check_assets.py             # legacy chrome by name and by FileDataID age
python3 tools/gen_legacy_chrome.py        # regenerate the asset checker's pinned-build data
python3 tools/gen_widget_methods.py       # regenerate the widget-method data from the pinned API annotations
python3 tools/bump_toolchain.py --dry-run # every pin tools/toolchain.json holds, against its recorded upstream
python3 tools/dependabot_merge.py --dry-run # Dependabot's open PRs in core and every consumer, no changes
python3 tools/gen_forever_api.py          # regenerate forever_tools/client_names.txt from the pinned UI source
python3 tools/lint_client_calls.py        # refuse a call of a client function the Forever client does not have
python3 tools/forever_perf.py             # the !!DevPerf and !!DevSmoke session report
python3 tools/headless/forever_client.py run -- tools/headless/perf_run.sh  # one profiled session in the headless client
python3 tools/headless/forever_client.py smoke --repo forever-core --ref main  # the release's headless-smoke status
python3 tools/headless/forever_client.py proof --repo R --ref SHA --checkout PATH --flow "update notice=/lf"
                                          # record the checkout's .visual-proof.json from a client session
python3 tools/smoke_queue.py --dry-run    # the commits the smoke timer would load in the client next
python3 tools/sync_consumers.py ..        # copy this repo's development tooling into local checkouts
python3 tools/sync_curseforge.py ..       # check CurseForge descriptions match docs/curseforge.md (--push publishes)
python3 tools/check_package.py            # .release/ForeverCore holds every loaded file, no development folder,
                                          # and no widget method that takes parameters passed as a script handler
uv run --project tools --frozen --group dev ruff check tools &&
uv run --project tools --frozen --group dev ruff format --check tools
python3 -m unittest discover -s tools -p "test_*.py"
```

`tests/tracker_host_spec.lua` is the native integration spec: it runs Blizzard's real objective-tracker source,
fetched at a pinned revision by `tools/fetch_tracker_ui.py`, against this host. The other tracker specs stub everything
and run anywhere. `tests/api_spec.lua` loads the TOC in order, registers two fake addons and checks the public API.

## Layout

- `Core.lua`: ForeverCore's own install of the host's settings (`ns.TrackerHostSettings`), the one `ADDON_LOADED`
  handler that makes `ForeverCoreDB`, and the hooks that attach core's journal and log and run the tracker migration.
- `Expose.lua`: the public `ForeverCore` table (`API = 2`), its modules, `Register`, `/fcore` and `/forever debug`; the
  last file the TOC loads, because it publishes what the modules built.
- `Core/SafeCall.lua`: one global error handler for every registered addon, attributing by `AddOns/<name>/`; the
  per-addon context's `SafeCall`, `RecordError`, `CaughtErrors` and journal live here.
- `Core/Log.lua`: the structured log and its 200-line saved ring per addon, the one `/forever debug` switch and the
  lines the report copies. `/forever debug on` starts the client-log capture and `/forever debug off` restores it.
- `Core/Capture.lua`: the client-log capture behind `/forever debug on`: it saves the previous `taintLog` and
  `advancedCombatLogging` CVars and the chat and combat logging switches in `ForeverCoreDB.debugCapture`, turns them
  on the way `!!DevSessionLog` does, and puts them back on `/forever debug off` or at the next login (`PLAYER_ENTERING_WORLD` with `isInitialLogin`; a reload keeps it). The originals are
  saved only on the first change, so a reload never records the capture's own values.
- `Core/Performance.lua`: the report's performance section: every loaded addon that depends on ForeverCore gets the
  `C_AddOnProfiler` metrics and its memory, with the all-addon and application figures above them. It is read once
  when the report window opens, never sampled in the background.
- `Core/OpenMap.lua` and `Core/OpenSettings.lua`: core's shared openers for the client's restricted world map and
  settings panel functions, each run through `CreateSecureDelegate`, never in combat. They are runtime files, published
  as `ForeverCore.OpenMap` and `ForeverCore.OpenSettingsPanel`, not vendored into any consumer.
- `UI/Art.lua`: the icon helper the report window draws its portrait with, and `Art.CooldownIcon`, which gives any
  icon texture the client's Cooldown Manager frame.
- `UI/Report.lua`: the per-addon report window and issue composer, bound to the addon's icon, version and `X-Website`.
  Its text carries the performance table from `Core/Performance.lua` and, while debug capture is on, the line that
  names the client's `Logs` folder and how to stop the capture.
- `UI/ForeverFamily.lua`: the Forever addons settings page and link windows, in core's L.
- `UI/Credits.lua`: the **Thanks** page the Forever addons page opens: every addon's `ns.Credits` merged by player
  name into one compact row per player, with every addon's line on hover and a short **Inspired by** group, a
  dropdown that filters the page to one registered addon, and the one-line thanks an addon's own settings page shows.
- `Data/Credits.lua`: core's own generated credits, from `THIRD_PARTY.md`'s `## Players` and `## Inspired by` tables;
  `Expose.lua` registers it under **ForeverCore**. `THIRD_PARTY.md` also feeds the one-sentence thanks between the
  `forever-credits` markers in README.md's `## Credits` and in `docs/curseforge.md`.
- `UI/TrackerHost.lua`: the private tracker column, its optional tooltip-art backdrop and opacity, its layout, combat
  and Edit Mode handling, and the one-time migration from a consumer's old tracker settings.
- `UI/ContextMenu.lua`: the suite's one context menu, drawn in its own frame because Blizzard's menu can assert on
  this client build; its own frames do not taint the gamepad interface's focus as Blizzard's menu does.
- `UI/TrackerLock.lua`: the grip and the Lock switch, which load before the host.
- `UI/TrackerOrder.lua`: the section order (`uiOrder`, then attach order).
- `UI/TrackerQuestie.lua`, `UI/TrackerEqot.lua` and `UI/TrackerEllesmere.lua`: another tracker's quest list, so the
  column steps beside it.
- `UI/TrackerQuests.lua` and `Core/QuestOrder.lua`: core's own optional quest list and its pure ordering.
- `UI/QuestLogTabs.lua`: the shared world map quest log side tab, stacking every addon's panel tab by order,
  restoring the client's own pages on demand and telling a panel through `shown` when it becomes visible or stops
  being visible, so panels set no OnShow or OnHide script under the map.
- `UI/ProfessionTabs.lua`: the shared side tab for addon pages in the Professions window, stacking every addon's tab
  under the client's own in registration order, handing the window back on a client tab or page, and keeping the
  window at one width for every profession and tab.
- `Core/RetiredLeaderboards.lua`: the no-op `ForeverCore.Leaderboards` and `ForeverCore.PeerStats.New` answers an older
  addon release still calls unguarded while it loads. They keep a login from raising a Lua error, store nothing, register
  no addon-message prefix and send nothing. Remove the file once no supported release calls those members.
- `Core/APIKit.lua`: the shape every addon's own public API follows, published as `ForeverCore.APIKit`: `Hub` for a
  next-frame change dispatch, `NotReady` and `Invalid` for the two `nil, reason` answers, and `Publish` and `Addons`
  for the suite's published API list. `docs/api-conventions.md` is the convention, `docs/api.md` is ForeverCore's own
  page for third-party authors, and `tools/check_api_docs.py` checks an addon's `Core/API.lua` against its
  `docs/api.md`.
- `Core/MinimapButton.lua`: the one minimap ring; each addon draws one button.
- `Core/Text.lua`: the shared search fold and ranking.
- `UI/SettingsPage.lua`: the settings canvas; `Register(name, build, L)` reads every label and tooltip through the
  calling addon's L, and carries the debug-capture notice while `/forever debug on` is active.
- `UI/MapCanvas.lua`: read-only drawings on the world map, with each addon's markers keyed on its name.
- `Locales/`: core's own phrases in enUS and the nine shipped locales. A consumer keeps its own locale file for its own
  copy; the phrases here are the only ones core owns.
- The suite's ownership boundaries live in `docs/handoff/boundaries.md`, with the rest of the suite notes in
  `docs/handoff/`. Read `docs/handoff/boundaries.md` before assigning a feature or moving code between addons.
- `tools/check_core_shared.py`: the development-tooling map (`VENDORED`), the per-consumer addon folder
  `CONSUMER_ROOT`, and the consumer-side check, vendored into every consumer. In a consumer it compares its copies with
  core main; with `--base REF` it checks only the vendored files `REF...HEAD` changes, so a hand edit fails a PR while a
  lag behind core does not.
- `tools/toolchain.json`: the single manifest of every pin Dependabot cannot read: the LuaJIT commit, Lua 5.1.5 and its
  sha256, luacheck, argparse and luafilesystem commits, LuaLS, StyLua and gitleaks versions with their release asset
  URL and sha256, the Ketho API annotations commit, the speedpatrol npm package, and the Python, Node and Bun runtime
  versions the `setup-*` actions take. Each entry's `upstream` records how to find a newer version (a GitHub release,
  tag or branch head, or npm), which is all `tools/bump_toolchain.py` needs to move it; `series` restricts a pin to
  the line it tracks, so `lua51` stays on 5.1 with a `note` saying why (the client is Lua 5.1), while `node` may
  propose a newer major for review. It sits under `tools/` with the project below, the folder `.pkgmeta` already
  ignores, so vendoring it never changes a package selection or a recorded visual proof. Consumers vendor it because
  their `tools/typecheck.sh`, `tools/forever_sim/gen_script_types.py` and `tools/forever_tools/doctor.py` read it.
- `tools/pyproject.toml` and `tools/uv.lock`: ruff, ty, zizmor, actionlint-py and Pillow (the wowmock tests draw
  images) as a `[dependency-groups] dev` group, run from the repository root as
  `uv run --project tools --frozen --group dev <tool>`, which keeps uv's environment at `tools/.venv`. Not a package
  (`[tool.uv] package = false`); the lock is generated by `uv lock --project tools`, and Dependabot's `uv` ecosystem
  is its only owner, so the bump-toolchain workflow never runs `uv lock --upgrade`.
- `tools/check_client_load.py`: the client load rule, vendored with its font list `tools/blizzard_fonts.txt`: every
  font object the addon's Lua or XML inherits is one the client's UI or the addon defines, and no TOC lists
  Bindings.xml. Regenerate the list from the pinned Blizzard UI source with
  `python3 tools/check_client_load.py --blizzard-ui ../wow-handoff/blizzard-ui`; `tools/test_check_client_load.py` is
  its spec.
- `tools/check_menu_scroll.py`: the menu rule, vendored into every consumer: a menu description that gets entries in a
  loop calls `SetScrollMode` in the same function, or the loop says why it stays short (`-- menu-scroll-ok: <reason>`).
  It reads Lua through the skill pack's `forever_tools/lua.py` lexer; `tools/test_check_menu_scroll.py` is its spec.
- `tools/check_core_name.py`: the name rule, vendored into every consumer: the suite's shared addon is ForeverCore, one
  word. The full read scans every text file but shipped `CHANGELOG.md` history; `--base REF` scans only the lines
  `REF...HEAD` adds, so a new two-word spelling fails in a changelog entry while history stays untouched. It never
  matches the `forever-core` repository slug, and `tools/test_check_core_name.py` is its spec.
- `tools/gen_legacy_chrome.py`: regenerates the shared checker's pinned-build data from the wago.tools listfile for
  1.60.1.70124. `tools/check_assets.py` is the entry point over this repo; the age rule lives in
  `.agents/skills/wow-forever-addon/tooling/forever_tools/assets.py`, and `tools/test_check_assets.py` is its spec.
- `tools/gen_widget_methods.py`: regenerates `forever_tools/widget_methods.txt`, every method the client's API
  annotations declare on a widget class that takes a parameter, from the Ketho vscode-wow-api checkout
  `tools/typecheck.sh` pins. The vendored `forever_tools/widget_handlers.py` uses it to fail a `SetScript`/`HookScript`
  whose handler is a widget's own method read that takes parameters (`edit.HighlightText`) instead of a function the
  addon wrote; a method that declares none (`frame.StopMovingOrSizing`) ignores the handler's arguments and passes.
  Every consumer's package job runs it over the packaged files, and `tools/test_gen_widget_methods.py` keeps the data
  matching the pin.
- `tools/gen_forever_api.py` and `forever_tools/client_names.txt`: the Forever client's callable names, generated
  from the same pinned Blizzard UI source the simulator fetches (`forever_sim/fetch.py`, one pin). The file holds
  every documented `C_X.Y` and global function, every global function Blizzard's UI Lua defines, every bare global
  that UI calls and every `C_X.Y` it reads, documented or not. Global tables, named frames, strings, colors and
  constants are not callable, so they stay out: a plain read of one is not a nil call, and a method call on a frame is
  never checked. `tools/forever_probe_api.lua` is the `ForeverProbeDB.api` table of the client dump ForeverProbe writes
  in forever-dev, committed as data on build 1.60.1.70938 and merged by every run; `--probe ForeverProbe.lua` merges a
  newer dump instead. It is the one source for a real client function neither the documentation nor Blizzard's UI
  names, and its build is recorded in the header. `--check` fails when the committed file differs from a fresh
  generation, and the `check` CI job runs it that way. Regenerate the file after the UI pin moves or a probe table is
  refreshed; never hand-edit it.
- `forever_tools/client_calls.py` and `tools/lint_client_calls.py`: the client-call lint, vendored into every
  published addon and run by each addon's own `tools/typecheck.sh` beside LuaLS, because LuaLS checks against the
  retail `vscode-wow-api` annotations and this client lacks some of those functions. Every bare global the runtime
  files call (`Name(...)`, which is where `attempt to call a nil value` comes from) and every read of `C_X.Y`
  must be in `client_names.txt`, a Lua 5.1 or WoW global the pinned annotations define, or a global the addon or
  ForeverCore defines (assigned, a `CreateFrame(type, "Name")` frame, a frame one of ForeverCore's three naming
  helpers builds from the addon's string, an XML `name=`, or a TOC `## SavedVariables`). A method call
  (`Name:Method(...)`) makes the global a table, and a plain read of a string, table or constant is neither: neither is
  checked. An addon whose global comes from an optional dependency declares it in
  `tools/client_optional.txt`, one `Name  OwningAddonFolder` line per global function it calls, and the folder must be
  in the root TOC's `## OptionalDeps` (exact, `client-optional-folder` otherwise); a declared name it never calls fails
  (`client-optional-unused`). A deliberate exception carries `-- client-ok: <reason>`; a waiver that excuses nothing
  fails (`client-waiver-unused`). `tools/test_gen_forever_api.py` and the tooling's `test_client_calls.py` are the
  specs.
- `tools/core-shared-drift.yml`: the drift workflow each consumer keeps under `.github/workflows/`, running the client
  load rule, the menu rule, the name rule and the tooling check on every PR (`--base`) and on a schedule. Its
  `core-shared` job is required in every consumer. It lives outside `.github/workflows` so it never runs here; the
  `workflows` CI job lints it.
- `tools/dependabot-consumer.yml`: the Dependabot config every consumer gets as `.github/dependabot.yml`. Core's
  own `.github/dependabot.yml` adds the `uv` ecosystem at `/tools`, which a consumer does not need because its
  `tools/pyproject.toml` and `tools/uv.lock` are vendored. Dependabot's PRs are merged by core's one
  `.github/workflows/dependabot-merge.yml`, not by a workflow in each addon.
- `tools/dependabot_merge.py`: the central auto-merge behind that workflow. For forever-core and every consumer it
  lists Dependabot's open pull requests over REST, reads each head commit's Dependabot trailers, and arms squash
  auto-merge only when every dependency in the pull request is a `semver-patch` or `semver-minor` update; one
  `semver-major` anywhere leaves it for review with the `major` label, and so does a message it cannot read. A pull
  request left for review also has auto-merge taken back, so a force-pushed major cannot land on an earlier patch
  decision. It runs
  hourly with `CONSUMER_SYNC_TOKEN`, a PAT, because a merge enabled with `GITHUB_TOKEN` creates no push run on main
  and `tools/release_check.py` releases only a commit with a green CI push run; a Dependabot-triggered run cannot
  read Actions secrets either. The consumer list comes from `check_core_shared.VENDORED` and
  `sync_consumer_prs.consumer_repos`, never a second list. `tools/test_dependabot_merge.py` runs it over recorded
  REST JSON.
- `tools/bump_toolchain.py`: moves every `tools/toolchain.json` pin to its newest upstream release, one day after it
  was published, downloading and hashing an entry's asset whenever it holds a `sha256`. A newer major is proposed like
  any other update, but `--publish` arms auto-merge only when no pin crosses a major version; otherwise the PR waits
  for review with the `major` label and auto-merge taken back. A branch head move (LuaJIT, the Ketho annotations) is
  always minor.
  `--dry-run` prints the plan and writes nothing; `--publish` commits the staged `tools/toolchain.json` through
  GitHub's signed-commit API and opens or refreshes the `toolchain-bump` PR with the `dependencies` label.
  `tools/test_bump_toolchain.py` runs it over recorded upstream JSON, with no network.
- `.github/actions/toolchain`: the one composite action that installs a tool pin, reading the calling repository's
  `tools/toolchain.json` through its `manifest` input, which defaults to that file and resolves against the workspace,
  so the pins a job installs are the ones the same checkout's `tools/typecheck.sh` and
  `tools/forever_tools/doctor.py` check for. Kiln Forever, whose copies sit under its addon folder, names
  `addon/KilnForever/tools/toolchain.json` through that input. The caller checks out first. Its `tools` input is a
  space-separated subset of `lua` (LuaJIT, the PUC Lua 5.1.5 compiler `luac5.1` and interpreter `lua5.1`, luacheck,
  built from the pinned commits by `build.sh`), `luals`, `stylua` and `gitleaks` (`install.sh` downloads the entry's
  asset and verifies its sha256). Each tool is cached under a key hashed from its manifest entry and from the contents
  of `build.sh` and `install.sh`, so a bump and a change to either script move the cache with the pin, and `verify.sh`
  checks the installed version afterwards. It also outputs the manifest's Python, Node and Bun versions for the
  `setup-*` actions. Consumers call it by SHA, replacing their apt, curl and pipx lines.
- `tools/check_consumers.py`, `tools/sync_consumers.py`: the tooling gate and its fix, both reading the map above.
  Beyond the file copies, the gate checks each consumer once: its `tools/forever-core.txt` must name core's latest
  release tag (the GitHub API, or with `--local` this checkout's newest `v*` tag), and a consumer whose root TOC lists
  ForeverCore in `## Dependencies` must ship it in its own zip (`externals:` at the pin and
  `move-folders:` `<package-as>/ForeverCore: ForeverCore`), must not also list `- forevercore` under
  `required-dependencies:`, and must carry `## X-Forever-Core: <pin>` in that TOC, the tag a sibling addon compares.
  The pin, the external and the TOC field are compared by `forever_tools/core_pin.py`, whose `--latest` form also
  requires the pin to name cjber/forever-core's latest published GitHub release, read with `GH_TOKEN` or
  `GITHUB_TOKEN` when either is set. It fails closed when that release cannot be read. The package job runs it in every
  consumer as part of `tools/check_package.py`, and `tools/sync_consumers.py` inserts the same gate directly above the
  packager in each consumer's `release.yml`, so a commit that moves one copy without the others, or a core release that
  lands between CI and the upload, fails before a player is downgraded. This gate also checks that each published
  consumer's `release.yml` still runs the pin step directly above its packager, so a hand edit cannot reopen it. That
  job also runs `forever_tools/widget_handlers.py` over the packaged files, so a widget method that takes parameters
  passed straight as a script handler fails before it can reach a player. `.github/workflows/drift.yml` runs the
  checker on a schedule only, so a core change never blocks on consumer release timing.
- `tools/sync_consumer_prs.py`: the automatic tooling sync behind `.github/workflows/sync-consumers.yml`. On every push
  to main, and again from the release workflow once a release is published (a tag a workflow creates with
  `GITHUB_TOKEN` fires no push event), it derives the consumers from `VENDORED` plus the live repositories that vendor
  `tools/forever_tools/` or `tools/forever_sim/`, runs the same syncs as `sync_consumers.py`, regenerates each
  consumer's `Locales/phrases.txt` when it has `tools/phrases.py`, and moves each consumer's `tools/forever-core.txt`
  pin to core's latest release when it lags (one API read per run, and a failed read leaves the pins alone). Every run
  also rewrites that consumer's `.pkgmeta` ForeverCore external and `## X-Forever-Core:`, and, when the consumer ships
  core and its latest released tag bundles a core different from the pin, adds a marked `CHANGELOG.md` release entry
  (above a marked entry whose own tag is already released), then the run creates the signed commit through the GraphQL
  `createCommitOnBranch` mutation and opens or updates an auto-merging PR in each consumer. An open sync PR is updated
  in place: the sync runs on that PR's own head, so a commit pushed to it (a recorded visual proof, say) stays on the
  branch, and a PR the sync cannot update that way is left untouched with a comment saying why. It needs the
  `CONSUMER_SYNC_TOKEN` secret; without it the job prints a notice and stays green. A sync PR that changes runtime
  files or moves the pin cannot record the visual proof itself, so the run prints the `forever_client.py proof`
  command for that PR's head and the release session runs it and commits `.visual-proof.json`.
  `tools/test_sync_consumer_prs.py` is its spec.
- `tools/release_consumers.py`: the automatic consumer release behind `.github/workflows/release-consumers.yml`, on a
  20-minute schedule. For each consumer it reads main's head and that commit's `CHANGELOG.md`; when the newest
  `## [X.Y.Z]` entry carries `<!-- forever-core-sync -->`, its tag does not exist, no `release.yml` run is queued or
  running, no `release.yml` run at that head has already failed, `ci.yml` on that head is green and the newest
  `headless-smoke` status on that head is `success`, it dispatches the consumer's `release.yml` with the version and
  commit. A commit the smoke has not reached yet is reported as waiting and retried by the next run, never as failed; a
  consumer whose release already failed at main's head is reported as failed, so the job goes red instead of retrying
  every 20 minutes, and the maintainer fixes it and dispatches by hand.
  Every core release therefore re-releases every consumer, whose zips all carry the same `ForeverCore` folder. It is
  dispatch-only and idempotent. `CONSUMER_SYNC_TOKEN` needs Actions write on the consumers; without the secret the job
  prints a notice and stays green. `tools/test_release_consumers.py` is its spec.
- `tools/headless/forever_client.py`: the one way an agent touches the client (`wow-forever-addon/in-game.md`). `up`,
  `run`, `shot`, `slash`, `errors` and the rest act on a private gamescope display only, one session at a time. Its
  `build-dev REPO REF` writes `test-artifacts/<repo>-dev` for a hand link, with the code the workspace's
  `rebuild-dev.sh` used to carry, and `smoke --repo R --ref SHA` builds the commit a release would ship, links its
  addon folders (recording each slot so it is put back exactly, store installs included), runs `/forever selftest` and
  `errors --addon` per folder, and posts the result as the `headless-smoke` commit status. `proof --repo R --ref SHA
  --checkout PATH --flow NAME=SLASH_OR_LUA_FILE` builds and links the same way, reloads, runs each flow (a Forever
  addon's slash command or a Lua file through `!!DevSmoke`), takes a screenshot after each, uploads the PNGs to a new
  secret gist, and writes `<checkout>/.visual-proof.json` from `visual_proof --digests` with full-SHA raw URLs and
  sha256s before running `visual_proof --compare` against the installed build; it never commits or pushes the
  checkout, and there is no default flow because ForeverCore has no shared opener for an addon's update notice. Exit 3
  means the client is in use and nothing was posted or recorded. A stop that ran no handler leaves that record behind,
  and the next `up`, `run`, `smoke`, `proof` or `build-dev` replays it before it touches AddOns.
  `tools/test_forever_client.py` is its spec.
- `tools/smoke_queue.py`: for forever-core and every consumer, the commit the next release would ship (`main`'s head,
  read as `tools/release_consumers.py` reads it) that has no `headless-smoke` status, smoked one at a time and stopped
  at the first exit 3 so it never queues behind the player. `tools/systemd/forever-smoke.service` and
  `forever-smoke.timer` run it every 30 minutes at `Nice=10`; `in-game.md` says how to install them.
  `tools/test_smoke_queue.py` is its spec.
- `tools/devsmoke/!!DevSmoke`: the `!!DevSmoke` dev addon behind `/forever selftest`, linked into the client from
  this checkout. It opens and closes every loaded addon that depends on ForeverCore (read from the client, so a new
  addon is covered with no list to update) and the world map, saving a pass or fail per surface in `DevSmokeDB`,
  which `tools/forever_errors.py` and `tools/forever_perf.py` read. A snippet from `tools/devsmoke/eval.py FILE` is
  written to the gitignored `!!DevSmokeInbox` folder inside it, linked into AddOns as a load-on-demand addon of the
  same name, and run under `xpcall` at login and on `/devsmoke eval` (its `print` output and returns go to the Agent
  tab and `DevSmokeDB.eval`). The client reads the inbox once a session, so a snippet written after that needs
  `/reload`. `tests/devsmoke_spec.lua` is its spec, `tools/test_devsmoke_eval.py` the writer's.
- `tools/discord_digest.py`: the Discord release digest, with pure payload builders over GitHub releases and
  `CHANGELOG.md` data and a thin fetch and post layer. `.github/workflows/discord-digest.yml` posts hourly on the
  schedule only; `tools/test_discord_digest.py` is its spec.
- `tools/release_check.py` and `tools/changelog.py`: the release gate (the commit's full CI run on main and its green
  `headless-smoke` status, which a missing or pending one makes wait and a failed one names) and the version's
  CHANGELOG notes, both thin wrappers over the skill pack's `forever_tools`.
- `types/`: LuaLS declarations. `types/ForeverTracker.lua` is the tracker contract; `types/Forever.lua` holds the
  `ForeverCoreAPI`, `ForeverCoreAddon` context and the modules' classes; `types/Client.lua` is the client API core
  reads. `tools/typecheck.sh` checks every Lua file outside `tests/`, `tools/`, `docs/` and `.agents/` against them;
  CI installs LuaLS at `tools/toolchain.json`'s version and sha256, and the script refuses any other version.

## CI

`.github/workflows/ci.yml` runs on every PR and push to main: `deadcode`, `check` (luacheck, the specs, the native
tracker spec, StyLua, ruff, the `tools/` unit tests, `tools/changelog.py --check` against the `v*` tags), `typecheck`,
`project-rules` (the client load rule and the menu rule), `packaged`, `secrets` and `workflows` (actionlint and zizmor
over `.github` and the consumer workflow template).
`.github/workflows/forever-tools.yml` and `.github/workflows/forever-sim.yml` test the skill pack's tooling on every PR,
with no path filter, so they can be required checks. Every PR job runs on `ubuntu-24.04`, and every tool it installs
comes from `tools/toolchain.json` through `.github/actions/toolchain`: `build.sh` builds LuaJIT, the PUC Lua 5.1.5
compiler and interpreter and luacheck from the pinned commits, `install.sh` downloads LuaLS, StyLua or gitleaks at the
pinned version and verifies its sha256, each tool is cached with `actions/cache` under a key hashed from its manifest
entry and from those two scripts, and the runner's apt mirror is never touched. The Python tools run from
`tools/pyproject.toml`'s `uv` group with `uv run --project tools --frozen`.
`.github/workflows/bump-toolchain.yml` runs `tools/bump_toolchain.py` daily and opens or refreshes one `toolchain-bump`
PR, and `.github/workflows/dependabot-merge.yml` runs `tools/dependabot_merge.py` hourly: a Dependabot patch or minor
gets squash auto-merge in core and every consumer, and a major waits for review with the `major` label.
Dependabot itself (`/.github/dependabot.yml`) updates the actions and the `uv` group daily with a one-day cooldown.
`.github/workflows/suite.yml` runs `tools/suite_load.py` daily and on demand (`gh workflow run suite.yml`): it clones
ForeverCore and every published addon's main and runs `tests/suite/suite_scenario.lua`, which loads ForeverCore first
with the addons that require it in one forever_sim client and calls `sim:exercise()`. It reads other repositories'
main, so it is not a PR job. Locally, `python3 tools/suite_load.py --root ..` runs it over the sibling checkouts as
they are.

## Agent skills

The suite-wide skills live here, in the one repo every addon already vendors from, so an addon repo carries only
what is specific to itself. Repo-specific skills (a repo's `release` checklist, its `tools/repo_rules.py`) stay
in that repo's `.agents/skills/`, never in `cjber/skills`; `cjber/skills` holds only skills that build repo-specific
logic out of a general rule.

| Skill | Load it when |
|---|---|
| `.agents/skills/wow-forever-addon/SKILL.md` | the shared standards pack (`WFA-*`), UI look, icon, docs, CI and release baseline |
| `.agents/skills/wow-addon-publish/SKILL.md` | publishing to CurseForge and Wago, or cutting a release |
| `.agents/skills/wow-retail-ui-style/SKILL.md` | drawing or auditing addon windows, frames and widgets |

Each addon declares `wow-forever-addon` under `## Standards` in its `AGENTS.md`, pinned to this repo. The pack's
tooling (`tooling/forever_tools`, `tooling/forever_sim`) is produced here and vendored byte for byte into the
consumers' `tools/`; edit it here, then run `sync.py update --source <this checkout>` in the consumer.

## Versions and releases

Every version needs a `CHANGELOG.md` entry before its `v*` tag. `.github/workflows/release.yml` waits for full CI on
the commit, checks it with `tools/release_check.py`, writes the version's notes with `tools/changelog.py`, and runs the
packager with `CF_API_KEY`, `WAGO_API_TOKEN` and `GITHUB_OAUTH`, so the GitHub release, CurseForge and Wago all get the
same words. A release preparation that edits the update notice or a locale records the visual proof its runtime change
needs with `python3 tools/headless/forever_client.py proof --repo <repo> --ref <sha> --checkout <tree> --flow
"update notice=<slash command or Lua file>"` and commits the `.visual-proof.json` it writes, so the required
`visual-proof` check passes without an admin merge; a sync PR that moves the ForeverCore pin runs the command its own
run prints. See `wow-forever-addon/in-game.md`. CurseForge is the published description and gallery; Wago is an upload
mirror with a fixed stub pointing at CurseForge. A core version bump reaches consumers through the stores, since they
require it; nothing is copied into them. Raise `ForeverCore.API` only when the public table or `Register` breaks.

## Load order

`ForeverCore.toc` loads the module files, then `Expose.lua` last. Consumers declare `## Dependencies: ForeverCore`, so
the client loads ForeverCore before them and exactly one copy of each shared file runs. `ForeverCore.toc` has no
`OptionalDeps`: it does not adopt anything built by another addon.
