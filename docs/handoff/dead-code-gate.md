# Brief: a dead-code gate in CI for every suite repo

Owner asked: "make sure our CI finds and removes all dead code too, across all repos".

## What CI already catches (measured 2026-10-26, all nine repos)

- `luacheck .` is green everywhere: 0 warnings, 0 errors. That already covers unused locals (211), unused
  arguments (212), unused loop variables (213), unused values (311-313) and unreachable code (511 and friends).
  The only exemptions are `212/_.*` and `212/self`, which are deliberate.
- `ruff check tools` is clean everywhere for F401/F811/F841. forever-core has one `--unsafe-fixes`-only finding.

So do not rebuild those. The gate has to cover what luacheck and ruff structurally cannot see.

## The four gaps, and what to do about each

1. **Namespace members nobody references.** `function ns.X()` / `ns.X = function` where the repo never reads
   `ns.X`. A scan found exactly seven: AGF `Rebuilding`, skillup `DetailsBarTop`, Field Guide `GetErrors` and
   `ClearErrors`, atlas `OnReady`, `GetErrors`, `ClearErrors`. Adjudicate each by hand before enforcing:
   `OnReady` is a lifecycle hook the loader calls dynamically and is NOT dead; `GetErrors`/`ClearErrors` may be
   a deliberate public reporting API shared with forever-core's `UI/Report.lua`. Keep an explicit allowlist file
   (`tools/deadcode-allow.txt`, one `path:symbol` per line with a reason) so a real dynamic-dispatch symbol
   never has to be re-argued.
2. **Lua files the TOC never loads.** Every `.lua` in the addon tree that no `.toc` names. Today the only hits
   are `types/` LuaLS annotation stubs, which are not shipped by design: exclude `types/`, `tests/`, `tools/`,
   `docs/`, `.agents/`, `Nav/` and treat everything else as a failure.
3. **Media references and unreferenced files.** Check references in every `.lua`, `.xml` and `.toc` against files
   under `media/`, accepting both slash styles and WoW's extensionless texture names. Report a missing referenced
   file as well as a `.tga` or `.blp` with no reference. This specifically prevents a repeat of the legacy-forever
   #186 incident: `tools/deadcode.py` treated `media\\Shade` in `UI/Completion.xml` as dead, which removed live UI
   art and broke `check_package`; the matcher must normalize both separators before checking references. Icon.tga is
   referenced only from the TOC, so the TOC has to be part of the search.
4. **Python modules no entrypoint reaches.** `tools/*.py` that nothing imports and that is not a documented
   entrypoint (a `__main__`, a CI step, or a workflow `run:` line). CI steps are in `.github/workflows/*.yml`,
   so parse those too or the gate cries wolf.

## Deliverable

- `tools/deadcode.py` in forever-core: the four checks above, `--check` (exit 1 with file:line, CI mode) and a
  short report. No `--fix` that deletes Lua: report only, deletions stay a reviewed change.
- Vendored to every consumer through `tools/sync_consumers.py` (add it to `VENDORED` with the full consumer
  list) and to the consumers' `check_core_shared.py` expectation, so drift stays caught.
- A `deadcode` job in each repo's `.github/workflows/ci.yml`, next to the existing `check` job: plain
  `python3 tools/deadcode.py --check`, ubuntu, no extra installs (standard library only, do not depend on Pillow).
- Remove what it proves dead in the same round: the two dead TGAs, the two adjudicated namespace members that
  are not dynamic dispatch. Keep every test green.

## Rules

- Absence of a reference is not proof of death. Anything reached by string, by the client, or by another addon
  goes in the allowlist with its reason, not in the bin.
- Do not touch `types/`, `Nav/`, `.types/`, `tools/.cache/`.
- Conventional commits, no `-s`. CI green before you open the PR; report which repos the job was added to.
