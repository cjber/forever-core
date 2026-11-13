# forever_tools

(Beside it, [forever_sim/](forever_sim/README.md) is the shared headless client for scenario tests, vendored as
`tools/forever_sim/` with its own `sync.py`.)

Offline, stdlib-only Python (3.10+) shared by the WoW: Forever addon repos. Each repo vendors
`forever_tools/` byte for byte as `tools/forever_tools/`; `MANIFEST.json` holds a sha256 per file and
the producer commit the copy came from.

The same sync also copies core's `tools/toolchain.json` (every tool pin, with how to find its newer version),
`tools/pyproject.toml` and `tools/uv.lock` (ruff, ty, zizmor, actionlint-py and Pillow as a `[dependency-groups] dev`
group) to the repository's `tools/`, because the vendored `tools/typecheck.sh`, `tools/forever_sim/gen_script_types.py`
and `tools/forever_tools/doctor.py` read them. They sit under `tools/`, the folder every addon's `.pkgmeta` already
ignores, so vendoring a development file never changes what a release ships or invalidates a recorded visual proof.
The scripts name a tool, never a version: CI's `cjber/forever-core/.github/actions/toolchain@<sha>` reads this
repository's own `tools/toolchain.json` through its `manifest` input, so the tools it installs are the ones those
scripts check for even when Dependabot moves the action's SHA and the sync moves the file in separate pull requests.
Core's daily `bump-toolchain` workflow moves the pins, and Dependabot updates the actions and the uv group; a major
version that either one proposes waits for review.

## Modules

| Module | Does |
|---|---|
| `lua` | Lua 5.1 lexer (`tokenize`, `Token`, `LuaSyntaxError`) |
| `toc` | TOC and nested XML traversal, orphan Lua check per addon `runtime_dirs`, LuaLS coverage gate |
| `identity` | One in-game identity icon per addon: the TOC's `X-Forever-Icon` is a client icon in the pinned build, and no shipped Lua repeats it |
| `multivalue` | `select()` and multi-return expansion lint; `Rules` carries the addon's policy |
| `art` | Art lint (WFA-27): raw texture, atlas and markup calls outside the addon's art helper files need an `art-ok` reason |
| `readable` | Secret-value lint (WFA-30): `UnitGUID`, `UnitName` and tooltip data reads go through the `Readable` guard, tooltip hooks check `IsForbidden`; `Policy` names the guard and safe units |
| `client_calls` | Client-call lint: every bare global the runtime files call (`Name(...)`) and every `C_X.Y` they read exists in `client_names.txt` (generated in forever-core from the pinned Blizzard UI source and an optional probe dump), a Lua 5.1 or WoW global from the pinned annotations, a global the addon or ForeverCore defines, or a global function the addon's `tools/client_optional.txt` declares for an addon in its `## OptionalDeps`; a method call and a plain read are not calls and are not checked; a deliberate exception carries `-- client-ok: <reason>` |
| `pkgmeta` | The files a checkout's `.pkgmeta` ships, with the packager's own `ignore` and `plain-copy` rules: a directory entry becomes `entry/*`, a missing one matches file and directory, and dot paths are always pruned |
| `visual_proof` | The actual-client visual proof gate: the source runtime digest (TOC graph, Core pin and packaging policy), the canonical packaged runtime digest (`.pkgmeta` selection plus the packager's line endings and TOC version), the checkout-to-installed comparison, its fail-closed token check, and the exact pull request base commit (event SHA, or the PR's base through the API when the payload has none) |
| `package` | The packaged-zip check: TOC/XML-loaded files and addon paths present, no development folders, a licence file (LICENSE, LICENCE, COPYING or UNLICENSE) in every folder and THIRD_PARTY.md ship, README's `## Credits` and THIRD_PARTY's `## Players` (or the older `## Ideas and contributors`) ship with text under them, the ForeverCore pin, `.pkgmeta` external and TOC field agree, no widget method that takes parameters is passed straight as a script handler, specs pass on the packaged files |
| `widget_handlers` | The script-handler lint: a `SetScript`/`HookScript` handler that is a widget's own client method read taking parameters (`edit.HighlightText`, `frame["SetText"]`) rather than a function the addon wrote fails, with the wrapping closure as its fix; a method that declares none (`frame.StopMovingOrSizing`) ignores the handler's arguments and passes. The method set comes from `widget_methods.txt`, generated in forever-core by `tools/gen_widget_methods.py` from the pinned Ketho API annotations |
| `core_pin` | The release gate: a consumer's ForeverCore pin (`tools/forever-core.txt`) names core's latest published GitHub release, and the `.pkgmeta` external and `## X-Forever-Core:` name the same tag; `--latest` fails closed when that release cannot be read, and an addon with no external is exempt only from the bundle comparison |
| `doctor` | Every tool pin in the vendored `tools/toolchain.json` and `tools/pyproject.toml` checked on this machine, each problem with its fix |
| `screens` | `docs/screenshots/scenes.sha256`: each image's hash beside its scene dump's, and the CI check for a stale image |
| `editorconfig` | The family `.editorconfig` template and its check against `stylua.toml` and `ruff.toml` |
| `locales` | The translation check (WFA-34): every `Locales/<locale>.lua` parses, is loaded by the TOC, uses only the template's keys and keeps English's placeholders and escapes; prints each locale's coverage |
| `family` | The shared "The Forever addons" block and its check in `README.md` and `docs/curseforge.md` |
| `credits` | The in-game credits data (WFA-31): reads `THIRD_PARTY.md`'s `## Players` and `## Inspired by` tables into `Data/Credits.lua`, keeps the thanks sentence in README.md and docs/curseforge.md, and `--check` fails a stale file or block |
| `changelog`, `release_check`, `latest_build` | Release gates and the newest Forever build: `release_check` needs the commit's full CI push run on main and its green `headless-smoke` commit status, which `forever_client.py smoke` posts |
| `docs_contract` | The API docs check: every function `Core/API.lua` publishes is named in `docs/api.md` as `Name(`, and the API table's `minor` appears in its history |
| `csvtable`, `wago` | Strict DB2 CSV parsing and cached, validated downloads |
| `fsio` | `atomic_write`, and `publish` for multi-output generators (stage all, replace, roll back on failure) |
| `luadata`, `report` | Read generated Lua tables; the semantic change report |
| `generated` | The fresh-then-offline generated-data gate, its two passes run at once, and `data_report` |
| `specs` | Every `tests/*_spec.lua` under LuaJIT in parallel, reported in glob order with each spec's time |
| `sync` | `check`, `update`, `pin`, `manifest` |

