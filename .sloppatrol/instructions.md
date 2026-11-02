# About the code

ForeverCore is the Lua 5.1 library the WoW: Forever addons vendor: the tracker host, the error report
and the family files. The files the TOC lists are what the game loads; `tests/*_spec.lua` load them in
that order inside a stubbed client.

- A change here reaches every addon on the next `tools/sync_consumers.py`, so keep the public surface
  (`ForeverCore`, `/fcore`, the namespaces the addons read) exactly as it is unless the change is about
  that surface.
- Every consumer's vendored copy has to match: `python3 tools/check_consumers.py` is a check here for a
  reason, and it fails when a shared file changes without the sync.
- Never replace a Blizzard global, hook a secure function, or write a field on a Blizzard table.
- `tests/tracker_host_spec.lua` runs Blizzard's real tracker source, fetched at a pinned revision; it
  is not part of the default spec loop and needs `TRACKER_UI_ROOT`.
- Never launch the game, Battle.net, Lutris or Wine, and never use the network.
