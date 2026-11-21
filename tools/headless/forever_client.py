#!/usr/bin/env python3
"""Run the WoW: Forever client on a private GPU display for agents to test the addons in the real game.

The client runs under gamescope's headless backend: it renders on the real GPU into a display of its own, so no
window reaches the desktop and the player's mouse and keyboard are never touched. Every verb talks to that display
only: screenshots through `gamescopectl`, input through `xdotool` on gamescope's nested X server. The host also
needs `tesseract` on PATH to locate the launcher's visible Play control from the private screenshot.
Startup stops with the launcher frame path when Battle.net shows an update or installation dialog, or two Play
attempts produce no game process. Update the game in Battle.net before retrying an update failure.

    forever_client.py serve               # the resident session: start, wait for the world, stay up while jobs arrive
    forever_client.py up                  # the same lifecycle in the foreground
    forever_client.py job [--hyprland] [--max S] -- <command>  # exclusive job, with a hard command limit
    forever_client.py run -- <command>    # alias for job
    forever_client.py lease [--ttl S]     # ensure the session; print a token for commands that each take the lock
    forever_client.py release TOKEN       # end that lease now
    forever_client.py down                # stop the session once the job in flight, if any, has finished
    forever_client.py status
    forever_client.py shot [PATH]         # PNG of what the client shows now
    forever_client.py click X Y           # left click at a point in the 1920x1080 frame (after a fresh shot)
    forever_client.py hover X Y           # move the pointer to a point in the frame (after a fresh shot)
    forever_client.py scroll X Y N        # N wheel-up ticks (zoom in) or -N wheel-down ticks, at a point
    forever_client.py drag X1 Y1 X2 Y2 [--button 1] [--steps N]
                                          # press at one point, move in steps, release at the other (after a fresh shot)
    forever_client.py click X Y --hold shift [--hold ctrl]
                                          # hold shift, ctrl or alt through any pointer verb; released after
    forever_client.py key Escape          # any key xdotool names
    forever_client.py key --action MOVEFORWARD --for 2
                                          # hold the key this client binds to a game action: walk, turn, strafe
    forever_client.py slash "/fgf"        # open chat, type a Forever addon's slash command, send it
    forever_client.py reload              # /reload and wait for the world to load again
    forever_client.py sv ADDON            # print an addon's SavedVariables (after a reload, they are current)
    forever_client.py eval FILE...        # run each FILE through !!DevSmoke's inbox, print each one's own result
    forever_client.py eval --live FILE    # run FILE in the running session, no reload: UI and globals stay
    forever_client.py errors [--addon X]  # reload, then the Lua errors this session raised (forever_errors.py)
    forever_client.py capture-env         # record the launch from the player's client started in Faugus
    forever_client.py build-dev REPO REF  # test-artifacts/<repo>-dev from a ref, the dev build rebuild-dev.sh made
    forever_client.py build-dev REPO REF --core-ref SHA  # the same, embedding a forever-core candidate commit
    forever_client.py smoke --repo R --ref SHA [--no-post]
                                          # build the commit, selftest it, post its status (--no-post prints instead)
    forever_client.py smoke --repo forever-core --ref SHA
                                          # the same with every consumer's latest released build linked beside core
    forever_client.py proof --repo R --ref SHA --checkout PATH --flow NAME=SLASH_OR_LUA_FILE
                                          # record the checkout's .visual-proof.json from a client session
    forever_client.py attest --repo R --ref SHA --checkout PATH [--shot FILE]
                                          # the same from the user's checklist pass, without the client

`smoke` is the release gate: it builds the dev archive of the commit a release would ship, links its addon folders
over the client's, runs `/forever selftest` and `errors --addon` for each of them, and posts the result on that exact
commit as the `headless-smoke` commit status, which `tools/release_check.py` requires and `tools/smoke_queue.py`
fills in. When the repository is ForeverCore itself it also links every consumer's latest released build from
`tools/released_consumers.py` beside the candidate, so a core release is tested against the addons already on the
stores, and counts their folders too: a consumer Lua error, or a released addon that never reached
`ForeverCore.Registered` because its startup check refused this core, fails the status. It runs as one job: it
ensures a session, takes the job lock, builds and links the candidate, reloads so the client loads it, runs the
checks, puts the links back and releases the lock. `--no-post` runs exactly the same checks and prints the result
without posting a commit status, for a local demonstration. `--manual-launcher` starts a session that way while
launcher OCR is not finding Play (cjber/forever-core#547), so an agent runs `smoke --manual-launcher` in the
background, takes `shot` and clicks Play itself; those two launcher verbs run without the job lock, so they cannot
queue behind the job that is waiting for READY. Exit 0 is a clean commit, 1 a recorded failure, 2 a smoke whose
checks never ran (the session could not reach the world, or the client refused the selftest), and 3 means the player's
own client is running (the Wine prefix is used by processes this tool does not own); after 2 and 3 nothing is posted
and a caller retries later. Another agent's job is waited for, up to `--timeout`. A Game Menu an earlier job left
open is closed before the selftest is typed. The AddOns folder is shared: every slot the smoke
borrows is put back exactly as it was, including a store install it moved aside. A stop that never reaches Python's
handlers leaves that record behind, and the next `up`, `serve`, `job`, `run`, `smoke`, `proof` or `build-dev` replays
it under the job lock before it touches AddOns. A held job lock leaves the record untouched.
A missing full commit SHA fetches origin once and retries resolution for smoke, proof and build-dev.

`attest` writes the same file from the user's own checklist pass of that build (tools/checklist/README.md), without
the client: the round must have passed every check for the commit and recorded a runtime digest equal to the
checkout's `visual_proof --digests`, and the recorded unpacked build must still compare equal to the checkout.

`proof` records the in-game visual proof a release prep or a ForeverCore pin bump needs. It runs as a job the way
`smoke` does: it builds and links the candidate, reloads once, runs each `--flow NAME=SLASH_OR_LUA_FILE` through
`!!DevSmoke` (a slash command, or a Lua file), takes a screenshot after each, uploads the PNGs to a
new secret gist, and writes `<checkout>/.visual-proof.json` from `visual_proof --digests` with full-SHA raw URLs and
each image's sha256, then checks the installed folder with `visual_proof --compare`. It never commits or pushes the
checkout. A slash command runs through `ChatEdit_SendText`, the client's own parser, so the capture follows a confirmed
run rather than a fixed pause (#573). A flow that returns a ready check is captured once `!!DevSmoke` has polled it
true, so a window filled in from late data is not photographed empty (#593); a check that raises or never turns true
records its reason and fails the proof with it. A flow that needs real input names it with `--flow-click "NAME=X,Y"`,
`--flow-drag "NAME=X1,Y1,X2,Y2"`, `--flow-key "NAME=ACTION"` (the key the client binds to that action, as `key
--action` presses it) or `--flow-type "NAME=/COMMAND"` (typed into chat, so a protected command such as `/tar` runs):
once that reload's world screenshot has landed, `proof` sends them in order inside its own job and then waits for the
flow's ready screenshot as any other flow does, so a merchant window a key opens is still open for the capture (#655,
#857, #860). There is no default flow: ForeverCore has
no shared opener for an addon's update notice, so the flow is named on the command line and
`wow-forever-addon/in-game.md` shows both. A flow's own result is read after its screenshot, and a snippet that raised
fails the proof before any gist or `.visual-proof.json` exists (#580). Proof verifies its candidate links before
each capture and at teardown; a changed slot fails before a proof record is written.

The session is shared: `serve` starts the client once, and every `job` runs against that same client, so a test pays
the login once rather than once per test. A job holds `STATE_DIR/job.lock` only while it touches the client.
Waiters hold exclusive locks on numbered ticket files and acquire in arrival order; unlocked tickets are removed.
Serve teardown takes priority over waiters without interrupting the holder. Wait logs update the holder and queue
position; a timeout bounds the wait without guaranteeing acquisition. `STATE_DIR/job.json` names its holder
(pid, token, label, start) so a waiter can say who it waits for. The session
ends `IDLE_LIMIT` (60 min) after the last job ended, or after READY when none has run yet, and not while a request
is queued or a lease is live, and never later than
`MAX_SESSION` (3 h) from the launch; at either end it takes the job lock first, so a job in flight is never cut off.
`job` starts a detached `serve` when none runs and reuses a ready one. `up` is `serve` in the foreground, and `run`
is an alias for `job`. `lease` prints a token valid for its TTL without holding the lock between calls.
Each verb using that token takes and releases the lock itself; `release TOKEN` ends the lease and retains its reason.
Tokens are bound to their issuing session; expired or ended tokens fail before queuing. Issuing a lease prunes
expired records, and session teardown records the reason in unexpired leases.
Use `job --max S -- COMMAND` for exclusive work, limited to 600 s by default and at most 1800 s.
`job --hyprland` has serve relaunch into a private nested Hyprland for deskpilot, then back into gamescope before
releasing the lock. The command limit excludes relaunches: each world wait is bounded to 600 s; the return allowance
is 900 s including shutdown. Cancellation and command failure also return (tools/headless/README.md).
A source digest change in the launcher, its loaded repository modules or the headless addon also ends serve
through the same locked teardown; the next job starts a fresh serve with the updated code.

Every verb that touches the client (`shot`, `click`, `scroll`, `key`, `slash`, `reload`, `eval`, `errors`) runs as a
job: it proceeds when `FOREVER_CLIENT_JOB` names the token in `job.json`, and otherwise takes the job lock itself for
that one invocation. `status` and `sv` need no lock.

One Battle.net account means one client: a resident session holds an exclusive lock for its lifetime and refuses to
start while any process uses the Wine prefix, which is how a player's own running client is left alone. Another
agent's session is reused and its job is waited for up to `--timeout`; only the player's own client makes a job exit
3.

The client is for testing the Forever addons' interface, never for playing, and the verbs hold to that:

- Any input. `slash` sends any one-line slash command and `key` any key, so a check can use the character's own
  items and keybinds or move it where the check needs it. `click` and `scroll` need a screenshot taken since the
  last input, so every input aims at what the agent has just seen. `slash` puts the keyboard back in the chat box
  first, so a focused addon EditBox cannot swallow the command, and `click` and `slash` close a Game Menu left open.
- `--manual-launcher` (`serve`, `up`, `job`, `run`, `lease`, `smoke`, `proof`) disables OCR clicks and permits shots
  and left clicks before READY. Inspect each private screenshot before clicking. Never click Uninstall or change
  credentials.
- One client, one job. The session ends 10 minutes after the last job and 3 hours at most, and every ending logs the
  character out and stops the client.
- Human pace. Inputs are at least INPUT_GAP apart, across invocations, and slash commands type at TYPE_DELAY_MS.

Client verbs require FOREVER_CLIENT_CALLER (in-game or smoke-queue), or FOREVER_CLIENT_JOB inside a job.
Send the shared in-game agent an INGAME request as described in
.agents/skills/wow-forever-addon/in-game.md#requesting-a-check.
Battle.net sign-in labels persist a launcher-sign-in.txt block under STATE_DIR. Automatic starts refuse until
the player starts with --manual-launcher, signs in and reaches READY, which removes the record.
"""

from __future__ import annotations

import argparse
import fcntl
import functools
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import signal
import socket
import stat
import string
import struct
import subprocess
import sys
import tarfile
import time
import uuid
import zlib
from collections.abc import Callable, Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from PIL import Image

# The workspace checkout of each addon repository, and the test builds beside it: the same places the workspace's
# rebuild-dev.sh used, now built here so a build has one implementation.
WORKSPACE = Path.home() / "drive/proj/wow"
BUILD_ROOT = WORKSPACE / "test-artifacts"
# The development folders a dev build drops, so the client loads the addon and nothing that builds it.
DEV_FOLDERS = (
    "tools",
    "tests",
    "docs",
    "types",
    ".bugpatrol",
    ".sloppatrol",
    ".speedpatrol",
    ".github",
    ".agents",
    ".luacheckrc",
    ".luarc.json",
    ".pkgmeta",
)
PACKAGE_AS = re.compile(r"^package-as:\s*(\S+)\s*$", re.MULTILINE)
# The smoke's record: a commit status on the repository, in this context, which the release gate reads.
SMOKE_OWNER = "cjber"
SMOKE_CONTEXT = "headless-smoke"
SMOKE_REPO = re.compile(r"^[A-Za-z0-9._-]+$")
# ForeverCore's own repository: its smoke also links the consumers' latest released builds, because a core release
# reaches players before the addons that depend on it are re-released.
CORE_REPO = "forever-core"
STATUS_LIMIT = 140
# The visual proof a release prep or a Core pin bump records: `.visual-proof.json` in the checkout the proof is for,
# its screenshots in a secret gist, and the client build the session's own log names.
PROOF_FILE = ".visual-proof.json"
PROOF_SCRATCH = Path.home() / ".cache/agent-scratch"
GIST_OWNER = "cjber"
GIST_URL = re.compile(r"https://gist\.github\.com/[^/\s]+/([0-9a-f]+)")
GIST_DESCRIPTION = "WoW: Forever visual proof"
CLIENT_BUILD_LINE = re.compile(r"World of Warcraft \S+ \S+ (\d+(?:\.\d+)+)")
INTERFACE_LINE = re.compile(r"(?m)^## Interface:\s*(\d+)\s*$")

PREFIX = Path.home() / "Games/battlenet"
CLIENT = PREFIX / "drive_c/Program Files (x86)/World of Warcraft/_forever_"
LAUNCHER = PREFIX / "drive_c/Program Files (x86)/Battle.net/Battle.net.exe"
LAUNCH_ARGS = ["--exec=launch_uid wowf"]
# Battle.net ignores --exec once it is logged in, so the session presses the visible Play control on the WoW: Forever
# page that --exec opens. The target is read from the private gamescope screenshot, in its own pixel coordinates.
# The account's Battle.net region: the launcher logs in here before it can start the game.
BATTLE_NET = ("eu.actual.battle.net", 1119)
SIGN_IN_BLOCK = "launcher-sign-in.txt"
SIGN_IN_MESSAGE = (
    "Battle.net needs the player's sign-in; start with --manual-launcher while the player is present, "
    "sign in, and reach READY to clear the block"
)
# Battle.net's own exact labels on its sign-in pages: the returning-account page and the logged-out "Log in or sign up"
# page (#951). Neither has a Play button, so the startup loop would otherwise press Escape until its deadline.
LAUNCHER_SIGN_IN_LABELS = (
    ("welcome", "back"),
    ("email", "a", "code"),
    ("use", "password"),
    ("use", "passkey"),
    ("log", "in", "or", "sign", "up"),
)
# Battle.net's update modal, excluding the unrelated "Upgrade Available" account banner.
LAUNCHER_UPDATE_LABELS = (("installation", "required"),)
# Allow one retry for a launcher that did not accept Play, then stop sending input without a game process.
MAX_PLAY_CLICKS = 2
PLAY_RETRY_WAIT = 15.0  # Give each launch attempt the startup loop's full nudge interval to create the process.
# A driver upgrade whose loaded kernel module is still the old one makes Vulkan fail before gamescope can start. The
# module names itself here, and nvidia-smi or the installed userspace library names the other half (#567).
NVIDIA_MODULE_VERSION = Path("/sys/module/nvidia/version")
NVIDIA_MISMATCH = "driver/library version mismatch"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "forever-client"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "forever-client/env.json"
ADDON = Path(__file__).resolve().parent / "!!ForeverHeadless"
WIDTH, HEIGHT = 1920, 1080
# The session is shared, so the client stays up while jobs arrive instead of ending after one test. These are fixed
# limits, not heuristics: it ends IDLE_LIMIT after the last job ended (or after READY; never while work is
# pending), and never later than MAX_SESSION from the launch. Both are checked only between jobs; a job in flight is
# never cut off.
IDLE_LIMIT = 60 * 60
MAX_SESSION = 3 * 60 * 60
EVAL_SAVE_WAIT = 10  # seconds an eval's saved result may take to reach disk before the saving reload is used
WAIT_POLL = 1.0  # how often a waiter checks the session lock, the job lock and the Wine prefix
JOB_POLL = 0.5  # how often a job waiter checks the job lock while it waits
LOGOUT_WAIT = 60  # /quit outside an inn counts down 20 s before the client exits
# A `down` waits for the job in flight to finish first: a smoke is the longest job.
STOP_WAIT = 30 * 60
INPUT_GAP = 1.5
TYPE_DELAY_MS = "120"
WHEEL_DELAY_MS = "120"
# A drag moves in this many steps by default, at most DRAG_STEPS_MAX, pausing DRAG_STEP_DELAY seconds around each so
# the client sees the button go down, the pointer travel over several frames, and the button come up at the end.
DRAG_STEPS = 10
DRAG_STEPS_MAX = 100
DRAG_STEP_DELAY = "0.03"
# Seconds a proof waits for a flow's screenshot, or for !!DevSmoke's failure record. Its own ready check stops at
# 60 s; the extra 5 s only lets that failure reach SavedVariables before the proof falls back to its final reload.
FLOW_READY_SECONDS = 65
# The job lock's file, the holder it names, the mark of the last job's end, the stop `down` asks for, and the
# session's own log.
JOB_LOCK = "job.lock"
JOB_RECORD = "job.json"
LAST_JOB = "last-job"
STOP = "stop"
SERVE_LOG = "serve.log"
LEASE_TTL = 10 * 60
LEASE_MAX = 30 * 60
HYPRLAND_REQUEST = "hyprland-request.json"
HYPRLAND_RESULT = "hyprland-result"
HYPRLAND_END = "hyprland-end"
HYPRLAND_WORLD_WAIT = 600
HYPRLAND_RETURN_WAIT = 900
WORLD_CHECK = 30  # Resident world checks are infrequent and never interrupt a job.
RELOAD_WAIT = 120  # how long a /reload's loading screen may hide the strip, the same bound `reload` waits for the world
# The modifiers `--hold` takes, by the X keysym xdotool presses for each. Job end releases every one of them.
MODIFIER_KEYS = {"shift": "Shift_L", "ctrl": "Control_L", "alt": "Alt_L"}
# Key names people write that xdotool spells another way: the game binds autorun to Num Lock.
KEY_ALIASES = {"NumLock": "Num_Lock"}
# The game actions `key --action` presses. Each resolves to the key the running client binds to it, never a fixed key:
# an account can rebind any of them (the headless account moves forward on S, so W does nothing there) (#820).
ACTIONS = (
    "MOVEFORWARD",
    "MOVEBACKWARD",
    "TURNLEFT",
    "TURNRIGHT",
    "STRAFELEFT",
    "STRAFERIGHT",
    "JUMP",
    "INTERACTTARGET",
    "TARGETNEARESTENEMY",
)
# The client's own default keys for those actions, as its Key Bindings "Reset to Default" sets them. The defaults live
# in the client binary, not in its Bindings XML, so this is the one copy; it is read only when the running client's
# answer is not on disk, and bindings-cache.wtf records every change from it.
DEFAULT_BINDINGS: dict[str, tuple[str, ...]] = {
    "MOVEFORWARD": ("W", "UP"),
    "MOVEBACKWARD": ("S", "DOWN"),
    "TURNLEFT": ("A", "LEFT"),
    "TURNRIGHT": ("D", "RIGHT"),
    "STRAFELEFT": ("Q",),
    "STRAFERIGHT": ("E",),
    "JUMP": ("SPACE",),
    "INTERACTTARGET": (),
    "TARGETNEARESTENEMY": ("TAB",),
}
# The game's names for keys xdotool spells another way; a single letter or digit is lowercased, F-keys stay as they are.
GAME_KEYSYMS = {
    "SPACE": "space",
    "TAB": "Tab",
    "UP": "Up",
    "DOWN": "Down",
    "LEFT": "Left",
    "RIGHT": "Right",
    "ENTER": "Return",
    "ESCAPE": "Escape",
    "BACKSPACE": "BackSpace",
    "DELETE": "Delete",
    "INSERT": "Insert",
    "HOME": "Home",
    "END": "End",
    "PAGEUP": "Prior",
    "PAGEDOWN": "Next",
    "NUMLOCK": "Num_Lock",
    "-": "minus",
    "=": "equal",
    "`": "grave",
    "[": "bracketleft",
    "]": "bracketright",
    ";": "semicolon",
    "'": "apostrophe",
    ",": "comma",
    ".": "period",
    "/": "slash",
    "\\": "backslash",
}
GAME_MODIFIERS = {"SHIFT": "Shift_L", "CTRL": "Control_L", "ALT": "Alt_L"}
# The resolved keys, per session and per SavedVariables write, so one walk does not re-read the client each step.
BINDINGS_CACHE = "bindings.json"
# The hold in progress, its token and keys, so a job end or the hold's watchdog releases them after a killed verb.
HELD_KEYS = "held-keys"
# The mouse button a drag holds down, recorded so a drag killed mid-chain is released by the next job's cleanup.
HELD_BUTTON = "held-button"
HOLD_MAX = 10.0  # seconds one `key --for` may hold; longer walks go through `walkto`, which re-reads as it goes
HOLD_SLICE = 0.25  # seconds between safety checks while keys are held
HOLD_GRACE = 2.0  # seconds past a hold's end before its watchdog releases what is still down
# Keys that move the character on the client's default bindings: a raw hold of one marks the job as having moved it.
MOVEMENT_KEYSYMS = {"w", "a", "s", "d", "q", "e", "space", "Up", "Down", "Left", "Right"}
CHAT_FOCUS_POLLS = 30  # 0.1 s strip reads after a Return before the next key: the frame lags on a loaded machine
MENU_CLOSE_TRIES = 2  # Escape presses to close a Game Menu left open; one closes it, the second covers a dropped key
# The game's own window title: the character-select nudge sends Return only to it, never to the launcher, whose
# focused Play button a Return would press again.
GAME_WINDOW = "World of Warcraft"

# The player's client is a Faugus Launcher game: Faugus runs its `umu-run`, which starts Battle.net under the game's
# Proton runner in the Steam runtime. `capture-env` records that launch from the running `umu-run` process: the
# script and the environment Faugus gives it, minus what belongs to one run or to the desktop. DISPLAY and
# WAYLAND_DISPLAY above all: the session's own come from gamescope, and an inherited Wayland socket would let Wine
# open a window on the player's desktop.
KEEP_PREFIXES = ("WINE", "DXVK_", "VKD3D_", "__GL", "__GLX", "PROTON", "STAGING_", "LD_", "VK_", "UMU_", "GAMEID")
DROP = {
    "WINESERVERSOCKET",
    "WINEPRELOADRESERVE",
    "WINELOADERNOEXEC",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "UMU_INVOCATION_ID",
    "PROTON_VERB",
}


# A headless session plays nothing to the person at the desk. Disabling Wine's audio drivers leaves the game with no
# output device, so it runs silent. This acts on the session's process environment only: muting through the game's
# sound CVars would be saved into the shared Config.wtf and silence the player's own client too.
SILENT_AUDIO = ("winepulse.drv=d", "winealsa.drv=d")


def silenced(env: Mapping[str, str]) -> dict[str, str]:
    """The launch environment with Wine's audio drivers disabled, keeping any DLL overrides it already carries."""
    overrides = [o for o in env.get("WINEDLLOVERRIDES", "").split(";") if o]
    return {**env, "WINEDLLOVERRIDES": ";".join([*overrides, *SILENT_AUDIO])}


class ClientError(Exception):
    """A failure the agent should read: printed without a traceback, exit status 2."""


class SignInRequired(ClientError):
    """Battle.net is unavailable until the player signs in."""


def require_launcher_available(manual_launcher: bool = False) -> None:
    if not manual_launcher and (STATE_DIR / SIGN_IN_BLOCK).exists():
        raise SignInRequired(SIGN_IN_MESSAGE)


class SafetyRefusal(ClientError):
    """Live character safety is unsafe or unknown, exit status 4. No recovery input is sent."""


def wine_env(environ: Mapping[str, str]) -> dict[str, str]:
    """The part of a running client's environment that launches another one the same way."""
    return {k: v for k, v in environ.items() if k.startswith(KEEP_PREFIXES) and k not in DROP}


def read_environ(pid: int) -> dict[str, str]:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return {}
    pairs = (item.split(b"=", 1) for item in raw.split(b"\0") if b"=" in item)
    return {k.decode(errors="replace"): v.decode(errors="replace") for k, v in pairs}


def in_prefix(env: Mapping[str, str], prefix: Path = PREFIX) -> bool:
    """Whether a process runs in the prefix. Proton gives its Wine processes `<prefix>/pfx/`, which umu links back
    to the prefix itself, so the paths are compared resolved, not as written."""
    value = env.get("WINEPREFIX")
    return bool(value) and Path(value).resolve() == prefix.resolve()


def pids() -> Iterable[int]:
    uid = os.getuid()
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                if entry.stat().st_uid == uid:
                    yield int(entry.name)
            except OSError:
                continue


def cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return ""


def prefix_snapshot(prefix: Path = PREFIX, exclude: Iterable[int] = ()) -> dict[int, dict[str, str]]:
    """Read prefix membership and ownership together, before a process can exit between separate reads."""
    skip = set(exclude)
    found = {}
    for pid in pids():
        if pid not in skip:
            env = read_environ(pid)
            if in_prefix(env, prefix):
                found[pid] = env
    return found


def prefix_users(prefix: Path = PREFIX, exclude: Iterable[int] = ()) -> list[int]:
    """Processes running in the Wine prefix: a player's client, its launcher, or a wineserver left behind."""
    return list(prefix_snapshot(prefix, exclude))


def prefix_ownership(processes: Mapping[int, Mapping[str, str]], token: str | None) -> tuple[list[int], list[int]]:
    """Split a single prefix snapshot into this session's processes and processes we must never touch."""
    if not token:
        return [], list(processes)
    owned, foreign = [], []
    for pid, env in processes.items():
        (owned if env.get("FOREVER_CLIENT_SESSION") == token else foreign).append(pid)
    return owned, foreign


def require_owned_prefix(token: str | None) -> list[int]:
    processes = prefix_snapshot()
    users = list(processes)
    _, foreign = prefix_ownership(processes, token)
    if foreign:
        detail = ", ".join(map(str, foreign))
        raise ClientError("teardown refused: foreign or unowned Wine prefix processes: " + detail)
    if users and not token:
        raise ClientError("teardown refused: session ownership is unavailable for Wine prefix processes")
    return users


def kill_owned_pid(pid: int, token: str, server: Path) -> bool:
    """Signal a token-matched process through a pidfd, so PID reuse cannot hit a new process."""
    try:
        pidfd = os.pidfd_open(pid)
    except (AttributeError, OSError):
        return False
    try:
        env = read_environ(pid)
        if not in_prefix(env) or env.get("FOREVER_CLIENT_SESSION") != token:
            return False
        try:
            executable = Path(f"/proc/{pid}/exe").readlink().resolve()
        except OSError:
            return False
        # Even a token-owned server can acquire a foreign client after our prefix scan. Let it exit idle.
        if executable == server:
            return False
        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
        return True
    except ProcessLookupError:
        return False
    finally:
        os.close(pidfd)


def client_pid() -> int | None:
    return next((p for p in pids() if "Wow.exe" in cmdline(p) and in_prefix(read_environ(p))), None)


