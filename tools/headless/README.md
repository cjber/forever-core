# Headless character configuration

`forever_client.py up`, `smoke` and `proof` read the launch record at
`$XDG_CONFIG_HOME/forever-client/env.json` (or `~/.config/forever-client/env.json`).
The record must contain the runner fields captured by `capture-env` and an owner-approved
character block:

```json
"character": {
  "name": "Barry",
  "guid": "Player-...",
  "require_resting": true
}
```

The name and GUID prevent a proof from entering a different character. `require_resting`
requires the client to report the character resting before the headless addon emits its
world-ready marker. A missing or malformed block stops before the launcher starts. The
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

Walking and opening or searching the auction house are allowed. Bidding, buying, posting,
fighting, resurrection and automatic recovery are forbidden. A refusal sends no recovery input.
An older resident addon or an unreadable safety strip is replaced through the guarded
session teardown path before reuse. Unknown safety still refuses input.

Exit 3 means the player's client is in use. Exit 4 means live safety refused the operation:
`player is dead or a ghost`, `player is in combat`, or the version 2 safety protocol is
unavailable or outdated. Other client errors use exit 2.

## Shared commands

Run `lease --label NAME [--ttl S]` to ensure the resident session and print a token.
Use `FOREVER_CLIENT_JOB=TOKEN forever_client.py shot` (or `click`, `key`, `slash`,
`eval`, `reload`, `scroll` or `errors`) for each command. Each invocation takes
the job lock and releases it when it returns, allowing agents to interleave commands.
The client stays logged in between commands. Lease tokens last 600 seconds by default,
at most 1800 seconds. `release TOKEN` deletes the record, and session teardown clears
all leases. An expired token requires a new `lease`.

Use `job --max S -- COMMAND` for work that needs exclusive access. The default limit
is 600 seconds and the maximum is 1800 seconds. At the limit the command's process
group receives SIGTERM, then SIGKILL after a short grace period. Commands inside the
job use its token without taking the lock again. Calling `down` inside that job
requests a stop and returns immediately; the session stops when the job ends.

`job` and `lease` reuse the resident session without `--wait`.
`serve --wait` queues for a separate session and reports the current holder,
its launch lifetime deadline and its idle deadline before waiting.


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
