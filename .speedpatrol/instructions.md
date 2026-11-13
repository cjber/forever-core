# About the app

ForeverCore is the Lua 5.1 library the WoW: Forever addons vendor. The game cannot run here, so the
benchmarks run the headless harness: the specs stub the client API and load the files the TOC lists, in
order, and `tools/check_consumers.py` compares every consumer's vendored copy against this repo.

- Keep a change only when it speeds up a file the addons load, or the gate itself.
- Every change must pass the full gate in `AGENTS.md` under "Commands", with lua-language-server and
  stylua first on `PATH`, at the versions `toolchain.json` pins.
- `tests/tracker_host_spec.lua` needs Blizzard's tracker source, fetched by
  `python3 tools/fetch_tracker_ui.py`; it is not part of the timed suite.
- Vendor changes out with `python3 tools/sync_consumers.py`, then one PR per consumer.
- Never use the network, and never start the game, Battle.net, Lutris or Wine. The headless client (forever-core's `wow-forever-addon/in-game.md`) tests the build linked into the game, not this checkout, so in-game checks belong to the agent that ships a change.
