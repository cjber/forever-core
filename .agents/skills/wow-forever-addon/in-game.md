# Testing an addon in the real client

## Requesting a check

One agent session drives the client: the long-lived kiln session titled `wow in-game`. Every other agent, whatever
the repo or task, gets its proofs, smokes and in-game checks by sending that session a request and waiting for the
reply. Only the in-game agent runs `forever_client.py` or anything that starts the game, so requests run one after
another from one queue instead of racing for the job lock, the sign-in and the AddOns folder. The unattended
`forever-smoke` timer is the one other caller, and it takes the same job lock.

1. Find it with `kiln msg list`. If none runs, check again, then start the one session (a second would compete for
   the client):

   ```sh
   kiln msg spawn claude --interactive --dir ~/drive/proj/wow --title "wow in-game" -- \
     "Read ~/.agents/skills/sweep/profiles/wow-ingame.md and follow it. Resume ~/.local/state/sweep/wow/ingame-queue.md."
   ```

2. Cover every logic check offline first: busted specs plus the vendored `tools/forever_sim`, which stubs the
   client API. Ask the client only for what only it can show: real layout and pixels, Blizzard frame interplay
   (tracker, map, Questie), taint, load order, real game data, motion over reload, zone change or a taxi flight.
   The PR says which checks the specs or sim cover.

   Testing runs in rounds: all coding first, then one round tests every addon. Push the code-complete commit, then
   append the request below as one block to `~/.local/state/sweep/wow/notes/ingame/round-next.md`. The coordinator
   cuts the round; a request outside a sweep goes to the in-game session directly and joins the next round.

   ```
   INGAME <repo> <full sha> from <your kiln id>
   kind: proof | smoke | check
   checkout: <worktree path>                       (proof and check)
   flows: <name>=<slash or lua file>; ...          (proof)
   check: <what to verify, steps, expected result> (check)
   changelog: <bullet> => <flow name>; ...         (proof)
   needs: <third-party addons, character, place>   (optional)
   ```

   A proof's flows follow [Behaviour and cost flows](#behaviour-and-cost-flows): one per changed surface, each doing
   what a player does there and raising on an unexpected result or a handler over one frame. `changelog:` maps every
   `CHANGELOG.md` bullet the change adds to the flow that proves it; a bullet with no flow sends the request back.

   The ref is the full 40-character SHA of a pushed commit. Every check one commit needs goes in one message, as
   several `kind:` blocks one after another, so the in-game agent loads that build once.

   A round is one logged-in session: it links one build per addon together, runs every block in one pass and posts
   each proof to its own PR. A request that arrives mid-round waits for the next. Split a batch only for a real
   conflict (two builds of one addon, incompatible characters or places) and say the reason in the reply.

   The client stays logged in while any work is queued. Never `down` it between checks or batches; send the
   request and the live session picks it up. A `check` names
   everything the in-game agent needs to judge it without asking back: the steps, the expected result, and the frame
   or text that shows it.

3. Wait for the reply as a kiln message, in the background: it arrives in your session on its own, so carry on
   with other work and leave the queue, the client and the commit statuses unpolled.
   - `INGAME PASS`: carries the capture paths, gist URLs and, for a proof, the `.visual-proof.json` it wrote into
     your checkout. Commit that file and embed the captures.
   - `INGAME FAIL`: observed against expected, with captures and Lua errors. Fix the defect and request again.
   - `INGAME BLOCKED`: only when the client cannot reach the world because the player's own client is running or
     sign-in needs the user. Where the character stands, resting or not, is never a block: the in-game agent moves
     it. Report it as your blocker.

The rest of this file is the in-game agent's reference for running requests. Its commands set
`FOREVER_CLIENT_CALLER=in-game`; jobs and detached sessions preserve the marker.

## The tool

`tools/headless/forever_client.py` in the `forever-core` checkout runs the WoW: Forever client under gamescope's
headless backend: the game renders on the GPU into a display of its own, so nothing appears on the player's desktop
and their mouse and keyboard are never touched. Every verb acts on that display only.

