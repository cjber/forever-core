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
python3 $FC eval /tmp/probe.lua                # write a snippet through !!DevSmoke, reload, print DevSmokeDB.eval
python3 $FC down          # logs out, stops gamescope and every Wine process, removes the dev addon link
```

`run -- <command>` does `up`, runs the command with `FOREVER_CLIENT_DISPLAY` set, and logs out and stops the client
whatever the command returns. Stopping `up` with SIGTERM or Ctrl-C, or the 30 minute cap, ends it the same way.

## Smoking a release commit

Every release, manual or automatic, needs a green `headless-smoke` commit status on the exact commit it ships.
`tools/release_check.py` refuses without one, so the status is the release's record of a client load; nothing is
written to a local file:

```sh
FC=~/drive/proj/wow/forever-core/tools/headless/forever_client.py
python3 $FC smoke --repo legacy-forever --ref <sha>   # build, lock, selftest, errors, logout, post the status
```

`smoke` builds that commit's dev archive under `test-artifacts/<repo>-smoke` the way `rebuild-dev.sh` did (the same
code, `forever_client.py build-dev <repo> <ref>`, writes `test-artifacts/<repo>-dev` for a hand link), points the
build's addon folders at it in `Interface/AddOns`, then runs `up`, `/forever selftest`, `errors --addon <folder>` for
each of the repo's addon folders, and `down`. It posts the result with
`gh api repos/cjber/<repo>/statuses/<sha> -f state=success|failure -f context=headless-smoke -f description=...`,
the error count or "clean". `--manual-launcher` is passed through to `up`, so while launcher OCR is not finding Play
(cjber/forever-core#547) an agent runs `smoke --manual-launcher` in the background, takes `shot`, and clicks Play
itself.

- Exit 0 is a clean commit and exit 1 a recorded failure.
- Exit 3 means the client cannot start: the player's game is running, or another agent's session holds it. Nothing is
  posted then, so a caller runs it again later.
- The AddOns folder is shared, so each slot is put back exactly as it was: a link at its own target, a store install
  moved back from `<folder>.smoke-backup`. The record of what it borrowed is `~/.local/state/forever-client/smoke-links.json`
  while the session runs, kept only if a restore could not finish.

`tools/smoke_queue.py` finds, for forever-core and every consumer, the commit the next release would ship (`main`'s
head) that has no `headless-smoke` status, and smokes them one at a time, stopping at exit 3 so the queue never fights
the player for the client. `python3 tools/smoke_queue.py --dry-run` lists them without starting anything.

Its timer is `tools/systemd/forever-smoke.timer`, every 30 minutes at `Nice=10`. Install it once, without editing
anything else:

```sh
mkdir -p ~/.config/systemd/user
cp ~/drive/proj/wow/forever-core/tools/systemd/forever-smoke.service ~/.config/systemd/user/
cp ~/drive/proj/wow/forever-core/tools/systemd/forever-smoke.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now forever-smoke.timer
```

`systemctl --user list-timers forever-smoke.timer` shows the next run, `systemctl --user start forever-smoke.service`
runs the queue now, and `journalctl --user -u forever-smoke.service` has its lines. The unit runs outside the desktop
session: it needs `gh` logged in without a prompt (put a token in an `EnvironmentFile` if the login lives in a
keyring), and the GPU and Wine prefix reachable from the user manager. A commit whose build or session fails is named
by the client tool and the queue moves on; the client being in use is the only reason it stops early.

## The Agent chat tab and /devsmoke

The dev addon `!!DevSmoke` prints short lines to a chat tab named **Agent**, made on first use with no channels, so
General stays clean and no line needs a `/run` long enough for the chat box's 255 character cut. Use these instead of
typing a long `/run` line:

| Command | What it does |
|---|---|
| `/devsmoke tab` | selects the Agent tab |
| `/devsmoke tab off` | goes back to General |
| `/devsmoke versions` | one line per loaded addon depending on ForeverCore, plus ForeverCore and LibAHTab: folder, Version metadata, loaded state |
| `/devsmoke errors` | this session's BugGrabber entries, leaving out the chat `/run` line's own errors: the count and the first 180 characters of each |
| `/devsmoke eval` | runs the snippet the inbox loaded this session; a snippet written after that first load needs `/reload` |
| `/devsmoke thanks <addon title> [player]` | opens the Thanks page filtered to the addon, scrolled to the named player's row |
| `/devsmoke prof <tab>` | opens the Cooking window when no profession window is open, then selects the addon's tab |
| `/devsmoke close` | hides the Thanks window, the Professions window, the world map and the Settings panel, so Escape is never pressed |

`/devsmoke` on its own still runs the same selftest as `/forever selftest`.

### Anything longer than one `/run` line

A chat `/run` line is cut at 255 characters, so a longer statement reaches Lua as half of itself and fills BugGrabber
with `')' expected near '<eof>'` and `'<name>' expected near '<eof>'`, which bury the addon errors you are looking
for. Write the snippet to a file and run it as an eval instead:

```sh
FC=~/drive/proj/wow/forever-core/tools/headless/forever_client.py
python3 $FC eval /tmp/probe.lua   # in a session: writes it, /reloads, prints DevSmokeDB.eval (exit 1 on failure)
```

With a session already running, the steps by hand are:

```sh
python3 tools/devsmoke/eval.py /tmp/probe.lua   # compile and write the inbox
python3 $FC slash "/devsmoke eval"              # the first eval this session loads and runs the inbox chunk
python3 $FC reload                              # saves DevSmokeDB.eval; a snippet written later needs this
python3 $FC sv '!!DevSmoke'                     # DevSmokeDB.eval: ran, ok, out, err
```

`eval.py` compiles the file with `luajit -bl` (and `luac5.1 -p` when it is installed) and refuses a parse error
before anything reaches the client. It writes the chunk into the gitignored `!!DevSmokeInbox` folder inside the linked
`!!DevSmoke` checkout, linked into AddOns as the load-on-demand addon of the same name; the snippet's line 1 is the
generated file's line 2, so an error naming `Eval.lua:6` is snippet line 5. The chunk runs at login and on
`/devsmoke eval`: what it prints and every value it returns go to the Agent tab in lines under 255 characters and
into `DevSmokeDB.eval`, and its errors are caught there instead of reaching BugGrabber.

The client reads the inbox once per session: the first `/devsmoke eval` or login loads it, and any snippet written
after that needs `/reload`. `forever_client.py eval` writes the file and reloads, so it always runs the snippet it
just wrote.

`DevSmokeDB.eval` is `{ ran = <time>, ok = <bool>, out = { <lines> }, err = <string|nil> }`, where `out` holds the
same lines the Agent tab showed. Use eval for anything longer than a one-line `/run`.

## What it relies on

- The addon under test is the build linked into `_forever_/Interface/AddOns`: rebuild the `test-artifacts` link
  first, as the workspace `AGENTS.md` says.
- `!!ForeverHeadless`, linked in only for the session, takes a screenshot each time the world loads; that file is
  the sign the client is in the world.
- The launch is the player's own: Faugus Launcher's Battle.net game, which runs `umu-run` with the game's Proton
  runner on the prefix `~/Games/battlenet`. `capture-env` records it into `~/.config/forever-client/env.json` while
  Battle.net runs from Faugus, and is needed again only when the game's runner in Faugus changes. One Wine build per
  prefix: a launch with another Wine logs Battle.net out.
- Battle.net needs the network, so run the tool outside the agent sandbox; `up` checks Battle.net is reachable
  before it starts anything.
- The launcher logs in on its own and opens the WoW: Forever page, but ignores the launch it was started with, so
  until the game starts `up` clicks Play every 15 s (`PLAY_BUTTON`, measured in the launcher window gamescope
  gives it; a launcher redesign moves it). Enter at the character list enters with the last character. A timeout prints the last frame's path: a login form or an update prompt there needs the player.

## Scope

Scripted input to a logged-in client may count as botting under Blizzard's terms; the player accepted that for
testing their own addons only. The hard rules above are that boundary.
