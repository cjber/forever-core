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