## Hard rules

The client exists to test the Forever addons' interface. These rules hold for every session, and the tool enforces
them where it can:

1. **Interface only.** Open and close frames, click or scroll addon UI, send slash commands, `/reload`, take
   screenshots, read SavedVariables and Lua errors. To reach a place a check needs (an auction house, a trainer, a
   vendor), walk with Click-to-Move: `eval` `SetCVar("autoInteract", 1)`, then `click --button 3` on the ground or the
   NPC, and put the CVar back to its earlier value before the job ends. At an auction house, open it and search; never
   bid, buy or post. Never attack a creature or walk into one's aggro range, fight, loot, quest, trade or chat to
   other players. Nothing else blocks the game: `slash` sends any one-line slash command (`/use Hearthstone` to get
   somewhere) and `key` any key. Move only with `face` and `walkto`, which turn and walk on the measured facing and
   position: `walkto 61.2 73.9` (map coordinates as the map shows them), `walkto target` (to interact distance),
   `face 61.2 73.9`, `face target`, and `where` to read the position. They press the keys the running client binds to
   TURNLEFT, TURNRIGHT, MOVEFORWARD and JUMP (`key --action ACTION [--for SECONDS]` presses one by hand, never a raw
   movement key: the headless account walks forward on S). `walkto` reports where it stuck instead of looping. Never
   park or end a job inside a shop: a job that moved the character ends by walking it to the nearest outdoor park spot
   with a merchant and creatures in reach (`park`; record a new one standing there with `park --add LABEL`). With
   `autoInteract` on, INTERACTTARGET walks to an out-of-range target first. Whether the character is resting never
   matters, so move it wherever a check needs it rather than waiting or asking. `click`, `scroll` and `drag`
   refuse until a `shot` was taken after the last input, so each input aims at what you have just read in the frame.
2. **One job at a time.** The client is shared and stays up while jobs arrive; only one job touches it at once.
   Every verb that touches the client (`shot`, `click`, `scroll`, `drag`, `key`, `slash`, `reload`, `eval`, `errors`, `face`,
   `walkto`, `where`, `park`) runs
   inside a job, so run a test as `job -- <script>` (or `run -- <script>`, the name it had before); the one exception
   is the `shot` and button-1 `click` that click Play for a `--manual-launcher` session, which run without the job
   lock. The session ends 60 minutes after the last job (never while a request is queued or a lease is live) and 3 hours after it started, and every ending types `/quit`
   so the character logs out, then stops the client.
3. **Human pace.** Inputs are at least 1.5 s apart across invocations and slash commands type at 120 ms a key.
   Never loop inputs: take a shot, read it, decide the next action.

## One client, one job at a time

There is one Battle.net account, so one client, and one AddOns folder, so one job. `serve` starts the client once
and keeps it up while jobs arrive; `job -- <command>` starts that session when none runs, waits for any job in
flight, and runs the command with the job lock held. A verb run on its own (`shot`, `slash`, `errors`, ...) takes
the same lock for that one invocation. `job.json` in `~/.local/state/forever-client` names the holder, so a waiter
prints what it waits for.

A job exits 3 only when the player's own client is running, because the Wine prefix is used by processes this tool
does not own. Another job (the smoke timer's) is waited for, up to `--timeout` (1800 s for `job`, `lease`, `smoke` and `proof`,
600 s for a single verb or for `up`/`serve` to reach the world). When the player is in game, the test waits for them;
a PR then lists its `/reload` steps for the player instead.

`lease` holds the job lock for an agent driving the client across several tool calls: it prints a token, and every
verb run with `FOREVER_CLIENT_JOB=<token>` in its environment proceeds without waiting. `release <token>` ends it,
as does its `--ttl` (10 minutes by default, 30 at most) or the session ending.

## A session

