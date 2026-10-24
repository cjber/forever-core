# Finish the engagement-tracking branches (3 red branches)

Context: an audit of the sandbox found three in-progress engagement-tracking
branches. All their work is committed and pushed; each fails CI. Finish each,
get CI green, and merge to main.

## 1. cjber/shortest-path-forever — PR #261 `feat/engagement-tracking`
CI job `check` fails in `tests/locales_spec.lua`: new user-facing strings are
not wrapped in `L[]`:
- `Core/Progress.lua`: "Travel milestone reached: %s"
- `UI/Settings.lua`: "Travel stats are not ready yet."
- `UI/Settings.lua`: "Use /path leaderboard routes, distance, transports, flights or portals."
- `UI/Settings.lua`: "Local travel journal — approx. %d yd walked; %d journeys; %d transports; %d flights; %d portal legs."
- `UI/Settings.lua`: "%d. %s — %s"
Wrap each in `L[...]`, add the keys to `Locales/enUS.lua` (and phrases.txt if
the repo uses it), run `luacheck . && stylua --check . && for s in tests/*_spec.lua; do luajit "$s" || exit 1; done`,
push to the PR branch, then merge #261 to main (squash).

## 2. cjber/adventure-guide-forever — branch `feat/engagement-tracking` (no PR yet)
Syntax error: `Core/Stats.lua:72` uses `C_Timer.After(SEND_GAP, function Flush()`
— a named function expression is not valid Lua. Change to `function()` (or a
named local function). Then `luacheck .`, `stylua --check .`, all specs, open a
PR to main, and merge once green.

## 3. cjber/legacy-forever — branch `feat/engagement-tracking` (no PR yet)
Syntax error around `Core/Stats.lua:71` (stylua cannot parse it). Fix it, run
`luacheck .`, `stylua --check .`, all specs, open a PR to main, merge once green.

## Rules
- Commit trailers: end every commit with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01JcwULHwLekhyjYKyVykXY3`.
- Do not use `-s`/`--signoff`.
- Merge only when CI is green; do not force-push main.
