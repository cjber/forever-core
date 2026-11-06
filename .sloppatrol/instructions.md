# About the code

ForeverCore is the Lua 5.1 library the WoW: Forever addons vendor: the tracker host, the error report
and the family files. The files the TOC lists are what the game loads; `tests/*_spec.lua` load them in
that order inside a stubbed client.

- A change here reaches every addon on the next `tools/sync_consumers.py`, so keep the public surface
  (`ForeverCore`, `/fcore`, the namespaces the addons read) exactly as it is unless the change is about
  that surface.
- The files `tools/check_core_shared.py` lists are vendored byte for byte into the consumers, which
  adopt a change through their own sync PRs. There is no consumer check here: it reads the other
  repos' main branches, so it goes red whenever a consumer lags and says nothing about a refactor.
- Never replace a Blizzard global, hook a secure function, or write a field on a Blizzard table.
- `tests/tracker_host_spec.lua` runs Blizzard's real tracker source, fetched at a pinned revision; it
  is not part of the default spec loop and needs `TRACKER_UI_ROOT`.
- The paths mirror a consumer repo on purpose: a shared file stays at the path its vendored copy has, so the copy
  is a pure copy. Moving one breaks every consumer's spec.
- `Expose.lua` publishes the public `ForeverCore` table and `/fcore`, and loads last; `UI/TrackerLock.lua` loads
  before the tracker host.
- Never launch the game, Battle.net, Lutris or Wine, and never use the network.
