# Testing an addon in the real client

Agents test in game with `tools/headless/forever_client.py` from the `forever-core` checkout. It runs the
WoW: Forever client under gamescope's headless backend: the game renders on the GPU into a display of its own, so
nothing appears on the player's desktop and their mouse and keyboard are never touched. Every verb acts on that
display only.

## Hard rules

The client exists to test the Forever addons' interface. These rules hold for every session, and the tool enforces
them where it can:

1. **Interface only.** Open and close frames, click addon UI, send slash commands, `/reload`, take screenshots,
   read SavedVariables and Lua errors. Never move the character, target, fight, loot, quest, trade, chat to other
   players or use the auction house. `slash` sends only the Forever addons' own commands (read from their `SLASH_`
   globals) and `/reload`, `/rl`, `/fstack`, `/etrace`; `key` sends only Return, Escape and BackSpace; there is no
   free typing; `click` refuses until a `shot` was taken after the last input, so each click aims at UI you have
   just read in the frame.
2. **Short sessions.** Log in, test, log out. Every ending, whether the test returns, fails, is cancelled or hits
   the 30 minute cap, types `/quit` so the character logs out, then stops the client. Prefer `run -- <script>` so
   the session lasts only as long as the test.
3. **Human pace.** Inputs are at least 1.5 s apart across invocations and slash commands type at 120 ms a key.
   Never loop inputs: take a shot, read it, decide the next action.

## One client at a time

There is one Battle.net account, so one client. `up` holds an exclusive lock for its session and refuses to start
while anything runs in the Wine prefix, which includes the player's own game: it fails with the reason and exits 2.
Another agent's session makes it fail too, unless `--wait` queues behind it. When the player is in game, the test
waits for them; a PR then lists its `/reload` steps for the player instead.

## A session

```sh
FC=~/drive/proj/wow/forever-core/tools/headless/forever_client.py
python3 $FC up            # run in the background; prints READY once in the world (about 1 to 3 min)
python3 $FC shot          # prints the PNG path; read it to see the frame
python3 $FC click 960 540 # points in the 1920x1080 frame, on UI from the last shot
python3 $FC key Escape    # Return, Escape or BackSpace
python3 $FC slash "/fgf"  # a Forever addon's own command
python3 $FC reload        # /reload, returns once the world is back
python3 $FC errors --addon FieldGuideForever   # reload, then this session's Lua errors (exit 1 when any)
python3 $FC sv FieldGuideForever               # SavedVariables as of the last reload
python3 $FC down          # logs out, stops gamescope and every Wine process, removes the dev addon link
```

`run -- <command>` does `up`, runs the command with `FOREVER_CLIENT_DISPLAY` set, and logs out and stops the client
whatever the command returns. Stopping `up` with SIGTERM or Ctrl-C, or the 30 minute cap, ends it the same way.

## What it relies on

- The addon under test is the build linked into `_forever_/Interface/AddOns`: rebuild the `test-artifacts` link
  first, as the workspace `AGENTS.md` says.
- `!!ForeverHeadless`, linked in only for the session, takes a screenshot each time the world loads; that file is
  the sign the client is in the world.
- The Wine environment comes from `~/.config/forever-client/env.json`. `capture-env` records it from a client Lutris
  started, and is needed again only when the Lutris runner changes.
- The launcher logs in on its own and Enter at the character list enters with the last character. A timeout
  prints the last frame's path: a login form or an update prompt there needs the player.

## Scope

Scripted input to a logged-in client may count as botting under Blizzard's terms; the player accepted that for
testing their own addons only. The hard rules above are that boundary.