def read_launch_config() -> dict:
    try:
        launch = json.loads(CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ClientError(
            f"no launch recorded: start Battle.net from Faugus, then run `forever_client.py capture-env` ({CONFIG})"
        ) from None
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ClientError(f"{CONFIG}: invalid JSON ({error})") from None
    if not isinstance(launch, dict):
        raise ClientError(f"{CONFIG}: expected a JSON object")
    return launch


def character_config(launch: Mapping) -> dict[str, str]:
    """Validate the owner-approved character's identity before starting any client process."""
    character = launch.get("character")
    if not isinstance(character, dict):
        raise ClientError(f"{CONFIG} has no approved character: add character.name and character.guid")
    name, guid = character.get("name"), character.get("guid")
    if not isinstance(name, str) or not name.strip() or not isinstance(guid, str) or not guid.strip():
        raise ClientError(f"{CONFIG} has an invalid character identity: name and guid are required")
    return {"name": name, "guid": guid}


def lua_string(value: str) -> str:
    """Encode a character field as a Lua 5.1 quoted string without control escapes or lossy Unicode."""
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ClientError(f"{CONFIG} character identity contains a control character")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def prepare_headless_addon(character: Mapping[str, str]) -> Path:
    """Create an isolated headless addon copy with immutable session configuration."""
    target = STATE_DIR / "headless-addon"
    if target.exists() or target.is_symlink():
        raise ClientError(f"{target} is left over from an earlier session: recover it before starting")
    try:
        shutil.copytree(ADDON, target)
        (target / "Config.lua").write_text(
            "FOREVER_HEADLESS_CHARACTER = {name="
            + lua_string(str(character["name"]))
            + ", guid="
            + lua_string(str(character["guid"]))
            + "}\n",
            encoding="utf-8",
        )
        toc = target / "!!ForeverHeadless.toc"
        text = toc.read_text(encoding="utf-8")
        toc.write_text(text.replace("ForeverHeadless.lua\n", "Config.lua\nForeverHeadless.lua\n"), encoding="utf-8")
    except BaseException:
        if target.is_dir():
            shutil.rmtree(target)
        raise
    return target


# --- session state ---------------------------------------------------------------------------------------------


def state_file() -> Path:
    return STATE_DIR / "session.json"


def write_state(state: Mapping) -> None:
    """Publish session changes atomically, including the reload gate queued jobs read."""
    path = state_file()
    atomic_write(path, json.dumps(dict(state)))


def atomic_write(path: Path, contents: str) -> None:
    """Publish a small state file durably, including its directory entry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(contents)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def load_state() -> dict:
    try:
        return json.loads(state_file().read_text())
    except (OSError, ValueError):
        raise ClientError("no headless session is running: start one with `forever_client.py up`") from None


def session_alive(state: Mapping) -> bool:
    """Whether the process that wrote session.json still runs; a reused pid is told apart by its start time."""
    return owner_alive({"pid": state.get("pid"), "started": state.get("start_ticks"), "boot_id": state.get("boot_id")})


def current_session() -> dict | None:
    """The live session's state, or None when none runs or its process is gone."""
    try:
        state = json.loads(state_file().read_text())
    except (OSError, ValueError):
        return None
    return state if isinstance(state, dict) and session_alive(state) else None


def session_lock_held() -> bool:
    """Whether a process holds the session lock, whether or not it has written session.json yet."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        handle = open(STATE_DIR / "lock", "w")
    except OSError:
        return False
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    finally:
        handle.close()
    return False


def screenshots() -> set[Path]:
    folder = CLIENT / "Screenshots"
    return set(folder.glob("*")) if folder.is_dir() else set()


def wait_for_world(
    before: set[Path],
    timeout: float,
    nudge=None,
    *,
    require_marker: bool = False,
    safety_state: Mapping | None = None,
    handshake_state: Mapping | None = None,
) -> Path:
    """Block until the dev addon's screenshot appears: the world has loaded. `nudge` runs every 15 s meanwhile.

    With `handshake_state`, a world that stays loaded HANDSHAKE_WAIT without the marker screenshot is a refusal:
    !!ForeverHeadless withholds the marker when the character is not the approved one or is unsafe, and waiting out
    the whole timeout would leave that character parked in the world.
    """
    deadline, next_nudge = time.monotonic() + timeout, time.monotonic() + 20
    in_world_since = next_handshake_check = None
    while time.monotonic() < deadline:
        if safety_state is not None:
            require_safe(safety_state, waiting=True)
        if handshake_state is not None and time.monotonic() >= (next_handshake_check or 0):
            next_handshake_check = time.monotonic() + 5
            if client_ui(handshake_state).get("world"):
                in_world_since = in_world_since or time.monotonic()
                if time.monotonic() - in_world_since >= HANDSHAKE_WAIT:
                    raise SafetyRefusal(
                        f"the world loaded but !!ForeverHeadless sent no readiness marker within {HANDSHAKE_WAIT} s: "
                        "the character is not the approved one, or is dead or in combat"
                    )
            else:
                in_world_since = None
        new = screenshots() - before
        if new:
            candidates = []
            for path in new:
                if not require_marker:
                    candidates.append(path)
                    continue
                try:
                    if path.is_file() and has_headless_marker(path):
                        candidates.append(path)
                except ClientError:
                    # Screenshot() can expose the file before its final PNG chunk; retry on the next poll.
                    continue
            if candidates:
                return max(candidates, key=lambda p: p.stat().st_mtime)
        if nudge and time.monotonic() >= next_nudge:
            nudge()
            next_nudge = time.monotonic() + 15
        time.sleep(1)
    raise ClientError(f"the world did not load within {timeout:.0f} s")


# --- display verbs ---------------------------------------------------------------------------------------------


def x(state: Mapping, *args: str) -> None:
    require_safe(state, waiting=not state.get("ready"))
    # Under a nested Hyprland, XWayland puts the client's output at its own root offset; a point is in the output's
    # pixels, the same pixels a screenshot of it shows, so the offset is added here, once, for every absolute move.
    # A pointer chain (one that starts with a move, as a drag does) carries no typed text, so every move in it is one.
    origin = state.get("origin")
    if origin and args and args[0] == "mousemove":
        moved = list(args)
        for index, word in enumerate(moved):
            if word == "mousemove":
                moved[index + 1] = str(int(moved[index + 1]) + origin[0])
                moved[index + 2] = str(int(moved[index + 2]) + origin[1])
        args = tuple(moved)
    subprocess.run(["xdotool", *args], env={**os.environ, "DISPLAY": state["display"]}, check=True)


def game_focused(state: Mapping) -> bool:
    """Whether the game's own window, not the launcher or an empty desktop, has keyboard focus."""
    found = subprocess.run(
        ["xdotool", "getwindowfocus", "getwindowname"],
        env={**os.environ, "DISPLAY": state["display"]},
        capture_output=True,
        text=True,
        check=False,
    )
    return found.stdout.strip() == GAME_WINDOW


def mark(name: str) -> float:
    """When the session last did `name` (an input or a screenshot), as a timestamp; 0 when never."""
    try:
        return (STATE_DIR / name).stat().st_mtime
    except OSError:
        return 0.0


def modifier_keys(hold: Sequence[str]) -> list[str]:
    """The keysyms for `--hold` names, once each in the order given; any name but shift, ctrl or alt is refused."""
    refused = [name for name in hold if name not in MODIFIER_KEYS]
    if refused:
        raise ClientError(f"--hold takes {', '.join(MODIFIER_KEYS)}; refused {', '.join(refused)}")
    return list(dict.fromkeys(MODIFIER_KEYS[name] for name in hold))


def release_modifiers(display: str | None, keys: Iterable[str] = MODIFIER_KEYS.values()) -> str | None:
    """Send keyup for modifier keys on a display; the failure as text, or None. It never raises.

    No safety check runs first: a key release is the one input that is always safe, and job end must send it even
    when the client is somewhere a verb would be refused. The X server ignores a release for a key that is not down.
    """
    keys = list(keys)
    if not display or not keys:
        return None
    try:
        subprocess.run(
            ["xdotool", "keyup", *keys],
            env={**os.environ, "DISPLAY": display},
            check=True,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return f"keyup {' '.join(keys)} on {display} failed: {error}"
    return None


def release_button(display: str | None) -> str | None:
    """Send mouseup for the button a drag recorded as down, if any; the failure as text, or None. It never raises.

    A drag stopped between its press and its release (a job timeout's SIGTERM kills its xdotool chain) leaves the
    button down in the client, so every later pointer move would drag; the record says which button to let go.
    """
    record = STATE_DIR / HELD_BUTTON
    try:
        button = record.read_text().strip()
    except OSError:
        return None
    if display and button in ("1", "3"):
        try:
            subprocess.run(
                ["xdotool", "mouseup", button],
                env={**os.environ, "DISPLAY": display},
                check=True,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return f"mouseup {button} on {display} failed: {error}"
    record.unlink(missing_ok=True)
    return None


def release_session_modifiers(state: Mapping | None) -> None:
    """Release shift, ctrl, alt, any key a verb was holding and a dragged button on the session's display, so no job
    inherits an input an ended one held."""
    display = (state or {}).get("display")
    keys = list(MODIFIER_KEYS.values())
    keys += [key for key in held_record()[1] if key not in keys]
    failure = release_modifiers(display, keys)
    if not failure:
        (STATE_DIR / HELD_KEYS).unlink(missing_ok=True)
    for problem in (failure, release_button(display)):
        if problem:
            print(f"forever_client: {problem}", file=sys.stderr, flush=True)


def held_record() -> tuple[str | None, list[str]]:
    """The token and keys of the hold in progress, from its record; (None, []) when there is none."""
    try:
        record = json.loads((STATE_DIR / HELD_KEYS).read_text())
    except (OSError, ValueError):
        return None, []
    keys = record.get("keys") if isinstance(record, dict) else None
    if not isinstance(keys, list):
        return None, []
    return record.get("token"), [key for key in keys if isinstance(key, str)]


def release_held_later(display: str, token: str, seconds: float) -> None:
    """Start a detached watchdog that releases this hold's keys `seconds` from now if its record is still there: a verb
    killed mid-hold has no process left to release them, and no job may start for a long time (#833 review)."""
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "release-held", token, f"{seconds:.2f}", display],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        raise ClientError(f"cannot start the held-key watchdog: {error}") from None


def release_held(token: str, seconds: float, display: str) -> int:
    """The watchdog: after `seconds`, release the keys of hold `token` if that hold is still recorded."""
    time.sleep(seconds)
    recorded, keys = held_record()
    if recorded == token and keys:
        if release_modifiers(display, keys) is None:
            (STATE_DIR / HELD_KEYS).unlink(missing_ok=True)
    return 0


@contextmanager
def held(state: Mapping, keys: Sequence[str], watchdog: float | None = None) -> Generator[None]:
    """Hold keys down for the body, releasing every key pressed even when the body raises.

    The keys are recorded under the state directory first, so the next job start or end releases them after a verb
    killed while holding them; with `watchdog`, a detached process also releases them that many seconds on.
    """
    pressed: list[str] = []
    record = STATE_DIR / HELD_KEYS
    if keys:
        token = uuid.uuid4().hex
        atomic_write(record, json.dumps({"token": token, "keys": list(keys)}))
        if watchdog is not None:
            release_held_later(str(state.get("display") or ""), token, watchdog)
    try:
        for key in keys:
            x(state, "keydown", key)
            pressed.append(key)
        yield
    finally:
        failure = release_modifiers(state.get("display"), pressed)
        if keys and not failure:
            record.unlink(missing_ok=True)
    if failure:
        raise ClientError(failure)


def send(state: Mapping, *args: str, hold: Sequence[str] = ()) -> None:
    """One input action, at least INPUT_GAP after the last one from any invocation, with `hold` keys held down."""
    wait = INPUT_GAP - (time.time() - mark("last-input"))
    if wait > 0:
        time.sleep(wait)
    with held(state, hold):
        x(state, *args)
    (STATE_DIR / "last-input").touch()


def _complete_png(path: Path) -> bool:
    """Return whether path contains a complete PNG, including its terminal IEND chunk."""
    try:
        with path.open("rb") as image:
            if image.read(8) != b"\x89PNG\r\n\x1a\n":
                return False
            while True:
                header = image.read(8)
                if len(header) != 8:
                    return False
                length, chunk = struct.unpack(">I4s", header)
                if chunk == b"IEND":
                    return length == 0 and len(image.read(4)) == 4
                image.seek(length + 4, os.SEEK_CUR)
    except (OSError, struct.error):
        return False


def runtime_dir(environ: Mapping[str, str], uid: int, root: Path = Path("/run/user")) -> Path:
    """Use an existing login runtime directory, never repair permissions or create one."""
    explicit = environ.get("XDG_RUNTIME_DIR")
    path = Path(explicit) if explicit else root / str(uid)
    try:
        info = path.lstat()
        valid = path.is_absolute() and stat.S_ISDIR(info.st_mode) and info.st_uid == uid
        valid = valid and stat.S_IMODE(info.st_mode) == 0o700
    except OSError:
        valid = False
    if not valid:
        raise ClientError(f"invalid XDG_RUNTIME_DIR {path}: need an existing owned directory with mode 0700")
    if not explicit:
        print(f"warning: XDG_RUNTIME_DIR is unset; using {path}", file=sys.stderr)
    return path


def nvidia_userspace_version(run=None) -> str | None:
    """The installed NVIDIA userspace driver version, when nvidia-smi cannot report it itself.

    An upgraded userspace whose loaded module is still the old one makes nvidia-smi fail with its own mismatch line.
    The installed package (Arch's nvidia-utils, Debian's nvidia-driver) or the versioned NVML library then names the
    userspace half, so the error can give both versions rather than only "Vulkan failed" (#567).
    """
    run = run or subprocess.run
    for command in (
        ["pacman", "-Q", "nvidia-utils"],
        ["dpkg-query", "-W", "-f=${Version}\n", "nvidia-driver"],
    ):
        try:
            result = run(command, capture_output=True, text=True, check=False)
        except OSError:
            continue
        if result.returncode == 0:
            words = (result.stdout or "").strip().split()
            if words:
                return words[-1].split("-", 1)[0]  # Arch's 620.70.06-1 is driver 620.70.06
    for library in sorted(Path("/usr/lib").glob("libnvidia-ml.so.*")):
        match = re.search(r"\.so\.(\d+(?:\.\d+)+)$", library.name)
        if match:
            return match.group(1)
    return None


def nvidia_mismatch(module_path: Path = NVIDIA_MODULE_VERSION, run=None) -> str | None:
    """The loaded NVIDIA module and its userspace disagreeing, as the sentence `up` prints, or None.

    A driver package upgrade installs new userspace while the old kernel module stays loaded until a reboot. Vulkan
    then finds no device and gamescope asserts, which used to surface only as "gamescope started no client" (#567).
    """
    try:
        module = module_path.read_text().strip()
    except OSError:
        return None
    if not module:
        return None
    run = run or subprocess.run
    try:
        smi = run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if smi.returncode == 0:
        lines = (smi.stdout or "").strip().splitlines()
        userspace = lines[0].strip() if lines else ""
        if userspace and userspace != module:
            return f"the NVIDIA kernel module ({module}) does not match its userspace ({userspace}): reboot first"
        return None
    output = f"{smi.stdout or ''}\n{smi.stderr or ''}".casefold()
    if NVIDIA_MISMATCH not in output:
        return None
    userspace = nvidia_userspace_version(run)
    detail = f" ({userspace})" if userspace else ""
    return f"the NVIDIA kernel module ({module}) does not match its userspace{detail}: reboot first"


def shot(state: Mapping, path: Path, *, mark_read: bool = True) -> Path:
    if "runtime_dir" not in state:
        raise ClientError("session has no runtime directory recorded; restart the headless session")
    runtime = runtime_dir({"XDG_RUNTIME_DIR": state["runtime_dir"]}, os.getuid())
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    nested = state.get("nested")
    if state.get("mode") == "hyprland" and nested:
        env = {**os.environ, "XDG_RUNTIME_DIR": str(runtime), "WAYLAND_DISPLAY": nested["wayland"]}
        subprocess.run(["grim", "-o", nested["output"], str(path)], env=env, check=True, capture_output=True)
    else:
        env = {**os.environ, "XDG_RUNTIME_DIR": str(runtime), "GAMESCOPE_WAYLAND_DISPLAY": state["gamescope_socket"]}
        subprocess.run(["gamescopectl", "screenshot", str(path)], env=env, check=True, capture_output=True)
    for _ in range(50):
        if _complete_png(path):
            if mark_read:
                (STATE_DIR / "last-shot").touch()
            return path
        time.sleep(0.1)
    raise ClientError(f"gamescope wrote no screenshot to {path}")


# Gamescope maps absolute XTEST coordinates onto its focused window, whatever that window's X position, so a point
# here is in the window's own pixels, the same pixels a screenshot shows. xdotool's --window option adds the window's
# X position to the point and must never be used.
# A drag moves in this many steps, pausing between them, so the client sees the press, a move and the release apart.
DRAG_STEPS = 8
DRAG_PAUSE_S = "0.05"


def click(state: Mapping, px: int, py: int, button: str, hold: Sequence[str] = ()) -> None:
    if button not in ("1", "3"):
        raise ClientError("click takes --button 1 (left) or 3 (right)")
    keys = modifier_keys(hold)
    if mark("last-shot") <= mark("last-input"):
        raise ClientError("take a `shot` and read it first: a click must aim at addon UI in the current frame")
    if not (0 <= px < WIDTH and 0 <= py < HEIGHT):
        raise ClientError(f"({px}, {py}) is outside the {WIDTH}x{HEIGHT} frame")
    if state.get("ready"):
        close_game_menu(state)
    send(state, "mousemove", str(px), str(py), "click", button, hold=keys)


def hover(state: Mapping, px: int, py: int, hold: Sequence[str] = ()) -> None:
    """Move the pointer to a point in the current frame, for a tooltip or an OnEnter check; screenshot-bound."""
    keys = modifier_keys(hold)
    if mark("last-shot") <= mark("last-input"):
        raise ClientError("take a `shot` and read it first: a hover must aim at addon UI in the current frame")
    if not (0 <= px < WIDTH and 0 <= py < HEIGHT):
        raise ClientError(f"({px}, {py}) is outside the {WIDTH}x{HEIGHT} frame")
    send(state, "mousemove", str(px), str(py), hold=keys)


def scroll(state: Mapping, px: int, py: int, ticks: int, hold: Sequence[str] = ()) -> None:
    """Turn the mouse wheel at a point in the current frame: positive is up (zoom in), negative down.

    The world map's zoom lives on its ScrollContainer, which a click does not reach and `slash` refuses to open up as
    arbitrary Lua. This is the same screenshot-bound input as `click`, so it aims only at UI just read in a shot (#548).
    """
    if ticks == 0:
        raise ClientError("scroll takes a non-zero number of wheel ticks: positive up, negative down")
    keys = modifier_keys(hold)
    if mark("last-shot") <= mark("last-input"):
        raise ClientError("take a `shot` and read it first: a scroll must aim at addon UI in the current frame")
    if not (0 <= px < WIDTH and 0 <= py < HEIGHT):
        raise ClientError(f"({px}, {py}) is outside the {WIDTH}x{HEIGHT} frame")
    button = "4" if ticks > 0 else "5"  # X11 wheel up and wheel down
    send(
        state,
        "mousemove",
        str(px),
        str(py),
        "click",
        "--repeat",
        str(abs(ticks)),
        "--delay",
        WHEEL_DELAY_MS,
        button,
        hold=keys,
    )


def game_keysyms(binding: str) -> list[str] | None:
    """The xdotool keysyms a game binding presses, modifiers first, or None for a mouse button or a key it cannot name.

    The game writes a binding as its modifiers and key joined by `-`, as `CTRL-SHIFT-B`; the key `-` itself is the
    last part, so `SHIFT--` is Shift and minus.
    """
    parts = binding.split("-")
    if binding.endswith("-"):
        parts = [*parts[:-2], "-"]
    *modifiers, key = parts
    if not key or any(modifier not in GAME_MODIFIERS for modifier in modifiers):
        return None
    if key.startswith("BUTTON") or key.startswith("MOUSEWHEEL"):
        return None
    if re.fullmatch(r"F\d{1,2}", key):
        keysym = key
    elif len(key) == 1 and key.isalnum():
        keysym = key.lower()
    elif key.startswith("NUMPAD") and key[6:].isdigit():
        keysym = f"KP_{key[6:]}"
    else:
        keysym = GAME_KEYSYMS.get(key)
    if keysym is None:
        return None
    return [GAME_MODIFIERS[modifier] for modifier in modifiers] + [keysym]


def bindings_from_cache_file(text: str) -> dict[str, list[str]]:
    """Each action's keys from the client's defaults changed by a bindings-cache.wtf: `bind KEY ACTION` moves the key
    to that action, first in its list, and `bind KEY NONE` unbinds it."""
    keys = {action: list(default) for action, default in DEFAULT_BINDINGS.items()}
    for line in text.splitlines():
        match = re.fullmatch(r"bind (\S+) (\S+)", line.strip())
        if not match:
            continue
        key, action = match.groups()
        for bound in keys.values():
            if key in bound:
                bound.remove(key)
        if action in keys:
            keys[action].insert(0, key)
    return keys


def approved_character() -> str | None:
    """The approved character's name from the launch config, or None when there is none to read."""
    try:
        character = json.loads(CONFIG.read_text()).get("character")
    except (OSError, ValueError, AttributeError):
        return None
    name = character.get("name") if isinstance(character, dict) else None
    return name if isinstance(name, str) and name.strip() else None


def character_folder() -> Path | None:
    """The approved character's WTF folder, `Account/<account>/<realm>/<name>-<suffix>` or `.../<name>`, or None when
    no folder or more than one matches."""
    name = approved_character()
    if not name:
        return None
    accounts = CLIENT / "WTF/Account"
    found = sorted(
        path
        for path in accounts.glob("*/*/*")
        if path.is_dir() and (path.name == name or path.name.startswith(f"{name}-"))
    )
    return found[0] if len(found) == 1 else None


def account_folder() -> Path | None:
    """The WTF account folder holding the approved character, or None when it cannot be told apart."""
    character = character_folder()
    return character.parent.parent if character else None


def recorded_bindings() -> tuple[dict[str, list[str]], str] | None:
    """The keys the running client gave GetBindingKey, from !!DevSmoke's SavedVariables, and the file's identity."""
    folder = account_folder()
    files = saved_variables("!!DevSmoke")
    if folder is not None:
        files = [path for path in files if folder in path.parents]
    lua = load_tool("forever_errors", Path(__file__).resolve().parents[1] / "forever_errors.py")
    for path in sorted(files, key=lambda candidate: candidate.stat().st_mtime, reverse=True):
        try:
            variables = lua.load_lua(path)
        except (OSError, lua.LuaSyntaxError):
            continue
        smoke = variables.get("DevSmokeDB")
        record = smoke.get("bindings") if isinstance(smoke, dict) else None
        keys = record.get("keys") if isinstance(record, dict) else None
        if not isinstance(keys, dict):
            continue
        resolved = {}
        for action in ACTIONS:
            bound = keys.get(action)
            values = bound.values() if isinstance(bound, dict) else bound if isinstance(bound, list) else ()
            resolved[action] = [value for value in values if isinstance(value, str)]
        return resolved, f"{path}:{path.stat().st_mtime_ns}"
    return None


def file_bindings() -> dict[str, list[str]]:
    """The client's defaults changed by the character's own bindings-cache.wtf when it keeps per-character bindings,
    otherwise by the account's."""
    character = character_folder()
    if character is None:
        raise ClientError("cannot tell which WTF folder is the session's character, so its bindings are unknown")
    for path in (character / "bindings-cache.wtf", character.parent.parent / "bindings-cache.wtf"):
        try:
            return bindings_from_cache_file(path.read_text(errors="replace"))
        except OSError:
            continue
    return bindings_from_cache_file("")


def asked_bindings(state: Mapping) -> dict[str, list[str]]:
    """Each action's keys from the running client's own GetBindingKey, asked through an eval: one reload runs it and a
    second saves its answer."""
    names = ", ".join(f'"{action}"' for action in ACTIONS)
    source = (
        f"for _, action in ipairs({{ {names} }}) do\n"
        "\tlocal first, second = GetBindingKey(action)\n"
        '\tprint("BIND", action, first or "", second or "")\n'
        "end\n"
    )
    tool = devsmoke_eval()
    try:
        written = tool.write_source(source, "key binding lookup", addons=CLIENT / "Interface/AddOns")
    except tool.EvalError as error:
        raise ClientError(str(error)) from None
    try:
        reload(state)
    finally:
        clear_eval_inbox(quiet=True)
    reload(state)
    data = saved_eval(str(written["token"]))
    out = data.get("out")
    lines = out.values() if isinstance(out, dict) else out if isinstance(out, list) else []
    keys: dict[str, list[str]] = {}
    for line in lines:
        parts = str(line).split("\t")
        if len(parts) >= 2 and parts[0] == "BIND" and parts[1] in ACTIONS:
            keys[parts[1]] = [part for part in parts[2:] if part]
    if set(keys) != set(ACTIONS):
        raise ClientError(f"the key binding lookup answered {len(keys)} of {len(ACTIONS)} actions: {data.get('err')}")
    return keys


def bindings_hash(keys: Mapping[str, Sequence[str]]) -> int:
    """The 16-bit hash !!ForeverHeadless draws of the client's movement bindings: each action's first two keys."""
    text = ""
    for action in ACTIONS:
        bound = [*keys.get(action, []), "", ""]
        text += f"{action}={bound[0]},{bound[1]};"
    return sum(ord(char) * index for index, char in enumerate(text, 1)) % 65536


def action_bindings(state: Mapping) -> dict[str, list[str]]:
    """Each action's keys in the running client. Every source is checked against the hash of the client's live
    bindings that the motion row carries, so a stale one is never pressed: the session's cached answer, !!DevSmoke's
    record (on disk only at a reload), the client's defaults changed by bindings-cache.wtf, and last the client itself
    through an eval of GetBindingKey (two reloads). When none matches, the action is refused.
    """
    live = read_motion(state)["bindings"]
    cache = STATE_DIR / BINDINGS_CACHE
    session = str(state.get("pid") or state.get("display") or "")
    try:
        cached = json.loads(cache.read_text())
    except (OSError, ValueError):
        cached = {}
    candidates = []
    if cached.get("session") == session and isinstance(cached.get("keys"), dict):
        candidates.append(cached["keys"])
    recorded = recorded_bindings()
    if recorded is not None:
        candidates.append(recorded[0])
    try:
        candidates.append(file_bindings())
    except ClientError:
        pass
    for keys in candidates:
        if bindings_hash(keys) == live:
            atomic_write(cache, json.dumps({"session": session, "keys": keys}))
            return keys
    keys = asked_bindings(state)
    live = read_motion(state)["bindings"]
    if bindings_hash(keys) != live:
        raise ClientError("the client's key bindings changed while they were read: run the action again")
    atomic_write(cache, json.dumps({"session": session, "keys": keys}))
    return keys


def action_keys(state: Mapping, actions: Sequence[str]) -> list[list[str]]:
    """The keysyms to press for each action: its first binding xdotool can press, modifiers first."""
    refused = [action for action in actions if action not in ACTIONS]
    if refused:
        raise ClientError(f"--action takes {', '.join(ACTIONS)}; refused {', '.join(refused)}")
    bindings = action_bindings(state)
    pressed = []
    for action in actions:
        bound = bindings.get(action) or []
        keysyms = next((found for found in map(game_keysyms, bound) if found), None)
        if keysyms is None:
            shown = ", ".join(bound) or "no key"
            raise ClientError(f"{action} is bound to {shown} in this client, which no key press reaches")
        pressed.append(keysyms)
    return pressed


def moving_action(action: str) -> bool:
    """Whether pressing a game action moves the character, which marks the job as having moved it."""
    return action.startswith(("MOVE", "TURN", "STRAFE", "JUMP"))


def press_actions(state: Mapping, actions: Sequence[str], hold_for: float | None = None) -> None:
    """Press game actions by the keys the running client binds to them: tapped, or with `hold_for` held together."""
    combos = action_keys(state, actions)
    if any(map(moving_action, actions)):
        mark_moved()
    if hold_for is None:
        for combo in combos:
            send(state, "key", "+".join(combo))
        return
    press(state, [keysym for combo in combos for keysym in combo], hold_for)


# The motion row the headless addon draws under the safety strip (forever-core#820): an 8-cell header, five flags, ten
# 16-bit fields and an 8-bit checksum, one 4-pixel cell per bit on pixel row 4 to 7.
MOTION_HEADER = [True, False, False, True, True, False, True, True]
MOTION_FIELDS = ("map", "x", "y", "facing", "width", "height", "plate_x", "bindings", "corpse_x", "corpse_y")
MOTION_FLAGS = ("known", "indoors", "plate", "near", "corpse")
MOTION_ROW = 6
STRIP_ROWS = 8  # both strips sit in the frame's top 8 pixel rows
# Closed-loop movement. Each step reads the motion row again; these bound one step, not the result.
FACE_TOLERANCE = math.radians(4)  # close enough to walk straight at a point
PLATE_TOLERANCE = 0.03  # a target's nameplate this near the screen's middle is in front
TURN_RATE = math.pi  # radians a second while a turn key is held, the client's own rate; each step re-measures it
TURN_STEP_MIN, TURN_STEP_MAX = 0.04, 0.8
TURN_TRIES = 16
CAMERA_FOV = 1.5  # radians across the screen, for the first turn toward a nameplate; the loop corrects the rest
RUN_SPEED = 7.0  # yards a second running, for one step's length
WALK_STEP_MAX = 1.5
WALK_TOLERANCE = 1.5  # yards from the point counts as arrived
WALK_STEPS = 120
WALK_BUDGET = 240.0  # seconds a walk may take before it reports where it got to
STUCK_PROGRESS = 0.3  # yards a step must gain, or it counts toward stuck
STUCK_STEPS = 2
# A blocked straight line (a shop counter between the player and the point): follow the obstacle to one side, stepping
# at ESCAPE_ANGLE off the line and probing the line after every step, then to the other side. The client gives no
# collision geometry, so following the obstacle is how a walker without a map gets round it; it is bounded and
# reports what it tried.
ESCAPE_ANGLE = math.radians(80)
ESCAPE_STEP = 1.0
ESCAPE_STEPS = 20  # steps along the obstacle on each side, about 100 yd with the straight probes between
ESCAPE_PROBE = 0.5  # seconds of the straight step after each step aside: short, as a blocked one slides back
ESCAPE_REVISIT = 2.0  # yards: going round again from within this of an earlier start is a loop
MOVED_MARK = "moved"
PARK_FAILED_CODE = 3
PARK_SPOTS = CONFIG.parent / "park.json"


class MotionUnread(ClientError):
    """The motion row is on screen but did not decode: a torn frame or cells that do not line up with the pixels."""


def motion_state(state: Mapping, frame: tuple[int, list[bytes]] | None = None) -> dict | None:
    """Where the player stands, from the motion row: map, x and y (0 to 1), facing (radians), the map's size in yards,
    indoors, the target's nameplate across the screen (0 to 1), whether it is within interact distance and a hash of
    the client's movement key bindings. None when the row is missing or from an older addon; MotionUnread when it is on
    screen but fails its checksum."""
    frame = frame or strip_rows(state)
    if frame is None:
        return None
    channels, rows = frame
    cells = len(MOTION_HEADER) + len(MOTION_FLAGS) + 16 * len(MOTION_FIELDS) + 8
    try:
        bits = [rows[MOTION_ROW][(column * 4 + 2) * channels] >= 128 for column in range(cells)]
    except IndexError:
        return None
    motion = decode_motion(bits)
    if motion is None and bits[: len(MOTION_HEADER)] == MOTION_HEADER:
        raise MotionUnread("the motion row is on screen but fails its checksum")
    return motion


def decode_motion(bits: Sequence[bool]) -> dict | None:
    """The motion row's bits as values, or None when the header or checksum does not match."""
    if list(bits[: len(MOTION_HEADER)]) != MOTION_HEADER:
        return None
    at = len(MOTION_HEADER)
    flags = list(bits[at : at + len(MOTION_FLAGS)])
    at += len(MOTION_FLAGS)
    fields = []
    for _ in MOTION_FIELDS:
        fields.append(int("".join("1" if bit else "0" for bit in bits[at : at + 16]), 2))
        at += 16
    checksum = int("".join("1" if bit else "0" for bit in bits[at : at + 8]), 2)
    if checksum != (sum(index for index, flag in enumerate(flags, 1) if flag) + sum(fields)) % 256:
        return None
    values = dict(zip(MOTION_FLAGS, flags, strict=True)) | dict(zip(MOTION_FIELDS, fields, strict=True))
    for name in ("x", "y", "plate_x", "corpse_x", "corpse_y"):
        values[name] /= 65535
    values["facing"] = values["facing"] / 65535 * 2 * math.pi
    return values


def read_motion(state: Mapping) -> dict:
    """The motion state from one fresh frame, which must be safe and known: a dead or fighting character, a missing row
    or an unknown position stops movement. A frame caught mid-paint fails its checksum, so a failed read is taken again,
    up to three times."""
    for attempt in range(3):
        frame = strip_rows(state)
        ui = client_ui(state, frame) if frame else {"safety": False}
        if ui.get("safety") and ui["combat"]:
            raise SafetyRefusal("player is in combat")
        if ui.get("safety") and ui["dead"] and not dead_ok:
            raise SafetyRefusal("player is dead or a ghost")
        try:
            motion = motion_state(state, frame)
            break
        except MotionUnread:
            if attempt == 2:
                raise
    if motion is None:
        raise ClientError("no motion row on screen: the session's headless addon predates `face` and `walkto`")
    if not motion["known"]:
        raise ClientError("the client gives no position here (an instance or a loading screen)")
    return motion


def map_size(motion: Mapping) -> tuple[int, int]:
    """The map's size in yards, which yard distances need: a map the client gives no size for refuses them."""
    if not motion["width"] or not motion["height"]:
        raise ClientError(f"the client gives no size in yards for map {motion['map']}, so distances there are unknown")
    return motion["width"], motion["height"]


def angle_between(heading: float, facing: float) -> float:
    """The turn from facing to heading, in (-pi, pi]; positive turns left (the client's facing grows to the left)."""
    turn = (heading - facing) % (2 * math.pi)
    return turn - 2 * math.pi if turn > math.pi else turn


def heading_to(motion: Mapping, x: float, y: float) -> tuple[float, float]:
    """The facing that points from the player at map point (x, y), both 0 to 1, and the distance in yards.

    Facing 0 is north and grows to the left (west); map x grows east and map y south.
    """
    width, height = map_size(motion)
    east = (x - motion["x"]) * width
    south = (y - motion["y"]) * height
    return math.atan2(-east, -south) % (2 * math.pi), math.hypot(east, south)


def mark_moved() -> None:
    (STATE_DIR / MOVED_MARK).touch()


def hold_action(state: Mapping, actions: Sequence[str], seconds: float) -> None:
    mark_moved()
    press_actions(state, actions, seconds)


def progress(message: str) -> None:
    """One line per movement step, so a caller sees a long walk advance rather than silence."""
    print(f"forever_client: {message}", file=sys.stderr, flush=True)


def face(state: Mapping, heading: float, motion: dict | None = None) -> dict:
    """Turn until the measured facing is within FACE_TOLERANCE of `heading`; the motion state when it is."""
    rate = TURN_RATE
    motion = motion or read_motion(state)
    moved = False
    for _ in range(TURN_TRIES):
        turn = angle_between(heading, motion["facing"])
        if abs(turn) <= FACE_TOLERANCE:
            return motion
        seconds = min(max(abs(turn) / rate, TURN_STEP_MIN), TURN_STEP_MAX)
        hold_action(state, ["TURNLEFT" if turn > 0 else "TURNRIGHT"], seconds)
        after = read_motion(state)
        turned = abs(angle_between(after["facing"], motion["facing"]))
        if turned > 0.01:
            rate, moved = turned / seconds, True
        motion = after
    if abs(angle_between(heading, motion["facing"])) <= FACE_TOLERANCE:
        return motion
    facing, goal = math.degrees(motion["facing"]), math.degrees(heading)
    if moved:
        raise ClientError(
            f"facing ended at {facing:.0f} deg after {TURN_TRIES} turns toward {goal:.0f} deg: the character turns "
            f"but never settled within {math.degrees(FACE_TOLERANCE):.0f} deg"
        )
    raise ClientError(
        f"facing stayed {facing:.0f} deg after {TURN_TRIES} turns toward {goal:.0f} deg: "
        f"TURNLEFT and TURNRIGHT do not turn this character"
    )


def face_target(state: Mapping) -> dict:
    """Turn until the target's nameplate is in the middle of the screen; a target off screen is searched for in
    quarter turns."""
    rate = TURN_RATE
    motion = read_motion(state)
    searched = 0
    for _ in range(TURN_TRIES):
        if not motion["plate"]:
            if searched >= 4:
                raise ClientError("no nameplate for the target after a full turn: target it and show nameplates")
            hold_action(state, ["TURNLEFT"], min(math.pi / 2 / rate, TURN_STEP_MAX * 2))
            searched += 1
            motion = read_motion(state)
            continue
        off = motion["plate_x"] - 0.5
        if abs(off) <= PLATE_TOLERANCE:
            return motion
        seconds = min(max(abs(off) * CAMERA_FOV / rate, TURN_STEP_MIN), TURN_STEP_MAX)
        hold_action(state, ["TURNRIGHT" if off > 0 else "TURNLEFT"], seconds)
        motion = read_motion(state)
    raise ClientError("the target's nameplate never came to the middle of the screen")


def walk_step(state: Mapping, seconds: float, *, jump: bool = False) -> dict:
    hold_action(state, ["MOVEFORWARD", "JUMP"] if jump else ["MOVEFORWARD"], seconds)
    return read_motion(state)


def yards_between(a: Mapping, b: Mapping) -> float:
    width, height = map_size(a)
    return math.hypot((a["x"] - b["x"]) * width, (a["y"] - b["y"]) * height)


class Walk:
    """One walk to map point (x, y), 0 to 1, on one map: every read is checked against that map and the time budget,
    and every step is reported."""

    def __init__(self, state: Mapping, x: float, y: float, map_id: int | None, budget: float):
        self.state, self.x, self.y = state, x, y
        self.deadline = time.monotonic() + budget
        self.blocked: list[int] = []
        self.steps = 0
        self.side = 1  # the side of the line go_round tries first: the one that last got round
        self.rounds: list[tuple[Mapping, float]] = []  # where each go_round began, and the nearest the walk had been
        self.motion = read_motion(state)
        self.nearest = self.distance()
        self.map = self.motion["map"] if map_id is None else map_id
        self.check(self.motion)

    def check(self, motion: Mapping) -> None:
        if motion["map"] != self.map:
            raise ClientError(f"the player is on map {motion['map']}, not {self.map}: walkto stays on one map")
        if time.monotonic() > self.deadline:
            raise ClientError(self.stuck("ran out of time"))

    def distance(self, motion: Mapping | None = None) -> float:
        return heading_to(motion or self.motion, self.x, self.y)[1]

    def read(self, motion: dict) -> dict:
        self.check(motion)
        self.motion = motion
        self.nearest = min(self.nearest, self.distance())
        return motion

    def step(self, seconds: float | None = None, *, jump: bool = False, heading: float | None = None) -> float:
        """Face the point (or `heading`), walk one step, and return the yards it gained toward the point."""
        before = self.distance()
        aim = heading if heading is not None else heading_to(self.motion, self.x, self.y)[0]
        self.read(face(self.state, aim, self.motion))
        length = seconds if seconds is not None else min(self.distance() / RUN_SPEED, WALK_STEP_MAX)
        self.read(walk_step(self.state, max(length, 0.1), jump=jump))
        self.steps += 1
        progress(
            f"step {self.steps}: {self.motion['x'] * 100:.2f}, {self.motion['y'] * 100:.2f}, "
            f"{self.distance():.1f} yd to go"
        )
        return before - self.distance()

    def stuck(self, why: str) -> str:
        heading, distance = heading_to(self.motion, self.x, self.y)
        seen = list(dict.fromkeys(self.blocked))
        return (
            f"stuck ({why}) at {self.motion['x'] * 100:.2f}, {self.motion['y'] * 100:.2f} on map {self.motion['map']}, "
            f"{distance:.1f} yd from {self.x * 100:.2f}, {self.y * 100:.2f} (heading {math.degrees(heading):.0f} deg); "
            f"blocked toward {', '.join(f'{angle} deg' for angle in seen) or 'nothing measured'} (0 north, 90 west)"
        )

    def go_round(self, best: float) -> bool:
        """Follow the obstacle on one side, then the other, until the walk beats `best` (its nearest since the last
        detour) or a straight step toward the point runs free past the line where the obstacle stopped the walk (a free
        step that starts from a step away from the obstacle has not got round it). It keeps to the side that last got
        round: starting each time from the same side swings the walker back and forth across a corner between two spots
        (#923). Starting again where an earlier detour began, with no nearer point reached since, is a loop."""
        here = self.motion
        if any(yards_between(here, spot) < ESCAPE_REVISIT and self.nearest >= nearest for spot, nearest in self.rounds):
            return False
        self.rounds.append((here, self.nearest))
        line = heading_to(here, self.x, self.y)[0]
        budget = ESCAPE_STEPS
        for side in (self.side, -self.side):
            taken = 0
            while taken < budget and self.step_aside(side):
                taken += 1
                start = self.motion
                heading = heading_to(start, self.x, self.y)[0]
                # Never past the point: a probe that overshoots it can end outside the arrival tolerance.
                probe = min(ESCAPE_PROBE, self.distance() / RUN_SPEED)
                self.step(probe, heading=heading)
                past = self.forward(here, line) >= STUCK_PROGRESS
                if self.distance() <= best - STUCK_PROGRESS or (
                    past and self.forward(start, heading) >= 0.8 * RUN_SPEED * probe
                ):
                    self.side = side
                    return True
                self.blocked.append(round(math.degrees(heading)) % 360)
            budget = ESCAPE_STEPS + taken  # the other side first walks back over the steps this one took
        return False

    def forward(self, start: Mapping, heading: float) -> float:
        """Yards the player now stands from `start` along `heading`."""
        moved, yards = heading_to(start, self.motion["x"], self.motion["y"])
        return yards * math.cos(moved - heading)

    def step_aside(self, side: int) -> bool:
        """One step off the line on `side`; False when it does not move."""
        start = self.motion
        aside = (heading_to(start, self.x, self.y)[0] + side * ESCAPE_ANGLE) % (2 * math.pi)
        self.step(ESCAPE_STEP, heading=aside)
        if yards_between(self.motion, start) >= STUCK_PROGRESS:
            return True
        self.blocked.append(round(math.degrees(aside)) % 360)
        return False


def walkto(
    state: Mapping,
    x: float,
    y: float,
    map_id: int | None = None,
    tolerance: float = WALK_TOLERANCE,
    budget: float = WALK_BUDGET,
) -> dict:
    """Walk to map point (x, y), 0 to 1, re-reading the position after every step and facing the point again.

    Progress is the best distance so far: STUCK_STEPS steps that do not beat it by STUCK_PROGRESS yards (straight into
    a wall, or sliding along one) count as stuck. Stuck, the walker jumps forward once, then follows the obstacle
    (Walk.go_round). When that gains nothing, or the time budget runs out, it stops and reports where it is and which
    headings were blocked, rather than looping.
    """
    walk = Walk(state, x, y, map_id, budget)
    best, stalled, jumped = walk.distance(), 0, False
    for _ in range(WALK_STEPS):
        if walk.distance() <= tolerance:
            return walk.motion
        heading = heading_to(walk.motion, x, y)[0]
        walk.step()
        if walk.distance() <= best - STUCK_PROGRESS:
            best, stalled = walk.distance(), 0
            continue
        stalled += 1
        if stalled < STUCK_STEPS:
            continue
        stalled = 0
        walk.blocked.append(round(math.degrees(heading)) % 360)
        if not jumped:
            jumped = True
            walk.step(0.8, jump=True)
            best = min(best, walk.distance())
        elif walk.go_round(best):
            best = walk.distance()  # round the obstacle: progress counts from here, even if the way round led away
        else:
            raise ClientError(walk.stuck("no way round"))
    if walk.distance() <= tolerance:
        return walk.motion
    raise ClientError(walk.stuck(f"{WALK_STEPS} steps"))


def walkto_target(state: Mapping, budget: float = WALK_BUDGET) -> dict:
    """Walk to the target until it is within interact distance, facing its nameplate before every step. Stuck, it jumps
    forward once and carries on; stuck again, it reports where it is."""
    deadline = time.monotonic() + budget
    stalled, jumped = 0, False
    for step in range(1, WALK_STEPS + 1):
        if time.monotonic() > deadline:
            raise ClientError("ran out of time walking to the target")
        motion = face_target(state)
        if motion["near"]:
            return motion
        after = walk_step(state, 1.0)
        progress(f"step {step}: {after['x'] * 100:.2f}, {after['y'] * 100:.2f} toward the target")
        stalled = stalled + 1 if yards_between(after, motion) < STUCK_PROGRESS else 0
        if stalled < STUCK_STEPS:
            continue
        stalled = 0
        if jumped:
            raise ClientError(
                f"stuck at {after['x'] * 100:.2f}, {after['y'] * 100:.2f} on map {after['map']} walking to the "
                f"target (heading {math.degrees(after['facing']):.0f} deg, 0 north, 90 west)"
            )
        jumped = True
        walk_step(state, 0.8, jump=True)
    raise ClientError("the target was never within interact distance")


def park_spots() -> list[dict]:
    try:
        spots = json.loads(PARK_SPOTS.read_text())
    except (OSError, ValueError):
        return []
    return [spot for spot in spots if isinstance(spot, dict)] if isinstance(spots, list) else []


def park_add(state: Mapping, label: str) -> dict:
    """Record where the player stands as a park spot: outdoors, with a merchant and creatures in reach."""
    motion = read_motion(state)
    if motion["indoors"]:
        raise ClientError("a park spot is outdoors: the player is indoors here")
    spot = {"label": label, "map": motion["map"], "x": round(motion["x"], 5), "y": round(motion["y"], 5)}
    spots = [old for old in park_spots() if old.get("label") != label] + [spot]
    PARK_SPOTS.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(PARK_SPOTS, json.dumps(spots, indent=1))
    return spot


def park(state: Mapping) -> dict:
    """Walk to the nearest park spot on the player's map and check it is outdoors."""
    motion = read_motion(state)
    spots = [spot for spot in park_spots() if spot.get("map") == motion["map"]]
    if not spots:
        raise ClientError(f"no park spot on map {motion['map']}: stand at one and run `park --add LABEL`")
    spot = min(spots, key=lambda spot: heading_to(motion, spot["x"], spot["y"])[1])
    progress(f"parking at {spot['label']}")
    motion = walkto(state, spot["x"], spot["y"], spot["map"])
    if motion["indoors"]:
        raise ClientError(f"park spot {spot['label']} reads as indoors")
    (STATE_DIR / MOVED_MARK).unlink(missing_ok=True)
    return spot


def park_after_job(state: Mapping) -> bool:
    """At the end of a job that moved the character, walk it back to a park spot. A failure is printed on stdout and
    stderr and keeps the moved mark, so the next job end tries again; True when the character is parked or never
    moved."""
    if not (STATE_DIR / MOVED_MARK).exists():
        return True
    try:
        spot = park(state)
    except (ClientError, SafetyRefusal) as error:
        line = f"forever_client: PARK FAILED, the character is not parked: {error}"
        print(line, flush=True)
        print(line, file=sys.stderr, flush=True)
        return False
    print(f"forever_client: parked at {spot['label']}", file=sys.stderr, flush=True)
    return True


def describe_motion(motion: Mapping) -> str:
    return (
        f"map {motion['map']} at {motion['x'] * 100:.2f}, {motion['y'] * 100:.2f} facing "
        f"{math.degrees(motion['facing']):.0f} deg (0 north, 90 west){', indoors' if motion['indoors'] else ''}"
        f"{', target within interact distance' if motion['near'] else ''}"
        + (f", corpse at {motion['corpse_x'] * 100:.2f}, {motion['corpse_y'] * 100:.2f}" if motion["corpse"] else "")
    )


def map_point(value: float) -> float:
    """A map coordinate as the game's map shows it, 0 to 100, as the 0 to 1 the client's API uses."""
    if not 0 <= value <= 100:
        raise ClientError(f"map coordinates run 0 to 100, as the map shows them: refused {value:g}")
    return value / 100


def drag_points(x1: int, y1: int, x2: int, y2: int, steps: int) -> list[tuple[int, int]]:
    """The points a drag passes through after its start, evenly spaced, ending exactly on the end point."""
    return [
        (round(x1 + (x2 - x1) * step / steps), round(y1 + (y2 - y1) * step / steps)) for step in range(1, steps + 1)
    ]


def drag(
    state: Mapping,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    button: str = "1",
    steps: int = DRAG_STEPS,
    hold: Sequence[str] = (),
) -> None:
    """Press a mouse button at one point, move to another in steps and release it there, as a player drags (#857).

    It is the same screenshot-bound input as `click`. The button is recorded as down for the length of the chain: a
    chain that fails or is interrupted is followed by a release here, and one whose process is killed outright is
    released by the next job's cleanup (`release_session_modifiers`).
    """
    if button not in ("1", "3"):
        raise ClientError("drag takes --button 1 (left) or 3 (right)")
    if not 1 <= steps <= DRAG_STEPS_MAX:
        raise ClientError(f"drag takes --steps from 1 to {DRAG_STEPS_MAX}, not {steps}")
    keys = modifier_keys(hold)
    if mark("last-shot") <= mark("last-input"):
        raise ClientError("take a `shot` and read it first: a drag must aim at addon UI in the current frame")
    for px, py in ((x1, y1), (x2, y2)):
        if not (0 <= px < WIDTH and 0 <= py < HEIGHT):
            raise ClientError(f"({px}, {py}) is outside the {WIDTH}x{HEIGHT} frame")
    if state.get("ready"):
        close_game_menu(state)
    chain = ["mousemove", str(x1), str(y1), "mousedown", button]
    for px, py in drag_points(x1, y1, x2, y2, steps):
        chain += ["sleep", DRAG_STEP_DELAY, "mousemove", str(px), str(py)]
    chain += ["sleep", DRAG_STEP_DELAY, "mouseup", button]
    (STATE_DIR / HELD_BUTTON).write_text(button)
    try:
        send(state, *chain, hold=keys)
    except BaseException:
        release_button(state["display"])
        raise
    (STATE_DIR / HELD_BUTTON).unlink(missing_ok=True)


def press(state: Mapping, keys: Sequence[str], hold_for: float | None = None) -> None:
    """Tap each key in turn, or with `hold_for`, hold them all down together for that many seconds.

    A tap is a press and release with no time between, which the game reads as a key event but not as movement: a
    held key is how the character walks (w), turns (a, d) or strafes, for as long as it is held (#820).
    """
    keys = [KEY_ALIASES.get(key, key) for key in keys]
    if hold_for is None:
        for k in keys:
            send(state, "key", k)
        return
    if not 0 < hold_for <= HOLD_MAX:
        raise ClientError(f"--for takes more than 0 and at most {HOLD_MAX:g} seconds; walk further with `walkto`")
    wait = INPUT_GAP - (time.time() - mark("last-input"))
    if wait > 0:
        time.sleep(wait)
    if any(key in MOVEMENT_KEYSYMS for key in keys):
        mark_moved()
    with held(state, list(dict.fromkeys(keys)), watchdog=hold_for + HOLD_GRACE):
        # The character can be pulled into a fight or die mid-hold: check between slices and let go at once.
        end = time.monotonic() + hold_for
        while (left := end - time.monotonic()) > 0:
            time.sleep(min(HOLD_SLICE, left))
            if time.monotonic() < end:
                require_safe(state)
    (STATE_DIR / "last-input").touch()


def one_line_slash(command: str) -> None:
    """A slash command is one chat line starting with `/`: a newline would send a second line, plain text a chat."""
    if not command.isprintable():
        raise ClientError("slash sends one line: a newline would send a second chat line")
    if not command.strip().startswith("/"):
        raise ClientError(f"slash sends a slash command, not chat text: refused {command.strip() or 'an empty line'!r}")


def strip_rows(state: Mapping) -> tuple[int, list[bytes]] | None:
    """The top rows of one fresh frame, where both pixel strips sit, and the bytes a pixel takes; None when no frame."""
    # Every gameplay verb reads the strip, so its full-frame capture is removed once decoded rather than left behind.
    path = STATE_DIR / f"client-state-{os.getpid()}.png"
    try:
        image = shot(state, path, mark_read=False)
        _width, _height, channels, rows = png_pixels(image, max_rows=STRIP_ROWS)
        return channels, rows
    except (subprocess.CalledProcessError, ClientError, OSError):
        return None
    finally:
        path.unlink(missing_ok=True)


def client_ui(state: Mapping, frame: tuple[int, list[bytes]] | None = None) -> dict[str, bool]:
    """Decode live safety, identifying older strips for guarded session replacement."""
    unknown = {"world": False, "menu": False, "chat": False, "safety": False, "dead": True, "combat": True}
    try:
        frame = frame or strip_rows(state)
        if frame is None:
            return unknown
        channels, rows = frame
        bits = []
        for column in range(8):
            offset = (column * 4 + 2) * channels
            bits.append(rows[2][offset] >= 128)
        if bits == [True, False, True, True, False, False, True, False]:
            return unknown | {"outdated": True}
        if bits != [False, True, True, True, False, False, True, False]:
            return unknown
        for column in range(8, 13):
            offset = (column * 4 + 2) * channels
            bits.append(rows[2][offset] >= 128)
        return dict(zip(("world", "menu", "chat", "dead", "combat"), bits[8:], strict=True)) | {"safety": True}
    except IndexError:
        return unknown


# Verbs a dead character out of combat still takes, so the test character can be revived: Release Spirit and the
# resurrect popups are clicks, the corpse run is `walkto corpse`, and the spirit healer is INTERACTTARGET in reach.
# Slash, eval and proofs still refuse a ghost (forever-core#1009).
DEAD_OK_VERBS = frozenset({"click", "hover", "key", "face", "walkto", "where"})
dead_ok = False  # True only while input_verb runs a DEAD_OK_VERBS command; read by require_safe and read_motion


def require_safe(state: Mapping, *, waiting: bool = False) -> None:
    ui = client_ui(state)
    if not ui.get("safety"):
        if waiting:
            return  # Loading screens have no strip. Keep waiting for the world.
        raise SafetyRefusal("live safety protocol unavailable or outdated: version 2 headless addon required")
    if ui["dead"] and not (dead_ok and not ui["combat"]):
        raise SafetyRefusal("player is dead or a ghost")
    if ui["combat"]:
        raise SafetyRefusal("player is in combat")


def client_ui_after_load(state: Mapping) -> dict[str, bool]:
    """The strip once any loading screen is over: a /reload hides it while the client still runs (#815).

    Only a strip that decodes, an outdated one, a client that is gone or RELOAD_WAIT without a strip ends the wait,
    so a verb sent during a reload waits for the world instead of reading the loading screen as the world being left.
    """
    deadline = time.monotonic() + RELOAD_WAIT
    ui = client_ui(state)
    while not ui.get("safety") and not ui.get("outdated") and time.monotonic() < deadline and client_alive(state):
        time.sleep(WAIT_POLL)
        ui = client_ui(state)
    return ui


def client_alive(state: Mapping) -> bool:
    """Whether the session and its gamescope still run; a Hyprland job session records no gamescope."""
    gamescope = state.get("gamescope")
    return session_alive(state) and (gamescope is None or gamescope_running(gamescope, state))


def resident_world_check(state: Mapping, last_check: float) -> tuple[float, str | None]:
    """Probe only between jobs; readiness can change only after the caller takes the job lock."""
    now = time.monotonic()
    if now - last_check < WORLD_CHECK or job_holder() is not None:
        return last_check, None
    return now, None if client_ui(state)["world"] else "the client left the world"


def close_game_menu(state: Mapping) -> None:
    """Close a Game Menu an earlier job left open, so this job starts in the world it expects (#727).

    The menu is the client's own pause screen and Escape closes it without changing anything a job set up. Only the
    menu is closed: outside the world nothing is sent.
    """
    for _ in range(MENU_CLOSE_TRIES):
        ui = client_ui(state)
        if not (ui["world"] and ui["menu"]):
            return
        send(state, "key", "Escape")
        time.sleep(0.1)


def focus_chat(state: Mapping) -> None:
    """Type only after the client reports that a chat edit box has keyboard focus.

    Outside the world there is no chat box, and the Return that would open one presses Enter World or Login instead,
    so nothing is sent there: `log_out` relies on this to never type into a login screen.
    """
    close_game_menu(state)
    for key in (None, "Return", "Escape", "Return"):
        if key:
            send(state, "key", key)
        # A loaded machine can take well over 0.1 s to draw the frame whose strip shows the focus a Return gave, so a
        # Return is followed by polls of the strip rather than one early read that types nothing.
        for poll in range(CHAT_FOCUS_POLLS if key == "Return" else 1):
            if key or poll:
                time.sleep(0.1)
            ui = client_ui(state)
            if not ui["world"]:
                raise ClientError("slash needs the world: there is no chat box at the login or character screen")
            if ui["chat"]:
                return
    raise ClientError("slash refused: the chat edit box did not acquire focus")


def slash(state: Mapping, command: str) -> None:
    one_line_slash(command)
    focus_chat(state)
    send(state, "type", "--delay", TYPE_DELAY_MS, command)
    send(state, "key", "Return")


# --- the launcher's Play button ----------------------------------------------------------------------------------

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_CHANNELS = {2: 3, 6: 4}  # truecolour, and truecolour with alpha
# !!ForeverHeadless takes its marker screenshot 2 s after the world loads; a world without one for this long refused.
HANDSHAKE_WAIT = 30
HEADLESS_MARKER = (
    "10011001",
    "01100110",
    "11001001",
    "00110110",
    "10101100",
    "01010011",
    "11100010",
    "00011101",
)
# The addon emits this as a 32x32 black/white grid. JPEG is the client's native
# screenshot format, so each 4x4 cell is decoded by its average luminance and
# the protocol's binary midpoint (128), rather than by a fitted colour ratio.
MARKER_CELL = 4
# The flat fill the launcher draws its primary Play button in on the game page. The word sits inside it as white
# text, and a whole-page tesseract pass skips the filled button along with its label, so the drawn fill is what
# locates the control: no fixed point and no page layout (#547). A launcher build that draws another fill is a change
# here, and the saved frame beside the spec is what shows the difference.
PLAY_FILL = bytes((0, 116, 224))
PLAY_LABEL = "play"


def png_pixels(path: Path, max_rows: int | None = None) -> tuple[int, int, int, list[bytes]]:
    """The screenshot's width, height, channels and rows, decoded without an image library. With `max_rows`, only
    that many rows from the top: the pixel strips sit there, and a full 1920-wide frame takes over a second to unfilter.

    gamescope writes an 8-bit, non-interlaced RGB or RGBA PNG. Anything else is a ClientError naming the file: a frame
    this tool cannot read must never be reported as a launcher without Play.
    """
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ClientError(f"cannot read the launcher screenshot {path}: {error}") from None
    if data[:8] != PNG_SIGNATURE:
        raise ClientError(f"{path} is not a PNG screenshot")
    at = 8
    compressed = []
    width = height = channels = None
    while at < len(data):
        try:
            length, kind = struct.unpack(">I4s", data[at : at + 8])
        except struct.error:
            raise ClientError(f"{path} is a truncated PNG") from None
        body = data[at + 8 : at + 8 + length]
        at += length + 12
        if kind == b"IHDR":
            try:
                width, height, depth, colour, _compression, _filter, interlace = struct.unpack(">IIBBBBB", body)
            except struct.error:
                raise ClientError(f"{path} has a truncated PNG header") from None
            channels = PNG_CHANNELS.get(colour)
            if depth != 8 or channels is None or interlace != 0:
                raise ClientError(
                    f"{path} is not the 8-bit RGB or RGBA, non-interlaced PNG gamescope writes "
                    f"(bit depth {depth}, colour type {colour}, interlace {interlace})"
                )
        elif kind == b"IDAT":
            compressed.append(body)
        elif kind == b"IEND":
            break
    if not width or not height or channels is None:
        raise ClientError(f"{path} has no PNG header")
    stride = width * channels
    wanted = height if max_rows is None else min(height, max_rows)
    try:
        if max_rows is None:
            raw = zlib.decompress(b"".join(compressed))
        else:
            raw = zlib.decompressobj().decompress(b"".join(compressed), (stride + 1) * wanted)
    except zlib.error as error:
        raise ClientError(f"{path} is not a readable PNG: {error}") from None
    rows: list[bytes] = []
    previous = bytes(stride)
    at = 0
    try:
        for _row in range(wanted):
            kind = raw[at]
            at += 1
            line = bytearray(raw[at : at + stride])
            at += stride
            png_unfilter(line, previous, channels, kind)
            rows.append(bytes(line))
            previous = rows[-1]
    except (IndexError, ValueError) as error:
        raise ClientError(f"{path} is a truncated PNG: {error}") from None
    return width, height, channels, rows


def has_headless_marker(path: Path) -> bool:
    """Identify the readiness screenshot by the marker drawn at screen center.

    ``Screenshot()`` writes JPEGs on the game client, while gamescope writes PNGs
    for host captures. Decode both formats here so the handshake follows the
    native client transport instead of assuming the host capture format.
    """
    try:
        if path.read_bytes()[:8] == PNG_SIGNATURE and not _complete_png(path):
            raise ClientError(f"{path} is not a complete screenshot")
        with Image.open(path) as image:
            image.load()
            rgb = image.convert("RGB")
            width, height = rgb.size
    except ClientError:
        raise
    except (OSError, ValueError) as error:
        raise ClientError(f"{path} is not a complete screenshot: {error}") from None
    marker_size = len(HEADLESS_MARKER) * MARKER_CELL
    if width < marker_size or height < marker_size:
        return False
    left, top = width // 2 - marker_size // 2, height // 2 - marker_size // 2
    for row, bits in enumerate(HEADLESS_MARKER):
        for column, bit in enumerate(bits):
            cell = rgb.crop(
                (
                    left + column * MARKER_CELL,
                    top + row * MARKER_CELL,
                    left + (column + 1) * MARKER_CELL,
                    top + (row + 1) * MARKER_CELL,
                )
            )
            luminance = sum((299 * r + 587 * g + 114 * b) // 1000 for r, g, b in cell.getdata()) / (MARKER_CELL**2)
            if (luminance >= 128) != (bit == "1"):
                return False
    return True


def png_unfilter(line: bytearray, previous: bytes, channels: int, kind: int) -> None:
    """Undo one row's PNG filter in place, on the row before it."""
    stride = len(line)
    if kind == 0:
        return
    if kind == 1:  # Sub
        for index in range(channels, stride):
            line[index] = (line[index] + line[index - channels]) & 0xFF
        return
    if kind == 2:  # Up
        for index in range(stride):
            line[index] = (line[index] + previous[index]) & 0xFF
        return
    if kind == 3:  # Average
        for index in range(stride):
            left = line[index - channels] if index >= channels else 0
            line[index] = (line[index] + ((left + previous[index]) >> 1)) & 0xFF
        return
    if kind == 4:  # Paeth
        for index in range(stride):
            left = line[index - channels] if index >= channels else 0
            up = previous[index]
            up_left = previous[index - channels] if index >= channels else 0
            guess = left + up - up_left
            distances = (abs(guess - left), abs(guess - up), abs(guess - up_left))
            line[index] = (line[index] + (left, up, up_left)[distances.index(min(distances))]) & 0xFF
        return
    raise ValueError(f"PNG filter {kind}")


def fill_regions(
    width: int, height: int, channels: int, rows: Sequence[bytes], fill: bytes = PLAY_FILL
) -> list[tuple[int, int, int, int, int]]:
    """Every connected region drawn in `fill`, as its area and box, the largest first.

    The fill is matched in the row's own bytes, so an RGB frame and an RGBA one are read the same way.
    """
    mask = bytearray(width * height)
    for y, row in enumerate(rows):
        at = row.find(fill)
        while at != -1:
            if at % channels == 0:
                mask[y * width + at // channels] = 1
            at = row.find(fill, at + 1)
    regions = []
    for start in range(width * height):
        if not mask[start]:
            continue
        stack = [start]
        mask[start] = 0
        area = 0
        left = right = start % width
        top = bottom = start // width
        while stack:
            index = stack.pop()
            area += 1
            x, y = index % width, index // width
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            for neighbour, inside in (
                (index - 1, x > 0),
                (index + 1, x + 1 < width),
                (index - width, y > 0),
                (index + width, y + 1 < height),
            ):
                if inside and mask[neighbour]:
                    mask[neighbour] = 0
                    stack.append(neighbour)
        regions.append((area, left, top, right - left + 1, bottom - top + 1))
    regions.sort(reverse=True)
    return regions


def write_ppm(path: Path, rows: Sequence[bytes], channels: int, box: tuple[int, int, int, int]) -> None:
    """One cropped region as a PPM, which tesseract reads and which needs no image encoder."""
    left, top, width, height = box
    data = bytearray(f"P6\n{width} {height}\n255\n".encode())
    for y in range(top, top + height):
        row = rows[y]
        for x in range(left, left + width):
            at = x * channels
            data += row[at : at + 3]
    path.write_bytes(data)


def write_pgm_channel(
    path: Path, width: int, height: int, channels: int, rows: Sequence[bytes], channel: int, scale: int = 1
) -> None:
    """Write one PNG channel as grayscale for OCR of colored game labels, each pixel repeated `scale` times a side.

    The client's small list text reads unreliably at its drawn size (a highlighted row is missed, `Hel` reads as
    `VHeI`), and tesseract reads it at twice the size; a caller divides the boxes it gets back by the same scale.
    """
    data = bytearray(f"P5\n{width * scale} {height * scale}\n255\n".encode())
    for row in rows:
        line = bytes(255 - value for value in row[channel::channels] for _ in range(scale))
        data.extend(line * scale)
    path.write_bytes(data)


def ocr_words(image: Path, psm: int = 11) -> list[tuple[str, float, int, int, int, int]]:
    """The words tesseract reads in one image: text, confidence, and the word's box in that image."""
    ocr = subprocess.run(
        ["tesseract", str(image), "stdout", "--psm", str(psm), "tsv"],
        capture_output=True,
        text=True,
        check=False,
    )
    if ocr.returncode != 0:
        raise ClientError(f"could not read {image} with tesseract: {ocr.stderr.strip()}")
    words = []
    for line in ocr.stdout.splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) != 12:
            continue
        try:
            left, top, width, height = (int(fields[index]) for index in (6, 7, 8, 9))
            confidence = float(fields[10])
        except (TypeError, ValueError):
            continue
        words.append((fields[11].strip(), confidence, left, top, width, height))
    return words


def ocr_words_with_lines(image: Path, psm: int) -> list[tuple[str, float, int, int, int, int, tuple[int, int, int]]]:
    """Read OCR words with their TSV line number for exact multi-word labels."""
    ocr = subprocess.run(
        ["tesseract", str(image), "stdout", "--psm", str(psm), "tsv"],
        capture_output=True,
        text=True,
        check=False,
    )
    if ocr.returncode != 0:
        raise ClientError(f"could not read {image} with tesseract: {ocr.stderr.strip()}")
    words = []
    for line in ocr.stdout.splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) != 12:
            continue
        try:
            block, paragraph, line_number = (int(fields[index]) for index in (2, 3, 4))
            left, top, width, height = (int(fields[index]) for index in (6, 7, 8, 9))
            confidence = float(fields[10])
        except (TypeError, ValueError):
            continue
        words.append((fields[11].strip(), confidence, left, top, width, height, (block, paragraph, line_number)))
    return words


def play_targets(image: Path) -> list[tuple[int, int, int, int, float]]:
    """Every visible Play label the launcher draws, as its box in the whole screenshot.

    The label is found inside the button the launcher draws, not by the page layout tesseract guesses for the whole
    frame: a whole-page pass skips the filled button and its word even when the word is plainly drawn (#547).
    The entire region must read as one Play word, so a promo button like Play Now is never a target (#681).
    """
    width, height, channels, rows = png_pixels(image)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    crop = STATE_DIR / "play-label.ppm"
    targets = []
    for _area, left, top, box_width, box_height in fill_regions(width, height, channels, rows):
        write_ppm(crop, rows, channels, (left, top, box_width, box_height))
        words = [word for word in ocr_words(crop) if word[0]]
        if len(words) != 1:
            continue
        text, confidence, x, y, word_width, word_height = words[0]
        if text.casefold() == PLAY_LABEL and confidence >= 0 and word_width > 0 and word_height > 0:
            targets.append((left + x, top + y, word_width, word_height, confidence))
    return targets


def press_play(state: dict) -> None:
    """Find and click the visible Play label in the launcher's current screenshot.

    Battle.net changes its page layout with the gamescope size and can show a login dialog before the game page. A
    fixed point therefore either misses Play or clicks another control. The button is located from the fill the
    launcher draws it in, and the label is read inside that region, so the click is screenshot-bound like the public
    ``click`` verb and does not depend on the page layout an OCR pass guesses for the whole frame.
    """
    found = subprocess.run(
        ["xdotool", "search", "--name", "^Battle.net$"],
        env={**os.environ, "DISPLAY": state["display"]},
        capture_output=True,
        text=True,
        check=False,
    )
    if not found.stdout.split():
        # Battle.net can swap its login window for the main one; the startup loop retries until its deadline.
        return
    if shutil.which("tesseract") is None:
        raise ClientError("tesseract is required for OCR; use up --manual-launcher for screenshot-guided clicks")
    if client_pid():
        return
    image = shot(state, STATE_DIR / "launcher.png")
    words = [word[0].casefold() for word in ocr_words(image) if word[0]]
    if any(
        words[index : index + len(phrase)] == list(phrase)
        for phrase in LAUNCHER_SIGN_IN_LABELS
        for index in range(len(words))
    ):
        atomic_write(STATE_DIR / SIGN_IN_BLOCK, SIGN_IN_MESSAGE)
        raise SignInRequired(SIGN_IN_MESSAGE)
    # These exact Battle.net UI labels name the blocked launch state; unrelated prose is not an update signal.
    if any(
        words[index : index + len(phrase)] == list(phrase)
        for phrase in LAUNCHER_UPDATE_LABELS
        for index in range(len(words))
    ):
        raise ClientError(
            f"the game needs an update in Battle.net before the headless client can start; inspect {image}"
        )
    clicks = state.get("play_clicks", 0)
    if clicks and time.monotonic() - state["last_play_click"] < PLAY_RETRY_WAIT:
        return
    if clicks >= MAX_PLAY_CLICKS:
        raise ClientError(
            f"no game process appeared after {MAX_PLAY_CLICKS} Play clicks in Battle.net; inspect {image}"
        )
    targets = play_targets(image)
    if not targets:
        # No input while Play is not drawn: the launcher shows its own splash and pop-ups first, and Blizzard's
        # token-security-checkpoint pop-up passes by itself within a second. A key sent to it cancels that check, and
        # Battle.net then deletes the saved login token, logging the player out.
        if not state.get("play_target_missing_reported"):
            # Every retry overwrites launcher.png, so by the time anyone reads this line the file shows a later
            # frame (often one with Play drawn). Keep the frame this report is about under its own name.
            missed = image.with_name(f"{image.stem}-no-play{image.suffix}")
            shutil.copyfile(image, missed)
            print(
                f"no visible Play label recognized; inspect {missed}. Retrying until the startup deadline. "
                "For screenshot-guided launcher clicks, restart with up --manual-launcher, then use shot and click.",
                file=sys.stderr,
                flush=True,
            )
            state["play_target_missing_reported"] = True
        return
    if len(targets) != 1:
        raise ClientError(f"expected one visible Play target in the Battle.net screenshot, found {len(targets)}")
    left, top, width, height, _ = targets[0]
    x(state, "mousemove", str(left + width // 2), str(top + height // 2))
    time.sleep(0.5)
    x(state, "click", "1")
    state["play_clicks"] = clicks + 1
    state["last_play_click"] = time.monotonic()
    (STATE_DIR / "last-input").touch()


CHARACTER_SELECT_OCR_SCALE = 2


def unscaled(word: tuple) -> tuple:
    """An OCR word read at CHARACTER_SELECT_OCR_SCALE, its box back in screenshot pixels."""
    text, confidence, left, top, width, height, *rest = word
    scale = CHARACTER_SELECT_OCR_SCALE
    return (text, confidence, left // scale, top // scale, width // scale, height // scale, *rest)


def enter_world_targets(image: Path) -> list[tuple[int, int, int, int, float]]:
    """Find exact Enter World labels in a character-select screenshot."""
    width, height, channels, rows = png_pixels(image)
    channel = STATE_DIR / "character-select-green.pgm"
    write_pgm_channel(channel, width, height, channels, rows, 1, CHARACTER_SELECT_OCR_SCALE)
    words = [unscaled(word) for word in ocr_words_with_lines(channel, psm=6) if word[1] >= 0]
    combined = [word for word in words if word[0].casefold().replace(" ", "") == "enterworld"]
    targets = [(word[2], word[3], word[4], word[5], word[1]) for word in combined]
    for enter in words:
        if enter[0].casefold() != "enter":
            continue
        for world in words:
            if world[0].casefold() != "world" or world[6] != enter[6]:
                continue
            left, top = min(enter[2], world[2]), min(enter[3], world[3])
            right = max(enter[2] + enter[4], world[2] + world[4])
            bottom = max(enter[3] + enter[5], world[3] + world[5])
            targets.append((left, top, right - left, bottom - top, min(enter[1], world[1])))
    return list(dict.fromkeys(targets))


def character_targets(image: Path, name: str) -> list[tuple[int, int, int, int]]:
    """Every OCR word on the character list that reads exactly as the approved character's name."""
    width, height, channels, rows = png_pixels(image)
    channel = STATE_DIR / "character-select-green.pgm"
    write_pgm_channel(channel, width, height, channels, rows, 1, CHARACTER_SELECT_OCR_SCALE)
    wanted = name.strip().casefold()
    # The list is the panel on the right; the selected character's name is also drawn large under the model, and
    # that copy is not a list entry to click. Frame-edge art can join a word as stray punctuation (`._Hel`).
    return [
        (word[2], word[3], word[4], word[5])
        for word in map(unscaled, ocr_words_with_lines(channel, psm=11))
        if word[1] >= 0 and word[2] > width // 2 and word[0].strip(string.punctuation + " ").casefold() == wanted
    ]


def enter_world(state: Mapping) -> None:
    """Select the approved character, then click Enter World, only when the frame visibly shows both.

    Enter World alone enters with whichever character the client selected last, often the player's own, so the
    approved name is clicked first and a list without exactly one reading of it is never entered.
    """
    if not game_focused(state):
        return
    image = shot(state, STATE_DIR / "character-select.png")
    targets = enter_world_targets(image)
    if len(targets) != 1:
        return
    name = approved_character()
    characters = character_targets(image, name) if name else []
    if len(characters) != 1:
        print(
            f"forever_client: character select shows {len(characters)} entries reading {name!r}; "
            f"not entering the world (frame: {image})",
            file=sys.stderr,
            flush=True,
        )
        return
    left, top, width, height = characters[0]
    x(state, "mousemove", str(left + width // 2), str(top + height // 2))
    time.sleep(0.5)
    x(state, "click", "1")
    time.sleep(1)
    left, top, width, height, _ = targets[0]
    x(state, "mousemove", str(left + width // 2), str(top + height // 2))
    time.sleep(0.5)
    x(state, "click", "1")
    (STATE_DIR / "last-input").touch()


def reload(state: Mapping, timeout: float = RELOAD_WAIT) -> Path:
    # The new cycle's screenshots are the ones after the command was sent: a screenshot an earlier reload's flow
    # still takes would otherwise be read as this one's world load.
    slash(state, "/reload")
    return wait_for_world(screenshots(), timeout, safety_state=state)


# --- dev builds ------------------------------------------------------------------------------------------------


def git(repo_root: Path, *args: str) -> str:
    """One git read from a repository's checkout, its failure a ClientError the agent can read."""
    try:
        return subprocess.check_output(["git", "-C", str(repo_root), *args], text=True, stderr=subprocess.PIPE).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise ClientError(f"git {' '.join(args)} in {repo_root}: {detail.strip()}") from None


def resolve_commit(root: Path, ref: str) -> str:
    """Resolve a ref in the shared sibling checkout, whose local branches are not kept current.

    A branch origin has resolves to origin's tip after one fetch (#771); a branch only this checkout has stays local.
    Anything else resolves locally, fetching origin once for a missing full commit SHA.
    """
    branches = (f"refs/heads/{ref}", f"refs/remotes/origin/{ref}")
    if any(
        subprocess.run(["git", "-C", str(root), "show-ref", "--verify", "--quiet", name]).returncode == 0
        for name in branches
    ):
        git(root, "fetch", "origin")
        try:
            return git(root, "rev-parse", "--verify", f"refs/remotes/origin/{ref}^{{commit}}")
        except ClientError:
            pass
    try:
        return git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    except ClientError:
        if not re.fullmatch(r"[0-9a-fA-F]{40}", ref):
            raise
    git(root, "fetch", "origin")
    try:
        return git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    except ClientError:
        raise ClientError(f"commit {ref} is not on origin in {root}") from None


def tag_name(repo_root: Path, commit: str) -> str | None:
    """The release tag naming exactly this commit, or None."""
    try:
        found = subprocess.check_output(
            ["git", "-C", str(repo_root), "describe", "--tags", "--exact-match", commit],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return found or None


def dev_version(repo_root: Path, commit: str) -> str:
    """`<version>-dev+<sha>`, the tag without its `v` as a release TOC carries it, so wowaddon returns the dev link to
    the store release once a newer one ships."""
    try:
        tag = subprocess.check_output(
            ["git", "-C", str(repo_root), "describe", "--tags", "--abbrev=0", commit],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        tag = "v0.0.0"  # a repository with no release yet
    version = tag[1:] if re.match(r"[vV]\d", tag) else tag
    return f"{version}-dev+{git(repo_root, 'rev-parse', '--short', commit)}"


def stamp_tocs(build: Path, version: str) -> None:
    """Replace the packager's `@project-version@` in every TOC, keeping the file's own line endings."""
    for toc in sorted(build.rglob("*.toc")):
        raw = toc.read_bytes()
        if b"@project-version@" in raw:
            toc.write_bytes(raw.replace(b"@project-version@", version.encode()))


def unpack(archive: Path, destination: Path) -> None:
    """Unpack a git archive; Python 3.12 and later take the `data` member filter that makes it refuse escapes."""
    with tarfile.open(archive) as tree:
        try:
            tree.extractall(destination, filter="data")
        except TypeError:
            tree.extractall(destination)


# Where the core checkout keeps the tooling each consumer vendors as tools/forever_tools.
CORE_TOOLING = Path(".agents/skills/wow-forever-addon/tooling/forever_tools")


def embed_core(staging: Path, core_root: Path | None = None, core_ref: str | None = None) -> None:
    """Run the build's own `forever_tools.embed` when its TOC opts in, as the consumer's release does.

    The core it embeds is a git archive of the `forever-core` checkout at the tag `tools/forever-core.txt` pins, so the
    dev build carries the same `Libs/ForeverCore/` bytes the release zip will. `core_ref` embeds that core commit
    instead, to test an unreleased core candidate inside a consumer; the build number still comes from the pin. The
    candidate's own vendored tooling replaces the build's first, as the consumer's tooling sync will, so its embed step
    and generated files are the candidate's too.
    """
    tool = staging / "tools" / "forever_tools" / "embed.py"
    pin = staging / "tools" / "forever-core.txt"
    if not tool.is_file() or not pin.is_file():
        return
    core_root = core_root or WORKSPACE / "forever-core"
    core = staging.with_name(f"{staging.name}.core")
    archive = staging.with_name(f"{staging.name}.core.tar")
    shutil.rmtree(core, ignore_errors=True)
    core.mkdir()
    try:
        try:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(core_root),
                    "archive",
                    "--format=tar",
                    f"--output={archive}",
                    core_ref or pin.read_text().strip(),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            detail = getattr(error, "stderr", "") or str(error)
            raise ClientError(
                f"git archive of ForeverCore {core_ref or pin.read_text().strip()} failed: {detail.strip()}"
            ) from None
        unpack(archive, core)
        tooling = core / CORE_TOOLING
        if core_ref and tooling.is_dir():
            shutil.copytree(tooling, staging / "tools" / "forever_tools", dirs_exist_ok=True)
        done = subprocess.run(
            [sys.executable, "-m", "tools.forever_tools.embed", "--core", str(core), str(staging)],
            cwd=staging,
            capture_output=True,
            text=True,
        )
        if done.returncode != 0:
            raise ClientError(f"embedding ForeverCore failed: {(done.stderr or done.stdout).strip()}")
        if "nothing to do" not in done.stdout:
            print(done.stdout.strip(), flush=True)
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(core, ignore_errors=True)


def build_dev(
    repo: str,
    commit: str,
    destination: Path | None = None,
    repo_root: Path | None = None,
    core_ref: str | None = None,
) -> Path:
    """Write the dev build of `commit` to `test-artifacts/<repo>-dev`, as `rebuild-dev.sh` did.

    The build is the commit's own tree without the development folders, with every TOC stamped `<tag>-dev+<sha>`, so
    `wowaddon` returns the dev link to the store release once one newer than the tag ships. The new build is unpacked
    beside the old one and swapped in, so a failed build leaves the previous one in place.
    """
    root = repo_root or WORKSPACE / repo
    folder = destination or BUILD_ROOT / f"{repo}-dev"
    sha = resolve_commit(root, commit)
    version = dev_version(root, sha)
    staging = folder.with_name(f"{folder.name}.new")
    previous = folder.with_name(f"{folder.name}.old")
    archive = folder.with_name(f"{folder.name}.tar")
    for stale in (staging, previous, archive):
        if stale.is_dir() and not stale.is_symlink():
            shutil.rmtree(stale)
        elif stale.exists() or stale.is_symlink():
            stale.unlink()
    staging.mkdir(parents=True)
    try:
        try:
            subprocess.run(
                ["git", "-C", str(root), "archive", "--format=tar", f"--output={archive}", sha],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            detail = getattr(error, "stderr", "") or str(error)
            raise ClientError(f"git archive {sha[:7]} in {root} failed: {detail.strip()}") from None
        unpack(archive, staging)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        archive.unlink(missing_ok=True)
    try:
        embed_core(staging, core_ref=core_ref)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    for name in DEV_FOLDERS:
        victim = staging / name
        if victim.is_dir() and not victim.is_symlink():
            shutil.rmtree(victim)
        elif victim.exists() or victim.is_symlink():
            victim.unlink()
    stamp_tocs(staging, version)
    if folder.exists() or folder.is_symlink():
        folder.rename(previous)
    staging.rename(folder)
    if previous.exists() or previous.is_symlink():
        shutil.rmtree(previous) if previous.is_dir() and not previous.is_symlink() else previous.unlink()
    print(f"{repo} <- {sha[:7]} ({version}) in {folder}", flush=True)
    return folder


def package_name(repo_root: Path, commit: str) -> str | None:
    """The addon folder `.pkgmeta` ships in `package-as`, or None for a repository without one."""
    try:
        text = git(repo_root, "show", f"{commit}:.pkgmeta")
    except ClientError:
        return None
    found = PACKAGE_AS.search(text)
    return found.group(1) if found else None


def addon_folders(build: Path, package: str | None = None) -> list[tuple[str, Path]]:
    """Each addon folder the build ships, as its name and the folder to link into AddOns.

    `package-as` names the addon. A repository without one (Kiln Forever keeps it under `addon/`) ships every TOC
    folder that is not a library the packager moves in from elsewhere.
    """
    found = sorted((toc.stem, toc.parent) for toc in build.rglob("*.toc"))
    if package:
        chosen = [(name, parent) for name, parent in found if name == package]
        if chosen:
            return chosen
    return [(name, parent) for name, parent in found if not name.startswith("Lib")]


# --- the AddOns links a smoke session borrows -------------------------------------------------------------------

LINK_RECORD = "smoke-links.json"


def addons_dir() -> Path:
    return CLIENT / "Interface/AddOns"


def link_record_path() -> Path:
    return STATE_DIR / LINK_RECORD


def process_start(pid: int) -> int | None:
    """A process's start time in clock ticks since boot, which tells a live process from one that reused its pid."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return int(stat.rsplit(")", 1)[1].split()[19])  # starttime is field 22, the 20th after the command name
    except (OSError, IndexError, ValueError):
        return None


def process_exited(pid: int) -> bool:
    """Whether a pid is a zombie (Z) or dead (X): it has exited and waits only for its parent to reap it."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] in ("Z", "X")
    except (OSError, IndexError):
        return False


def boot_id() -> str | None:
    """Identify the kernel boot, since process start ticks restart after reboot."""
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip() or None
    except OSError:
        return None


def owner_alive(owner: object) -> bool:
    """Whether the session that wrote a link record still runs; a reused pid is told apart by its start time."""
    pid = owner.get("pid") if isinstance(owner, Mapping) else None
    if not isinstance(pid, int) or pid <= 0:
        return False
    recorded_boot = owner.get("boot_id") if isinstance(owner, Mapping) else None
    current_boot = boot_id()
    if isinstance(recorded_boot, str) and isinstance(current_boot, str) and recorded_boot != current_boot:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (OSError, OverflowError):
        pass  # another user's pid, or a number no process can have: the start time below decides
    if process_exited(pid):
        return False  # a zombie has exited, whoever reaps it: no caller may wait on it or treat it as an owner
    started = owner.get("started")
    return process_start(pid) == started if isinstance(started, int) else True


def link_record() -> dict | None:
    """The way back a session wrote before it borrowed an AddOns slot, or None.

    The record names its owner by pid and start time. A record an older version wrote is the bare list of links and
    names no owner: it is replayed only while no session holds the client.
    """
    path = link_record_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ClientError(
            f"cannot read {path} ({error}): put the AddOns folder back by hand, then remove that file"
        ) from None
    if isinstance(data, list):
        return {"owner": None, "links": data}
    links = data.get("links") if isinstance(data, dict) else None
    if not isinstance(links, list) or any(not isinstance(link, dict) or "slot" not in link for link in links):
        raise ClientError(f"{path} is not a link record: put the AddOns folder back by hand, then remove that file")
    return data


def write_link_record(records: Sequence[dict]) -> None:
    """Record the way back before each change, naming this session, in one replace so a kill cannot truncate it."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = link_record_path()
    owner = {"pid": os.getpid(), "started": process_start(os.getpid()), "boot_id": boot_id()}
    atomic_write(path, json.dumps({"owner": owner, "links": list(records)}))


def link_build(folders: Sequence[tuple[str, Path]], addons: Path) -> list[dict]:
    """Point each addon folder in AddOns at the build, recording exactly what was there to put back.

    The AddOns folder is shared with the player and with other sessions: a store install is a real directory, so it is
    moved aside rather than replaced, and a link is put back at the very target it had. The record is written before
    each change, so a session killed outright leaves the way back on disk at `smoke-links.json`.
    """
    addons.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    try:
        for name, folder in folders:
            slot = addons / name
            aside = addons / f"{name}.smoke-backup"
            if aside.is_symlink() or aside.exists():
                raise ClientError(f"{aside} is left over from an earlier smoke session: put it back first")
            record: dict = {"slot": str(slot), "target": str(folder), "was": None}
            if slot.is_symlink():
                record["was"] = {"link": os.readlink(slot)}
                slot.unlink()
            elif slot.exists():
                slot.rename(aside)
                record["was"] = {"moved": str(aside)}
            records.append(record)
            write_link_record(records)
            slot.symlink_to(folder)
    except BaseException:
        restore_links(records)
        raise
    return records


def restore_links(records: Sequence[dict]) -> None:
    """Put every slot back exactly as it was, newest change first; a slot a smoke never made is left alone."""
    for record in reversed(records):
        if record.get("restored"):
            continue
        slot = Path(record["slot"])
        was = record["was"]
        if was is None:
            if slot.is_symlink():
                slot.unlink()
        elif "link" in was:
            if slot.is_symlink():
                slot.unlink()
            elif slot.exists():
                print(f"forever_client: {slot} is not the link a smoke session made; left alone", file=sys.stderr)
                continue
            slot.symlink_to(was["link"])
        else:
            aside = Path(was["moved"])
            if slot.is_symlink():
                slot.unlink()
            elif slot.exists():
                print(f"forever_client: {slot} is not the link a smoke session made; left alone", file=sys.stderr)
                continue
            aside.rename(slot)
        record["restored"] = True
    if records and all(record.get("restored") for record in records):
        link_record_path().unlink(missing_ok=True)


def describe_restore(record: Mapping) -> str:
    """One slot a replay put back, for the line the next session prints."""
    name = Path(record["slot"]).name
    was = record.get("was")
    if was is None:
        return f"{name} (the link removed)"
    if "link" in was:
        return f"{name} (link back to {was['link']})"
    return f"{name} (store install back)"


def recover_links(*, job_locked: bool = False) -> int:
    """Replay abandoned links only with exclusive ownership of the job lock."""
    if job_locked:
        return recover_locked_links()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(job_lock_path(), "a+") as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        return recover_locked_links()


def recover_locked_links() -> int:
    """Put back a record a session stopped without its teardown left, and say what it put back.

    A stop that never reaches Python's handlers (SIGKILL, a signal aimed at the wrapping shell, a hangup before the
    handler was installed) leaves the links a smoke borrowed in AddOns and the store install at `.smoke-backup`. The
    recovery holds the job lock, so no active job can own these links. Owner PID metadata is diagnostic only.
    """
    try:
        record = link_record()
    except ClientError:
        # A reboot can leave an empty or torn record. Infer only real store backups, never arbitrary slots.
        backups = sorted(addons_dir().glob("*.smoke-backup"))
        if not backups or client_in_use():
            raise
        links = []
        for aside in backups:
            slot = aside.with_name(aside.name.removesuffix(".smoke-backup"))
            if aside.is_symlink() or not aside.is_dir() or not slot.is_symlink():
                continue
            links.append({"slot": str(slot), "was": {"moved": str(aside)}})
        if not links:
            raise ClientError(f"cannot recover {link_record_path()}: no safe smoke backups found") from None
        record = {"owner": None, "links": links}
    if record is None:
        stale = STATE_DIR / "headless-addon"
        if stale.is_dir() and current_session() is None and not session_lock_held() and not prefix_users():
            shutil.rmtree(stale)
            return 1
        return 0
    links = record["links"]
    restore_links(links)
    try:
        stale_state = json.loads(state_file().read_text())
    except (OSError, ValueError):
        stale_state = {}
    generated = Path(stale_state.get("headless_addon", "")) if stale_state.get("headless_addon") else None
    if current_session() is None and not session_lock_held() and not prefix_users():
        if generated and generated.is_dir() and generated.parent == STATE_DIR:
            shutil.rmtree(generated)
        stale_addon = STATE_DIR / "headless-addon"
        if stale_addon.is_dir():
            shutil.rmtree(stale_addon)
    put_back = [describe_restore(link) for link in links if link.get("restored")]
    if put_back:
        detail = ", ".join(put_back)
        print(f"forever_client: put back the AddOns links a stopped session left behind: {detail}", flush=True)
    elif not links:
        link_record_path().unlink(missing_ok=True)
    return len(put_back)


def client_in_use() -> str | None:
    """Why no session can start now, or None: a client in the prefix, another session's lock, or a free client.

    A Wow.exe in the prefix is named as the player's only when it is one of the prefix's own processes; a headless
    session's client is named as that session's (#652).
    """
    users = prefix_users()
    if users:
        return prefix_who(users)
    return "another session holds the client" if session_lock_held() else None


def foreign_client() -> str | None:
    """Why the player's own client or a session this tool does not own blocks every job, or None when the Wine prefix
    is ours or empty.

    A resident session's Wine processes carry its token, so another agent's session is not a busy client: its job is
    waited for. Exit 3 is this reason only, the processes this tool does not own; the sentence names a headless
    session's own client as that session's, never as the player's (#652).
    """
    state = current_session()
    if state is None and session_lock_held():
        # A session is starting (or finishing) and has not written its token yet: its Wine processes are ours.
        return None
    processes = prefix_snapshot()
    _, foreign = prefix_ownership(processes, state.get("token") if state else None)
    return prefix_who(foreign) if foreign else None


# --- the job lock ------------------------------------------------------------------------------------------------
#
# One client and one AddOns folder are shared by every agent, but the session is not the unit of exclusion: the reload
# and the input are. A job holds `job.lock` only while it touches the client, and `job.json` names its holder so a
# waiter can say who it waits for. flock releases the lock when the holder dies, so a `job.json` whose pid is gone is
# stale and treated as free.


def job_lock_path() -> Path:
    return STATE_DIR / JOB_LOCK


def job_record_path() -> Path:
    return STATE_DIR / JOB_RECORD


def read_job_record() -> dict | None:
    """The job.json a holder wrote, or None when there is none to read: it names the holder, never the lock."""
    try:
        record = json.loads(job_record_path().read_text())
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def write_job_record(record: Mapping) -> None:
    """Name the lock's holder in one replace, so a waiter never reads half a record."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = job_record_path()
    atomic_write(path, json.dumps(dict(record)))


def job_alive(record: object) -> bool:
    """Whether the process that wrote a job.json still runs; a reused pid is told apart by its start time."""
    if not isinstance(record, Mapping):
        return False
    return owner_alive(
        {"pid": record.get("pid"), "started": record.get("start_ticks"), "boot_id": record.get("boot_id")}
    )


def job_holder() -> dict | None:
    """The live holder named by job.json, or None when the file is missing or its owner is gone."""
    record = read_job_record()
    return record if job_alive(record) else None


def describe_job() -> str:
    """Who holds the job lock, for a waiter's line: its label, pid and token."""
    record = job_holder()
    if record is None:
        return "another job"
    label = record.get("label") or "a job"
    return f"{label} (pid {record.get('pid')}, token {str(record.get('token') or '')[:8]})"


def job_started() -> float:
    """When the job holding the client started, which is where an `errors` read begins."""
    record = job_holder()
    started = record.get("started") if record else None
    return float(started) if isinstance(started, (int, float)) else time.time()


def enqueue_job(*, session_end: bool = False) -> tuple[Path, object]:
    """Allocate an arrival ticket under a short counter lock, before competing for the job lock."""
    directory = STATE_DIR / "queue"
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "counter.lock", "a+") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        counter = directory / "counter"
        number = int(counter.read_text() if counter.exists() else "0") + 1
        atomic_write(counter, str(number))
        ticket = directory / f"{number:020d}.json"
        handle = None
        try:
            atomic_write(
                ticket,
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "start_ticks": process_start(os.getpid()),
                        "boot_id": boot_id(),
                        "session_end": session_end,
                    }
                ),
            )
            handle = ticket.open()
            fcntl.flock(handle, fcntl.LOCK_EX)
        except BaseException:
            if handle is not None:
                handle.close()
            ticket.unlink(missing_ok=True)
            raise
    return ticket, handle


def job_queue() -> list[Path]:
    """Live tickets in arrival order, with serve teardown ahead of ordinary callers."""
    return [path for _ordinary, path in live_tickets()]


def live_tickets() -> list[tuple[bool, Path]]:
    """(ordinary, path) of each ticket whose caller still holds it, teardown first, then in arrival order.

    A ticket is live while its caller holds its lock, so a locked ticket whose record cannot be read is still a caller
    waiting: it counts as ordinary rather than ending the scan, which the serve loop's idle check and teardown share.
    """
    live = []
    directory = STATE_DIR / "queue"
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "counter.lock", "a+") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        for path in sorted(directory.glob("*.json")):
            try:
                with path.open() as ticket:
                    try:
                        fcntl.flock(ticket, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    except BlockingIOError:
                        try:
                            record = json.load(ticket)
                        except ValueError:
                            record = {}
                        ending = isinstance(record, dict) and record.get("session_end", False) is True
                        live.append((not ending, path))
                    else:
                        path.unlink(missing_ok=True)
            except FileNotFoundError:
                continue
            except OSError:
                # Unreadable by this process: a caller's lock cannot be seen, so it is neither queued nor pruned.
                continue
    return sorted(live)


def acquire_job(timeout: float | None, label: str, *, session_end: bool = False) -> tuple[object, str]:
    """Take the lock in ticket order. Serve teardown has priority, but never interrupts a holder."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ticket, ticket_handle = enqueue_job(session_end=session_end)
    handle = None
    deadline = None if timeout is None else time.monotonic() + timeout
    announced = None
    try:
        handle = open(job_lock_path(), "a+")
        while True:
            queue = job_queue()
            if ticket not in queue:
                raise ClientError("job queue ticket disappeared: retry the command")
            position = queue.index(ticket) + 1
            try:
                if position != 1:
                    raise BlockingIOError
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if not session_end and (current_session() or {}).get("reloading"):
                    fcntl.flock(handle, fcntl.LOCK_UN)
                    raise BlockingIOError
                break
            except BlockingIOError:
                waiting = (describe_job(), position)
                if waiting != announced:
                    print(
                        f"forever_client: waiting for {waiting[0]}; queue position {position}",
                        file=sys.stderr,
                        flush=True,
                    )
                    announced = waiting
                if deadline is not None and time.monotonic() >= deadline:
                    raise ClientError(
                        f"timed out after waiting {timeout:.0f} s for the client: {waiting[0]}; "
                        f"queue position {position}"
                    ) from None
                time.sleep(JOB_POLL)
        # A verb that held a modifier and was killed before its own release left no process to send keyup, so the
        # next holder of the lock sends it before any input of its own.
        release_session_modifiers(current_session())
        token = uuid.uuid4().hex
        write_job_record(
            {
                "pid": os.getpid(),
                "start_ticks": process_start(os.getpid()),
                "boot_id": boot_id(),
                "token": token,
                "label": label,
                "started": time.time(),
            }
        )
        return handle, token
    except BaseException:
        if handle is not None:
            handle.close()
        raise
    finally:
        ticket.unlink(missing_ok=True)
        ticket_handle.close()


def release_job(handle, token: str, *, ended: bool = True) -> None:
    """Release the job lock, record when the job ended, and forget its holder before the lock opens.

    `ended` is False for a session's own teardown, which is not a job ending: the next session's idle limit starts
    from its READY, not from a mark this teardown would leave.
    """
    try:
        if ended:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            (STATE_DIR / LAST_JOB).touch()
    finally:
        record = read_job_record()
        if record is not None and record.get("token") == token:
            job_record_path().unlink(missing_ok=True)
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def compatible_session(state: dict, timeout: float) -> dict:
    """Replace changed helper code, even at the same protocol version, under the job lock."""
    if state.get("headless_addon_digest") != headless_addon_digest():
        return ensure_session(timeout)
    return state


def with_job(label: str, timeout: float, action) -> int:
    """Run one verb that touches the client: inside the job that gave it the token, or holding the lock itself.

    A verb invoked by a `job` command carries `FOREVER_CLIENT_JOB`, and proceeds without taking the lock again. A
    verb run on its own takes the job lock for this one invocation, waiting for the job in flight, and releases it
    afterwards. A lease token labels one invocation; expired or unknown tokens fail before queuing.
    """
    token = os.environ.get("FOREVER_CLIENT_JOB")
    holder = job_holder()
    if token and holder is not None and holder.get("token") == token:
        return action(load_state())
    if token:
        label = f"{live_lease(token)['label']}: {label}"
    handle, own = acquire_job(timeout, label)
    try:
        if token:
            live_lease(token)
        state = compatible_session(load_state(), timeout)
        if token:
            live_lease(token)
        if not session_alive(state):
            raise ClientError("the session ended while this verb waited for the client: run it again")
        return action(state)
    finally:
        release_job(handle, own)


def stop_handlers() -> dict[int, object]:
    """Turn SIGTERM, SIGHUP and SIGINT into a KeyboardInterrupt so a stopped smoke puts the AddOns links back."""
    previous = {signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)}

    def on_signal(_signum, _frame):
        raise KeyboardInterrupt

    for signum in previous:
        signal.signal(signum, on_signal)
    return previous


def restore_handlers(previous: Mapping[int, object]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


# --- the release smoke ------------------------------------------------------------------------------------------


def errors(state: Mapping, addon: str | None = None, *, as_json: bool = False) -> subprocess.CompletedProcess:
    """Reload so the client writes its SavedVariables, then read this session's Lua errors (exit 1 when any)."""
    reload(state)
    return saved_errors(state, addon, as_json=as_json)


def saved_errors(state: Mapping, addon: str | None = None, *, as_json: bool = False) -> subprocess.CompletedProcess:
    """This session's Lua errors as the last reload saved them, read without another reload (exit 1 when any)."""
    tool = Path(__file__).resolve().parents[1] / "forever_errors.py"
    command = [sys.executable, str(tool), "--since", str(state["started"])]
    if addon:
        command += ["--addon", addon]
    if as_json:
        command += ["--json"]
    return subprocess.run(command, check=False, capture_output=True, text=True)


def smoke_counts(state: Mapping, folders: Sequence[tuple[str, Path]]) -> dict[str, int]:
    """`errors --addon <folder>` for each folder, counted once `/forever selftest` has run.

    One reload saves every folder's errors, so each folder is read from that one save: a reload per folder only
    repeated the same login, and a core smoke with its released consumers spent one on each. Every folder is counted
    over the same session, the candidate's login and the selftest. Before, the first folder covered that session and
    each later one also covered the logins of the reloads before it, so coverage depended on a folder's place.
    """
    reload(state)
    counts: dict[str, int] = {}
    for name, _folder in folders:
        completed = saved_errors(state, name, as_json=True)
        if completed.returncode not in (0, 1):
            raise ClientError(f"errors --addon {name} failed ({completed.returncode}): {completed.stderr.strip()}")
        try:
            groups = json.loads(completed.stdout or "[]")
        except ValueError:
            raise ClientError(f"errors --addon {name} printed no JSON: {completed.stdout.strip()[:200]}") from None
        counts[name] = len(groups)
    return counts


def smoke_description(counts: Mapping[str, int], not_started: Sequence[str] = (), error: str | None = None) -> str:
    """The commit status's text: the Lua error count, any released addon that never started, or why it stopped."""
    total = sum(counts.values())
    if not total and not not_started and not error:
        folders = len(counts)
        return f"clean: no Lua errors in {folders} addon folder{'s' if folders != 1 else ''}"
    parts = []
    if total:
        named = ", ".join(f"{count} {name}" for name, count in counts.items() if count)
        parts.append(f"{total} Lua error{'s' if total != 1 else ''}: {named}")
    if not_started:
        parts.append(f"{len(not_started)} did not start: {', '.join(not_started)}")
    if error:
        parts.append(f"smoke did not finish: {error}")
    return "; ".join(parts)[:STATUS_LIMIT]


def post_status(repo: str, commit: str, ok: bool, description: str) -> None:
    """Record the smoke's result on the commit: the release gate reads this context and nothing else."""
    try:
        completed = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{SMOKE_OWNER}/{repo}/statuses/{commit}",
                "-f",
                f"state={'success' if ok else 'failure'}",
                "-f",
                f"context={SMOKE_CONTEXT}",
                "-f",
                f"description={description[:STATUS_LIMIT]}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise ClientError(f"cannot run gh to post {SMOKE_CONTEXT} on {repo}@{commit[:7]}: {error}") from None
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ClientError(f"could not post {SMOKE_CONTEXT} on {SMOKE_OWNER}/{repo}@{commit[:7]}: {detail}")
    if ok:
        dispatch_consumer_release_check(repo, commit)


def dispatch_consumer_release_check(repo: str, commit: str) -> None:
    """Wake the release gate after its final smoke status, independently of GitHub's cron delivery."""
    if repo == "forever-core":
        return
    tools = Path(__file__).resolve().parents[1]
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    sync = load_tool("sync_consumer_prs", tools / "sync_consumer_prs.py")
    try:
        if repo not in sync.consumer_repos():
            return
        head = sync.api_json(f"repos/{SMOKE_OWNER}/{repo}/git/ref/heads/main")["object"]["sha"]
        if head != commit:
            return
        sync.gh(
            "api",
            f"repos/{SMOKE_OWNER}/forever-core/actions/workflows/release-consumers.yml/dispatches",
            "--method",
            "POST",
            "-f",
            "ref=main",
        )
    except (sync.SyncError, OSError, ValueError, KeyError, TypeError) as error:
        # The status is already posted and the scheduled release check still picks the commit up, so the smoke
        # result stands; the failed wake-up is only worth a warning.
        print(
            f"warning: smoke status posted, but could not dispatch consumer release check: {error}",
            file=sys.stderr,
        )


def report_smoke(repo: str, commit: str, outcome: Mapping, *, post: bool = True) -> int:
    """Post a smoke's result and say it, from whatever its job recorded: a count per folder, or the error.

    `post=False` is `--no-post`: the result is printed exactly as it would be posted and no commit status is written.
    """
    counts = outcome["counts"]
    not_started = outcome.get("not_started") or []
    if outcome["error"]:
        print(f"{repo}@{commit[:7]}: {outcome['error']}", file=sys.stderr)
    if not counts and not outcome["error"]:
        print(f"smoke of {repo}@{commit[:7]} stopped before it finished; nothing posted", file=sys.stderr)
        return 1
    if not counts:
        # The checks never ran, so there is no verdict on the commit to post: a failure status here would be read as
        # one by release_check.py and stop smoke_queue.py from trying the commit again (#727).
        print(f"{repo}@{commit[:7]}: no result, nothing posted: {outcome['error']}", flush=True)
        return 2
    ok = not any(counts.values()) and not not_started and not outcome["error"]
    description = smoke_description(counts, not_started, outcome["error"])
    if not post:
        print(f"{repo}@{commit[:7]}: {description} (not posted)", flush=True)
        return 0 if ok else 1
    post_status(repo, commit, ok, description)
    print(f"{repo}@{commit[:7]}: {description} ({SMOKE_CONTEXT} posted)", flush=True)
    return 0 if ok else 1


def released_consumers_tool():
    """tools/released_consumers.py: the consumer release downloads a core smoke links beside the candidate."""
    tools = Path(__file__).resolve().parents[1]
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    return load_tool("released_consumers", tools / "released_consumers.py")


def smoke_folders(
    repo: str, folders: Sequence[tuple[str, Path]]
) -> tuple[list[tuple[str, Path]], list[tuple[str, Path]]]:
    """A candidate's addon folders and, when the candidate is ForeverCore, every consumer's latest released build.

    A core release reaches players before the addons that depend on it are re-released, so core's smoke links the builds
    already on the stores beside the candidate and counts their folders too. The two lists are returned separately, so
    the startup check asks after the released addons and no other. The released folders go through the same
    `link_build` record, so every borrowed AddOns slot, a store install included, is put back. They are unpacked into a
    smoke-private folder so a concurrent suite_load.py cannot remove them while the client has them linked.
    """
    folders = list(folders)
    if repo != CORE_REPO:
        return folders, []
    tool = released_consumers_tool()
    try:
        released = tool.released_folders(BUILD_ROOT / "forever-core-smoke-released")
    except tool.ReleasedError as error:
        raise ClientError(str(error)) from None
    print(f"linking {len(released)} released consumer folder(s) beside the candidate core", flush=True)
    return [*folders, *released], released


# The line the startup-check snippet prints for a released addon that never called ForeverCore.Register: its prefix
# and the folder, so the smoke can name it in the commit status.
NOT_REGISTERED = "not registered: "


def registration_source(names: Sequence[str]) -> str:
    """The Lua !!DevSmoke runs after the selftest: one line per addon that never called ForeverCore.Register.

    Every Forever addon registers from its own files once its `Core/Require.lua` feature check passed. A refusal is one
    UIErrorsFrame line and a stopped file list, not a Lua error, so a folder that loaded but never registered is a
    consumer that did not start (#666).
    """
    strings = devsmoke_eval().lua_string
    listed = ", ".join(strings(name) for name in names)
    return (
        "local core = _G.ForeverCore\n"
        "if type(core) ~= 'table' or type(core.Registered) ~= 'function' then\n"
        "\terror('this ForeverCore does not publish Registered, so the startup check cannot run')\n"
        "end\n"
        f"for _, name in ipairs({{ {listed} }}) do\n"
        f"\tif not core.Registered(name) then print({strings(NOT_REGISTERED)} .. name) end\n"
        "end\n"
    )


def not_registered(lines: Sequence) -> list[str]:
    """The folders the startup-check snippet named, in the order it printed them."""
    prefix = NOT_REGISTERED
    return [line[len(prefix) :] for line in lines if isinstance(line, str) and line.startswith(prefix)]


def stage_registrations(folders: Sequence[tuple[str, Path]]) -> str:
    """Write the !!DevSmoke snippet that asks ForeverCore.Registered for each folder; answer its run token.

    The smoke writes it before the reload that loads the candidate, so it runs at that login, and the reload
    `smoke_counts` makes saves its record with the errors: no reload of its own (#580 is why one save is needed).
    """
    names = [name for name, _folder in folders]
    snippet = STATE_DIR / "smoke-registered.lua"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    snippet.write_text(registration_source(names), encoding="utf-8")
    tool = devsmoke_eval()
    try:
        written = tool.write_snippet(snippet, addons=CLIENT / "Interface/AddOns", capture=False)
    except tool.EvalError as error:
        raise ClientError(f"could not check the released addons' startup: {error}") from None
    return written["token"]


def smoke_registrations(token: str) -> list[str]:
    """Each folder that never called ForeverCore.Register, from the staged snippet's saved record.

    The snippet prints a line per unregistered folder; its record is on disk once a reload after its login has run.
    """
    data = saved_eval(token)
    report, ok = format_eval(data)
    if not ok:
        raise ClientError(f"the released addons' startup check failed: {report}")
    return not_registered(_ordered(data.get("out")))


def verify_links(records: Sequence[dict]) -> None:
    for record in records:
        slot = Path(record["slot"])
        if not slot.is_symlink() or slot.resolve() != Path(record["target"]).resolve():
            raise ClientError(f"{slot} no longer points at the candidate build: no proof recorded")


def github_token_from_gh() -> None:
    """Give this process's GitHub API reads the token of the `gh` login when neither GH_TOKEN nor GITHUB_TOKEN is set.

    A core smoke reads every consumer's latest release through `check_consumers.authorized`, which sends only those
    variables. CI sets them; the machine that smokes locally has a `gh` login instead, and without it the reads go out
    anonymously and share the 60-an-hour limit with every session on the machine (#934).
    """
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return
    result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
    token = result.stdout.strip()
    if result.returncode == 0 and token:
        os.environ["GH_TOKEN"] = token


def smoke(args: argparse.Namespace) -> int:
    """Build a repository's commit, test it in the client as one job, and record the result as a commit status.

    It ensures a session, takes the job lock, builds and links the candidate, reloads so the client loads it, runs
    `/forever selftest` and `errors --addon` for each folder, and puts the links back before it releases the lock.
    ForeverCore's candidate is linked with every consumer's latest released build, and those folders count too; after
    the selftest, one !!DevSmoke eval asks `ForeverCore.Registered` for each of them, so a released addon that refused
    to start on this core fails even though it raised no Lua error. A released build that cannot be fetched is a
    `ClientError` before anything is linked, so nothing is posted and the commit is smoked again later. Exit 0 is a
    clean commit and 1 a failure that was recorded; 3 means the player's own client is running, so nothing is posted and
    a caller retries later. Another agent's job is waited for. A smoke whose checks never ran (no checkout, no such
    ref, a session that could not reach the world, a client that refused the selftest) exits 2 and posts nothing
    either, so the commit is smoked again later. `--manual-launcher` starts the session that way, so the caller can
    take `shot` and click Play itself, and `--no-post` prints the result without posting a commit status.
    """
    repo = args.repo
    if not SMOKE_REPO.fullmatch(repo):
        raise ClientError(f"--repo takes a repository name, not {repo!r}")
    root = WORKSPACE / repo
    if not root.is_dir():
        raise ClientError(f"no checkout of {repo} in {WORKSPACE}")
    commit = resolve_commit(root, args.ref)
    post = not args.no_post
    github_token_from_gh()
    recover_links()
    busy = foreign_client()
    if busy:
        print(f"client in use: {busy}; nothing posted on {repo}@{commit[:7]}", flush=True)
        return 3
    handle, job_token = acquire_job(args.timeout, f"smoke {repo}@{commit[:7]}")
    outcome: dict = {"counts": {}, "not_started": [], "error": None}
    try:
        try:
            state = ensure_session(args.timeout, args.manual_launcher)
            require_safe(state)
        except SignInRequired as error:
            print(f"client unavailable: {error}; nothing posted on {repo}@{commit[:7]}", flush=True)
            return 3
        except SafetyRefusal:
            raise
        except ClientError as error:
            busy = foreign_client()
            if busy:
                print(f"client in use: {busy}; nothing posted on {repo}@{commit[:7]}", flush=True)
                return 3
            outcome["error"] = str(error)
            return report_smoke(repo, commit, outcome, post=post)
        # The client log holds every job's lines: this job's result starts where its own work starts.
        state = {**state, "started": job_started()}
        recover_links(job_locked=True)
        folder = build_dev(repo, commit, destination=BUILD_ROOT / f"{repo}-smoke", repo_root=root)
        folders = addon_folders(folder, package_name(root, commit))
        if not folders:
            raise ClientError(f"{folder} ships no addon folder")
        folders, released = smoke_folders(repo, folders)
        previous = stop_handlers()
        try:
            clear_eval_inbox()
            records = link_build(folders, addons_dir())
            try:
                startup = stage_registrations(released) if released else None
                reload(state)
                # The startup snippet ran at this login; a later login must not run it again.
                clear_eval_inbox()
                slash(state, "/forever selftest")
                # The selftest is synchronous Lua; the reload `smoke_counts` makes settles it and writes SavedVariables.
                outcome["counts"] = smoke_counts(state, folders)
                if startup:
                    outcome["not_started"] = smoke_registrations(startup)
            finally:
                restore_links(records)
        except SafetyRefusal:
            raise
        except ClientError as error:
            outcome["error"] = str(error)
        except KeyboardInterrupt:
            print(f"smoke of {repo}@{commit[:7]} stopped before it finished; nothing posted", file=sys.stderr)
            return 1
        finally:
            clear_eval_inbox(quiet=True)
            restore_handlers(previous)
    finally:
        release_job(handle, job_token)
    return report_smoke(repo, commit, outcome, post=post)


# --- the visual proof ------------------------------------------------------------------------------------------


def lua_flow(action: str) -> bool:
    """Whether a flow's action is a Lua file: an absolute path starts with "/" as a slash command does (#573)."""
    return action.endswith(".lua")


# The client's secure slash words (SecureCmdList in Blizzard's ChatFrame, hash_SecureCmdList at run time). They run
# protected actions, so only a player's typed chat line may send them: a Lua snippet that calls ChatEdit_SendText
# is insecure and the client ignores the command (#901). !!DevSmoke's slash route cannot even find them, because they
# are not in SlashCmdList. The words are fixed by the client, so this is a documented list, not a guess at content.
SECURE_SLASH_WORDS = frozenset(
    (
        "/assist /cancelaura /cancelform /cast /castrandom /castsequence /click /clearfocus /cleartarget /dismount "
        "/equip /equipslot /focus /leavevehicle /petaggressive /petassist /petattack /petdefensive /petfollow "
        "/petpassive /startattack /stopattack /stopcasting /stopmacro /target /targetenemy /targetfriend "
        "/targetlasttarget /use /userandom"
    ).split()
)
# How long a typed secure slash flow settles before the capture: it has no ready check to poll (#901).
SECURE_SLASH_SETTLE_SECONDS = 3


def secure_slash(action: str) -> bool:
    """Whether a flow's action is a secure slash command, decided by its command word."""
    return not lua_flow(action) and action.split()[0].lower() in SECURE_SLASH_WORDS


def flow_step(action: str) -> str:
    """What a proof records for one flow: a slash command as typed, or a Lua snippet by name and content digest.

    A caller's path names a machine, a user and a scratch folder in a public proof, and the file it names is gone with
    that folder, so a Lua step is its sha256 followed by the snippet's file name (#591). Putting the digest first keeps
    keyword file names from looking like credentials to secret scanners (#656).
    """
    if not lua_flow(action):
        return action
    path = Path(action)
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ClientError(f"cannot read the flow's snippet {action}: {error}") from None
    return f"sha256:{digest} {path.name}"


def flow_ready_failure(token: str | None) -> str | None:
    """The readiness failure !!DevSmoke recorded for this run token, when it is already on disk.

    A ready check that raises or never turns true writes `ready` and `readyErr` into DevSmokeDB.eval and asks the
    client to save it, so the proof can report the client's own reason rather than only its timeout (#593).
    """
    if not token:
        return None
    try:
        data = saved_eval(token)
    except ClientError:
        return None
    if data.get("ready") in ("failed", "timeout"):
        return _text(data.get("readyErr")) or f"the flow's ready check {data['ready']}"
    return None


def fresh_screenshots(before: set[Path]) -> list[tuple[float, Path]]:
    """The client's screenshots written since `before`, as (mtime, path); one rotated mid-read is skipped."""
    fresh = []
    for path in screenshots() - before:
        try:
            fresh.append((path.stat().st_mtime, path))
        except OSError:
            continue
    return fresh


def wait_for_flow_world(
    before: set[Path],
    action: str,
    token: str | None = None,
    timeout: float = FLOW_READY_SECONDS,
    *,
    state: Mapping | None = None,
) -> Path:
    """Block until the reload's own world screenshot is on disk: the frame a flow's click aims at.

    Every reload writes one screenshot as the world loads, before !!DevSmoke can run the flow's own, so it is the
    first new file after `before` (#593). A flow whose window needs a real click cannot click before that frame
    exists, so its click waits for this one and the ready screenshot then follows it (#655).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if state is not None:
            require_safe(state, waiting=True)
        fresh = fresh_screenshots(before)
        if fresh:
            return max(fresh)[1]
        failure = flow_ready_failure(token)
        if failure:
            raise ClientError(f"the flow {action} could not be captured: {failure}")
        time.sleep(1)
    raise ClientError(
        f"the flow {action}: the world screenshot its reload writes did not appear within {timeout:.0f} s"
    )


def wait_for_flow_ready(
    before: set[Path],
    action: str,
    token: str | None = None,
    timeout: float = FLOW_READY_SECONDS,
    *,
    state: Mapping | None = None,
) -> Path:
    """Block until a flow says its window is ready, by the screenshot it takes then or the failure it records.

    Every reload writes one screenshot as the world loads, and !!DevSmoke writes the flow's own once the flow returns
    true from its ready check. Both appear after `before`, and the flow's is the later one, so the second new file is
    the flag the capture waits on: a window filled in from late data is captured after it has filled rather than after
    a fixed pause (#593). A check that raises or never turns true records why, and the proof fails on that reason.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if state is not None:
            require_safe(state, waiting=True)
        fresh = fresh_screenshots(before)
        if len(fresh) >= 2:
            return max(fresh)[1]
        failure = flow_ready_failure(token)
        if failure:
            raise ClientError(f"the flow {action} could not be captured: {failure}")
        time.sleep(1)
    raise ClientError(
        f"the flow {action} did not say it was ready to capture within {timeout:.0f} s: a flow signals with the "
        "screenshot !!DevSmoke takes once its ready check returns true (see wow-forever-addon/in-game.md)"
    )


def parse_flows(values: Sequence[str]) -> list[tuple[str, str]]:
    """`--flow NAME=SLASH_OR_LUA_FILE` entries: a name for the proof and the in-game action that shows it."""
    flows = []
    for value in values:
        name, separator, action = value.partition("=")
        if not separator or not name.strip() or not action.strip():
            raise ClientError(f"--flow takes NAME=SLASH_OR_LUA_FILE, not {value!r}")
        action = action.strip()
        if lua_flow(action):
            if not Path(action).is_file():
                raise ClientError(f"--flow {name.strip()}: no Lua file at {action}")
        elif not action.startswith("/"):
            raise ClientError(f"--flow {name.strip()}: {action} is neither a slash command nor a .lua file")
        flows.append((name.strip(), action))
    return flows


# One input a proof flow sends: its kind and its points (click, drag) or its text (key action, typed command).
FlowInput = tuple[str, tuple[int, ...] | str]
# What each `--flow-<kind>` input takes after its flow's name, for the message that refuses a malformed one.
FLOW_INPUT_FORMS = {"click": "X,Y", "drag": "X1,Y1,X2,Y2", "key": "ACTION", "type": "/COMMAND"}


def flow_points(option: str, name: str, spec: str, count: int) -> tuple[int, ...]:
    """`count` X,Y points in screenshot coordinates, each inside the frame, as one flat tuple."""
    form = FLOW_INPUT_FORMS[option.removeprefix("--flow-")]
    parts = spec.split(",")
    try:
        if len(parts) != 2 * count:
            raise ValueError
        numbers = tuple(int(part.strip()) for part in parts)
    except ValueError:
        raise ClientError(f"{option} {name}: {form} takes {2 * count} integers, not {spec!r}") from None
    for px, py in zip(numbers[::2], numbers[1::2], strict=True):
        if not (0 <= px < WIDTH and 0 <= py < HEIGHT):
            raise ClientError(f"{option} {name}: ({px}, {py}) is outside the {WIDTH}x{HEIGHT} frame")
    return numbers


def parse_flow_inputs(
    values: Sequence[tuple[str, str]], flows: Sequence[tuple[str, str]]
) -> dict[str, list[FlowInput]]:
    """The input each named flow sends once its reload's world screenshot has landed, in command-line order.

    `values` are (kind, "NAME=SPEC") pairs from `--flow-click NAME=X,Y`, `--flow-drag NAME=X1,Y1,X2,Y2`,
    `--flow-key NAME=ACTION` and `--flow-type NAME=/COMMAND`. An input belongs to a flow by name, so a name that
    matches no `--flow`, a point outside the frame or an action `key --action` does not press is refused here,
    before the build takes the client, rather than a flow that quietly sends nothing.
    """
    names = [name for name, _ in flows]
    inputs: dict[str, list[FlowInput]] = {}
    for kind, value in values:
        option = f"--flow-{kind}"
        name, separator, spec = value.partition("=")
        name, spec = name.strip(), spec.strip()
        if not separator or not name or not spec:
            raise ClientError(f"{option} takes NAME={FLOW_INPUT_FORMS[kind]}, not {value!r}")
        if name not in names:
            known = ", ".join(names) if names else "no flow is named"
            raise ClientError(f"{option} {name}: no --flow of that name ({known})")
        parsed: tuple[int, ...] | str
        if kind == "click":
            parsed = flow_points(option, name, spec, 1)
        elif kind == "drag":
            parsed = flow_points(option, name, spec, 2)
        elif kind == "key":
            if spec not in ACTIONS:
                raise ClientError(f"{option} {name}: {spec} is not an action; it takes {', '.join(ACTIONS)}")
            parsed = spec
        else:
            one_line_slash(spec)
            parsed = spec
        inputs.setdefault(name, []).append((kind, parsed))
    return inputs


def flow_record(name: str, action: str, inputs: Sequence[FlowInput] = ()) -> dict:
    """One entry in the proof's `flows`: what ran, the input it sent in order, and that it was captured."""
    record: dict = {"name": name, "steps": [flow_step(action)]}
    if inputs:
        record["inputs"] = [{kind: list(value) if isinstance(value, tuple) else value} for kind, value in inputs]
    record["result"] = "pass"
    return record


def flow_capture_failure(state: Mapping, action: str, token: str, timeout: ClientError) -> ClientError:
    """The precise failure for a flow that produced no screenshot, or its timeout when none was recorded.

    !!DevSmoke saves a failing ready check into DevSmokeDB.eval as it happens. If that record is not on disk yet, the
    proof reloads once to save it; the inbox is already cleared, so the reload does not run the flow again (#593).
    """
    failure = flow_ready_failure(token)
    if failure:
        return ClientError(f"the flow {action} could not be captured: {failure}")
    try:
        reload(state)
    except SafetyRefusal:
        raise
    except ClientError:
        return timeout
    failure = flow_ready_failure(token)
    if failure:
        return ClientError(f"the flow {action} could not be captured: {failure}")
    return timeout


def flow_key_combos(state: Mapping, inputs: Sequence[FlowInput]) -> list[list[str]]:
    """The keysyms for a flow's `--flow-key` actions, resolved before its snippet is written and its reload runs.

    Resolving may itself write an eval and reload when the client's bindings are not on disk yet (`action_bindings`),
    which would overwrite the flow's snippet in the inbox or close the window the flow opened, so it runs first (#860).
    """
    actions = [value for kind, value in inputs if kind == "key" and isinstance(value, str)]
    return action_keys(state, actions) if actions else []


def run_flow_inputs(state: Mapping, inputs: Sequence[FlowInput], combos: Sequence[Sequence[str]]) -> None:
    """Send a flow's inputs in order through the verbs an agent uses: `click`, `drag`, a bound key, a typed slash.

    The first aimed input aims at the reload's world screenshot, which has just landed. A later one aims at a fresh
    `shot`, since the input before it may have changed the frame, and `click` and `drag` refuse an older one.
    """
    keys = iter(combos)
    sent = False
    for kind, value in inputs:
        if kind in ("click", "drag"):
            if sent:
                shot(state, STATE_DIR / "flow-input.png")
            else:
                (STATE_DIR / "last-shot").touch()
        if isinstance(value, tuple):
            if kind == "click":
                px, py = value
                click(state, px, py, "1")
                print(f"clicked {px},{py}", flush=True)
            else:
                x1, y1, x2, y2 = value
                drag(state, x1, y1, x2, y2)
                print(f"dragged {x1},{y1} to {x2},{y2}", flush=True)
        elif kind == "key":
            combo = next(keys)
            if moving_action(value):
                mark_moved()
            send(state, "key", "+".join(combo))
            print(f"pressed {value} ({'+'.join(combo)})", flush=True)
        else:
            slash(state, value)
            print(f"typed {value}", flush=True)
        sent = True


def world_load_shot(path: Path, timeout: float = 5.0) -> bool:
    """Whether a client screenshot is a world load's, by the marker !!DevSmoke draws only then; waits for a file the
    client is still writing."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return has_headless_marker(path)
        except ClientError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.5)


def secure_point(inputs: Sequence[FlowInput]) -> tuple[int, int] | None:
    """The one click a secure slash flow may take, sent after its typed line settles (`run_secure_flow`)."""
    if not inputs:
        return None
    kind, value = inputs[0]
    if len(inputs) == 1 and kind == "click" and isinstance(value, tuple):
        return value[0], value[1]
    raise ClientError("a secure slash flow takes at most one --flow-click and no other flow input")


def run_flow(
    state: Mapping, action: str, inputs: Sequence[FlowInput] = (), previous: tuple[str, str] | None = None
) -> str:
    """Run one proof flow through !!DevSmoke: a slash command, or a Lua file.

    Both routes write a snippet whose own run token `check_flow_eval` reads once the screenshot is taken: the reload
    that saves the result to disk would close the window the flow just opened (#580). A slash command runs through
    `ChatEdit_SendText`, the client's own parser, so the capture follows a confirmed run rather than a fixed pause
    (#573). The flow's ready check is polled by !!DevSmoke, whose screenshot then says the window has drawn, so the
    capture waits for that file instead of a pause (#593). `inputs` are clicks, drags, bound keys and typed slash
    commands, sent in order between the flow's reload's world screenshot and its ready one: the snippet has run by
    then, and nothing reloads after them, so a merchant or trainer window a key opens is still open for the capture
    (#655, #857, #860). Opening a protected window is not something a Lua snippet can do, and since #648 no outside
    input can reach the client while this job holds it.

    `previous` is the earlier flow's (action, token): this flow's reload saves that flow's eval, which is checked
    straight after it, before this flow sends any input or waits on its own capture, so a failure is reported against
    the flow that caused it.
    """
    if secure_slash(action):
        return run_secure_flow(state, action, secure_point(inputs))
    combos = flow_key_combos(state, inputs)
    tool = devsmoke_eval()
    try:
        if lua_flow(action):
            written = tool.write_snippet(Path(action), addons=CLIENT / "Interface/AddOns", capture=True)
        else:
            one_line_slash(action)
            written = tool.write_slash(action, addons=CLIENT / "Interface/AddOns", capture=True)
    except tool.EvalError as error:
        if previous:
            # The earlier flow has run, but only a reload saves its result: report that flow too, so this refusal
            # never hides its failure.
            print(f"flow {action} refused: {error}", file=sys.stderr, flush=True)
            clear_eval_inbox(quiet=True)
            reload(state)
            check_flow_eval(state, *previous, saved=True)
        raise ClientError(str(error)) from None
    print(f"wrote {written['chunk']} from {written['snippet']} ({written['lines']} lines)", flush=True)
    # The snippet runs at login of this reload. Clearing the inbox afterwards keeps the later reloads a proof makes
    # from running it again, which would schedule a second ready screenshot the next flow could mistake for its own.
    before = screenshots()
    reload(state)
    clear_eval_inbox()
    if previous:
        check_flow_eval(state, *previous, saved=True, next_flow=(action, written["token"]))
    try:
        if inputs:
            world = wait_for_flow_world(before, action, written["token"], state=state)
            print(f"sending {len(inputs)} input(s) after {world.name}", flush=True)
            run_flow_inputs(state, inputs, combos)
        ready = wait_for_flow_ready(before, action, written["token"], state=state)
        if inputs and world_load_shot(ready):
            raise ClientError(
                f"the flow {action}: its inputs reloaded the client, which closes any window they opened, so the "
                "screenshot after them is a fresh world load rather than the flow's ready one"
            )
    except SafetyRefusal:
        raise
    except ClientError as error:
        raise flow_capture_failure(state, action, written["token"], error) from None
    return written["token"]


def run_secure_flow(state: Mapping, action: str, point: tuple[int, int] | None = None) -> str:
    """Run a secure slash flow by typing it into chat, as the `slash` verb does, once the reload's world frame lands.

    A secure command cannot run from insecure Lua, so no snippet is written and the flow has no run token or ready
    check: the capture follows a short fixed settle after the typed line (#901). `point` is clicked once that settle
    ends, so a flow can open a protected window and then pick a tab inside it, then settles again before the capture.
    Each flow reloads first, so a later Lua flow starts from a fresh world; it does not continue from this window.
    """
    one_line_slash(action)
    before = screenshots()
    reload(state)
    clear_eval_inbox()
    try:
        world = wait_for_flow_world(before, action, state=state)
        print(f"typing {action} after {world.name}", flush=True)
        slash(state, action)
    except SafetyRefusal:
        raise
    except ClientError as error:
        raise ClientError(f"the flow {action} could not be typed: {error}") from None
    time.sleep(SECURE_SLASH_SETTLE_SECONDS)
    if point:
        # The typed line is the last input, so mark a fresh frame before clicking, as the Lua flow path does.
        (STATE_DIR / "last-shot").touch()
        click(state, point[0], point[1], "1")
        print(f"clicked {point[0]},{point[1]} after {action}", flush=True)
        time.sleep(SECURE_SLASH_SETTLE_SECONDS)
    return ""


def saved_within(token: str, wait: float) -> bool:
    """Whether the eval the run token names is on disk within `wait` seconds: !!DevSmoke saves an eval the moment it
    runs, so no reload is needed to read it, and the UI the snippet opened stays open (#894)."""
    deadline = time.monotonic() + wait
    while True:
        try:
            saved_eval(token)
            return True
        except ClientError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(WAIT_POLL)


def eval_result(state: Mapping, token: str, *, saved: bool = False, wait: float | None = None) -> tuple[str, bool]:
    """The report of the eval the run token wrote.

    SavedVariables are written at a reload or logout, so a proof flow's result reaches disk only at the reload after
    its own (#580). `saved` says a later reload, such as the next flow's, has already done that. An eval is saved by
    !!DevSmoke the moment it runs: `wait` seconds allow for that, and the reload is only the fallback for a
    !!DevSmoke that did not save (#894).
    """
    if not saved and not (wait is not None and saved_within(token, wait)):
        reload(state)
    return format_eval(saved_eval(token))


def live_eval(state: Mapping, source: Path) -> int:
    """Run a Lua file in the running session with no reload, and report what it printed and returned.

    The file travels as numbered `/devsmoke live` chat lines, so the UI stays as it is and globals the snippet sets
    stay for the slash commands that follow (#894). Every line is typed at the speed of any slash command, so a long
    helper costs time in proportion to its size: load it once, then drive it with short commands.
    """
    tool = devsmoke_eval()
    try:
        token, lines = tool.live_commands(source)
    except tool.EvalError as error:
        raise ClientError(str(error)) from None
    print(f"sending {source} as {len(lines)} chat lines", flush=True)
    for line in lines:
        slash(state, line)
    report, ok = eval_result(state, token, wait=EVAL_SAVE_WAIT)
    print(report)
    return 0 if ok else 1


def check_flow_eval(
    state: Mapping, action: str, token: str, *, saved: bool = False, next_flow: tuple[str, str] | None = None
) -> None:
    """Fail on a flow whose own snippet raised, quoting that snippet's error and nothing else's.

    `next_flow` is the (action, token) of the flow whose reload saved this one: !!DevSmoke saves that flow's own record
    over this one when its ready check fails before this read, and the error says so instead of "not saved".
    """
    try:
        report, ok = eval_result(state, token, saved=saved)
    except SafetyRefusal:
        raise
    except EvalMismatch as error:
        if next_flow and error.seen == next_flow[1]:
            raise ClientError(
                f"flow {action}: its result was overwritten by flow {next_flow[0]}'s own record, saved when that "
                "flow's ready check failed; rerun the proof with the flows apart to read it"
            ) from None
        raise ClientError(f"flow {action}: {error}") from None
    except ClientError as error:
        raise ClientError(f"flow {action}: {error}") from None
    print(report, flush=True)
    if not ok:
        raise ClientError(f"flow snippet {action} failed: {report}")


def flow_slug(name: str) -> str:
    """A flow name as a screenshot file name, so each image is recognisable in the gist."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return slug or "flow"


def client_build(folder: Path) -> str:
    """The client build the session ran, from the client's own log, and the interface its addons target."""
    version = None
    try:
        for line in (CLIENT / "Logs/gx.log").read_text(errors="replace").splitlines():
            match = CLIENT_BUILD_LINE.search(line)
            if match:
                version = match.group(1)
    except OSError:
        version = None
    if not version:
        raise ClientError(f"the client wrote no build line to {CLIENT / 'Logs/gx.log'}")
    interface = None
    for toc in sorted(folder.glob("*.toc")):
        match = INTERFACE_LINE.search(toc.read_text(errors="replace"))
        if match:
            interface = match.group(1)
            break
    return f"{version} (Interface {interface})" if interface else version


def run_tool(command: Sequence[str], purpose: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """One shell tool for the proof upload, its failure a ClientError the agent can read."""
    try:
        completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    except OSError as error:
        raise ClientError(f"cannot {purpose}: {error}") from None
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise ClientError(f"could not {purpose}: {detail}")
    return completed


def create_gist(description: str, workspace: Path) -> str:
    """A new secret gist holding its README, and its id: `gh gist create` prints the gist's URL."""
    workspace.mkdir(parents=True, exist_ok=True)
    readme = workspace / "README.md"
    readme.write_text(f"# {GIST_DESCRIPTION}\n\n{description}\n", encoding="utf-8")
    completed = run_tool(["gh", "gist", "create", "--desc", description, str(readme)], "create the proof gist")
    match = GIST_URL.search(completed.stdout)
    if not match:
        raise ClientError(f"gh gist create printed no gist URL: {completed.stdout.strip()[:200]}")
    return match.group(1)


def upload_screenshots(gist: str, screenshots: Sequence[Path], description: str) -> list[dict]:
    """Push the PNGs to the gist and name each one by the full commit SHA its raw URL is pinned to."""
    scratch = PROOF_SCRATCH / f"visual-proof-{gist}"
    PROOF_SCRATCH.mkdir(parents=True, exist_ok=True)
    run_tool(["git", "clone", f"https://gist.github.com/{gist}.git", str(scratch)], "clone the proof gist")
    for image in screenshots:
        shutil.copyfile(image, scratch / image.name)
    run_tool(["git", "-C", str(scratch), "add", "-A"], "add the proof screenshots")
    run_tool(["git", "-C", str(scratch), "commit", "-m", description], "commit the proof screenshots")
    run_tool(["git", "-C", str(scratch), "push", "origin", "HEAD"], "push the proof screenshots")
    commit = run_tool(["git", "-C", str(scratch), "rev-parse", "HEAD"], "read the proof gist commit").stdout.strip()
    return [
        {
            "url": f"https://gist.githubusercontent.com/{GIST_OWNER}/{gist}/raw/{commit}/{image.name}",
            "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
        for image in screenshots
    ]


def visual_proof_tool(checkout: Path) -> list[str]:
    """The visual proof checker of `checkout`, or this repository's own wrapper for a checkout without one."""
    wrapper = checkout / "tools/check_visual_proof.py"
    if wrapper.is_file():
        return [sys.executable, str(wrapper)]
    if (checkout / "tools/forever_tools/visual_proof.py").is_file():
        return [sys.executable, "-m", "tools.forever_tools.visual_proof"]
    core = Path(__file__).resolve().parents[2] / "tools/check_visual_proof.py"
    if core.is_file():
        return [sys.executable, str(core)]
    raise ClientError(f"no visual proof checker in {checkout} or beside this tool")


def visual_proof_run(checkout: Path, *args: str) -> subprocess.CompletedProcess:
    """One read of the checkout's own visual proof checker, run at the checkout so `.` is that tree."""
    try:
        return subprocess.run(
            [*visual_proof_tool(checkout), *args], cwd=checkout, text=True, capture_output=True, check=False
        )
    except OSError as error:
        raise ClientError(f"cannot run visual_proof in {checkout}: {error}") from None


def proof_digests(checkout: Path) -> dict:
    """`visual_proof --digests`: the source identity and the canonical packaged runtime."""
    completed = visual_proof_run(checkout, "--digests")
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise ClientError(f"visual proof --digests failed in {checkout}: {detail}")
    try:
        return json.loads(completed.stdout)
    except ValueError:
        raise ClientError(f"visual proof --digests printed no JSON: {completed.stdout.strip()[:200]}") from None


EMBED_FIELD_LINE = re.compile(r"^\ufeff?[ \t]*##[ \t]*X-Forever-Core-Embed[ \t]*:", re.IGNORECASE | re.MULTILINE)


def track_stage(stage: Path) -> None:
    """Make the staged tree its own git work tree with every file tracked, the embedded core included.

    The packager rules the checker applies read git's untracked and ignored paths as unshipped, and fail outright when a
    `.git` sits above the tree but git cannot read it (an empty `.git` placeholder over the workspace, with the build
    root on another filesystem). Its own repository, everything force-added, answers both: no untracked paths, and git
    never looks above the stage.
    """
    for args in (["init", "-q"], ["add", "-A", "-f"]):
        try:
            subprocess.run(["git", "-C", str(stage), *args], check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as error:
            detail = getattr(error, "stderr", "") or str(error)
            raise ClientError(f"cannot track the embedded proof stage {stage}: {detail.strip()}") from None


@contextmanager
def proof_source(checkout: Path, repo: str) -> Generator[Path, None, None]:
    """The tree the installed proof build must match: the checkout, run through its embed step when it embeds core.

    A consumer whose root TOC carries the embed field ships `embed(checkout, pin)`, not the checkout itself: the build
    rewrites its TOC and Lua and adds `Libs/ForeverCore/`. So its tracked files, as they stand in the checkout
    (uncommitted edits included, as the plain comparison reads them), are staged outside any git work tree and given
    the same `embed_core` the build ran, at the same pin, then tracked in a repository of its own (`track_stage`); that
    staged tree is compared. The proof's digests still come
    from the checkout itself (`proof_digests`), so the recorded identity is the source the pull request carries, and the
    pin it hashes binds the embedded bytes. A checkout without the field is compared as it is. The stage is removed on
    every exit.
    """
    if not any(
        EMBED_FIELD_LINE.search(toc.read_text(encoding="utf-8", errors="replace")) for toc in checkout.glob("*.toc")
    ):
        yield checkout
        return
    stage = BUILD_ROOT / f"{repo}-proof-source"
    shutil.rmtree(stage, ignore_errors=True)
    try:
        listed = subprocess.run(
            ["git", "-C", str(checkout), "ls-files", "-z"], check=True, capture_output=True, text=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise ClientError(f"cannot list {checkout}'s tracked files for the embedded proof: {detail.strip()}") from None
    try:
        for name in filter(None, listed.split("\0")):
            source = checkout / name
            if source.is_file():
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        embed_core(stage)
        track_stage(stage)
        yield stage
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def proof_compare(checkout: Path, installed: Path) -> dict:
    """`visual_proof --compare`: the checkout's shipped runtime against the installed addon folder."""
    completed = visual_proof_run(checkout, "--compare", str(installed))
    try:
        comparison = json.loads(completed.stdout)
    except ValueError:
        detail = (completed.stderr or completed.stdout).strip()
        raise ClientError(f"visual proof --compare printed no JSON in {checkout}: {detail[:200]}") from None
    if not comparison.get("equivalent"):
        problems = [
            f"{key}: {', '.join(comparison.get(key) or [])}"
            for key in ("missing", "differing", "extra")
            if comparison.get(key)
        ]
        raise ClientError(f"{installed} does not match {checkout}: {'; '.join(problems) or 'not equivalent'}")
    return comparison


def proof(args: argparse.Namespace) -> int:
    """Record a commit's in-game visual proof into the checkout the pull request carries.

    It runs as one job: the build and the AddOns links are the smoke's, so every borrowed slot is put back on any
    exit. The job reloads once, runs each flow and takes a screenshot after it, and the PNGs go to a new secret gist.
    A flow's `--flow-click`, `--flow-drag`, `--flow-key` and `--flow-type` inputs run inside this job, in order, once
    its reload's world screenshot has landed.
    The proof is written to `<checkout>/.visual-proof.json`; the checkout is never committed or pushed here.
    """
    flows = parse_flows(args.flow)
    if not flows:
        raise ClientError(
            "proof needs at least one --flow: ForeverCore has no shared opener for an addon's update notice, so name "
            'it here, such as --flow "update notice=/lf" or --flow "update notice=notice.lua"'
        )
    inputs = parse_flow_inputs(args.flow_inputs, flows)
    repo = args.repo
    if not SMOKE_REPO.fullmatch(repo):
        raise ClientError(f"--repo takes a repository name, not {repo!r}")
    root = WORKSPACE / repo
    if not root.is_dir():
        raise ClientError(f"no checkout of {repo} in {WORKSPACE}")
    checkout = Path(args.checkout).resolve()
    if not checkout.is_dir():
        raise ClientError(f"no checkout at {checkout}: --checkout is the tree the proof is written to")
    commit = resolve_commit(root, args.ref)
    head = git(checkout, "rev-parse", "--verify", "HEAD")
    if head != commit:
        raise ClientError(f"{checkout} is at {head[:7]}, not {repo}@{commit[:7]}: check out the proof's commit first")
    recover_links()
    busy = foreign_client()
    if busy:
        print(f"client in use: {busy}; no proof recorded for {repo}@{commit[:7]}", flush=True)
        return 3
    handle, job_token = acquire_job(args.timeout, f"proof {repo}@{commit[:7]}")
    screenshots: list[Path] = []
    shots_folder = PROOF_SCRATCH / f"proof-{repo}-{commit[:7]}"
    folders: list[tuple[str, Path]] = []
    try:
        try:
            state = ensure_session(args.timeout, args.manual_launcher)
            require_safe(state)
        except SafetyRefusal:
            raise
        except ClientError:
            # Only the player's own client makes a proof exit 3; another agent's job was waited for above.
            busy = foreign_client()
            if busy:
                print(f"client in use: {busy}; no proof recorded for {repo}@{commit[:7]}", flush=True)
                return 3
            raise
        state = {**state, "started": job_started()}
        recover_links(job_locked=True)
        folder = build_dev(repo, commit, destination=BUILD_ROOT / f"{repo}-proof", repo_root=root)
        folders = addon_folders(folder, package_name(root, commit))
        if not folders:
            raise ClientError(f"{folder} ships no addon folder")
        previous = stop_handlers()
        try:
            clear_eval_inbox()
            records = link_build(folders, addons_dir())
            try:
                reload(state)
                # A flow's eval is read after the shot, once a reload has saved it: the reload that saves it opens the
                # world again, which would close what the flow showed (#580). The next flow's own reload is that
                # save, so only the last flow needs a reload of its own: N flows take N + 2 reloads, not 2N + 1.
                unread: tuple[str, str] | None = None
                for index, (name, action) in enumerate(flows, start=1):
                    verify_links(records)
                    flow_token = run_flow(state, action, inputs.get(name, ()), unread)
                    verify_links(records)
                    screenshots.append(shot(state, shots_folder / f"{index}-{flow_slug(name)}.png"))
                    unread = (action, flow_token) if flow_token else None
                if unread:
                    check_flow_eval(state, *unread)
            finally:
                try:
                    verify_links(records)
                finally:
                    restore_links(records)
        except KeyboardInterrupt:
            print(f"proof of {repo}@{commit[:7]} stopped before it finished; nothing recorded", file=sys.stderr)
            return 1
        finally:
            clear_eval_inbox(quiet=True)
            restore_handlers(previous)
        if screenshots:
            # A queued proof can rebuild this shared folder as soon as the job lock is released.
            build = client_build(folders[0][1])
            try:
                with proof_source(checkout, repo) as source:
                    proof_compare(source, folders[0][1])
            except ClientError:
                # A proof that does not describe the installed build must never be left where it could be committed.
                (checkout / PROOF_FILE).unlink(missing_ok=True)
                raise
    finally:
        release_job(handle, job_token)
    if not screenshots:
        print(f"proof of {repo}@{commit[:7]} stopped before it finished; nothing recorded", file=sys.stderr)
        return 1
    digests = proof_digests(checkout)
    description = f"Visual proof for {repo} at {commit} (flows: {', '.join(name for name, _ in flows)})"
    gist = create_gist(description, shots_folder)
    images = upload_screenshots(gist, screenshots, description)
    proof_data = {
        "input_digest": digests["input_digest"],
        "runtime_sha256": digests["input_digest"],
        "candidate": digests["candidate"],
        "client_build": build,
        "tested_artifact": "source-tree",
        "source_commit": commit,
        "flows": [flow_record(name, action, inputs.get(name, ())) for name, action in flows],
        "images": images,
    }
    target = checkout / PROOF_FILE
    atomic_write(target, json.dumps(proof_data, indent=2) + "\n")
    print(f"{repo}@{commit[:7]}: wrote {target} and checked it against {folders[0][1]}", flush=True)
    return 0


CHECKLIST = Path(__file__).resolve().parents[1] / "checklist/checklist"
CHECKLIST_RESULTS = Path(os.environ.get("CHECKLIST_HOME", WORKSPACE / "wow-handoff")) / "results"
SHOT_SUFFIXES = {".png", ".jpg", ".jpeg", ".tga", ".webp"}


def checklist_status(repo: str, commit: str, round_name: str | None = None) -> dict:
    """`checklist status --json` for one build: the user's answers for it and the build the round recorded.

    Exit 0 is a passed build, 1 a build with a check not passed, 2 a build no round covers (tools/checklist/README.md).
    """
    command = [str(CHECKLIST), "status", "--addon", repo, "--sha", commit, "--json"]
    if round_name:
        command += ["--round", round_name]
    try:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError as error:
        raise ClientError(f"cannot run {CHECKLIST}: {error}") from None
    if completed.returncode == 2:
        raise ClientError(f"no checklist round has checks for {repo}@{commit[:7]}: add them and test it first")
    try:
        report = json.loads(completed.stdout)
    except ValueError:
        detail = (completed.stderr or completed.stdout).strip()
        raise ClientError(f"checklist status printed no JSON for {repo}@{commit[:7]}: {detail[:200]}") from None
    if completed.returncode or not report.get("passed"):
        open_checks = [
            f"{row.get('id')} ({row.get('status') or 'open'})"
            for row in report.get("checks", [])
            if row.get("status") != "pass"
        ]
        raise ClientError(
            f"{report.get('round')}: {repo}@{commit[:7]} has not passed the checklist: {', '.join(open_checks)}"
        )
    return report


def attest(args: argparse.Namespace) -> int:
    """Write a commit's `.visual-proof.json` from the user's own checklist pass in the live client (#874).

    It never touches the client, so it runs while the user plays. The pass binds to the exact runtime that was tested:
    the round's build must name this commit, its recorded runtime digest must equal the checkout's
    `visual_proof --digests`, and the unpacked build it recorded must still compare equal to the checkout. The
    screenshots are the ones the user pasted into the checklist plus any `--shot` from the client's Screenshots folder;
    they go to a new secret gist like a proof's, and the record carries `kind: user-checked` and the round.
    """
    repo = args.repo
    if not SMOKE_REPO.fullmatch(repo):
        raise ClientError(f"--repo takes a repository name, not {repo!r}")
    root = WORKSPACE / repo
    if not root.is_dir():
        raise ClientError(f"no checkout of {repo} in {WORKSPACE}")
    checkout = Path(args.checkout).resolve()
    if not checkout.is_dir():
        raise ClientError(f"no checkout at {checkout}: --checkout is the tree the proof is written to")
    commit = resolve_commit(root, args.ref)
    head = git(checkout, "rev-parse", "--verify", "HEAD")
    if head != commit:
        raise ClientError(f"{checkout} is at {head[:7]}, not {repo}@{commit[:7]}: check out the tested commit first")
    report = checklist_status(repo, commit, args.round)
    build = report.get("build") or {}
    if build.get("sha") != commit:
        raise ClientError(f"{report['round']} recorded {repo} at {str(build.get('sha'))[:7]}, not {commit[:7]}")
    digests = proof_digests(checkout)
    recorded = build.get("digest")
    if not recorded:
        raise ClientError(
            f"{report['round']} recorded no runtime digest for {repo}: record it with checklist build --digest "
            "when the build is linked, so the pass binds to what was tested"
        )
    if recorded != digests["input_digest"]:
        raise ClientError(
            f"{report['round']} tested {repo} runtime {recorded[:12]}, but {checkout} at {commit[:7]} is "
            f"{digests['input_digest'][:12]}: the user's pass is for another build"
        )
    # The checklist resolves the recorded path and hashes it there; compare that same folder.
    artifact = Path(build.get("artifact_path") or "")
    folders = addon_folders(artifact, package_name(root, commit)) if build.get("artifact") and artifact.is_dir() else []
    if not folders:
        raise ClientError(f"{report['round']} names no unpacked build for {repo} to check ({build.get('artifact')!r})")
    tested_in = build.get("client_build")
    if not tested_in:
        raise ClientError(
            f"{report['round']} recorded no client build for {repo}: record it with checklist build --client-build"
        )
    if not build.get("artifact_sha256") or build["artifact_sha256"] != build.get("artifact_sha256_now"):
        raise ClientError(
            f"{report['round']}: the unpacked build at {build.get('artifact')} is not the one recorded when it was "
            "linked (rebuilt, removed or recorded before artifact hashing): relink, record it and test again"
        )
    identity = {
        "sha": commit,
        "digest": recorded,
        "artifact_sha256": build["artifact_sha256"],
        "client_build": tested_in,
    }
    stale = [row["id"] for row in report["checks"] if any(row.get(k) != v for k, v in identity.items())]
    if stale:
        raise ClientError(f"{report['round']}: checks {', '.join(stale)} were not answered for this build")
    proof_compare(checkout, folders[0][1])
    passed = [row for row in report["checks"] if row.get("status") == "pass"]
    if not passed:
        raise ClientError(f"{report['round']}: no check for {repo}@{commit[:7]} was answered pass")
    shots = [Path(image) for row in passed for image in row.get("images", [])] + [Path(s) for s in args.shot]
    missing = [str(s) for s in shots if not s.is_file()]
    if missing:
        raise ClientError(f"screenshot not found: {', '.join(missing)}")
    flows = [
        {
            "name": row["title"],
            "steps": [s.strip() for s in row.get("steps") or [] if s.strip()] or [row.get("pass") or row["title"]],
            "result": "pass",
        }
        for row in passed
    ]
    # visual_proof refuses a Lua flow named by an absolute path (#591), with or without its sha256 annotation; the
    # same rule as its absolute_lua_step, which this tool cannot import from a checkout it has not checked yet.
    lua = [
        step
        for flow in flows
        for step in flow["steps"]
        if (bare := re.sub(r"^sha256:[0-9a-f]{64}\s+|\s+sha256:[0-9a-f]{64}$", "", step)).endswith(".lua")
        and (PurePosixPath(bare).is_absolute() or PureWindowsPath(bare).is_absolute())
    ]
    if lua:
        raise ClientError(
            f"a passed check names a Lua file by absolute path, which a public proof may not carry: {lua}"
        )
    # Evidence goes to a gist, so only an image from the client or the checklist's own results can be sent.
    allowed = [(CLIENT / "Screenshots").resolve(), CHECKLIST_RESULTS.resolve()]
    stray = [
        str(s)
        for s in shots
        if s.suffix.lower() not in SHOT_SUFFIXES or not any(s.resolve().is_relative_to(base) for base in allowed)
    ]
    if stray:
        raise ClientError(
            f"not a screenshot from the client's Screenshots folder or the checklist results: {', '.join(stray)}"
        )
    if not shots:
        raise ClientError(
            f"no screenshot for {repo}@{commit[:7]}: paste one into a passed check or name a client capture with --shot"
        )
    staging = PROOF_SCRATCH / f"attest-{repo}-{commit[:7]}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    named = []
    for index, shot_path in enumerate(shots, start=1):
        # The checker accepts PNG evidence only; client captures are JPEG or TGA and pasted ones may be JPEG or WebP.
        target = staging / f"{index}-{flow_slug(shot_path.stem)}.png"
        try:
            with Image.open(shot_path) as image:
                image.convert("RGB").save(target, "PNG")
        except OSError as e:
            raise ClientError(f"{shot_path} is not a readable image: {e}") from e
        named.append(target)
    description = f"User-checked visual proof for {repo} at {commit} ({report['round']})"
    gist = create_gist(description, staging)
    images = upload_screenshots(gist, named, description)
    proof_data = {
        "input_digest": digests["input_digest"],
        "runtime_sha256": digests["input_digest"],
        "candidate": digests["candidate"],
        "client_build": tested_in,
        "tested_artifact": "source-tree",
        "source_commit": commit,
        "kind": "user-checked",
        "round": report["round"],
        "flows": flows,
        "images": images,
    }
    target = checkout / PROOF_FILE
    atomic_write(target, json.dumps(proof_data, indent=2) + "\n")
    print(f"{repo}@{commit[:7]}: wrote {target} from {report['round']} ({len(passed)} checks passed)", flush=True)
    return 0


# --- session lifecycle -----------------------------------------------------------------------------------------


def gamescope_failure_hint() -> str:
    """What the session log says when gamescope started no client, including a driver mismatch (#567)."""
    try:
        log = (STATE_DIR / "session.log").read_text(errors="replace")
    except OSError:
        return ""
    if "vkCreateInstance failed" not in log and "CVulkanDevice::BInit" not in log:
        return ""
    mismatch = nvidia_mismatch()
    if mismatch:
        return f"; {mismatch}"
    return "; gamescope could not create a Vulkan instance: see the session log"


def child_env(token: str, timeout: float = 30) -> dict[str, str]:
    """Gamescope hands its children DISPLAY and GAMESCOPE_WAYLAND_DISPLAY: read them from the first child.

    Gamescope starts the child through its reaper, so the child is found by a token in the environment it inherits,
    not by its parent."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for p in pids():
            env = read_environ(p)
            if env.get("FOREVER_CLIENT_SESSION") == token and env.get("GAMESCOPE_WAYLAND_DISPLAY"):
                return env
        time.sleep(0.5)
    raise ClientError(f"gamescope started no client: see the session log{gamescope_failure_hint()}")


def log_out(state: Mapping) -> None:
    """/quit from the world: the character logs out and the client exits on its own, as a player's would."""
    try:
        focus_chat(state)
        send(state, "type", "--delay", TYPE_DELAY_MS, "/quit")
        send(state, "key", "Return")
    except (ClientError, subprocess.CalledProcessError):
        return
    deadline = time.monotonic() + LOGOUT_WAIT
    while client_pid() and time.monotonic() < deadline:
        time.sleep(1)


def signal_pid(pid: int, started: int | None, signum: int) -> bool:
    """Signal a process only if it is still the one that started at `started`, through a pidfd."""
    if not isinstance(started, int):
        return False
    try:
        pidfd = os.pidfd_open(pid)
    except (AttributeError, OSError):
        return False
    try:
        if process_start(pid) != started:
            return False
        signal.pidfd_send_signal(pidfd, signum)
        return True
    except ProcessLookupError:
        return False
    finally:
        os.close(pidfd)


def wait_for_pid(pid: int, started: int | None, timeout: float) -> bool:
    """Wait until the recorded process is gone, without treating a reused pid as it."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not owner_alive({"pid": pid, "started": started}):
            return True
        time.sleep(0.1)
    return not owner_alive({"pid": pid, "started": started})


def gamescope_running(gamescope: subprocess.Popen | int | None, state: Mapping | None) -> bool:
    """Whether the session's gamescope still runs, from a live handle or the pid a dead owner left in state."""
    if gamescope is None:
        return False
    if hasattr(gamescope, "poll"):
        return gamescope.poll() is None
    started = state.get("gamescope_start") if state else None
    return owner_alive({"pid": int(gamescope), "started": started})


def stop_gamescope(gamescope: subprocess.Popen | int | None, state: Mapping | None) -> None:
    """Stop the session's gamescope, by its live handle or by the pid a dead owner recorded."""
    if not gamescope_running(gamescope, state):
        return
    if hasattr(gamescope, "poll"):
        try:
            gamescope.terminate()
        except ProcessLookupError:
            return
        try:
            gamescope.wait(20)
        except subprocess.TimeoutExpired:
            try:
                gamescope.kill()
            except ProcessLookupError:
                return
            gamescope.wait(20)
        return
    pid = int(gamescope)
    started = state.get("gamescope_start") if state else None
    if signal_pid(pid, started, signal.SIGTERM) and not wait_for_pid(pid, started, 20):
        signal_pid(pid, started, signal.SIGKILL)
        wait_for_pid(pid, started, 20)
    if gamescope_running(gamescope, state):
        raise ClientError(f"cannot safely stop gamescope {pid}: session state retained")


def nested_hyprland():
    """tools/headless/nested_hyprland.py: the private nested Hyprland a Hyprland job runs the client in."""
    return load_tool("nested_hyprland", Path(__file__).resolve().parent / "nested_hyprland.py")


def nested_running(state: Mapping | None) -> bool:
    record = state.get("nested") if state else None
    return bool(record) and nested_hyprland().running(record)


def stop_nested(state: dict | None) -> None:
    """Stop the nested Hyprland the state records, if any, and forget it."""
    record = state.get("nested") if state else None
    if not record:
        return
    module = nested_hyprland()
    try:
        module.stop(record)
    except module.NestedError as error:
        raise ClientError(f"cannot stop the nested Hyprland: {error}") from None
    state["nested"] = None


def end_client(gamescope: subprocess.Popen | int | None, wine: Mapping[str, str], state: dict | None) -> None:
    """Log the character out, end the session's Wine processes, then stop the display they ran on.

    The display is gamescope or, during a Hyprland job, the nested Hyprland; the state keeps the session's link,
    headless addon and record, so the next launch reuses them.
    """
    token = state.get("token") if state else None
    require_owned_prefix(token)
    # Only a session in the world types /quit: at the character list Enter would enter the world instead.
    display_up = gamescope_running(gamescope, state) or nested_running(state)
    if state and state.get("ready") and display_up and client_pid():
        log_out(state)
    server = wineserver(wine)
    # Never use prefix-wide wineserver shutdown: another client can appear between ownership checks. Keep checking
    # and signal only exact token-owned PIDs, retaining state when a foreign or unverifiable process appears.
    deadline = time.monotonic() + 20
    empty_since = None
    while True:
        processes = prefix_snapshot()
        users = list(processes)
        owned, foreign = prefix_ownership(processes, token)
        if foreign:
            detail = ", ".join(map(str, foreign))
            raise ClientError("teardown refused: foreign or unowned Wine prefix processes: " + detail)
        now = time.monotonic()
        if owned:
            empty_since = None
            for pid in owned:
                kill_owned_pid(pid, token, server)
        elif empty_since is None:
            empty_since = now
        elif now - empty_since >= 1:
            break
        if now >= deadline:
            detail = ", ".join(map(str, users)) if users else "prefix did not remain empty"
            raise ClientError("teardown incomplete: Wine prefix processes survived: " + detail)
        time.sleep(0.25)
    # Do not trigger gamescope's child reaper while a shared Wine server could still serve another client.
    # Display processes do not inherit WINEPREFIX, so they remain alive until all Wine processes exit naturally.
    stop_gamescope(gamescope, state)
    stop_nested(state)


def teardown(
    gamescope: subprocess.Popen | int | None,
    wine: Mapping[str, str],
    link: Path | None,
    state: dict | None,
) -> None:
    release_session_modifiers(state)
    end_client(gamescope, wine, state)
    if link and link.is_symlink():
        link.unlink()
    if state and state.get("headless_addon"):
        generated = Path(state["headless_addon"])
        if generated.is_dir() and generated.parent == STATE_DIR:
            shutil.rmtree(generated)
    clear_leases((state or {}).get("end_reason", "session ended because teardown stopped the client"))
    for path in [STATE_DIR / HYPRLAND_REQUEST, STATE_DIR / HYPRLAND_END, *STATE_DIR.glob(f"{HYPRLAND_RESULT}-*.json")]:
        path.unlink(missing_ok=True)
    state_file().unlink(missing_ok=True)


def lock_holder() -> str:
    """The state of the session that holds the lock, for a waiter's message."""
    return state_file().read_text() if state_file().exists() else "{}"


def prefix_who(users: Sequence[int]) -> str:
    """Who is using the Wine prefix, for the sentence a caller prints when it refuses to start.

    A Wow.exe is the player's client only when it is one of the processes being refused over: a live headless
    session's own client runs beside the Wine processes a dead session left behind, and naming that the player's sends
    an agent to wait for a person who is not there (#652). A Wow.exe whose environment carries
    FOREVER_CLIENT_SESSION belongs to a headless session, which the sentence names by pid.
    """
    game = client_pid()
    if game is None:
        return f"{len(users)} Wine processes still run in it"
    if read_environ(game).get("FOREVER_CLIENT_SESSION"):
        return f"a headless session holds the client (Wow.exe, pid {game})"
    if game in users:
        return f"the player's client is running (Wow.exe, pid {game})"
    return f"{len(users)} Wine processes still run in it"


def wait_for_session(lock, timeout: float) -> None:
    """Wait until this process holds the session lock and no process uses the Wine prefix.

    The lock is taken first and held while the prefix empties, so another waiter cannot slip in between the two
    checks. The previous session's wineserver can outlive it for a moment, so the prefix is checked again until it
    is empty rather than once.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise ClientError(
                    f"another agent's session still holds the client after waiting {timeout:.0f} s: "
                    f"{lock_holder()}; pass a longer --timeout to queue"
                ) from None
            time.sleep(WAIT_POLL)
    while True:
        users = prefix_users()
        if not users:
            return
        if time.monotonic() >= deadline:
            raise ClientError(
                f"the Wine prefix {PREFIX} is still in use after waiting {timeout:.0f} s: {prefix_who(users)}. "
                "A second client would log the first one out, so no session starts; pass a longer --timeout to queue"
            )
        time.sleep(WAIT_POLL)


def at_character_select(state: dict, manual_launcher: bool) -> None:
    """Nudge the launch along, every 15 s until the world loads.

    Enter at the character list enters the world with the last character; before then it does nothing. It is sent
    only while the game's own window has focus: a Return on the focused Battle.net launcher presses Play again and
    starts a second client, which then ends on its own login form.
    """
    if client_pid():
        enter_world(state)
    elif not manual_launcher:
        press_play(state)


def pending_work(state: Mapping) -> str | None:
    """What still needs this session, or None: a queued ticket that is not the session's own end, or a usable lease
    on this session.

    A lease holder works between verbs (building a test addon, reading a screenshot), so no job ends in that time; the
    lease expires on its own, so a forgotten one costs at most LEASE_MAX.
    """
    try:
        if any(ordinary for ordinary, _path in live_tickets()):
            return "a request is queued"
        leases = list((STATE_DIR / "leases").glob("*.json"))
    except OSError:
        # The idle check must never end a healthy session on a state-directory fault; a queued job re-checks the
        # session under the job lock before teardown.
        return None
    identity = session_identity(state)
    for path in leases:
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if usable_lease(record, path.stem, identity):
            return "a lease is live"
    return None


def session_end_reason(
    now: float, started: float, ready: float, last_job: float, busy: str | None = None
) -> str | None:
    """Why the resident session should stop now, or None. Two fixed limits, checked in this order:

    - MAX_SESSION from the launch: the lifetime cap, whatever jobs arrive.
    - IDLE_LIMIT since the last job ended, or since READY when none has run yet: no job is coming. Not while
      `busy` names pending work (`pending_work`): a queued request or a live lease means a job is coming.

    `last_job` is never before `ready`: `last_job_mark` clamps it, because a mark an earlier session left says
    nothing about this one.
    """
    if now - started >= MAX_SESSION:
        return f"the {MAX_SESSION // 3600} h lifetime cap"
    if busy is None and now - last_job >= IDLE_LIMIT:
        return f"{IDLE_LIMIT // 60} min without a job"
    return None


def last_job_mark(ready: float) -> float:
    """When the last job ended on the monotonic clock, never before READY.

    The mark is a file's mtime, so it is converted from the wall clock; a mark an earlier session left is clamped to
    READY, and the idle limit starts from there.
    """
    try:
        ended = (STATE_DIR / LAST_JOB).stat().st_mtime
    except OSError:
        return ready
    return max(time.monotonic() - (time.time() - ended), ready)


def launcher_sources(paths: Iterable[Path] | None = None) -> dict[Path, str | None]:
    """Digest this launcher and loaded Python modules from its repository, excluding installed packages.

    Missing source counts as changed too, so removing a loaded module cannot leave its old code resident.
    """
    if paths is None:
        root = Path(__file__).resolve().parents[2]
        paths = {Path(__file__).resolve()}
        for module in tuple(sys.modules.values()):
            source = getattr(module, "__file__", None)
            if source:
                path = Path(source).resolve()
                if path.suffix == ".py" and path.is_relative_to(root) and "site-packages" not in path.parts:
                    paths.add(path)
    # Re-scan addon membership too: a new TOC-loaded file was not in the resident snapshot.
    paths = {*paths, *(path for path in ADDON.rglob("*") if path.is_file())}
    digests = {}
    for path in paths:
        try:
            digests[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            digests[path] = None
    return digests


def headless_addon_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(ADDON.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(ADDON)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


LAUNCHER_SOURCES = launcher_sources()


def serve(args: argparse.Namespace, after_ready=None) -> int:
    """The resident session: launch, wait for the world, stay up while jobs arrive, then log out and stop.

    IDLE_LIMIT after the last job ended (or READY), MAX_SESSION from launch, or changed launcher/imported repository
    source ends the session. It takes the job lock first, so a job in flight always finishes before teardown.
    `job` starts this detached when no session runs, and `up` is the same verb in the foreground. After a source
    change the next job starts a fresh process.
    """
    require_launcher_available(getattr(args, "manual_launcher", False))
    sources = LAUNCHER_SOURCES
    recover_links()
    mismatch = nvidia_mismatch()
    if mismatch:
        raise ClientError(mismatch)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / STOP).unlink(missing_ok=True)
    lock = open(STATE_DIR / "lock", "w")
    try:
        if args.wait:
            resident = current_session()
            if resident:
                latest = resident.get("started", time.time()) + MAX_SESSION
                ready = resident.get("ready", resident.get("started", time.time()))
                try:
                    ended = (STATE_DIR / LAST_JOB).stat().st_mtime
                except FileNotFoundError:
                    ended = ready
                idle = max(ready, ended) + IDLE_LIMIT
                holder = describe_job() if job_holder() else f"session pid {resident.get('pid')}"
                now = time.time()

                def deadline(end: float) -> str:
                    stamp = datetime.fromtimestamp(end, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                    return f"{stamp} ({max(0, (end - now) / 60):.0f} min remaining)"

                print(
                    f"forever_client: session holder {holder}; latest end {deadline(latest)}, "
                    f"idle end {deadline(idle)}; job/lease run inside the resident session "
                    "now without --wait",
                    file=sys.stderr,
                    flush=True,
                )
            wait_for_session(lock, args.timeout)
        else:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ClientError(
                    f"another agent's session holds the client: {lock_holder()}; pass --wait to queue"
                ) from None
            users = prefix_users()
            if users:
                raise ClientError(
                    f"the Wine prefix {PREFIX} is in use: {prefix_who(users)}. "
                    "A second client would log the first one out, so no session starts."
                )
        runtime = runtime_dir(os.environ, os.getuid())
        try:
            socket.create_connection(BATTLE_NET, timeout=10).close()
        except OSError as error:
            raise ClientError(
                f"cannot reach Battle.net at {BATTLE_NET[0]}:{BATTLE_NET[1]} ({error}): the launcher could not log in. "
                "A sandboxed shell has no network: run forever_client.py outside the sandbox."
            ) from None
        launch = read_launch_config()
        if "umu_run" not in launch:
            raise ClientError(
                f"{CONFIG} records an older Wine launch: start Battle.net from Faugus, "
                "then run `forever_client.py capture-env`"
            )
        character = character_config(launch)
        wine = launch["env"]
    except BaseException:
        # The session lock is held through these checks, so a refusal must not leave its descriptor open.
        lock.close()
        raise

    link = CLIENT / "Interface/AddOns" / ADDON.name
    session_addon: Path | None = None
    gamescope: subprocess.Popen | None = None
    state: dict | None = None
    job = None
    job_token = None

    def adopt(handle: subprocess.Popen) -> None:
        # Serve is the parent of every gamescope it starts, so teardown always stops it by this handle and reaps it,
        # including one a failed launch or a failed Hyprland return started.
        nonlocal gamescope
        gamescope = handle

    def on_signal(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGHUP, on_signal)
    log = open(STATE_DIR / "session.log", "w")
    try:
        session_addon = prepare_headless_addon(character)
        if not link.exists():
            link.symlink_to(session_addon)
        env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY", "WINEPREFIX")}
        env.update(wine)
        env["WINEPREFIX"] = str(PREFIX)
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        env["XDG_RUNTIME_DIR"] = str(runtime)
        token = uuid.uuid4().hex
        env["FOREVER_CLIENT_SESSION"] = token
        env = silenced(env)
        before = screenshots()
        started = time.time()
        launched = time.monotonic()
        # The session's ownership exists before its first child does, so an interrupt at the spawn has a token for
        # teardown rather than leaving unowned Wine processes and gamescope behind (#578).
        state = {
            "pid": os.getpid(),
            "start_ticks": process_start(os.getpid()),
            "boot_id": boot_id(),
            "gamescope": None,
            "gamescope_start": None,
            "token": token,
            "started": started,
            "runtime_dir": str(runtime),
            "manual_launcher": args.manual_launcher,
            "wine": {"PROTONPATH": wine["PROTONPATH"]} if wine.get("PROTONPATH") else {},
            "link": str(link),
            "headless_addon": str(session_addon),
            "headless_addon_digest": headless_addon_digest(),
        }
        write_state(state)
        gamescope = launch_gamescope(launch, env, log, state, adopt)
        reach_world(state, before, args.timeout, args.manual_launcher, started)
        ready = time.monotonic()
        if after_ready:
            return after_ready(state)
        last_world_check = ready
        while gamescope.poll() is None:
            request = hyprland_request()
            if request is not None:
                job, job_token = acquire_job(None, request["label"])
                # Recheck after waiting: a cancelled requester must not move the client.
                if hyprland_request() == request:
                    job_token = request["token"]
                    write_job_record(
                        {
                            "pid": os.getpid(),
                            "start_ticks": process_start(os.getpid()),
                            "token": job_token,
                            "label": request["label"],
                            "started": time.time(),
                        }
                    )
                    hyprland_job(request, gamescope, wine, env, launch, log, state, adopt)
                    ready = last_world_check = time.monotonic()
                release_job(job, job_token)
                job = job_token = None
                continue
            last_world_check, reason = resident_world_check(state, last_world_check)
            reason = reason or session_end_reason(
                time.monotonic(), launched, ready, last_job_mark(ready), pending_work(state)
            )
            if reason is None and launcher_sources(sources) != sources:
                reason = "launcher source changed"
            if reason is None and (STATE_DIR / STOP).exists():
                reason = "`down` asked"
            if reason is None:
                time.sleep(1)
                continue
            # A job is never cut off: take the job lock, then decide again with the job's own end recorded. A job
            # that just ended clears the idle reason, so the session stays up for the next one.
            if reason == "launcher source changed":
                state["reloading"] = True
                write_state(state)
            job, job_token = acquire_job(None, f"the session's end ({reason})", session_end=True)
            world = client_ui_after_load(state)["world"]
            if not world:
                state.pop("ready", None)
                state["world_lost"] = True
                write_state(state)
            if world and not state.get("ready"):
                state["ready"] = time.time()
                state.pop("world_lost", None)
                write_state(state)
            reason = ("the client left the world" if not world else None) or session_end_reason(
                time.monotonic(), launched, ready, last_job_mark(ready), pending_work(state)
            )
            if reason is None and launcher_sources(sources) != sources:
                reason = "launcher source changed"
            if reason is None and (STATE_DIR / STOP).exists():
                reason = "`down` asked"
            if reason is None:
                state.pop("reloading", None)
                write_state(state)
                release_job(job, job_token, ended=False)
                job = job_token = None
                continue
            state["end_reason"] = f"session ended because {reason}"
            print(f"forever_client: the session is ending: {reason}", flush=True)
            break
        else:
            raise ClientError("the client exited on its own")
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        if state is not None and not state.get("end_reason"):
            # Leases read why the session ended, not only that it did.
            state["end_reason"] = f"session ended because {error}"
            write_state(state)
        raise
    finally:
        for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(signum, signal.SIG_IGN)
        try:
            teardown(gamescope, wine, link, state)
        finally:
            # The job lock stays held through teardown, so no job starts against a client being stopped.
            if job is not None:
                release_job(job, job_token, ended=False)
            (STATE_DIR / STOP).unlink(missing_ok=True)
            if session_addon and session_addon.is_dir() and session_addon.parent == STATE_DIR:
                shutil.rmtree(session_addon)
            # Release the session lock before an exception reaches proof()/smoke(). Their error classifier probes
            # the lock to distinguish a foreign session, and a traceback retaining this frame must not see our own
            # failed startup as another owner (#573).
            log.close()
            lock.close()
        print("stopped: logged out, gamescope, Wine and the dev addon link are gone", flush=True)


# `up` is the same lifecycle in the foreground: the verb an agent already knows keeps working unchanged.
up = serve


def launch_gamescope(
    launch: Mapping, env: Mapping[str, str], log, state: dict, adopt: Callable[[subprocess.Popen], None]
) -> subprocess.Popen:
    """Start the client under headless gamescope and record the display it gives its child.

    `adopt` takes the handle before anything here can fail, so serve, its parent, stops and reaps it at teardown.
    """
    gamescope = subprocess.Popen(
        [
            "gamescope",
            "--backend",
            "headless",
            "-W",
            str(WIDTH),
            "-H",
            str(HEIGHT),
            "--",
            # Gamescope's reaper ends every process once its child exits, and Battle.net exits as the game
            # starts. umu-run's Proton `waitforexitandrun` returns only once the prefix's wineserver has, so the
            # child lasts the whole Wine session: the launcher, then the game.
            launch["umu_run"],
            str(LAUNCHER),
            *LAUNCH_ARGS,
        ],
        cwd=LAUNCHER.parent,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    adopt(gamescope)
    state["mode"] = "gamescope"
    state["gamescope"] = gamescope.pid
    state["gamescope_start"] = process_start(gamescope.pid)
    write_state(state)
    genv = child_env(state["token"])
    state.update(display=genv["DISPLAY"], gamescope_socket=genv["GAMESCOPE_WAYLAND_DISPLAY"])
    write_state(state)
    print(f"starting: display {state['display']}, log {STATE_DIR / 'session.log'}", flush=True)
    return gamescope


def reach_world(state: dict, before: set[Path], timeout: float, manual_launcher: bool, started: float, nudge=None):
    """Press the launcher on and wait for the headless addon's world screenshot, then mark the state READY."""
    nudge = nudge or functools.partial(at_character_select, state, manual_launcher)
    # MAX_PLAY_CLICKS bounds one launch. A Hyprland job launches twice more in the same session, and a count carried
    # over from an earlier launch refused the new launcher's first Play click as the limit already reached.
    for key in ("play_clicks", "last_play_click", "play_target_missing_reported"):
        state.pop(key, None)
    try:
        ready_shot = wait_for_world(before, timeout, nudge=nudge, require_marker=True, handshake_state=state)
    except SignInRequired:
        raise
    except ClientError as error:
        frame = shot(state, STATE_DIR / "failed.png")
        raise ClientError(f"{error}; last frame: {frame}") from None
    state["ready"] = time.time()
    write_state(state)
    (STATE_DIR / SIGN_IN_BLOCK).unlink(missing_ok=True)
    print(f"READY in the world after {time.time() - started:.0f} s ({ready_shot.name})", flush=True)
    # !!ForeverHeadless performs the character identity preflight before its ordinary readiness screenshot.
    # No eval or reload is needed here: wait_for_world only returns after that handshake succeeds.
    print("CHARACTER_PREFLIGHT passed", flush=True)


def down() -> int:
    """Stop the resident session once the job in flight, if any, has finished, or clean up after a dead owner.

    A live session is asked to stop: one in the world through the stop marker its resident loop reads between jobs, so
    the job in flight finishes first, and one still starting through its own SIGTERM teardown, bound to the start
    identity it recorded so a reused pid is never signalled. Once that process is gone it can no longer run its own
    teardown, so `down` does the same work itself: the token-owned Wine processes, gamescope from `state["gamescope"]`,
    the dev addon link and the state file (#578). A pid that no longer exists must not crash `down`.
    """
    token = os.environ.get("FOREVER_CLIENT_JOB")
    holder = job_holder()
    if token and holder and holder.get("token") == token:
        (STATE_DIR / STOP).touch()
        print("forever_client: the session stops when this job ends")
        return 0
    if token:
        live_lease(token)
    state = load_state()
    started = state.get("owner_start", state.get("start_ticks"))
    owner = {"pid": state.get("pid"), "started": started, "boot_id": state.get("boot_id")}
    limit = None
    if owner_alive(owner):
        if state.get("ready") and started is not None:
            # A session in the world reads the stop marker between jobs: the job in flight finishes first, then
            # teardown logs out (up to LOGOUT_WAIT), gives gamescope 20 s and ends Wine.
            (STATE_DIR / STOP).touch()
            limit = STOP_WAIT
        elif signal_pid(state["pid"], started, signal.SIGTERM):
            # A session still starting has no resident loop to read the marker: its own SIGTERM handler is the way
            # out. It never reached the world, so nothing is logged out.
            limit = LOGOUT_WAIT + 60
        elif owner_alive(owner):
            raise ClientError(f"cannot safely signal session {state['pid']}: session state retained")
    if limit is not None:
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            if not state_file().exists():
                (STATE_DIR / STOP).unlink(missing_ok=True)
                return 0
            if not owner_alive(owner):
                break
            time.sleep(0.5)
        if owner_alive(owner):
            raise ClientError(f"session {state['pid']} did not stop within {limit} s")
    # A new session may acquire the released lock before this fallback does. Serialize cleanup with it and re-read the
    # record under that lock, so this down cannot remove the next session's link or state.
    with open(STATE_DIR / "lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ClientError("another session holds the client: stale cleanup deferred") from None
        if not state_file().exists():
            (STATE_DIR / STOP).unlink(missing_ok=True)
            return 0
        if load_state() != state:
            raise ClientError("the headless session changed: stale cleanup deferred")
        recover_links()
        if state.get("boot_id") and boot_id() and state["boot_id"] != boot_id():
            clear_leases()
            state_file().unlink(missing_ok=True)
            return 0
        link = Path(state["link"]) if state.get("link") else CLIENT / "Interface/AddOns" / ADDON.name
        teardown(state.get("gamescope"), state.get("wine") or {}, link, state)
        state_file().unlink(missing_ok=True)
    return 0


def start_serve(manual_launcher: bool) -> subprocess.Popen:
    """Start the resident session detached, its lines in serve.log, and hand back the process to watch."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "FOREVER_CLIENT_JOB"}
    env["FOREVER_CLIENT_CALLER"] = os.environ.get("FOREVER_CLIENT_CALLER") or "job"
    log = open(STATE_DIR / SERVE_LOG, "a")
    command = [sys.executable, str(Path(__file__).resolve()), "serve"]
    if manual_launcher:
        command.append("--manual-launcher")
    print(f"starting a session: {STATE_DIR / SERVE_LOG}", file=sys.stderr, flush=True)
    try:
        return subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    finally:
        log.close()


def serve_tail() -> str:
    """The last line the session's own log wrote, for a start that failed."""
    try:
        lines = [line.strip() for line in (STATE_DIR / SERVE_LOG).read_text(errors="replace").splitlines()]
    except OSError:
        return "the session wrote no log"
    written = [line for line in lines if line]
    return written[-1] if written else "the session wrote no log"


def ensure_session(timeout: float, manual_launcher: bool = False) -> dict:
    """The running session's state, starting a detached `serve` when none runs and waiting for READY.

    A session another agent is starting is waited for, never started twice: the session lock is what decides. The
    session's own idle and lifetime limits cannot end it while a job holds the job lock, so a caller that has the job
    lock can rely on this answer until it releases.
    """
    deadline = time.monotonic() + timeout
    child = None
    while True:
        # A queued caller keeps its imported decoder while detached serve loads the current files. Do not
        # let an old caller repeatedly reject sessions launched from a newer protocol implementation.
        if launcher_sources(LAUNCHER_SOURCES) != LAUNCHER_SOURCES:
            raise ClientError("launcher source changed while this command was waiting; rerun the command")
        require_launcher_available(manual_launcher)
        state = current_session()
        if state and (state.get("ready") or state.get("world_lost")):
            addon_matches = state.get("headless_addon_digest") == headless_addon_digest()
            # Changed helper code needs replacement even if its pixel protocol version is unchanged.
            ui = client_ui_after_load(state) if addon_matches else {}
            if addon_matches and ui.get("safety") and ui["world"]:
                if not state.get("ready"):
                    state["ready"] = time.time()
                    state.pop("world_lost", None)
                    write_state(state)
                return state
            if child is not None:
                reason = (
                    "headless addon source changed during startup"
                    if not addon_matches
                    else "live safety protocol unavailable or outdated"
                    if not ui.get("safety")
                    else "the client left the world"
                )
                # This invocation just launched this session. Repeating that launch cannot repair a waiter
                # whose loaded decoder disagrees with the new addon, and used to bypass the timeout forever.
                raise ClientError(f"fresh session reached READY but cannot be used: {reason}; rerun the command")
            holder = job_holder()
            if (
                holder
                and holder.get("pid") != os.getpid()
                and not (
                    os.environ.get("FOREVER_CLIENT_JOB") and holder.get("token") == os.environ["FOREVER_CLIENT_JOB"]
                )
            ):
                raise ClientError("the client left the world while another job holds it")
            # The caller owns the job lock (or no job does). Clear ready so down uses the resident's
            # signal teardown, rather than waiting for that same job lock through the stop marker.
            state["end_reason"] = (
                "session ended because headless addon source changed"
                if not addon_matches
                else "session ended because the client left the world"
            )
            print(f"forever_client: {state['end_reason']}; restarting", file=sys.stderr, flush=True)
            guard = None
            if holder is None:
                guard = acquire_job(0, "replace a client outside the world")
            try:
                state.pop("ready", None)
                write_state(state)
                down()
            finally:
                if guard is not None:
                    release_job(*guard, ended=False)
            child = None
            continue
        if state is None and child is None and not session_lock_held():
            child = start_serve(manual_launcher)
        if child is not None and child.poll() is not None:
            # Our serve exited before READY. Another agent's serve may hold the lock now: wait for that one instead.
            if not session_lock_held():
                require_launcher_available(manual_launcher)
                raise ClientError(f"the headless session did not start: {serve_tail()}")
            child = None
        if time.monotonic() >= deadline:
            raise ClientError(f"the session did not reach READY within {timeout:.0f} s: {serve_tail()}")
        time.sleep(WAIT_POLL)


def job(args: argparse.Namespace) -> int:
    """Run a command as one job against the shared session, holding the job lock for exactly its length.

    It takes the job lock first, so the session cannot end between ensuring it and running the command, then starts
    or reuses the session. The command sees `FOREVER_CLIENT_JOB`, so a `forever_client.py` verb it runs proceeds
    without taking the lock again, and `FOREVER_CLIENT_DISPLAY`, the session's private display. The lock is released,
    and the job's end recorded, whatever the command returns.
    """
    command = [word for word in args.command if word != "--"]
    if not command:
        raise ClientError("job needs a command after --")
    maximum = getattr(args, "max", LEASE_TTL)
    if not 0 < maximum <= LEASE_MAX:
        raise ClientError(f"--max takes 1 to {LEASE_MAX} s")
    if getattr(args, "hyprland", False):
        return request_hyprland_job(args, command, maximum)
    label = (args.label or Path(command[0]).name)[:80]
    handle, token = acquire_job(args.timeout, label)
    try:
        state = ensure_session(args.timeout, args.manual_launcher)
        require_safe(state)
        recover_links(job_locked=True)
        env = {
            **os.environ,
            "XDG_RUNTIME_DIR": state["runtime_dir"],
            "FOREVER_CLIENT_DISPLAY": state["display"],
            "FOREVER_CLIENT_JOB": token,
            "FOREVER_CLIENT_CALLER": os.environ.get("FOREVER_CLIENT_CALLER") or "job",
        }
        code = None
        try:
            code = run_job_command(command, env, maximum)
        finally:
            parked = park_after_job(state)
        # A job whose own command passed still fails when it left the character unparked.
        return code if code or parked else PARK_FAILED_CODE
    finally:
        release_job(handle, token)


def run_job_command(command, env, maximum, check=None) -> int:
    process = subprocess.Popen(command, env=env, start_new_session=True)
    try:
        if check is None:
            return process.wait(timeout=maximum)
        deadline = time.monotonic() + maximum
        while True:
            check()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, maximum)
            try:
                return process.wait(timeout=min(0.2, remaining))
            except subprocess.TimeoutExpired:
                continue
    except subprocess.TimeoutExpired:
        raise ClientError(f"job exceeded its {maximum:g} s limit") from None
    finally:
        # End the whole group, including children left behind by an exited command.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        grace_end = time.monotonic() + 2
        while True:
            process.poll()  # Reap the leader so it does not keep an otherwise empty group alive.
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                break
            remaining = grace_end - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.05, remaining))
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        # Whatever ended the command, including a SIGKILL that skipped a verb's own release, no modifier stays held.
        release_session_modifiers({"display": env.get("FOREVER_CLIENT_DISPLAY")})


def read_hyprland_json(name: str) -> dict | None:
    try:
        value = json.loads((STATE_DIR / name).read_text())
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def hyprland_request() -> dict | None:
    request = read_hyprland_json(HYPRLAND_REQUEST)
    if request and owner_alive({"pid": request.get("pid"), "started": request.get("start_ticks")}):
        return request
    return None


def hyprland_cancelled(request: Mapping) -> bool:
    try:
        ended = (STATE_DIR / HYPRLAND_END).read_text() == request["token"]
    except OSError:
        ended = False
    return ended or not owner_alive({"pid": request.get("pid"), "started": request.get("start_ticks")})


def request_hyprland_job(args: argparse.Namespace, command: list[str], maximum: float) -> int:
    """Queue one command for serve, then wait through the return to gamescope, including on cancellation."""
    module = nested_hyprland()
    try:
        parent = module.user_instance()
    except module.NestedError as error:
        raise ClientError(str(error)) from None
    previous = stop_handlers()
    token = None
    submitted = False
    completed = False
    try:
        handle, token = acquire_job(args.timeout, args.label or "Hyprland job")
        try:
            require_safe(ensure_session(args.timeout, args.manual_launcher))
            if hyprland_request():
                raise ClientError("another Hyprland job is waiting for serve")
            request = {
                "token": token,
                "pid": os.getpid(),
                "start_ticks": process_start(os.getpid()),
                "label": (args.label or Path(command[0]).name)[:80],
                "command": command,
                "maximum": maximum,
                "parent": parent,
            }
            atomic_write(STATE_DIR / HYPRLAND_REQUEST, json.dumps(request))
            submitted = True
        finally:
            release_job(handle, token, ended=False)
        queue_deadline = time.monotonic() + args.timeout
        deadline = None
        cancelled = False
        while True:
            try:
                # Read the session before the result: serve writes the result before its teardown ends the session.
                session_gone = current_session() is None
                result = read_hyprland_json(f"{HYPRLAND_RESULT}-{token}.json")
                if result and result.get("token") == token:
                    completed = True
                    (STATE_DIR / f"{HYPRLAND_RESULT}-{token}.json").unlink(missing_ok=True)
                    if result.get("error"):
                        raise ClientError(result["error"])
                    return 130 if cancelled else result["code"]
                if session_gone:
                    raise ClientError("the Hyprland job session ended; the next job starts fresh gamescope")
                now = time.monotonic()
                if deadline is None:
                    holder = job_holder()
                    if holder and holder.get("token") == token:
                        deadline = now + HYPRLAND_WORLD_WAIT + maximum + HYPRLAND_RETURN_WAIT + 60
                    elif now >= queue_deadline:
                        raise ClientError("serve did not take the Hyprland job within --timeout")
                if deadline is not None and now >= deadline:
                    raise ClientError("the Hyprland job did not finish within its bounded transition waits")
                time.sleep(JOB_POLL)
            except KeyboardInterrupt:
                cancelled = True
                atomic_write(STATE_DIR / HYPRLAND_END, token)
    finally:
        if submitted and not completed:
            atomic_write(STATE_DIR / HYPRLAND_END, token)
        restore_handlers(previous)


def hyprland_job(
    request: Mapping,
    gamescope,
    wine: Mapping,
    env: Mapping,
    launch: Mapping,
    log,
    state: dict,
    adopt: Callable[[subprocess.Popen], None],
) -> None:
    """Serve owns the lock throughout both relaunches and the bounded command.

    The command's --max excludes the transitions: each world wait is at most 600 seconds, and the return has
    a 900-second caller allowance covering logout, owned-process teardown and compositor shutdown as well.
    The result always reaches the requester, with the job's own error and any return error. A failed return still
    propagates to serve's full teardown rather than publishing a reusable broken session, and the relaunched
    gamescope is already serve's through `adopt`, so that teardown stops and reaps it.
    """
    (STATE_DIR / HYPRLAND_REQUEST).unlink(missing_ok=True)
    module = nested_hyprland()
    result: dict = {"token": request["token"], "code": 1}
    errors: list[str] = []
    client = None

    def check() -> None:
        if hyprland_cancelled(request):
            raise ClientError("the Hyprland job was cancelled")
        if state.get("nested") and (not module.running(state["nested"]) or (client and client.poll() is not None)):
            raise ClientError("the client or nested Hyprland exited during the job")

    def nudge() -> None:
        check()
        at_character_select(state, False)

    try:
        try:
            end_client(gamescope, wine, state)
            for key in ("gamescope", "gamescope_start", "gamescope_socket", "display", "ready"):
                state[key] = None
            state["mode"] = "hyprland"
            write_state(state)
            check()
            state["nested"] = module.start(request["parent"], STATE_DIR / "nested", WIDTH, HEIGHT)
            nested = state["nested"]
            state.update(display=nested["display"], origin=nested["origin"])
            write_state(state)
            before = screenshots()
            client = subprocess.Popen(
                [launch["umu_run"], str(LAUNCHER), *LAUNCH_ARGS],
                cwd=LAUNCHER.parent,
                env={**env, "DISPLAY": nested["display"]},
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            reach_world(state, before, HYPRLAND_WORLD_WAIT, False, time.time(), nudge=nudge)
            state["window"] = module.window(nested, GAME_WINDOW)
            if not state["window"]:
                raise ClientError("the nested Hyprland has no client window")
            write_state(state)
            recover_links(job_locked=True)
            command_env = {
                **read_environ(request["pid"]),
                "FOREVER_CLIENT_JOB": request["token"],
                "FOREVER_CLIENT_DISPLAY": nested["display"],
                "DISPLAY": nested["display"],
                "XDG_RUNTIME_DIR": state["runtime_dir"],
                "WAYLAND_DISPLAY": nested["wayland"],
                "HYPRLAND_INSTANCE_SIGNATURE": nested["signature"],
                "FOREVER_CLIENT_WINDOW": state["window"]["address"],
            }
            result["code"] = run_job_command(request["command"], command_env, request["maximum"], check)
            # The restored session reopens where this one ends, so a job that moved the character parks it first.
            if not park_after_job(state) and not result["code"]:
                result["code"] = PARK_FAILED_CODE
        except (ClientError, module.NestedError, subprocess.SubprocessError, OSError) as error:
            errors.append(f"job: {error}")
            print(f"forever_client: the Hyprland job failed: {error}", flush=True)
        try:
            end_client(None if state.get("mode") == "hyprland" else gamescope, wine, state)
            if client is not None:
                try:
                    client.wait(30)
                except subprocess.TimeoutExpired:
                    raise ClientError(f"umu-run {client.pid} outlived the Wine session") from None
            for key in ("display", "origin", "window", "ready"):
                state.pop(key, None)
            write_state(state)
            before = screenshots()
            launch_gamescope(launch, env, log, state, adopt)
            reach_world(state, before, HYPRLAND_WORLD_WAIT, bool(state.get("manual_launcher")), time.time())
        except Exception as error:
            errors.append(f"return to gamescope: {error}")
            print(f"forever_client: the return to gamescope failed: {error}", flush=True)
            raise
    except KeyboardInterrupt:
        errors.append("serve was interrupted during the Hyprland job")
        raise
    finally:
        if errors:
            result["error"] = "; ".join(errors)
        atomic_write(STATE_DIR / f"{HYPRLAND_RESULT}-{request['token']}.json", json.dumps(result))
        end = STATE_DIR / HYPRLAND_END
        if end.exists() and end.read_text() == request["token"]:
            end.unlink(missing_ok=True)


def lease_path(token: str) -> Path:
    if not token or Path(token).name != token or token in (".", ".."):
        raise ClientError("lease expired: run lease again")
    return STATE_DIR / "leases" / f"{token}.json"


def session_identity(state: Mapping) -> dict:
    return {key: state.get(key) for key in ("pid", "started", "start_ticks", "boot_id")}


def live_lease(token: str) -> dict:
    try:
        record = json.loads(lease_path(token).read_text())
    except (OSError, ValueError):
        raise ClientError("lease ended: unknown token, run lease again") from None
    if not isinstance(record, dict):
        raise ClientError("lease ended: unreadable record, run lease again")
    if record.get("ended"):
        raise ClientError(f"lease ended: {record['ended']}")
    if not unexpired_lease(record, token):
        raise ClientError("lease expired: run lease again")
    if record.get("session") != session_identity(current_session() or {}):
        raise ClientError("lease ended: session replaced or stopped, run lease again")
    return record


def unexpired_lease(record: Mapping, token: str) -> bool:
    expires = record.get("expires")
    return (
        record.get("token") == token
        and isinstance(expires, (int, float))
        and not isinstance(expires, bool)
        and time.time() < expires <= time.time() + LEASE_MAX
    )


def usable_lease(record: object, token: str, identity: Mapping) -> bool:
    """The checks `live_lease` makes, without raising: the idle limit waits only on a lease a caller could use."""
    return (
        isinstance(record, dict)
        and not record.get("ended")
        and unexpired_lease(record, token)
        and record.get("session") == identity
    )


def clear_leases(reason: str = "session ended because teardown stopped the client") -> None:
    directory = STATE_DIR / "leases"
    if directory.exists():
        for path in directory.glob("*.json"):
            try:
                record = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if isinstance(record, dict) and not record.get("ended"):
                record["ended"] = reason
                atomic_write(path, json.dumps(record))


def lease(args: argparse.Namespace) -> int:
    """Ensure the shared session and print a lease token; each verb takes its own job lock."""
    if not 0 < args.ttl <= LEASE_MAX:
        raise ClientError(f"--ttl takes 1 to {LEASE_MAX} s")
    label = (args.label or "a lease")[:80]
    handle, token = acquire_job(args.timeout, label)
    try:
        state = ensure_session(args.timeout, args.manual_launcher)
        require_safe(state)
        path = lease_path(token)
        path.parent.mkdir(parents=True, exist_ok=True)
        started = time.time()
        for old in path.parent.glob("*.json"):
            try:
                record = json.loads(old.read_text())
            except (OSError, ValueError):
                continue
            expires = record.get("expires") if isinstance(record, dict) else None
            if isinstance(expires, (int, float)) and expires <= started:
                old.unlink(missing_ok=True)
        atomic_write(
            path,
            json.dumps(
                {
                    "token": token,
                    "label": label,
                    "started": started,
                    "expires": started + args.ttl,
                    "session": session_identity(state),
                }
            ),
        )
    finally:
        release_job(handle, token)
    print(token, flush=True)
    return 0


def release(token: str) -> int:
    """End a lease, retaining the reason for its next caller, without stopping the session."""
    try:
        path = lease_path(token)
        record = json.loads(path.read_text())
        record["ended"] = "released by caller"
        atomic_write(path, json.dumps(record))
    except FileNotFoundError:
        raise ClientError("unknown lease token") from None
    return 0


def wineserver(wine: Mapping[str, str]) -> Path:
    """The Proton runner's wineserver, which serves every Wine process of a session it started."""
    return (Path(wine.get("PROTONPATH", "")) / "files/bin/wineserver").resolve()


def umu_launch() -> tuple[int, str] | None:
    """The running `umu-run` that started Battle.net in the prefix, and its script, or None."""
    for pid in pids():
        try:
            argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        words = [w.decode(errors="replace") for w in argv if w]
        script = next((w for w in words[:2] if Path(w).name == "umu-run"), None)
        if script and any(w.endswith("Battle.net.exe") for w in words) and in_prefix(read_environ(pid)):
            return pid, script
    return None


def capture_env() -> int:
    found = umu_launch()
    if not found:
        raise ClientError("Battle.net is not running from Faugus: start it there once, then run capture-env")
    pid, script = found
    env = wine_env(read_environ(pid))
    if "PROTONPATH" not in env:
        raise ClientError(f"process {pid} has no PROTONPATH; is it Faugus's umu-run launch?")
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(CONFIG, json.dumps({"umu_run": script, "env": env}, indent=1, sort_keys=True))
    print(f"recorded {script} and {len(env)} variables from {pid} to {CONFIG}")
    return 0


def saved_variables(addon: str) -> list[Path]:
    account = CLIENT / "WTF/Account"
    return sorted(account.glob(f"*/SavedVariables/{addon}.lua")) + sorted(
        account.glob(f"*/*/*/SavedVariables/{addon}.lua")
    )


def load_tool(name: str, path: Path):
    """A sibling Python tool, loaded once by path so one process shares it across calls."""
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ClientError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def devsmoke_eval():
    """tools/devsmoke/eval.py: the snippet compiler and Inbox writer the `eval` verb runs."""
    return load_tool("devsmoke_eval", Path(__file__).resolve().parents[1] / "devsmoke/eval.py")


def clear_eval_inbox(*, quiet: bool = False) -> None:
    """Remove !!DevSmoke's generated inbox so a later login has no snippet left to run (#589).

    A session that asks for a snippet clears the inbox when it ends, and a proof or smoke clears one before its own
    login so an earlier session's snippet cannot open a window over its screenshots.
    """
    tool = devsmoke_eval()
    try:
        tool.clear_inbox(addons=CLIENT / "Interface/AddOns")
    except tool.EvalError as error:
        if quiet:
            print(f"forever_client: could not clear the eval inbox: {error}", file=sys.stderr)
            return
        raise ClientError(str(error)) from None


class EvalMismatch(ClientError):
    """DevSmokeDB.eval on disk holds another run's record; `seen` is that run's token."""

    def __init__(self, seen: object, message: str):
        super().__init__(message)
        self.seen = seen


def saved_eval(token: str | None = None) -> dict:
    """DevSmokeDB.eval from the newest SavedVariables file the client wrote for !!DevSmoke.

    Given a run token, only the record that token wrote answers: SavedVariables reach disk at the next reload or
    logout, so the file can still hold the eval before this run's, and a reader without the token would report another
    snippet's result as this one's (#580).
    """
    files = saved_variables("!!DevSmoke")
    if not files:
        raise ClientError("no SavedVariables for !!DevSmoke: the client writes them at a reload or logout")
    lua = load_tool("forever_errors", Path(__file__).resolve().parents[1] / "forever_errors.py")
    seen = None
    for path in sorted(files, key=lambda candidate: candidate.stat().st_mtime, reverse=True):
        try:
            variables = lua.load_lua(path)
        except (OSError, lua.LuaSyntaxError) as error:
            raise ClientError(f"could not read {path}: {error}") from None
        smoke = variables.get("DevSmokeDB")
        data = smoke.get("eval") if isinstance(smoke, dict) else None
        if not isinstance(data, dict):
            continue
        if token is None or data.get("run") == token:
            return data
        if seen is None:
            seen = data
    if seen is None:
        raise ClientError("DevSmokeDB.eval is missing: the snippet did not run (is !!DevSmoke linked and loaded?)")
    raise EvalMismatch(
        seen.get("run"),
        f"DevSmokeDB.eval holds the run {_text(seen.get('run'))!r}, not this snippet's {token!r}: the snippet's own "
        "result was not saved (did the inbox load, and is !!DevSmoke linked and loaded?)",
    )


def _text(value) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _ordered(table) -> list:
    """A parsed Lua table's values, numeric keys in their own order, the way the client wrote them."""
    if not isinstance(table, dict):
        return []
    keys = list(table)
    if all(isinstance(key, int) for key in keys):
        keys.sort()
    return [table[key] for key in keys]


def format_eval(data: Mapping) -> tuple[str, bool]:
    """DevSmokeDB.eval as the lines the Agent tab showed, and whether the snippet succeeded."""
    ok = data.get("ok") is True
    lines = [f"DevSmokeDB.eval: {'ok' if ok else 'failed'}, ran {_text(data.get('ran'))}"]
    lines.extend(_text(value) for value in _ordered(data.get("out")))
    error = _text(data.get("err"))
    if error:
        lines.append("error:")
        lines.extend(error.splitlines())
    return "\n".join(lines), ok


def eval_files(state: Mapping, files: Sequence[Path]) -> int:
    """Run each snippet through !!DevSmoke at a login of its own and print each one's own result; 1 when any failed.

    A snippet's result reaches disk at the reload after its own (#580). The next snippet's reload is that save, so N
    snippets take N + 1 reloads instead of 2N. Clearing the inbox after each run keeps a later reload from running a
    snippet twice (#588), and an eval is not a proof flow, so it schedules no ready screenshot (#588).
    """
    tool = devsmoke_eval()
    failed = False
    missing: list[str] = []
    cleared = True
    unread: tuple[Path, str] | None = None

    def report(path: Path, token: str) -> None:
        nonlocal failed
        try:
            text, ok = format_eval(saved_eval(token))
        except SafetyRefusal:
            raise
        except ClientError as error:
            # A result missing from disk is named against its file, and the files after it still run; the eval then
            # ends as a client error, since nothing says whether that snippet passed.
            missing.append(f"{path}: {error}")
            return
        print(f"== {path}\n{text}" if len(files) > 1 else text, flush=True)
        failed = failed or not ok

    try:
        for path in files:
            cleared = False
            try:
                written = tool.write_snippet(path, addons=CLIENT / "Interface/AddOns", capture=False)
            except tool.EvalError as error:
                if unread:
                    # The earlier snippet has run: save and print its result before reporting this one's refusal.
                    clear_eval_inbox(quiet=True)
                    cleared = True
                    reload(state)
                    report(*unread)
                raise ClientError(str(error)) from None
            print(f"wrote {written['chunk']} from {written['snippet']} ({written['lines']} lines)", flush=True)
            reload(state)
            clear_eval_inbox()
            cleared = True
            if unread:
                report(*unread)
            unread = (path, written["token"])
        if unread:
            if not saved_within(unread[1], EVAL_SAVE_WAIT):
                reload(state)
            report(*unread)
    finally:
        if not cleared:
            clear_eval_inbox(quiet=True)
    if missing:
        raise ClientError("; ".join(missing))
    return 1 if failed else 0


JOB_VERBS = {
    "shot",
    "click",
    "hover",
    "drag",
    "scroll",
    "key",
    "slash",
    "reload",
    "eval",
    "errors",
    "face",
    "walkto",
    "park",
    "where",
}


def launcher_verb(state: Mapping, verb: str, button: str | None = None) -> bool:
    """A `shot` or button-1 `click` on the launcher of a manual session that is not in the world yet.

    `--manual-launcher` (needed while launcher OCR misses Play, cjber/forever-core#547) leaves clicking Play to the
    agent, from calls of its own, while the `job`, `lease`, `smoke` or `proof` that started the session holds the job
    lock waiting for READY. Those two verbs therefore run without that lock, or they would queue behind the job they
    are unblocking; every other verb still waits for it and is then refused before READY.
    """
    return (
        bool(state.get("manual_launcher"))
        and not state.get("ready")
        and (verb == "shot" or (verb == "click" and button == "1"))
    )


def input_verb(state: Mapping, args: argparse.Namespace) -> int:
    """One verb that touches the client, run inside the job that holds it."""
    global dead_ok
    dead_ok = args.verb in DEAD_OK_VERBS
    try:
        return run_input_verb(state, args)
    finally:
        dead_ok = False


def run_input_verb(state: Mapping, args: argparse.Namespace) -> int:
    if not state.get("ready") and not launcher_verb(state, args.verb, getattr(args, "button", None)):
        raise ClientError("the session is not in the world yet: wait for `up` to print READY")
    if args.verb != "shot" and state.get("ready"):
        require_safe(state)
    if args.verb == "shot":
        print(shot(state, args.path or STATE_DIR / f"shot-{int(time.time())}.png"))
    elif args.verb == "click":
        click(state, args.x, args.y, args.button, args.hold)
    elif args.verb == "hover":
        hover(state, args.x, args.y, args.hold)
    elif args.verb == "scroll":
        scroll(state, args.x, args.y, args.ticks, args.hold)
    elif args.verb == "drag":
        drag(state, args.x1, args.y1, args.x2, args.y2, args.button, args.steps, args.hold)
    elif args.verb == "key":
        if args.action and args.keys:
            raise ClientError("key takes key names or --action, not both")
        if not args.action and not args.keys:
            raise ClientError("key needs a key name or --action")
        if args.action:
            press_actions(state, args.action, args.hold_for)
        else:
            press(state, args.keys, args.hold_for)
    elif args.verb == "slash":
        slash(state, args.command)
    elif args.verb in ("face", "walkto"):
        if args.x == "target":
            motion = face_target(state) if args.verb == "face" else walkto_target(state)
        elif args.x == "corpse":
            here = read_motion(state)
            if not here["corpse"]:
                raise ClientError(f"{args.verb} corpse: the client shows no corpse on this map")
            point = here["corpse_x"], here["corpse_y"]
            motion = face(state, heading_to(here, *point)[0]) if args.verb == "face" else walkto(state, *point)
        else:
            if args.y is None:
                raise ClientError(f"{args.verb} takes X Y or `target`")
            try:
                x = float(args.x)
            except ValueError:
                raise ClientError(
                    f"{args.verb} takes map coordinates 0 to 100 or `target`: refused {args.x!r}"
                ) from None
            x, y = map_point(x), map_point(args.y)
            if args.verb == "face":
                motion = face(state, heading_to(read_motion(state), x, y)[0])
            else:
                motion = walkto(state, x, y, args.map_id, args.tolerance)
        print(describe_motion(motion))
    elif args.verb == "where":
        print(describe_motion(read_motion(state)))
    elif args.verb == "park":
        if args.add:
            print(f"park spot {park_add(state, args.add)}")
        else:
            print(f"parked at {park(state)['label']}")
    elif args.verb == "reload":
        print(f"reloaded ({reload(state).name})")
    elif args.verb == "eval" and args.live:
        if len(args.file) != 1:
            raise ClientError("eval --live runs one file")
        return live_eval(state, args.file[0])
    elif args.verb == "eval":
        return eval_files(state, args.file)
    elif args.verb == "errors":
        # A shared session's log holds every job's lines: read from where this job's own work started.
        completed = errors({**state, "started": job_started()}, args.addon)
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        return completed.returncode
    return 0


ENROL_GUID = "PENDING"


def pending_enrollment_character(launch: Mapping) -> dict[str, str]:
    character = character_config(launch)
    if character["guid"] != ENROL_GUID:
        raise ClientError(f"{CONFIG} character.guid is already set: enroll only fills a guid of {ENROL_GUID!r}")
    return character


def enroll(args) -> int:
    """Record the approved character's GUID in the launch config, for a name the owner approved with guid PENDING.

    The headless addon checks only the name for such a character, shows `UnitGUID("player")` large and refuses
    readiness, so the session ends without any job running on it. The GUID is read from that last frame; a misread
    cannot admit another character, since every later session needs this exact name and GUID (forever-core#978).
    """
    character = pending_enrollment_character(read_launch_config())
    frame = STATE_DIR / "failed.png"
    frame.unlink(missing_ok=True)
    try:
        up(args)
    except SignInRequired:
        raise
    except ClientError:
        if not frame.exists():
            raise
    words = " ".join(word[0] for word in ocr_words(frame, psm=11)) if frame.exists() else ""
    found = sorted(set(re.findall(r"Player-\d+-[0-9A-F]{8}", words)))
    if len(found) != 1:
        raise ClientError(f"read {len(found)} GUIDs for {character['name']} from {frame}: {found}")
    launch = read_launch_config()
    current_character = pending_enrollment_character(launch)
    if current_character["name"] != character["name"]:
        raise ClientError(f"{CONFIG} character.name changed during enrolment")
    launch["character"]["guid"] = found[0]
    atomic_write(CONFIG, json.dumps(launch, indent=2) + "\n")
    print(f"forever_client: {character['name']} enrolled as {found[0]} in {CONFIG}; the next up verifies it")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    words = list(sys.argv[1:] if argv is None else argv)
    if words[:1] == ["release-held"] and len(words) == 4:
        # The held-key watchdog a hold starts; it needs no session, lock or safety check, only the display.
        return release_held(words[1], float(words[2]), words[3])
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    for name in ("up", "serve"):
        p = sub.add_parser(name)
        p.add_argument("--wait", action="store_true", help="queue behind another agent's session")
        p.add_argument(
            "--manual-launcher",
            action="store_true",
            help="disable launcher OCR clicks; allow shot and fresh-screenshot left clicks before READY",
        )
        p.add_argument(
            "--timeout",
            type=float,
            default=600,
            help="seconds to wait behind another session and to reach the world",
        )
    for name in ("job", "run"):
        p = sub.add_parser(name, help="run a command as one job in the shared session")
        p.add_argument("--label", default=None, help="what a waiter is told this job is")
        p.add_argument(
            "--wait",
            action="store_true",
            help=argparse.SUPPRESS,
        )
        p.add_argument(
            "--manual-launcher",
            action="store_true",
            help="disable launcher OCR clicks; allow shot and fresh-screenshot left clicks before READY",
        )
        p.add_argument(
            "--timeout",
            type=float,
            default=1800,
            help="seconds to reach the world and to wait for the job in flight",
        )
        p.add_argument("--hyprland", action="store_true", help="run in a private nested Hyprland for deskpilot")
        p.add_argument("--max", type=float, default=LEASE_TTL, help=f"command limit in seconds, at most {LEASE_MAX}")
        p.add_argument("command", nargs=argparse.REMAINDER)
    p = sub.add_parser("lease", help="ensure the session and print a per-command lease token")
    p.add_argument("--ttl", type=float, default=LEASE_TTL, help=f"seconds the token is valid, at most {LEASE_MAX}")
    p.add_argument("--label", default=None, help="what a waiter is told this lease is")
    p.add_argument(
        "--manual-launcher",
        action="store_true",
        help="disable launcher OCR clicks; allow shot and fresh-screenshot left clicks before READY",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=1800,
        help="seconds to reach the world and to wait for the job in flight",
    )
    p = sub.add_parser("release", help="end a lease now")
    p.add_argument("token")
    sub.add_parser("down")
    p = sub.add_parser("enroll", help="record a newly approved character's GUID (guid PENDING in the launch config)")
    p.add_argument("--wait", action="store_true", help="queue behind another agent's session")
    p.add_argument("--manual-launcher", action="store_true", help="disable launcher OCR clicks")
    p.add_argument("--timeout", type=float, default=600, help="seconds to reach the world")
    sub.add_parser("status")
    sub.add_parser("capture-env")
    for name in (
        "reload",
        "shot",
        "click",
        "hover",
        "drag",
        "scroll",
        "key",
        "slash",
        "eval",
        "errors",
        "face",
        "walkto",
        "park",
        "where",
    ):
        p = sub.add_parser(name)
        p.add_argument("--timeout", type=float, default=600, help="seconds to wait for the job in flight")
        if name in ("click", "hover", "drag", "scroll"):
            p.add_argument(
                "--hold",
                action="append",
                default=[],
                choices=tuple(MODIFIER_KEYS),
                help="a modifier to hold down through the action and release after it; repeat for more than one",
            )
        if name == "shot":
            p.add_argument("path", nargs="?", type=Path)
        elif name == "click":
            p.add_argument("x", type=int)
            p.add_argument("y", type=int)
            p.add_argument("--button", default="1", choices=("1", "3"))
        elif name == "hover":
            p.add_argument("x", type=int)
            p.add_argument("y", type=int)
        elif name == "drag":
            for coord in ("x1", "y1", "x2", "y2"):
                p.add_argument(coord, type=int)
            p.add_argument("--button", default="1", choices=("1", "3"))
            p.add_argument(
                "--steps",
                type=int,
                default=DRAG_STEPS,
                help=f"moves between press and release, 1 to {DRAG_STEPS_MAX}",
            )
        elif name == "scroll":
            p.add_argument("x", type=int)
            p.add_argument("y", type=int)
            p.add_argument("ticks", type=int, help="wheel-up ticks (zoom in) when positive, wheel-down when negative")
        elif name == "key":
            p.add_argument("keys", nargs="*", help="xdotool key names; for movement use --action instead")
            p.add_argument(
                "--action",
                action="append",
                default=[],
                choices=ACTIONS,
                help="a game action, pressed by the key this client binds to it; repeat for more than one",
            )
            p.add_argument(
                "--for",
                dest="hold_for",
                type=float,
                metavar="SECONDS",
                help="hold the keys down together for this long instead of tapping them: walk with w, turn with a or d",
            )
        elif name == "slash":
            p.add_argument("command")
        elif name in ("face", "walkto"):
            p.add_argument("x", help="map x as the map shows it, 0 to 100, `target`, or `corpse` for a ghost's corpse")
            p.add_argument("y", nargs="?", type=float, help="map y, 0 to 100")
            if name == "walkto":
                p.add_argument("--map", type=int, dest="map_id", help="the map the point is on; refused on another")
                p.add_argument("--tolerance", type=float, default=WALK_TOLERANCE, help="yards from the point")
        elif name == "park":
            p.add_argument("--add", metavar="LABEL", help="record where the player stands as a park spot")
        elif name == "eval":
            p.add_argument(
                "file", type=Path, nargs="+", help="Lua snippets to run through !!DevSmoke, each at a reload of its own"
            )
            p.add_argument(
                "--live",
                action="store_true",
                help="run it in the running session with no reload, so globals and open panels stay",
            )
        elif name == "errors":
            p.add_argument("--addon")
    p = sub.add_parser("sv")
    p.add_argument("addon")
    p = sub.add_parser("build-dev", help="write test-artifacts/<repo>-dev from a ref")
    p.add_argument("repo", help="the repository under ~/drive/proj/wow")
    p.add_argument("ref")
    p.add_argument(
        "--core-ref",
        help="embed this forever-core commit instead of the pinned release, to test a core candidate in the addon",
    )
    p = sub.add_parser("smoke", help="build the commit a release would ship, test it, and post its status")
    p.add_argument("--repo", required=True, help="the repository under ~/drive/proj/wow, such as legacy-forever")
    p.add_argument("--ref", required=True, help="the commit the next release would ship")
    p.add_argument(
        "--timeout",
        type=float,
        default=1800,
        help="seconds to reach the world and to wait for the job in flight",
    )
    p.add_argument(
        "--manual-launcher",
        action="store_true",
        help="disable launcher OCR clicks; allow shot and fresh-screenshot left clicks before READY",
    )
    p.add_argument(
        "--no-post",
        action="store_true",
        help="run the whole smoke and print its result without posting the headless-smoke commit status",
    )
    p = sub.add_parser("attest", help="write .visual-proof.json from the user's checklist pass (no client)")
    p.add_argument("--repo", required=True, help="the repository under ~/drive/proj/wow, such as legacy-forever")
    p.add_argument("--ref", required=True, help="the commit the user tested")
    p.add_argument("--checkout", required=True, type=Path, help="the checkout of that commit the proof is written to")
    p.add_argument("--round", help="the checklist round (default: the newest round covering the build)")
    p.add_argument(
        "--shot", action="append", default=[], help="a client screenshot to add to the evidence; repeat for each"
    )
    p = sub.add_parser("proof", help="record a commit's .visual-proof.json from a client session")
    p.add_argument("--repo", required=True, help="the repository under ~/drive/proj/wow, such as legacy-forever")
    p.add_argument("--ref", required=True, help="the commit the proof is for")
    p.add_argument("--checkout", required=True, type=Path, help="the checkout of that commit the proof is written to")
    p.add_argument(
        "--flow",
        action="append",
        default=[],
        metavar="NAME=SLASH_OR_LUA_FILE",
        help="one flow to capture: a Forever addon slash command, or a Lua file run through !!DevSmoke",
    )
    # Every flow input shares one list, so a flow's clicks, drags, keys and typed commands run in the order given.
    for option, kind, metavar, text in (
        ("--flow-click", "click", "NAME=X,Y", "left click X,Y (screenshot coordinates)"),
        ("--flow-drag", "drag", "NAME=X1,Y1,X2,Y2", "drag with the left button from X1,Y1 to X2,Y2"),
        (
            "--flow-key",
            "key",
            "NAME=ACTION",
            f"press the key this client binds to ACTION, as `key --action` does ({', '.join(ACTIONS)})",
        ),
        ("--flow-type", "type", "NAME=/COMMAND", "type a slash command into chat as a player does, such as /tar NPC"),
    ):
        p.add_argument(
            option,
            dest="flow_inputs",
            action="append",
            default=[],
            type=lambda value, kind=kind: (kind, value),
            metavar=metavar,
            help=f"{text} for the flow called NAME, after its reload's world screenshot and before its ready "
            "screenshot; repeat for more, all inputs run in the order given",
        )
    p.add_argument(
        "--timeout",
        type=float,
        default=1800,
        help="seconds to reach the world and to wait for the job in flight",
    )
    p.add_argument(
        "--manual-launcher",
        action="store_true",
        help="disable launcher OCR clicks; allow shot and fresh-screenshot left clicks before READY",
    )
    args = parser.parse_args(argv)

    try:
        if args.verb in {
            "up",
            "serve",
            "job",
            "run",
            "lease",
            "smoke",
            "proof",
            "down",
            "release",
            "enroll",
            *JOB_VERBS,
        }:
            if not (os.environ.get("FOREVER_CLIENT_CALLER") or os.environ.get("FOREVER_CLIENT_JOB")):
                raise ClientError(
                    "send the shared in-game agent an INGAME request: "
                    ".agents/skills/wow-forever-addon/in-game.md#requesting-a-check; "
                    "client verbs require FOREVER_CLIENT_CALLER"
                )
        if args.verb in ("up", "serve"):
            return up(args)
        if args.verb in ("job", "run"):
            return job(args)
        if args.verb == "lease":
            return lease(args)
        if args.verb == "release":
            return release(args.token)
        if args.verb == "down":
            return down()
        if args.verb == "enroll":
            return enroll(args)
        if args.verb == "capture-env":
            return capture_env()
        if args.verb == "status":
            state = load_state()
            if state.get("ready") and (not session_alive(state) or not client_ui(state)["world"]):
                state.pop("ready", None)
            print(json.dumps(state, indent=1))
            return 0
        if args.verb == "build-dev":
            # A hand link follows this build, so a record a stopped session left is replayed before it.
            recover_links()
            root = WORKSPACE / args.repo
            commit = resolve_commit(root, args.ref)
            release_tag = tag_name(root, commit)
            if release_tag:
                # A ref at a release tag is that release: point the client back at the store build instead.
                print(
                    f"{args.repo}: {args.ref} is release {release_tag}; "
                    "run: wowaddon --flavor forever sync after removing its dev link"
                )
                return 0
            core_ref = None
            if args.core_ref:
                core_ref = resolve_commit(WORKSPACE / "forever-core", args.core_ref)
            build_dev(args.repo, commit, repo_root=root, core_ref=core_ref)
            return 0
        if args.verb == "smoke":
            return smoke(args)
        if args.verb == "proof":
            return proof(args)
        if args.verb == "attest":
            return attest(args)
        if args.verb in JOB_VERBS:
            state = load_state()
            if session_alive(state) and launcher_verb(state, args.verb, getattr(args, "button", None)):
                # Nothing to queue for: the launcher input itself is what the job holding the lock waits for.
                return input_verb(state, args)
            return with_job(args.verb, args.timeout, lambda current: input_verb(current, args))
        load_state()
        if args.verb == "sv":
            files = saved_variables(args.addon)
            if not files:
                raise ClientError(f"no SavedVariables for {args.addon}: it writes them at a reload or logout")
            for f in files:
                print(f"-- {f}\n{f.read_text(errors='replace')}")
        return 0
    except ClientError as error:
        print(f"forever_client: {error}", file=sys.stderr)
        return 4 if isinstance(error, SafetyRefusal) else 2


if __name__ == "__main__":
    sys.exit(main())
