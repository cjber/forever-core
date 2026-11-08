# About the app

ForeverCore is the shared library the WoW: Forever addons vendor: the tracker host, the error report
and the family files. It is Lua 5.1 and cannot run outside the game client, and this patrol never starts
it (see the rules below). What runs here is its headless harness.

- `tests/<name>_spec.lua` stubs the client API and loads the files the TOC lists, in order. Run one
  with `luajit tests/<name>_spec.lua`; a failing spec exits non-zero and prints the failed assertion.
- `tests/tracker_host_spec.lua` is the native integration spec: it runs Blizzard's real objective
  tracker source, which `python3 tools/fetch_tracker_ui.py` fetches at a pinned revision into an
  ignored cache. Run it with `TRACKER_UI_ROOT=<that cache> luajit tests/tracker_host_spec.lua`. If the
  source is not fetched, say so rather than treating the failure as a bug.
- `python3 tools/check_consumers.py` checks that every consumer's vendored copy matches this repo.
- `luacheck <file>` lints a file.

Every change here reaches the addons, so a regression is worth more than a finding in an addon: report
a spec that fails, an error a spec prints, or a behaviour a spec shows that the change does not intend.

## Sign in

No sign-in.

## Important flows

- Registering and rendering the shared tracker section: after `PLAYER_ENTERING_WORLD` and
  `VARIABLES_LOADED`, deferred one frame.
- The error report: what it captures, what it redacts, and what `/fcore` shows.
- The family block shared between README.md and docs/curseforge.md.

## Never do these things

- Never start the game, Battle.net, Lutris or Wine. The headless client (forever-core's `wow-forever-addon/in-game.md`) tests the build linked into the game, not this checkout, so in-game checks belong to the agent that ships a change.
- Never edit, move or delete files.
- Never use the network.
- Never copy Blizzard's source into the repo: the fetch tool writes it to an ignored cache.
