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
