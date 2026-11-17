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
frame. Unknown API answers are unsafe. Jobs, leases, proofs and smokes check immediately
after ensuring the session. Every input verb and each input send checks again, including
commands inside a job using `FOREVER_CLIENT_JOB`. Screenshots and status remain available. Error reads reload to flush SavedVariables and
are refused when unsafe. Reload and proof waits report a live safety refusal as soon as the strip shows it.

Walking and opening or searching the auction house are allowed. Bidding, buying, posting,
fighting, resurrection and automatic recovery are forbidden. A refusal sends no recovery input.
An older resident addon or an unreadable safety strip is replaced through the guarded
session teardown path before reuse. Unknown safety still refuses input.

Exit 3 means the player's client is in use. Exit 4 means live safety refused the operation:
`player is dead or a ghost`, `player is in combat`, or the version 2 safety protocol is
unavailable or outdated. Other client errors use exit 2.