```sh
FC=~/drive/proj/wow/forever-core/tools/headless/forever_client.py
FOREVER_CLIENT_CALLER=in-game python3 $FC job -- ./my-test.sh   # start or reuse the session, wait for the job lock, run the script
FOREVER_CLIENT_CALLER=in-game python3 $FC shot                  # prints the PNG path; read it to see the frame
FOREVER_CLIENT_CALLER=in-game python3 $FC click 960 540         # points in the 1920x1080 frame, on UI from the last shot
FOREVER_CLIENT_CALLER=in-game python3 $FC scroll 960 540 3      # wheel-up ticks (zoom in) or -N down, at UI from the last shot
FOREVER_CLIENT_CALLER=in-game python3 $FC drag 1700 300 1500 400 # press, move in steps (--steps N), release: a header drag
FOREVER_CLIENT_CALLER=in-game python3 $FC key Escape            # Return, Escape or BackSpace
FOREVER_CLIENT_CALLER=in-game python3 $FC slash "/fgf"          # a Forever addon's own command
FOREVER_CLIENT_CALLER=in-game python3 $FC reload                # /reload, returns once the world is back
FOREVER_CLIENT_CALLER=in-game python3 $FC errors --addon FieldGuideForever   # reload, then this job's Lua errors (exit 1 when any)
FOREVER_CLIENT_CALLER=in-game python3 $FC sv FieldGuideForever               # SavedVariables as of the last reload
FOREVER_CLIENT_CALLER=in-game python3 $FC eval /tmp/probe.lua                # write a snippet through !!DevSmoke, reload, print DevSmokeDB.eval
FOREVER_CLIENT_CALLER=in-game python3 $FC down                  # stop the session once the job in flight, if any, has finished
```

`job -- <command>` runs the command with `FOREVER_CLIENT_DISPLAY` and `FOREVER_CLIENT_JOB` set, so the verbs the
script calls join its job instead of queueing behind it. The session it starts stays up for the next job; `serve`
runs the same lifecycle in the foreground and `up` is its old name. Each verb run outside a job takes the job lock
for that one call. `run -- <command>` is `job` under the name it had before, so it runs one job in the shared session
rather than a session of its own.

`scroll` at a point on the world map zooms it, which is how a pin that appears only at full zoom is checked. It turns
the wheel at a point on the last shot, exactly as `click` aims there, and like `click` it is one of the verbs that
takes the job lock for its own invocation.

`drag X1 Y1 X2 Y2 [--button 1|3] [--steps N] [--hold shift]` moves a draggable frame the way a player does: it presses
the button at the first point, moves to the second in `N` steps (10 by default) and releases there, so the frame's
OnDragStart and OnDragStop run. It aims like `click`, at UI from the last shot, and the whole drag is one input. A
drag that fails or is stopped mid-drag releases its button, and one killed outright is released when the next job
starts.

Driving the client across several tool calls, use a lease:

```sh
TOKEN=$(FOREVER_CLIENT_CALLER=in-game python3 $FC lease)        # starts or reuses the session, prints the token
FOREVER_CLIENT_JOB=$TOKEN FOREVER_CLIENT_CALLER=in-game python3 $FC shot
FOREVER_CLIENT_JOB=$TOKEN FOREVER_CLIENT_CALLER=in-game python3 $FC click 960 540
FOREVER_CLIENT_CALLER=in-game python3 $FC release $TOKEN
```

A session ends 60 minutes after the last job ended (or after READY when none has run), unless a request is queued or
a lease is live, and never later than 3 hours from its start. At either end it takes the job lock first, so a job in flight is never cut off; `down` does the
same. Every ending logs the character out and stops the client.

## Smoking a release commit

Every release, manual or automatic, needs a record that its exact commit was loaded in the client: a committed
`.visual-proof.json` that verifies against the commit's files and carries passing checks (`proof` below records
them), or else a green `headless-smoke` commit status. `tools/release_check.py` refuses without either. The proof is
bound to file contents, so a pull request proved in one session also releases its merge commit and a release
preparation that only bumps the version; `smoke` is for a commit no proof covers:

```sh
FC=~/drive/proj/wow/forever-core/tools/headless/forever_client.py
FOREVER_CLIENT_CALLER=in-game python3 $FC smoke --repo legacy-forever --ref <sha>   # build, link, reload, selftest, errors, restore, post status
```

