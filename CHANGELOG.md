# Changelog

## 0.1.0

- **The shared tracker column becomes a repo of its own.** `UI/TrackerHost.lua`, `UI/TrackerLock.lua`,
  `UI/TrackerOrder.lua` and `UI/TrackerQuestie.lua` move here as the single source, with the specs that pin them
  (`tests/tracker_host_spec.lua` against Blizzard's own tracker source, and the lock, order and Questie specs). The
  four addons that draw sections vendor these files at the same paths, so nothing changes in game until an addon
  moves to a new core version.
- **ForeverCore is installable on its own.** `Core.lua` keeps the column's settings in `ForeverCoreDB`, `Expose.lua`
  publishes `ForeverCore` and `/fcore`, and the TOC lists the five Forever addons as `OptionalDeps` so an addon that
  already owns the column loads first and core adopts it rather than starting a second one.
- **Drift is a gate now.** `tools/check_consumers.py` fails when any consumer's copy differs from this repo, and
  `tools/sync_consumers.py` is the one command that moves a fix out to them.
