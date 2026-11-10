# About the code

ForeverCore is the Lua 5.1 library the WoW: Forever addons vendor: the tracker host, the error report
and the family files. The files the TOC lists are what the game loads; `tests/*_spec.lua` load them in
that order inside a stubbed client.

- A change here reaches every addon on the next `tools/sync_consumers.py`, so keep the public surface
  (`ForeverCore`, `/fcore`, the namespaces the addons read) exactly as it is unless the change is about
  that surface.
- The Forever addons require ForeverCore and call it through the `ForeverCore` global, so a change
  to that surface (`docs/adoption.md`) breaks every addon. The dev tooling `tools/check_core_shared.py`
  lists is vendored into the consumers; the Lua runtime is not.
- Never replace a Blizzard global, hook a secure function, or write a field on a Blizzard table.
- `tests/tracker_host_spec.lua` runs Blizzard's real tracker source, fetched at a pinned revision; it
  is not part of the default spec loop and needs `TRACKER_UI_ROOT`.
- The paths mirror a consumer repo on purpose: a shared file stays at the path its vendored copy has, so the copy
  is a pure copy. Moving one breaks every consumer's spec.
- `Expose.lua` publishes the public `ForeverCore` table and `/fcore`, and loads last; `UI/TrackerLock.lua` loads
  before the tracker host.
- Never use the network, and never start the game, Battle.net, Lutris or Wine. The headless client (forever-core's `wow-forever-addon/in-game.md`) tests the build linked into the game, not this checkout, so in-game checks belong to the agent that ships a change.
