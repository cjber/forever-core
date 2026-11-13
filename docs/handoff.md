# Publishing ForeverCore changes

ForeverCore is the one copy of the suite's shared runtime. Runtime changes land here and ship with ForeverCore's own
release; every consumer requires it, so no consumer carries a copy to update. The development tooling in
`tools/check_core_shared.py`'s `VENDORED` map is still copied to the consumers with `tools/sync_consumers.py`.

## Release order

1. Open the core change against `main`. Run core CI and merge when it is green.
2. Release ForeverCore. The stores install it with the addons that require it, so players receive the change with the
   addon they already have.
3. Sync the consumers' development tooling from core and open one PR per changed consumer. Each consumer's CI is the
   gate.
4. The consumer drift workflows check their tooling against `forever-core/main` after they adopt.

Publish commits and releases through Nebula's GitHub flow, which supplies the linked user's verified identity and
canonical attribution. Do not add manual signing flags or signoff trailers.

## What stays true

- Every Forever addon declares `## Dependencies: ForeverCore`; ForeverCore loads first and no runtime file is copied.
- `.pkgmeta` lists ForeverCore under `required-dependencies`, so CurseForge and Wago install it automatically.
- Core's scheduled check does not run on push, because consumers adopt tooling changes on their own release schedules.