`smoke` runs as one job. It builds that commit's dev archive under `test-artifacts/<repo>-smoke` the way
`rebuild-dev.sh` did (the same code, `forever_client.py build-dev <repo> <ref>`, writes
`test-artifacts/<repo>-dev` for a hand link; `--core-ref <sha>` embeds that forever-core commit instead of the pinned
release, to check a core candidate inside an embedding addon), ensures a session, takes the job lock, points the build's addon
folders at it in `Interface/AddOns`, reloads so the client loads it, runs `/forever selftest` and waits for
`!!DevSmoke` to save the finished run, reloads once more and reads `errors --addon <folder>` for each of the repo's
addon folders, and puts the links back before it releases the lock. A selftest surface that failed, a Lua error or
(for core) a released addon that never started fails the smoke. It posts the result with
`gh api repos/cjber/<repo>/statuses/<sha> -f state=success|failure -f context=headless-smoke -f description=...`:
the failed surfaces and error counts, or "clean". `--manual-launcher` starts the session that way, so while launcher OCR is not finding
Play (cjber/forever-core#547) an agent runs `smoke --manual-launcher` in the background, takes `shot`, and clicks
Play itself. While that job holds the job lock and waits for READY, `shot` and a button-1 `click` act on the launcher
without the lock, so they never queue behind the job they are unblocking; `key` and `slash` still refuse until READY.

- Exit 0 is a clean commit and exit 1 a recorded failure.
- Exit 2 means the checks never ran: the session could not reach the world (a start that timed out), or the
  selftest was skipped (in combat) or saved no finished run. Nothing is posted, so a caller runs it again later. A Game Menu an earlier job left open is
  closed first, so it no longer stops a smoke.
- Exit 3 also covers a persisted Battle.net sign-in block. The player clears it with `up --manual-launcher`,
  signs in and reaches READY. Nothing is posted while blocked.
- Exit 3 means the player's own client is running: the Wine prefix is used by processes this tool does not own.
  Nothing is posted then, so a caller runs it again later. Another job (the smoke timer's) is waited for, up to `--timeout`.
- The AddOns folder is shared, so each slot is put back exactly as it was: a link at its own target, a store install
  moved back from `<folder>.smoke-backup`. The record of what it borrowed is `~/.local/state/forever-client/smoke-links.json`
  while the job runs, kept only if a restore could not finish. A stop that never reaches Python's own handlers
  (SIGKILL, or a signal aimed at the shell around it) leaves that record and its links behind; the next `up`,
  `serve`, `job`, `run`, `smoke` or `build-dev` puts them back before it touches AddOns and says what it restored,
  and a record whose session is still running is left to that session's own teardown.

`tools/smoke_queue.py` finds, for forever-core and every consumer, the commit the next release would ship (`main`'s
head) that has no `headless-smoke` status and no committed visual proof that covers it, and smokes them one at a time in release order (forever-core, SkillUp,
Shortest Path, then the rest), stopping at exit 3 so the queue never fights the player for the client.
`--repo NAME`, repeatable, smokes only those repositories in the order given. Each smoke is one job in the resident session, so the queue shares the client
with an agent instead of waiting for a whole session to end. `python3 tools/smoke_queue.py --dry-run` lists them
without starting anything.

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

## Recording a visual proof

Every pull request that changes what the player sees needs a `.visual-proof.json`, and the required `visual-proof`
job fails without one. A release preparation edits the update notice (`UI/WhatsNew.lua` or `ns.WHATS_NEW`) and every
locale, and a sync pull request moves the ForeverCore pin the recorded proof binds, so both need a new proof. One
command records it in the headless client and writes the file into the checkout the pull request carries:

```sh
FC=~/drive/proj/wow/forever-core/tools/headless/forever_client.py
FOREVER_CLIENT_CALLER=in-game python3 $FC proof --repo legacy-forever --ref <sha> --checkout ~/drive/proj/wow/legacy-forever \
  --flow "update notice=/lf"
```

`proof` runs as one job, as `smoke` does: it builds that commit's dev archive under `test-artifacts/<repo>-proof`,
ensures a session, takes the job lock, points the build's addon folders at it in `Interface/AddOns`, reloads once,
and then for each flow runs the flow and takes a screenshot. After the last flow it runs the smoke's checks on the
same session (`/forever selftest`, every addon folder's Lua errors since the job started, and for core the released
addons' startup) and records them as `checks`; a failed surface, a Lua error or an addon that did not start fails
the proof and writes nothing, so the one session proves the change and stands in for its `headless-smoke`. A flow is a Forever addon's own slash command after
`=`, or a Lua file that `!!DevSmoke` runs; anything longer than a `/run` line belongs in a file, exactly as `eval`
takes it. The PNGs go to a new secret gist, and `<checkout>/.visual-proof.json` gets their full-SHA raw URLs and
sha256s beside `visual_proof --digests`' input and candidate digests and the client build. It then runs
`visual_proof --compare` against the installed build, so a mismatch fails before the proof is committed. Every
AddOns slot is put back exactly as it was, and the checkout is never committed or pushed: commit
`.visual-proof.json` yourself, in the pull request it proves.

There is no default flow. ForeverCore has no shared opener for an addon's update notice: every addon prints it as one
chat line at login, and a dev build's stamped version does not equal the addon's `WHATS_NEW_VERSION`, so that line
does not fire on its own in a proof session. Name the flow that shows the changed text: a slash command, usually the
addon's own (such as `/lf` or `/fgf`), or a Lua file through `!!DevSmoke` for anything a chat command cannot reach,
written as the eval section below shows. Exit 3 means the player's own client is running, so nothing was recorded and a later run tries again; another job is waited for. Exit 1 is a job that stopped
before its flows ran, and exit 2 is a failure the tool names. `--manual-launcher` starts the session that way while
launcher OCR is not finding Play.

A flow is captured once it says its window is ready, so a window that fills in from late data is not photographed
empty (#593). A Lua snippet may `return` a function; `!!DevSmoke` polls it every 0.25 s, takes the client's own
screenshot the moment it first returns true, and `proof` waits for that file before its capture:

```lua
-- notice.lua: open the panel, then say when its data has arrived.
local panel = MyAddon:OpenPanel()
return function()
	return panel and #panel.cards > 0
end
```

A flow with no ready function is still captured, just after the world load. A ready check that raises or never turns
true writes the client's own reason to `DevSmokeDB.eval` and saves it; `proof` reports that reason instead of only its
65 s fallback timeout. Nothing is uploaded and `.visual-proof.json` is not written. A slash flow now runs through
`ChatEdit_SendText` in the same `!!DevSmoke` route, so its capture follows a confirmed run and its own eval result is
checked; there is no fixed settle. Name a Lua flow for anything that must wait on data.

A secure slash flow (`--flow "route=/cast Cooking"`; also `/use`, `/click`, `/target`, ...: the client's secure
words, listed as `SECURE_SLASH_WORDS` in `forever_client.py`) cannot run from Lua at all, so the proof types it into
chat as the `slash` verb does, after the reload's world screenshot, then settles 3 s before the capture. It has no ready
check and no eval result, and takes at most one `--flow-click`, clicked after that settle. Each flow reloads first, so a later Lua flow starts from a fresh world and
does not continue from the window the secure flow opened.

A flow whose window only a real click opens names that click with `--flow-click "NAME=X,Y"`, where `X,Y` are the same
screenshot coordinates `click` takes:

A flow that needs real input names it with these options, each `NAME=...` where `NAME` matches a `--flow`:

| Option | Input |
|---|---|
| `--flow-click "NAME=X,Y"` | a left click, in the screenshot coordinates `click` takes |
| `--flow-drag "NAME=X1,Y1,X2,Y2"` | a left-button drag, as the `drag` verb sends it |
| `--flow-key "NAME=ACTION"` | the key the running client binds to a game action, as `key --action` presses it |
| `--flow-type "NAME=/COMMAND"` | a slash command typed into chat, as `slash` types it |

A flow's inputs run in the order given, inside the proof's own job, once that flow's reload has written its world
screenshot (the flow's snippet has run by then) and before its ready screenshot is waited for. Nothing reloads between
them and the capture, so a window they open is still open for it. An input that reloads the client (a typed
`/reload`) would close that window, so the proof fails when the screenshot after the inputs is a world load's. A `--flow-key` binding is looked up before the
flow's reload, because a lookup that is not cached reloads the client itself. An aimed input after the first aims at
a fresh `shot`.

For a click:

```sh
FOREVER_CLIENT_CALLER=in-game python3 $FC proof --repo skillup-forever --ref <sha> --checkout ~/drive/proj/wow/skillup-forever \
  --flow "professions=professions.lua" --flow-click "professions=960,540"
```

The click runs inside the proof's own job, once that reload's world screenshot has landed and before the flow's ready
screenshot is waited for. Opening a profession window is a protected action no Lua snippet can take, and no outside
`click` can reach the client while the job holds it (#648), so this is how such a window is opened and then captured
once `professions.lua`'s ready check sees it filled.

A merchant, trainer or bank window opens only by interacting with the NPC, and a Lua snippet can neither target it
(`TargetUnit` is restricted for addon code) nor interact. Type the target and press the interact key instead, from a
spot within interact range of the NPC, with a Lua flow whose ready check waits for the window:

```sh
FOREVER_CLIENT_CALLER=in-game python3 $FC proof --repo tweaks-forever --ref <sha> --checkout ~/drive/proj/wow/tweaks-forever \
  --flow "junk merchant=merchant.lua" \
  --flow-type "junk merchant=/tar Thurman Mullby" --flow-key "junk merchant=INTERACTTARGET"
```

```lua
-- merchant.lua: captured once the merchant window has opened.
return function()
	return MerchantFrame and MerchantFrame:IsShown()
end
```

A drag flow is the same shape: `--flow "move header=header.lua" --flow-drag "move header=1700,300,1500,400"`, with
`header.lua`'s ready check returning true once the frame's saved position has changed. Give every input flow a ready
check that waits for the input's result: a slash flow is ready as soon as its command is sent, so it can be captured
before a window its inputs open has drawn. The proof's flow entry records the inputs in order under `inputs` (such
as `[{"type": "/tar Thurman Mullby"}, {"key": "INTERACTTARGET"}]`), so the evidence says what was sent. A flow with no
input options is unchanged.

### From the user's checklist pass

When the user has tested a build in the live client from the checklist (`tools/checklist/README.md`), that pass is the
proof: no headless run is needed. The in-game agent records each linked build with
`checklist build --addon R --sha SHA --artifact test-artifacts/<dir> --digest <input_digest> --client-build <build>`,
where the digest is `visual_proof --digests`' `input_digest` of that commit and the client build is the client's
version line (`1.60.1.70959 (Interface 16001)`). Recording `--artifact` also hashes every file of that unpacked build.
Once the round passes, anyone writes the proof without the
client:

```sh
python3 $FC attest --repo shortest-path-forever --ref <sha> --checkout <worktree at that sha> [--shot <client screenshot>]
```

`attest` reads `checklist status --addon R --sha SHA --json` and refuses unless the build passed the gate (every check
passed, or skipped where the check is optional, with at least one pass), each answer was given against this build, the
round recorded this commit and a client build, its digest equals the checkout's `input_digest`, the unpacked build
still hashes to what was recorded when it was linked, and it compares equal to the checkout (`visual_proof
--compare`). Each passed check becomes a flow. The screenshots pasted into passed checks, plus any `--shot` from the
client's Screenshots folder, are converted to PNG and go to a new secret gist, at least one in total. The file carries
`kind: user-checked` and the round, and is committed with the change like any proof. A move-folders addon, whose proof
must test a release package, cannot be attested from a source build.

### Behaviour and cost flows

A proof shows that the change works and what it costs, not only how it looks (WFA-40). Each flow is a Lua file that
does what a player does on the changed surface, then checks the result and the cost from its ready function. A raise
there fails the proof with its message, so the message says what was expected and what happened. The cost comes from
`!!DevPerf`'s per-event split: `/devperf events reset` at the start scopes it to the flow, and the session's
`events` table (format in forever-dev's `!!DevPerf/AGENTS.md`) holds every Forever handler's peak and its calls
over one frame.

```lua
-- sorted-recipe.lua: with the Professions window open (the flow's --flow-click), sort by skill-up and pick a recipe.
SlashCmdList.DEVPERF("events reset")
local events = DevPerfDB.sessions[#DevPerfDB.sessions].events
SkillUpForever.SortBy("skillup")
SkillUpForever.SelectRow(1)
local started = GetTime()
return function()
	-- Expected result: the window stays open on the chosen recipe.
	if not ProfessionsFrame:IsShown() then
		error("expected ProfessionsFrame open after picking a sorted recipe, it closed")
	end
	-- Cost: no Forever handler call or tick over one frame during the flow.
	for addon, handlers in pairs(events.handlers or {}) do
		for key, stat in pairs(handlers) do
			if stat.over > 0 then
				error(("%s %s took %.1f ms, over one frame"):format(addon, key, stat.peakMs))
			end
		end
	end
	local spike = events.spikes and events.spikes[1]
	if spike then
		error(("%s spent %.1f ms in one tick (%s)"):format(spike.addon, spike.ms, spike.source))
	end
	-- Give late events a second to land before passing.
	return GetTime() - started > 1
end
```

- One flow per changed surface, named for it, and every action a player takes there: a list sorted and clicked, a
  purchase, the bags opened at a merchant, the camera turned with a route loaded. A flow that only opens a window
  proves only that it opens.
- Each action states its expected result in the check that raises, the frame or value a player would see.
- `events.off` set means the build cannot time handlers: report it, since the cost half of the proof is missing.
- The `SkillUpForever` calls above stand for the addon's own entry points: drive the addon through its real
  functions or widgets, never a test-only path.

`tools/sync_consumer_prs.py` cannot drive the client itself, so for a sync pull request whose changed files need a
proof it prints this command for the pull request's head, and the release session runs it and commits the result.

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
| `/devsmoke live RUN I/N BASE64` | what `eval --live` types: numbered base64 pieces of a snippet, run in this session when the last one arrives |
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
FOREVER_CLIENT_CALLER=in-game python3 $FC eval /tmp/probe.lua   # in a session: writes it, /reloads, prints DevSmokeDB.eval (exit 1 on failure)
FOREVER_CLIENT_CALLER=in-game python3 $FC eval --live /tmp/helper.lua   # no reload: runs in the live UI, globals and open panels stay
```

An `eval` leaves the UI as the snippet made it: one reload runs the snippet once the world has loaded, `!!DevSmoke`
saves the result at once, and nothing reloads afterwards, so `eval` a file that opens a panel (`C_Map.OpenWorldMap(1436)`)
and then `shot` shows it (#894). `eval --live FILE` skips even that reload. The compiled file is typed into the chat box
as numbered `/devsmoke live` lines (base64, about 200 characters each) and runs when the last arrives; its printed and
returned lines come back the same way as an eval's, from `DevSmokeDB.eval`, which `!!DevSmoke` saves immediately.
Globals it sets stay for later `slash` commands, so load a helper library once with `--live` and drive it with short
`/run` lines. Lines type at slash speed (`TYPE_DELAY_MS`), so keep the loaded file small: a 1 KB snippet is about 7
lines. A live snippet is not a proof flow: it schedules no screenshot and a returned function is not polled.

With a session already running, the steps by hand are:

```sh
python3 tools/devsmoke/eval.py /tmp/probe.lua   # compile and write the inbox
FOREVER_CLIENT_CALLER=in-game python3 $FC slash "/devsmoke eval"              # the first eval this session loads and runs the inbox chunk
FOREVER_CLIENT_CALLER=in-game python3 $FC reload                              # saves DevSmokeDB.eval; a snippet written later needs this
FOREVER_CLIENT_CALLER=in-game python3 $FC sv '!!DevSmoke'                     # DevSmokeDB.eval: run, ran, ok, out, err
```

`eval.py` compiles the file with `luajit -bl` (and `luac5.1 -p` when it is installed) and refuses a parse error
before anything reaches the client. It writes the chunk into the gitignored `!!DevSmokeInbox` folder inside the linked
`!!DevSmoke` checkout, linked into AddOns as the load-on-demand addon of the same name; the snippet's line 1 is the
generated file's line 2, so an error naming `Eval.lua:6` is snippet line 5. The chunk runs at login and on
`/devsmoke eval`: what it prints and every value it returns go to the Agent tab in lines under 255 characters and
into `DevSmokeDB.eval`, and its errors are caught there instead of reaching BugGrabber. A function it returns is not
printed: it is the flow's ready check, polled by `!!DevSmoke`, whose screenshot when it first returns true is what
`proof` waits for (#593).

The client reads the inbox once per session: the first `/devsmoke eval` or login loads it, and any snippet written
after that needs `/reload`. `forever_client.py eval` writes the file and reloads, so it always runs the snippet it
just wrote, then clears the inbox before reloading once more and reading the result that snippet's own run token
names. The second reload therefore saves that one run instead of running the snippet again (#588). `eval A.lua B.lua`
runs each file at a login of its own, and each file's reload saves the result of the file before it, so N files take
N + 1 reloads instead of 2N; batch independent probes into one call. The last result is read without that
extra reload when `!!DevSmoke` has already saved it, so the UI the last snippet opened stays open for a `shot`.

A session ends after 10 min with no job, unless a queued job ticket or an unexpired lease on the session says more
work is coming. An agent with more requests queued holds `lease --ttl` across them, so the next job skips a cold login
(1 to 2.5 min). The 3 h lifetime cap still applies.

`DevSmokeDB.eval` is `{ run = <token>, ran = <time>, ok = <bool>, out = { <lines> }, err = <string|nil>,
ready = <"captured"|"failed"|"timeout"|nil>, readyErr = <string|nil> }`, where `out` holds the same lines the Agent
tab showed and `readyErr` is the reason a proof flow was not captured. SavedVariables reach disk only at a reload or
logout, so the file still
holds the session before the one that just ran: `run` is the token `eval.py` stamped that session's chunk with, and it
is what tells a result apart from an earlier snippet's (#580). Use eval for anything longer than a one-line `/run`.

## What it relies on

- The addon under test is the build linked into `_forever_/Interface/AddOns`: rebuild the `test-artifacts` link
  first, as the workspace `AGENTS.md` says.
- `!!ForeverHeadless`, linked in only for the session, takes a screenshot each time the world loads; that file is
  the sign the client is in the world.
- The launch is the player's own: Faugus Launcher's Battle.net game, which runs `umu-run` with the game's Proton
  runner on the prefix `~/Games/battlenet`. `capture-env` records it into `~/.config/forever-client/env.json` while
  Battle.net runs from Faugus, and is needed again only when the game's runner in Faugus changes. One Wine build per
  prefix: a launch with another Wine logs Battle.net out.
- Battle.net needs the network, so run the tool outside the agent sandbox; `serve` (and the `job` that starts it)
  checks Battle.net is reachable before it starts anything.
- The launcher logs in on its own and opens the WoW: Forever page, but ignores the launch it was started with, so
  until the game starts `serve` clicks Play every 15 s. Play is located from the flat fill the launcher draws its button
  in, with the label read inside that button, so the click follows the launcher's own layout (#547). A launcher build
  that draws another fill needs a fresh `tools/headless/launcher-play.png` for its spec and the `PLAY_FILL` in
  `tools/headless/forever_client.py` moved with it. Enter at the character list enters with the last character. A
  timeout prints the last frame's path: a login form or an update prompt there needs the player.

## Scope

Scripted input to a logged-in client may count as botting under Blizzard's terms; the player accepted that for
testing their own addons only. The hard rules above are that boundary.
