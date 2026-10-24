# forever_tools

(Beside it, [forever_sim/](forever_sim/README.md) is the shared headless client for scenario tests, vendored as
`tools/forever_sim/` with its own `sync.py`.)

Offline, stdlib-only Python (3.10+) shared by the WoW: Forever addon repos. Each repo vendors
`forever_tools/` byte for byte as `tools/forever_tools/`; `MANIFEST.json` holds a sha256 per file and
the producer commit the copy came from.

## Modules

| Module | Does |
|---|---|
| `lua` | Lua 5.1 lexer (`tokenize`, `Token`, `LuaSyntaxError`) |
| `toc` | TOC and nested XML traversal, orphan Lua check per addon `runtime_dirs`, LuaLS coverage gate |
| `multivalue` | `select()` and multi-return expansion lint; `Rules` carries the addon's policy |
| `taint` | Taint lint; `Policy` carries the map openers, frames and getters (`C_Map.OpenWorldMap` is the safe call) |
| `art` | Art lint (WFA-27): raw texture, atlas and markup calls outside the addon's art helper files need an `art-ok` reason |
| `readable` | Secret-value lint (WFA-30): `UnitGUID`, `UnitName` and tooltip data reads go through the `Readable` guard, tooltip hooks check `IsForbidden`; `Policy` names the guard and safe units |
| `package` | The packaged-zip check: TOC/XML-loaded files and addon paths present, no development folders, a licence file (LICENSE, LICENCE, COPYING or UNLICENSE) in every folder and THIRD_PARTY.md ship, README's `## Credits` and THIRD_PARTY's `## Ideas and contributors` ship with text under them, specs pass on the packaged files |
| `doctor` | Every tool pin in `ci.yml` and `typecheck.sh` checked on this machine, each problem with its fix |
| `screens` | `docs/screenshots/scenes.sha256`: each image's hash beside its scene dump's, and the CI check for a stale image |
| `editorconfig` | The family `.editorconfig` template and its check against `stylua.toml` and `ruff.toml` |
| `locales` | The translation check (WFA-34): every `Locales/<locale>.lua` parses, is loaded by the TOC, uses only the template's keys and keeps English's placeholders and escapes; prints each locale's coverage |
| `family` | The shared "The Forever addons" block and its check in `README.md` and `docs/curseforge.md` |
| `changelog`, `release_check`, `latest_build` | Release gates and the newest Forever build |
| `csvtable`, `wago` | Strict DB2 CSV parsing and cached, validated downloads |
| `fsio` | `atomic_write`, and `publish` for multi-output generators (stage all, replace, roll back on failure) |
| `luadata`, `report` | Read generated Lua tables; the semantic change report |
| `generated` | The fresh-then-offline generated-data gate and `data_report` |
| `sync` | `check`, `update`, `pin`, `manifest` |

A repo's `tools/*.py` entry points stay thin (`changelog.py`, `release_check.py`, `lint_taint.py`, `lint_art.py`,
`lint_multivalue.py`, `lint_secret.py`, `typecheck_coverage.py`, `check_package.py`, `check_screenshots.py`,
`check_editorconfig.py`, `check_family.py`, `check_locales.py`, `doctor.py`) and add only per-addon policy such as `RUNTIME_DIRS`.

The packaged-zip check runs in its own CI job, after the pinned packager builds without uploading:

```yaml
  package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<sha> # pinned as the repo's other jobs
        with:
          fetch-depth: 0
          persist-credentials: false
      - run: sudo apt-get update && sudo apt-get install -y luajit
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