A repo's `tools/*.py` entry points stay thin (`changelog.py`, `release_check.py`, `lint_art.py`,
`lint_multivalue.py`, `lint_secret.py`, `typecheck_coverage.py`, `check_package.py`, `check_screenshots.py`,
`check_editorconfig.py`, `check_family.py`, `check_locales.py`, `check_store_page.py`, `doctor.py`) and add only per-addon policy such as `RUNTIME_DIRS`.

The packaged-zip check runs in its own CI job, after the pinned packager builds without uploading:

```yaml
  package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<sha> # pinned as the repo's other jobs
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: cjber/forever-core/.github/actions/toolchain@<sha> # pinned as the repo's other actions
        with:
          tools: lua
      - run: printf 'Package check\n' > .release-notes.md # .pkgmeta's manual-changelog
      - uses: BigWigsMods/packager@<sha> # the release workflow's pin
        with:
          args: -d -z
      - run: python3 tools/check_package.py
```
Addon-specific generators and hints stay in the repo.

## Change and update

1. Edit here and run `python3 -m unittest discover -s tests -t .` and `ruff format . && ruff check .`.
2. `python3 forever_tools/sync.py manifest`, commit, note the commit.
3. In each repo, from a clean producer checkout at that commit:
   `python3 tools/forever_tools/sync.py update --source <producer checkout>`.
   `update` deletes a module the producer dropped or renamed, so update the repo's entry points in the same sync.
   `check` runs offline in `typecheck.sh` and fails on any edited, missing or extra file or an unpinned
   manifest; `check --source <checkout>` also compares with the producer.
