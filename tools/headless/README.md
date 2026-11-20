# Headless character configuration

`forever_client.py up`, `smoke` and `proof` read the launch record at
`$XDG_CONFIG_HOME/forever-client/env.json` (or `~/.config/forever-client/env.json`).
The record must contain the runner fields captured by `capture-env` and an owner-approved
character block:

```json
"character": {
  "name": "Barry",
  "guid": "Player-..."
}
```

The name and GUID prevent a proof from entering a different character. Where the character
stands does not matter: a check moves it wherever it needs (Hearthstone, Click-to-Move).
A missing or malformed block stops before the launcher starts. The
headless addon copy and its generated Lua configuration live only under the session state
directory and are removed during normal or stale-session cleanup.

Startup reads each launcher frame before clicking Play. The exact Battle.net label
`Installation Required` stops startup with the frame path and a message to update the
game in Battle.net. No dialog button is clicked. The page's `Upgrade Available` banner
advertises an account upgrade and does not stop startup.
Without a game process, startup allows two Play attempts, at least 15 seconds apart,
each requiring a fresh visible Play target, then fails with the frame path.

## Live safety

The version 2 pixel strip reports death or ghost state and combat or combat lockdown every
frame. Unknown API answers are unsafe. Jobs, Hyprland jobs, leases, proofs and smokes check
immediately after ensuring the session. Every input verb and each input send checks again, including
commands inside a job using `FOREVER_CLIENT_JOB`. Screenshots and status remain available. Error reads reload to flush SavedVariables and
are refused when unsafe. Reload and proof waits report a live safety refusal as soon as the strip shows it.

A second strip row, under the first, carries where the player stands: map, position, facing, the map's size in
yards, whether the player is indoors, where the target's nameplate is across the screen and whether the target is
within interact distance, as 16-bit fields closed by a checksum. `face X Y`, `face target`, `walkto X Y`, `walkto
target`, `where` and `park` read it after every step, so movement is a closed loop on the measured facing and
position rather than a timed key hold. `walkto` jumps forward once when blocked, then follows the obstacle, keeping
to the side that last got round, until a straight step runs free; when neither side gets round, or it starts going round
again where it already did, it stops and reports the position and the blocked headings. A job that moved the
character ends with `park`: a walk to the nearest spot recorded with `park --add LABEL` on that map
(`~/.config/forever-client/park.json`), which must be outdoors.

`slash` sends any one-line slash command, such as `/use Hearthstone`, and `key` sends any key,
including movement and keybinds. `click` and `slash` close a Game Menu left open rather than
refusing. Walking and opening or searching the auction house are allowed. Bidding, buying, posting,
fighting, resurrection and automatic recovery are forbidden. A refusal sends no recovery input.
An older resident addon or an unreadable safety strip is replaced through the guarded
session teardown path before reuse. Unknown safety still refuses input.

A `proof` flow given as a secure slash command (`--flow "route=/cast Cooking"`, or `/use`, `/click`, `/target`; the
words are `SECURE_SLASH_WORDS` in `forever_client.py`) cannot run from insecure Lua, so it is typed through the same
chat path as `slash` once the reload's world screenshot exists, then settles 3 s before the capture. It has no ready
check or eval result. Its `--flow-click` runs after that settle, inside the window the command opened (a tab in the
profession window, say), and settles again. Each flow reloads first, so a later Lua flow does not continue from its window.

Exit 3 means the player's client is in use. Exit 4 means live safety refused the operation:
`player is dead or a ghost`, `player is in combat`, or the version 2 safety protocol is
unavailable or outdated. Other client errors use exit 2.

## Shared commands

Run `lease --label NAME [--ttl S]` to ensure the resident session and print a token.
Use `FOREVER_CLIENT_JOB=TOKEN forever_client.py shot` (or `click`, `key`, `slash`,
`eval`, `reload`, `scroll` or `errors`) for each command. Each invocation takes
the job lock and releases it when it returns, allowing agents to interleave commands.
The client stays logged in between commands. Lease tokens last 600 seconds by default,
at most 1800 seconds. `release TOKEN` ends the lease, and session teardown ends all leases with a recorded
reason. Tokens are bound to the session that issued them. Expired, released or replaced
leases fail before queuing and require a new `lease`. Issuing a lease removes expired records.

Use `job --max S -- COMMAND` for work that needs exclusive access. The default limit
is 600 seconds and the maximum is 1800 seconds. At the limit the command's process
group receives SIGTERM, then SIGKILL after a short grace period. Commands inside the
job use its token without taking the lock again. Calling `down` inside that job
requests a stop and returns immediately; the session stops when the job ends.

