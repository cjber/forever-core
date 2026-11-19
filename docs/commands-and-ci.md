# Commands and CI reference

The full command list and CI description. `tools/gate` is the fast subset.

## Commands

```sh
luacheck .
stylua --check .
python3 .agents/skills/wow-forever-addon/tooling/forever_tools/specs.py   # every spec, in parallel
python3 tools/fetch_tracker_ui.py && TRACKER_UI_ROOT=tools/.cache/tracker-ui luajit tests/tracker_host_spec.lua
TRACKER_UI_ROOT=tools/.cache/tracker-ui luajit tests/tracker_reflow_spec.lua
bash tools/typecheck.sh                   # LuaLS and the WoW API annotations at tools/toolchain.json's pins
python3 tools/check_consumers.py          # every consumer's tooling, ForeverCore pin and packaging match this repo
python3 tools/check_client_load.py        # every font object exists in the client; no TOC lists Bindings.xml (WFA-37)
python3 tools/check_menu_scroll.py        # a menu built from a list scrolls (WFA-36)
python3 tools/check_core_name.py          # the shared addon is ForeverCore, one word, in every text file
python3 tools/check_api_docs.py           # docs/api.md names every published API function and its minor
python3 tools/check_assets.py             # legacy chrome by name and by FileDataID age
python3 tools/export_markers.py --check   # media/Numbers holds the step markers tools/marker_source draws
python3 tools/gen_legacy_chrome.py        # regenerate the asset checker's pinned-build data
python3 tools/gen_widget_methods.py       # regenerate the widget-method data from the pinned API annotations
python3 tools/bump_toolchain.py --dry-run # every pin tools/toolchain.json holds, against its recorded upstream
python3 tools/dependabot_merge.py --dry-run # Dependabot's open PRs in core and every consumer, no changes
python3 tools/gen_forever_api.py          # regenerate forever_tools/client_names.txt from the pinned UI source
python3 tools/lint_client_calls.py        # refuse a call of a client function the Forever client does not have
python3 tools/forever_perf.py             # the !!DevPerf and !!DevSmoke session report
# The forever_client.py lines below are for the `wow in-game` agent only; every other agent sends it an INGAME
# request (wow-forever-addon/in-game.md#requesting-a-check).
FOREVER_CLIENT_CALLER=in-game python3 tools/headless/forever_client.py job --max 600 -- tools/headless/perf_run.sh  # bounded exclusive profiling job
FOREVER_CLIENT_CALLER=in-game python3 tools/headless/forever_client.py job --hyprland --max 600 -- COMMAND  # exclusive nested Hyprland job for deskpilot
FOREVER_CLIENT_CALLER=in-game python3 tools/headless/forever_client.py lease     # ensure the session, print a token; each verb takes and releases the lock
FOREVER_CLIENT_CALLER=in-game python3 tools/headless/forever_client.py smoke --repo forever-core --ref main  # the release's headless-smoke status
FOREVER_CLIENT_CALLER=in-game python3 tools/headless/forever_client.py proof --repo R --ref SHA --checkout PATH --flow "update notice=/lf"
                                          # record the checkout's .visual-proof.json from a client session
python3 tools/headless/forever_client.py attest --repo R --ref SHA --checkout PATH
                                          # the same from the user's passed checklist round, without the client
python3 tools/released_consumers.py      # every consumer's latest release, unpacked under tools/.cache/released
python3 tools/suite_load.py --released -v # this candidate ForeverCore with those released builds, under forever_sim
python3 tools/smoke_queue.py --dry-run    # the commits the smoke timer would load in the client next
python3 tools/sync_consumers.py ..        # copy this repo's development tooling into local checkouts
python3 tools/sync_curseforge.py ..       # check CurseForge descriptions match docs/curseforge.md (--push publishes)
python3 tools/check_package.py            # .release/ForeverCore holds every loaded file, no development folder,
                                          # and no widget method that takes parameters passed as a script handler
uv run --project tools --frozen --group dev ruff check tools &&
uv run --project tools --frozen --group dev ruff format --check tools
uv run --project tools --frozen --group dev python -m unittest discover -s tools -p "test_*.py"
```

`tests/tracker_host_spec.lua` is the native integration spec: it runs Blizzard's real objective-tracker source, fetched
at a pinned revision by `tools/fetch_tracker_ui.py`, against this host. `tests/tracker_reflow_spec.lua` runs the same
source to check that a client event or another frame moving never moves the column, that an Edit Mode move of the game
tracker carries it through the anchor alone, and that only a dirty section rebuilds. `tests/sim/jitter795_scenario.lua`
is the #795 loop under forever_sim (`luajit .agents/skills/wow-forever-addon/tooling/forever_sim/run.lua -v
--only=jitter795`): 0 column moves while the section heights swing. The other tracker specs stub everything and run anywhere. `tests/api_spec.lua` loads the TOC in order,
registers two fake addons and checks the public API.


## CI

`.github/workflows/ci.yml` runs on every PR and push to main: `deadcode`, `check` (luacheck, the specs, the native
tracker spec, StyLua, ruff, the `tools/` unit tests, `tools/changelog.py --check` against the `v*` tags), `typecheck`,
`project-rules` (the client load rule and the menu rule), `visual-proof`, `released-consumers` (this checkout with every
consumer's latest released build, under forever_sim), `packaged`, `secrets` and `workflows` (actionlint and zizmor over
`.github` and the consumer workflow template).
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
they are. The `released-consumers` job runs `python3 tools/suite_load.py --released` on every PR and push instead:
`tools/released_consumers.py` unpacks each consumer's latest release and the scenario loads this checkout with those
builds, so a core that would break an addon already on the stores fails here. After the exercise the scenario asks
`ForeverCore.Registered` for every addon in the suite, in every mode, so a consumer whose startup check refused this
core fails too even though it raised no Lua error. `release.yml` runs the same check again
for the exact release candidate, before it packages anything.


## Load order

`ForeverCore.toc` loads the module files, then `Expose.lua` last. Consumers declare `## OptionalDeps: ForeverCore`, so
the client loads ForeverCore before them when it is installed and exactly one copy of each shared file runs; without
it, the consumer still loads and its vendored `Core/ForeverRequire.lua` says what is missing. `ForeverCore.toc` has no
`OptionalDeps`: it does not adopt anything built by another addon.
