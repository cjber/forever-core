# Publishing shared Forever Core changes

Forever Core is the authority for every byte-identical file listed in `adoption.md`. Shared changes land here first;
consumer copies are updated with `tools/sync_consumers.py` and shipped by the consumer addons so standalone installs
continue to work without a dependency.

## Release order

1. Open the core change against `main`. Run core CI and merge when it is green.
2. Sync the five consumer checkouts from core and open one PR per changed consumer. Each consumer's CI is the gate.
3. Merge green consumer PRs, then release Forever Core and each consumer whose packaged files changed.
4. The scheduled core drift workflow checks consumers after they adopt. Each consumer's scheduled drift workflow checks
   its own files against `forever-core/main`.

Publish commits and releases through Nebula's GitHub flow, which supplies the linked user's verified identity and
canonical attribution. Do not add manual signing flags or signoff trailers.

## What stays true

- Consumers remain standalone and vendor the shared files; Forever Core stays optional.
- `ForeverCore.toc` keeps all five consumers in `OptionalDeps` so core adopts the tracker column they load first.
- Core's scheduled check does not run on push, because consumers adopt on their own release schedules.