`job` and `lease` reuse the resident session without `--wait`.
`serve --wait` queues for a separate session and reports the current holder,
its launch lifetime deadline and its idle deadline before waiting.

The session ends 60 minutes after the last job ended (or after READY when none has run) and 3 hours after launch.
The idle end never fires while a request is queued or a lease of the session is live; the lifetime cap always does.


## Hyprland job

Run an occasional exclusive deskpilot test from your Hyprland session:

```sh
python3 tools/headless/forever_client.py job --hyprland --max 600 --label deskpilot-95 -- bash /path/to/reproduce.sh
```

Serve holds the job lock while it logs out, replaces gamescope with a private nested
Hyprland, waits for the parked character in the world, runs the script, then logs out
and restores gamescope. The nested compositor opens only on the hidden
`special:forever-client` workspace. Its minimal configuration runs no user autostarts.
Install `Hyprland`, `hyprctl`, `grim`, `xdotool`, `xrandr` and deskpilot first.

The script receives `FOREVER_CLIENT_JOB`, `FOREVER_CLIENT_DISPLAY`, `DISPLAY`,
`XDG_RUNTIME_DIR`, `HYPRLAND_INSTANCE_SIGNATURE`, `WAYLAND_DISPLAY` and
`FOREVER_CLIENT_WINDOW` (the game window's Hyprland address). Deskpilot uses that
signature to load its plugin only in the nested compositor on its first input action.
You can run `deskpilot plugin load` first inside the script; a first build counts
against the command limit. Keep these environment values for every deskpilot call.

For deskpilot#95, the script can log out to character select, capture the window with
`deskpilot shot "$FOREVER_CLIENT_WINDOW"`, locate the Characters button, and
compare `deskpilot click` with and without `--take-pointer` using each fresh shot's
coordinates and shot ID. Use `--show` inside the nested compositor for XWayland keys
and text. Log the parked character back in before the script exits. The runner then
performs the return login under gamescope. `forever_client.py shot`, `click` and other
verbs inside the script use its job token; screenshots use grim and click coordinates
include the nested output's XWayland origin.

`--max` bounds the command, default 600 seconds, maximum 1800 seconds. It excludes
both relaunches: each world wait has a fixed 600-second limit, and the return allows
900 seconds including logout and process shutdown. Command exit, timeout, SIGINT or
SIGTERM to the waiting job all trigger the return. Timeout and cancellation end the
command's entire process group, with SIGKILL after the SIGTERM grace period. The lock
is released only after return or full teardown. If the return fails, the session ends
and the next job starts fresh gamescope. This is an occasional job with two extra
logins; `lease` remains a token for individual commands.

## Queue and recovery

Job waiters take numbered tickets under the state directory and run in arrival order.
Each waiter holds an exclusive lock on its ticket until it acquires the job or stops waiting.
A ticket whose lock is available is abandoned and removed. PID metadata is diagnostic only.
A timeout or interrupted wait removes its ticket. Waiting messages update when the holder
or queue position changes. The timeout bounds the wait and does not guarantee acquisition.
Serve teardown has priority over waiting tickets, but waits for the active job to finish.
This lets a pending reload finish while ordinary waiters yield to it.

Proof verifies every borrowed slot before each capture and at teardown. A slot that no
longer points to the candidate fails the proof before any proof record is written.
Recovery replays a link record only while holding the job lock. If another job holds it,
recovery leaves the record untouched, even when its owner PID is invisible to the caller.

The resident source digest includes `!!ForeverHeadless` files. Session state records that
addon's digest too: newer verbs replace an obsolete session through teardown while holding
the job lock, including helper changes that keep the same pixel protocol version. The live
safety strip separately triggers replacement when its protocol is missing or outdated. A verb inside an active job
uses that session until the job ends; serve handles source changes afterward.

For smoke, proof and build-dev, a missing full 40-hex commit SHA triggers one `git fetch origin`
and a resolution retry. A missing branch name or abbreviated SHA does not trigger a fetch.

Battle.net sign-in blocks automatic starts until the player runs
`FOREVER_CLIENT_CALLER=in-game python3 tools/headless/forever_client.py up --manual-launcher`,
signs in and reaches READY. That clears `launcher-sign-in.txt` under the session state directory.
Client commands require `FOREVER_CLIENT_CALLER`; send the shared in-game agent an INGAME request
([request format](../../.agents/skills/wow-forever-addon/in-game.md#requesting-a-check)).
