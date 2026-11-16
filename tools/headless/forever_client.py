#!/usr/bin/env python3
"""Run the WoW: Forever client on a private GPU display for agents to test the addons in the real game.

The client runs under gamescope's headless backend: it renders on the real GPU into a display of its own, so no
window reaches the desktop and the player's mouse and keyboard are never touched. Every verb talks to that display
only: screenshots through `gamescopectl`, input through `xdotool` on gamescope's nested X server. The host also
needs `tesseract` on PATH to locate the launcher's visible Play control from the private screenshot.

    forever_client.py serve               # the resident session: start, wait for the world, stay up while jobs arrive
    forever_client.py up                  # the same lifecycle in the foreground
    forever_client.py job -- <command>    # run one job in the session, holding the job lock for its length
    forever_client.py run -- <command>    # the same verb under the name it had before
    forever_client.py lease [--ttl S]     # hold the job lock for an interactive agent; prints a token
    forever_client.py release TOKEN       # end that lease now
    forever_client.py down                # stop the session once the job in flight, if any, has finished
    forever_client.py status
    forever_client.py shot [PATH]         # PNG of what the client shows now
    forever_client.py click X Y           # left click at a point in the 1920x1080 frame (after a fresh shot)
    forever_client.py scroll X Y N        # N wheel-up ticks (zoom in) or -N wheel-down ticks, at a point
    forever_client.py key Escape          # Return, Escape or BackSpace
    forever_client.py slash "/fgf"        # open chat, type a Forever addon's slash command, send it
    forever_client.py reload              # /reload and wait for the world to load again
    forever_client.py sv ADDON            # print an addon's SavedVariables (after a reload, they are current)
    forever_client.py eval FILE           # write FILE into !!DevSmoke's inbox, run it, print its own result
    forever_client.py errors [--addon X]  # reload, then the Lua errors this session raised (forever_errors.py)
    forever_client.py capture-env         # record the launch from the player's client started in Faugus
    forever_client.py build-dev REPO REF  # test-artifacts/<repo>-dev from a ref, the dev build rebuild-dev.sh made
    forever_client.py smoke --repo R --ref SHA [--no-post]
                                          # build the commit, selftest it, post its status (--no-post prints instead)
    forever_client.py smoke --repo forever-core --ref SHA
                                          # the same with every consumer's latest released build linked beside core
    forever_client.py proof --repo R --ref SHA --checkout PATH --flow NAME=SLASH_OR_LUA_FILE
                                          # record the checkout's .visual-proof.json from a client session

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
queue behind the job that is waiting for READY. Exit 0 is a clean commit, 1 a recorded failure, 3 means the player's
own client is running (the Wine prefix is used by processes this tool does not own), so nothing is posted and a caller
retries later; another agent's job is waited for, up to `--timeout`. The AddOns folder is shared: every slot the smoke
borrows is put back exactly as it was, including a store install it moved aside. A stop that never reaches Python's
handlers leaves that record behind, and the next `up`, `serve`, `job`, `run`, `smoke`, `proof` or `build-dev` replays
it before it touches AddOns.

`proof` records the in-game visual proof a release prep or a ForeverCore pin bump needs. It runs as a job the way
`smoke` does: it builds and links the candidate, reloads once, runs each `--flow NAME=SLASH_OR_LUA_FILE` through
`!!DevSmoke` (a Forever addon's own slash command, or a Lua file), takes a screenshot after each, uploads the PNGs to a
new secret gist, and writes `<checkout>/.visual-proof.json` from `visual_proof --digests` with full-SHA raw URLs and
each image's sha256, then checks the installed folder with `visual_proof --compare`. It never commits or pushes the
checkout. A slash command runs through `ChatEdit_SendText`, the client's own parser, so the capture follows a confirmed
run rather than a fixed pause (#573). A flow that returns a ready check is captured once `!!DevSmoke` has polled it
true, so a window filled in from late data is not photographed empty (#593); a check that raises or never turns true
records its reason and fails the proof with it. A flow whose window needs a real click names it with
`--flow-click "NAME=X,Y"`: once that reload's world screenshot has landed, `proof` clicks the point inside its own job
and then waits for the flow's ready screenshot as any other flow does (#655). There is no default flow: ForeverCore has
no shared opener for an addon's update notice, so the flow is named on the command line and
`wow-forever-addon/in-game.md` shows both. A flow's own result is read after its screenshot, and a snippet that raised
fails the proof before any gist or `.visual-proof.json` exists (#580).

The session is shared: `serve` starts the client once, and every `job` runs against that same client, so a test pays
the login once rather than once per test. A job holds `STATE_DIR/job.lock` only while it touches the client, and
`STATE_DIR/job.json` names its holder (pid, token, label, start) so a waiter can say who it waits for. The session
ends `IDLE_LIMIT` (10 min) after the last job ended, or after READY when none has run yet, and never later than
`MAX_SESSION` (3 h) from the launch; at either end it takes the job lock first, so a job in flight is never cut off.
`job` starts a detached `serve` when none runs and reuses a ready one. `up` is `serve` in the foreground, and `run`
is `job` under its old name. `lease` holds the job lock for an agent that drives the client across several tool
calls, and `release TOKEN` ends it.

Every verb that touches the client (`shot`, `click`, `scroll`, `key`, `slash`, `reload`, `eval`, `errors`) runs as a
job: it proceeds when `FOREVER_CLIENT_JOB` names the token in `job.json`, and otherwise takes the job lock itself for
that one invocation. `status` and `sv` need no lock.

One Battle.net account means one client: a resident session holds an exclusive lock for its lifetime and refuses to
start while any process uses the Wine prefix, which is how a player's own running client is left alone. Another
agent's session is reused and its job is waited for up to `--timeout`; only the player's own client makes a job exit
3.

The client is for testing the Forever addons' interface, never for playing, and the verbs hold to that:

- Interface only. There is no free typing: `slash` sends only the Forever addons' own commands (read from their
  `SLASH_` globals) and the UI debugging ones in UI_COMMANDS, `key` sends only UI_KEYS, and `click` and `scroll` need
  a screenshot taken since the last input, so every input aims at UI the agent has just seen. `slash` puts the
  keyboard back in the chat box first, so a focused addon EditBox cannot swallow the command.
- `--manual-launcher` (`serve`, `up`, `job`, `run`, `lease`, `smoke`, `proof`) disables OCR clicks and permits shots
  and left clicks before READY, only while the game process is absent. Inspect each private screenshot before
  clicking. Never click Uninstall or change credentials.
- One client, one job. The session ends 10 minutes after the last job and 3 hours at most, and every ending logs the
  character out and stops the client.
- Human pace. Inputs are at least INPUT_GAP apart, across invocations, and slash commands type at TYPE_DELAY_MS.
"""

from __future__ import annotations

import argparse
import fcntl
import functools
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tarfile
import time
import uuid
import zlib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

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
# A driver upgrade whose loaded kernel module is still the old one makes Vulkan fail before gamescope can start. The
# module names itself here, and nvidia-smi or the installed userspace library names the other half (#567).
NVIDIA_MODULE_VERSION = Path("/sys/module/nvidia/version")
NVIDIA_MISMATCH = "driver/library version mismatch"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "forever-client"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "forever-client/env.json"
ADDON = Path(__file__).resolve().parent / "!!ForeverHeadless"
WIDTH, HEIGHT = 1920, 1080
# The session is shared, so the client stays up while jobs arrive instead of ending after one test. These are fixed
# limits, not heuristics: it ends IDLE_LIMIT after the last job ended (or after READY when none has run yet), and
# never later than MAX_SESSION from the launch. Both are checked only between jobs; a job in flight is never cut off.
IDLE_LIMIT = 10 * 60
MAX_SESSION = 3 * 60 * 60
WAIT_POLL = 1.0  # how often a waiter checks the session lock, the job lock and the Wine prefix
JOB_POLL = 0.5  # how often a job waiter checks the job lock while it waits
LOGOUT_WAIT = 60  # /quit outside an inn counts down 20 s before the client exits
# A `down` waits for the job in flight to finish first: a smoke is the longest job.
STOP_WAIT = 30 * 60
INPUT_GAP = 1.5
TYPE_DELAY_MS = "120"
WHEEL_DELAY_MS = "120"
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
FOREVER_ADDONS = (
    # The dev addon behind /devsmoke: its commands are the suite's own test surface.
    "!!DevSmoke",
    "AdventureGuideForever",
    "CommissionsForever",
    "FieldGuideForever",
    "ForeverCore",
    "KilnForever",
    "LegacyForever",
    "MacroAssistForever",
    "ShortestPathForever",
    "SkillUpForever",
    "TweaksForever",
)
UI_COMMANDS = {"/reload", "/rl", "/fstack", "/framestack", "/etrace", "/eventtrace"}
UI_KEYS = {"Return", "Escape", "BackSpace"}
# The game's own window title: the character-select nudge sends Return only to it, never to the launcher, whose
# focused Play button a Return would press again.
GAME_WINDOW = "World of Warcraft"
SLASH_ASSIGN = re.compile(r"SLASH_\w+\s*=(.*)$", re.MULTILINE)
SLASH_WORD = re.compile(r'"(/[^"\s]+)"')

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


class ClientError(Exception):
    """A failure the agent should read: printed without a traceback, exit status 2."""


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


def character_config(launch: Mapping) -> dict[str, str | bool]:
    """Validate the owner-approved parked character before starting any client process."""
    character = launch.get("character")
    if not isinstance(character, dict):
        raise ClientError(
            f"{CONFIG} has no approved character: add character.name, character.guid and character.require_resting=true"
        )
    name, guid = character.get("name"), character.get("guid")
    if not isinstance(name, str) or not name.strip() or not isinstance(guid, str) or not guid.strip():
        raise ClientError(f"{CONFIG} has an invalid character identity: name and guid are required")
    if character.get("require_resting") is not True:
        raise ClientError(f"{CONFIG} must set character.require_resting=true for automatic proofs")
    return {"name": name, "guid": guid, "require_resting": True}


def lua_string(value: str) -> str:
    """Encode a character field as a Lua 5.1 quoted string without control escapes or lossy Unicode."""
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ClientError(f"{CONFIG} character identity contains a control character")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def prepare_headless_addon(character: Mapping[str, str | bool]) -> Path:
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
            + ", require_resting=true}\n",
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


def load_state() -> dict:
    try:
        return json.loads(state_file().read_text())
    except (OSError, ValueError):
        raise ClientError("no headless session is running: start one with `forever_client.py up`") from None


def session_alive(state: Mapping) -> bool:
    """Whether the process that wrote session.json still runs; a reused pid is told apart by its start time."""
    return owner_alive({"pid": state.get("pid"), "started": state.get("start_ticks")})


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


def wait_for_world(before: set[Path], timeout: float, nudge=None, *, require_marker: bool = False) -> Path:
    """Block until the dev addon's screenshot appears: the world has loaded. `nudge` runs every 15 s meanwhile."""
    deadline, next_nudge = time.monotonic() + timeout, time.monotonic() + 20
    while time.monotonic() < deadline:
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


def send(state: Mapping, *args: str, before_input=None) -> None:
    """One input action, at least INPUT_GAP after the last one from any invocation."""
    wait = INPUT_GAP - (time.time() - mark("last-input"))
    if wait > 0:
        time.sleep(wait)
    if before_input:
        before_input()
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


def shot(state: Mapping, path: Path) -> Path:
    if "runtime_dir" not in state:
        raise ClientError("session has no runtime directory recorded; restart the headless session")
    runtime = runtime_dir({"XDG_RUNTIME_DIR": state["runtime_dir"]}, os.getuid())
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    env = {**os.environ, "XDG_RUNTIME_DIR": str(runtime), "GAMESCOPE_WAYLAND_DISPLAY": state["gamescope_socket"]}
    subprocess.run(["gamescopectl", "screenshot", str(path)], env=env, check=True, capture_output=True)
    for _ in range(50):
        if _complete_png(path):
            (STATE_DIR / "last-shot").touch()
            return path
        time.sleep(0.1)
    raise ClientError(f"gamescope wrote no screenshot to {path}")


# Gamescope maps absolute XTEST coordinates onto its focused window, whatever that window's X position, so a point
# here is in the window's own pixels, the same pixels a screenshot shows. xdotool's --window option adds the window's
# X position to the point and must never be used.
def click(state: Mapping, px: int, py: int, button: str) -> None:
    if button not in ("1", "3"):
        raise ClientError("click takes --button 1 (left) or 3 (right)")
    if mark("last-shot") <= mark("last-input"):
        raise ClientError("take a `shot` and read it first: a click must aim at addon UI in the current frame")
    if not (0 <= px < WIDTH and 0 <= py < HEIGHT):
        raise ClientError(f"({px}, {py}) is outside the {WIDTH}x{HEIGHT} frame")

    def launcher_guard():
        if state.get("manual_launcher") and not state.get("ready") and client_pid():
            raise ClientError("the game has started: wait for READY before clicking")

    send(state, "mousemove", str(px), str(py), "click", button, before_input=launcher_guard)


def scroll(state: Mapping, px: int, py: int, ticks: int) -> None:
    """Turn the mouse wheel at a point in the current frame: positive is up (zoom in), negative down.

    The world map's zoom lives on its ScrollContainer, which a click does not reach and `slash` refuses to open up as
    arbitrary Lua. This is the same screenshot-bound input as `click`, so it aims only at UI just read in a shot (#548).
    """
    if ticks == 0:
        raise ClientError("scroll takes a non-zero number of wheel ticks: positive up, negative down")
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
    )


def press(state: Mapping, keys: Sequence[str]) -> None:
    refused = [k for k in keys if k not in UI_KEYS]
    if refused:
        raise ClientError(f"key sends only {', '.join(sorted(UI_KEYS))}; refused {', '.join(refused)}")
    for k in keys:
        send(state, "key", k)


def addon_commands(addons: Path | None = None) -> set[str]:
    """The slash commands the Forever addons register, read from the `SLASH_` globals in their installed files.

    Every `"/word"` literal on the right-hand side of a `SLASH_<KEY><n> =` assignment counts, so a plain
    `SLASH_X = "/x"` and the `SLASH_X = cond and "/x" or nil` form both register their command."""
    addons = addons or CLIENT / "Interface/AddOns"
    found: set[str] = set()
    for name in FOREVER_ADDONS:
        for lua in (addons / name).rglob("*.lua"):
            text = lua.read_text(errors="replace")
            for assignment in SLASH_ASSIGN.finditer(text):
                found.update(c.lower() for c in SLASH_WORD.findall(assignment.group(1)))
    return found


def allowed_command(command: str, addons: Path | None = None) -> None:
    if not command.isprintable():
        raise ClientError("slash sends one line: a newline would send a second chat line")
    word = command.split(maxsplit=1)[0].lower() if command.strip() else ""
    if word not in UI_COMMANDS | addon_commands(addons):
        raise ClientError(
            f"slash sends only the Forever addons' own commands and {', '.join(sorted(UI_COMMANDS))}: "
            f"refused {word or 'an empty command'}"
        )


def focus_chat(state: Mapping) -> None:
    """Put keyboard focus in the chat edit box, whichever frame held it.

    From a clean frame, Return opens chat, Escape closes it and Return opens it again. When an addon EditBox
    has focus and no OnEnterPressed (the Forever copy-link box), the first Return stays in that
    box, Escape runs its OnEscapePressed, which closes its window, and the second Return opens chat. A box
    whose OnEnterPressed clears its own focus lets the Escape through to the game, which closes the topmost
    window or opens the game menu, so `reload` then times out as before."""
    send(state, "key", "Return")
    send(state, "key", "Escape")
    send(state, "key", "Return")


def slash(state: Mapping, command: str) -> None:
    allowed_command(command)
    focus_chat(state)
    send(state, "type", "--delay", TYPE_DELAY_MS, command)
    send(state, "key", "Return")


# --- the launcher's Play button ----------------------------------------------------------------------------------

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_CHANNELS = {2: 3, 6: 4}  # truecolour, and truecolour with alpha
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


def png_pixels(path: Path) -> tuple[int, int, int, list[bytes]]:
    """The screenshot's width, height, channels and rows, decoded without an image library.

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
    try:
        raw = zlib.decompress(b"".join(compressed))
    except zlib.error as error:
        raise ClientError(f"{path} is not a readable PNG: {error}") from None
    stride = width * channels
    rows: list[bytes] = []
    previous = bytes(stride)
    at = 0
    try:
        for _row in range(height):
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


def write_pgm_channel(path: Path, width: int, height: int, channels: int, rows: Sequence[bytes], channel: int) -> None:
    """Write one PNG channel as grayscale for OCR of colored game labels."""
    data = bytearray(f"P5\n{width} {height}\n255\n".encode())
    for row in rows:
        data.extend(255 - value for value in row[channel::channels])
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
        raise ClientError("Battle.net launcher window was not found")
    if shutil.which("tesseract") is None:
        raise ClientError("tesseract is required for OCR; use up --manual-launcher for screenshot-guided clicks")
    image = shot(state, STATE_DIR / "launcher.png")
    targets = play_targets(image)
    if not targets:
        # A launcher dialog can cover the page. Dismiss it on the discovered
        # Battle.net window, then let the startup loop inspect a fresh frame.
        x(state, "key", "--window", found.stdout.split()[0], "Escape")
        if not state.get("play_target_missing_reported"):
            print(
                f"no visible Play label recognized; inspect {image}. Retrying until the startup deadline. "
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
    (STATE_DIR / "last-input").touch()


def enter_world_targets(image: Path) -> list[tuple[int, int, int, int, float]]:
    """Find exact Enter World labels in a character-select screenshot."""
    width, height, channels, rows = png_pixels(image)
    channel = STATE_DIR / "character-select-green.pgm"
    write_pgm_channel(channel, width, height, channels, rows, 1)
    words = [word for word in ocr_words_with_lines(channel, psm=6) if word[1] >= 0]
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


def enter_world(state: Mapping) -> None:
    """Click Enter World only when the current game frame visibly contains that label."""
    if not game_focused(state):
        return
    image = shot(state, STATE_DIR / "character-select.png")
    targets = enter_world_targets(image)
    if len(targets) != 1:
        return
    left, top, width, height, _ = targets[0]
    x(state, "mousemove", str(left + width // 2), str(top + height // 2))
    time.sleep(0.5)
    x(state, "click", "1")
    (STATE_DIR / "last-input").touch()


def reload(state: Mapping, timeout: float = 120) -> Path:
    # The new cycle's screenshots are the ones after the command was sent: a screenshot an earlier reload's flow
    # still takes would otherwise be read as this one's world load.
    slash(state, "/reload")
    return wait_for_world(screenshots(), timeout)


# --- dev builds ------------------------------------------------------------------------------------------------


def git(repo_root: Path, *args: str) -> str:
    """One git read from a repository's checkout, its failure a ClientError the agent can read."""
    try:
        return subprocess.check_output(["git", "-C", str(repo_root), *args], text=True, stderr=subprocess.PIPE).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise ClientError(f"git {' '.join(args)} in {repo_root}: {detail.strip()}") from None


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
    """`<tag>-dev+<sha>`, so wowaddon returns the dev link to the store release once a newer one ships."""
    try:
        tag = subprocess.check_output(
            ["git", "-C", str(repo_root), "describe", "--tags", "--abbrev=0", commit],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        tag = "v0.0.0"  # a repository with no release yet
    return f"{tag}-dev+{git(repo_root, 'rev-parse', '--short', commit)}"


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


def build_dev(repo: str, commit: str, destination: Path | None = None, repo_root: Path | None = None) -> Path:
    """Write the dev build of `commit` to `test-artifacts/<repo>-dev`, as `rebuild-dev.sh` did.

    The build is the commit's own tree without the development folders, with every TOC stamped `<tag>-dev+<sha>`, so
    `wowaddon` returns the dev link to the store release once one newer than the tag ships. The new build is unpacked
    beside the old one and swapped in, so a failed build leaves the previous one in place.
    """
    root = repo_root or WORKSPACE / repo
    folder = destination or BUILD_ROOT / f"{repo}-dev"
    sha = git(root, "rev-parse", "--verify", f"{commit}^{{commit}}")
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


def owner_alive(owner: object) -> bool:
    """Whether the session that wrote a link record still runs; a reused pid is told apart by its start time."""
    pid = owner.get("pid") if isinstance(owner, Mapping) else None
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (OSError, OverflowError):
        pass  # another user's pid, or a number no process can have: the start time below decides
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
    owner = {"pid": os.getpid(), "started": process_start(os.getpid())}
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({"owner": owner, "links": list(records)}))
    os.replace(temporary, path)


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
            record: dict = {"slot": str(slot), "was": None}
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


def recover_links() -> int:
    """Put back a record a session stopped without its teardown left, and say what it put back.

    A stop that never reaches Python's handlers (SIGKILL, a signal aimed at the wrapping shell, a hangup before the
    handler was installed) leaves the links a smoke borrowed in AddOns and the store install at `.smoke-backup`. The
    record names the session that wrote it by pid and start time, so a record whose session still runs is left to that
    session's own teardown, and this session's own record is left alone too: the smoke reading it here is the one that
    just linked. Anything else is replayed through `restore_links`, the one teardown, before AddOns is used again.
    """
    record = link_record()
    if record is None:
        return 0
    owner = record.get("owner")
    if owner == {"pid": os.getpid(), "started": process_start(os.getpid())}:
        return 0
    # A record an older version wrote names no owner, so the client lock and the prefix decide: while any session
    # holds the client, that record may be its live smoke.
    if owner_alive(owner) or (owner is None and client_in_use()):
        print(
            f"forever_client: {link_record_path()} belongs to a running session; its links are left alone",
            file=sys.stderr,
        )
        return 0
    links = record["links"]
    restore_links(links)
    try:
        stale_state = json.loads(state_file().read_text())
    except (OSError, ValueError):
        stale_state = {}
    generated = Path(stale_state.get("headless_addon", "")) if stale_state.get("headless_addon") else None
    if generated and generated.is_dir() and generated.parent == STATE_DIR:
        shutil.rmtree(generated)
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
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(dict(record)))
    os.replace(temporary, path)


def job_alive(record: object) -> bool:
    """Whether the process that wrote a job.json still runs; a reused pid is told apart by its start time."""
    if not isinstance(record, Mapping):
        return False
    return owner_alive({"pid": record.get("pid"), "started": record.get("start_ticks")})


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


def acquire_job(timeout: float | None, label: str, *, ttl: float | None = None) -> tuple[object, str]:
    """Take the job lock for this process, waiting up to `timeout` (None: until it is free) for its holder.

    The holder is printed once while the wait runs, so an agent knows which job it queues behind. The record names
    this process and its start time, so a later reader can tell a live holder from a dead one's leftover file.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    handle = open(job_lock_path(), "a+")
    deadline = None if timeout is None else time.monotonic() + timeout
    announced = False
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if not announced:
                print(f"forever_client: waiting for {describe_job()}", file=sys.stderr, flush=True)
                announced = True
            if deadline is not None and time.monotonic() >= deadline:
                handle.close()
                raise ClientError(
                    f"another job still holds the client after waiting {timeout:.0f} s: {describe_job()}; "
                    "pass a longer --timeout to queue"
                ) from None
            time.sleep(JOB_POLL)
    token = uuid.uuid4().hex
    record: dict = {
        "pid": os.getpid(),
        "start_ticks": process_start(os.getpid()),
        "token": token,
        "label": label,
        "started": time.time(),
    }
    if ttl is not None:
        record["expires"] = time.time() + ttl
    write_job_record(record)
    return handle, token


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


def with_job(label: str, timeout: float, action) -> int:
    """Run one verb that touches the client: inside the job that gave it the token, or holding the lock itself.

    A verb invoked by a `job` command carries `FOREVER_CLIENT_JOB`, and proceeds without taking the lock again. A
    verb run on its own takes the job lock for this one invocation, waiting for the job in flight, and releases it
    afterwards. A token that is not the holder's queues like any other caller.
    """
    token = os.environ.get("FOREVER_CLIENT_JOB")
    holder = job_holder()
    if token and holder is not None and holder.get("token") == token:
        return action(load_state())
    handle, own = acquire_job(timeout, label)
    try:
        state = load_state()
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
    tool = Path(__file__).resolve().parents[1] / "forever_errors.py"
    command = [sys.executable, str(tool), "--since", str(state["started"])]
    if addon:
        command += ["--addon", addon]
    if as_json:
        command += ["--json"]
    return subprocess.run(command, check=False, capture_output=True, text=True)


def smoke_counts(state: Mapping, folders: Sequence[tuple[str, Path]]) -> dict[str, int]:
    """`errors --addon <folder>` for each folder, counted once `/forever selftest` has run."""
    counts: dict[str, int] = {}
    for name, _folder in folders:
        completed = errors(state, name, as_json=True)
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
        description = f"no result: {outcome['error'] or 'the session ended before the checks ran'}"
        if not post:
            print(f"{repo}@{commit[:7]}: {description} (not posted)", flush=True)
            return 1
        post_status(repo, commit, False, description)
        print(f"{repo}@{commit[:7]}: {description} ({SMOKE_CONTEXT} posted)", flush=True)
        return 1
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


def smoke_registrations(state: Mapping, folders: Sequence[tuple[str, Path]]) -> list[str]:
    """Each folder that never called ForeverCore.Register, read through one !!DevSmoke eval after the selftest.

    The snippet prints a line per unregistered folder. The eval route reloads twice: the first reload runs the snippet
    at login, and the second saves its record to disk, because SavedVariables reach disk only at a reload (#580).
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
    try:
        reload(state)
        clear_eval_inbox()
        reload(state)
        data = saved_eval(written["token"])
    finally:
        clear_eval_inbox(quiet=True)
    report, ok = format_eval(data)
    if not ok:
        raise ClientError(f"the released addons' startup check failed: {report}")
    return not_registered(_ordered(data.get("out")))


def smoke(args: argparse.Namespace) -> int:
    """Build a repository's commit, test it in the client as one job, and record the result as a commit status.

    It ensures a session, takes the job lock, builds and links the candidate, reloads so the client loads it, runs
    `/forever selftest` and `errors --addon` for each folder, and puts the links back before it releases the lock.
    ForeverCore's candidate is linked with every consumer's latest released build, and those folders count too; after
    the selftest, one !!DevSmoke eval asks `ForeverCore.Registered` for each of them, so a released addon that refused
    to start on this core fails even though it raised no Lua error. A released build that cannot be fetched is a
    `ClientError` before anything is linked, so nothing is posted and the commit is smoked again later. Exit 0 is a
    clean commit and 1 a failure that was recorded; 3 means the player's own client is running, so nothing is posted and
    a caller retries later. Another agent's job is waited for. A smoke that could not run at all (no checkout, no such
    ref) raises ClientError and posts nothing either. `--manual-launcher` starts the session that way, so the caller can
    take `shot` and click Play itself, and `--no-post` prints the result without posting a commit status.
    """
    repo = args.repo
    if not SMOKE_REPO.fullmatch(repo):
        raise ClientError(f"--repo takes a repository name, not {repo!r}")
    root = WORKSPACE / repo
    if not root.is_dir():
        raise ClientError(f"no checkout of {repo} in {WORKSPACE}")
    commit = git(root, "rev-parse", "--verify", f"{args.ref}^{{commit}}")
    post = not args.no_post
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
        except ClientError as error:
            busy = foreign_client()
            if busy:
                print(f"client in use: {busy}; nothing posted on {repo}@{commit[:7]}", flush=True)
                return 3
            outcome["error"] = str(error)
            return report_smoke(repo, commit, outcome, post=post)
        # The client log holds every job's lines: this job's result starts where its own work starts.
        state = {**state, "started": job_started()}
        recover_links()
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
                reload(state)
                slash(state, "/forever selftest")
                # The selftest is synchronous Lua; the reload `errors` makes settles it and writes SavedVariables.
                outcome["counts"] = smoke_counts(state, folders)
                if released:
                    outcome["not_started"] = smoke_registrations(state, released)
            finally:
                restore_links(records)
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


def flow_step(action: str) -> str:
    """What a proof records for one flow: a slash command as typed, or a Lua snippet by name and content digest.

    A caller's path names a machine, a user and a scratch folder in a public proof, and the file it names is gone with
    that folder, so a Lua step is the snippet's file name and sha256 instead (#591).
    """
    if not lua_flow(action):
        return action
    path = Path(action)
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ClientError(f"cannot read the flow's snippet {action}: {error}") from None
    return f"{path.name} sha256:{digest}"


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
    before: set[Path], action: str, token: str | None = None, timeout: float = FLOW_READY_SECONDS
) -> Path:
    """Block until the reload's own world screenshot is on disk: the frame a flow's click aims at.

    Every reload writes one screenshot as the world loads, before !!DevSmoke can run the flow's own, so it is the
    first new file after `before` (#593). A flow whose window needs a real click cannot click before that frame
    exists, so its click waits for this one and the ready screenshot then follows it (#655).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
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
    before: set[Path], action: str, token: str | None = None, timeout: float = FLOW_READY_SECONDS
) -> Path:
    """Block until a flow says its window is ready, by the screenshot it takes then or the failure it records.

    Every reload writes one screenshot as the world loads, and !!DevSmoke writes the flow's own once the flow returns
    true from its ready check. Both appear after `before`, and the flow's is the later one, so the second new file is
    the flag the capture waits on: a window filled in from late data is captured after it has filled rather than after
    a fixed pause (#593). A check that raises or never turns true records why, and the proof fails on that reason.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
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


def parse_flow_clicks(values: Sequence[str], flows: Sequence[tuple[str, str]]) -> dict[str, tuple[int, int]]:
    """`--flow-click NAME=X,Y` entries: where a named flow clicks, in the screenshot coordinates `click` takes.

    A click belongs to a flow by name, so a name that matches no `--flow` is a typo the caller must hear about before
    the build takes the client rather than a flow that quietly never clicks.
    """
    names = [name for name, _ in flows]
    clicks: dict[str, tuple[int, int]] = {}
    for value in values:
        name, separator, point = value.partition("=")
        name = name.strip()
        if not separator or not name or not point.strip():
            raise ClientError(f"--flow-click takes NAME=X,Y, not {value!r}")
        if name not in names:
            known = ", ".join(names) if names else "no flow is named"
            raise ClientError(f"--flow-click {name}: no --flow of that name ({known})")
        try:
            px, py = (int(part.strip()) for part in point.split(","))
        except ValueError:
            raise ClientError(f"--flow-click {name}: X,Y takes two integers, not {point.strip()!r}") from None
        if not (0 <= px < WIDTH and 0 <= py < HEIGHT):
            raise ClientError(f"--flow-click {name}: ({px}, {py}) is outside the {WIDTH}x{HEIGHT} frame")
        clicks[name] = (px, py)
    return clicks


def flow_record(name: str, action: str, point: tuple[int, int] | None) -> dict:
    """One entry in the proof's `flows`: what ran, where it clicked, and that it was captured."""
    record: dict = {"name": name, "steps": [flow_step(action)]}
    if point:
        record["click"] = list(point)
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
    except ClientError:
        return timeout
    failure = flow_ready_failure(token)
    if failure:
        return ClientError(f"the flow {action} could not be captured: {failure}")
    return timeout


def run_flow(state: Mapping, action: str, point: tuple[int, int] | None = None) -> str:
    """Run one proof flow through !!DevSmoke: a Forever addon's own slash command, or a Lua file.

    Both routes write a snippet whose own run token `check_flow_eval` reads once the screenshot is taken: the reload
    that saves the result to disk would close the window the flow just opened (#580). A slash command runs through
    `ChatEdit_SendText`, the client's own parser, so the capture follows a confirmed run rather than a fixed pause
    (#573). The flow's ready check is polled by !!DevSmoke, whose screenshot then says the window has drawn, so the
    capture waits for that file instead of a pause (#593). `point` is a click in screenshot coordinates that runs
    between the reload's world screenshot and the flow's own: opening a protected window is not something a Lua
    snippet can do, and since #648 no outside `click` can reach the client while this job holds it (#655).
    """
    tool = devsmoke_eval()
    try:
        if lua_flow(action):
            written = tool.write_snippet(Path(action), addons=CLIENT / "Interface/AddOns", capture=True)
        else:
            allowed_command(action)
            written = tool.write_slash(action, addons=CLIENT / "Interface/AddOns", capture=True)
    except tool.EvalError as error:
        raise ClientError(str(error)) from None
    print(f"wrote {written['chunk']} from {written['snippet']} ({written['lines']} lines)", flush=True)
    # The snippet runs at login of this reload. Clearing the inbox afterwards keeps the later reloads a proof makes
    # from running it again, which would schedule a second ready screenshot the next flow could mistake for its own.
    before = screenshots()
    reload(state)
    clear_eval_inbox()
    try:
        if point:
            world = wait_for_flow_world(before, action, written["token"])
            # A click must aim at a screenshot newer than the last input; the flow's own world frame is that
            # screenshot, so the proof clicks through the same `click` an agent uses instead of a second input path.
            (STATE_DIR / "last-shot").touch()
            click(state, point[0], point[1], "1")
            print(f"clicked {point[0]},{point[1]} after {world.name}", flush=True)
        wait_for_flow_ready(before, action, written["token"])
    except ClientError as error:
        raise flow_capture_failure(state, action, written["token"], error) from None
    return written["token"]


def eval_result(state: Mapping, token: str) -> tuple[str, bool]:
    """The report of the eval the run token wrote, read after the reload that saves this session to disk.

    SavedVariables are written at a reload or logout, so the file the snippet's own reload left behind still holds the
    session before it: a second reload makes this run's own result the one on disk (#580).
    """
    reload(state)
    return format_eval(saved_eval(token))


def check_flow_eval(state: Mapping, action: str, token: str) -> None:
    """Fail on a flow whose own snippet raised, quoting that snippet's error and nothing else's."""
    report, ok = eval_result(state, token)
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
    A flow named in `--flow-click` clicks its point inside this job once its reload's world screenshot has landed.
    The proof is written to `<checkout>/.visual-proof.json`; the checkout is never committed or pushed here.
    """
    flows = parse_flows(args.flow)
    if not flows:
        raise ClientError(
            "proof needs at least one --flow: ForeverCore has no shared opener for an addon's update notice, so name "
            'it here, such as --flow "update notice=/lf" or --flow "update notice=notice.lua"'
        )
    clicks = parse_flow_clicks(args.flow_click, flows)
    repo = args.repo
    if not SMOKE_REPO.fullmatch(repo):
        raise ClientError(f"--repo takes a repository name, not {repo!r}")
    root = WORKSPACE / repo
    if not root.is_dir():
        raise ClientError(f"no checkout of {repo} in {WORKSPACE}")
    checkout = Path(args.checkout).resolve()
    if not checkout.is_dir():
        raise ClientError(f"no checkout at {checkout}: --checkout is the tree the proof is written to")
    commit = git(root, "rev-parse", "--verify", f"{args.ref}^{{commit}}")
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
        except ClientError:
            # Only the player's own client makes a proof exit 3; another agent's job was waited for above.
            busy = foreign_client()
            if busy:
                print(f"client in use: {busy}; no proof recorded for {repo}@{commit[:7]}", flush=True)
                return 3
            raise
        state = {**state, "started": job_started()}
        recover_links()
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
                for index, (name, action) in enumerate(flows, start=1):
                    flow_token = run_flow(state, action, clicks.get(name))
                    screenshots.append(shot(state, shots_folder / f"{index}-{flow_slug(name)}.png"))
                    if flow_token:
                        # After the shot: the reload that saves the eval opens the world again, which would close
                        # what the flow showed (#580).
                        check_flow_eval(state, action, flow_token)
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
                proof_compare(checkout, folders[0][1])
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
        "flows": [flow_record(name, action, clicks.get(name)) for name, action in flows],
        "images": images,
    }
    target = checkout / PROOF_FILE
    target.write_text(json.dumps(proof_data, indent=2) + "\n", encoding="utf-8")
    print(f"{repo}@{commit[:7]}: wrote {target} and checked it against {folders[0][1]}", flush=True)
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
        send(state, "key", "Return")
        send(state, "type", "--delay", TYPE_DELAY_MS, "/quit")
        send(state, "key", "Return")
    except subprocess.CalledProcessError:
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


def teardown(
    gamescope: subprocess.Popen | int | None,
    wine: Mapping[str, str],
    link: Path | None,
    state: Mapping | None,
) -> None:
    token = state.get("token") if state else None
    require_owned_prefix(token)
    # Only a session in the world types /quit: at the character list Enter would enter the world instead.
    if state and state.get("ready") and gamescope_running(gamescope, state) and client_pid():
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
    if link and link.is_symlink():
        link.unlink()
    if state and state.get("headless_addon"):
        generated = Path(state["headless_addon"])
        if generated.is_dir() and generated.parent == STATE_DIR:
            shutil.rmtree(generated)
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


def at_character_select(state: Mapping, manual_launcher: bool) -> None:
    """Nudge the launch along, every 15 s until the world loads.

    Enter at the character list enters the world with the last character; before then it does nothing. It is sent
    only while the game's own window has focus: a Return on the focused Battle.net launcher presses Play again and
    starts a second client, which then ends on its own login form.
    """
    if client_pid():
        enter_world(state)
    elif not manual_launcher:
        press_play(state)


def session_end_reason(now: float, started: float, ready: float, last_job: float) -> str | None:
    """Why the resident session should stop now, or None. Two fixed limits, checked in this order:

    - MAX_SESSION from the launch: the lifetime cap, whatever jobs arrive.
    - IDLE_LIMIT since the last job ended, or since READY when none has run yet: no job is coming.

    `last_job` is never before `ready`: `last_job_mark` clamps it, because a mark an earlier session left says
    nothing about this one.
    """
    if now - started >= MAX_SESSION:
        return f"the {MAX_SESSION // 3600} h lifetime cap"
    if now - last_job >= IDLE_LIMIT:
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


def serve(args: argparse.Namespace, after_ready=None) -> int:
    """The resident session: launch, wait for the world, stay up while jobs arrive, then log out and stop.

    It is the lifecycle `up` always had, with two fixed ends instead of the 30 minute alarm: IDLE_LIMIT after the last
    job ended (or after READY when none has run), and MAX_SESSION from the launch. At either end it takes the job lock
    first, so a job in flight always finishes before the client is torn down. `job` starts this detached when no
    session runs, and `up` is the same verb in the foreground.
    """
    recover_links()
    mismatch = nvidia_mismatch()
    if mismatch:
        raise ClientError(mismatch)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / STOP).unlink(missing_ok=True)
    lock = open(STATE_DIR / "lock", "w")
    try:
        if args.wait:
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
        if not CONFIG.exists():
            raise ClientError(
                f"no launch recorded: start Battle.net from Faugus, then run `forever_client.py capture-env` ({CONFIG})"
            )
        launch = json.loads(CONFIG.read_text())
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
    gamescope: subprocess.Popen | int | None = None
    state: dict | None = None
    job = None
    job_token = None

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
        before = screenshots()
        started = time.time()
        launched = time.monotonic()
        # The session's ownership exists before its first child does, so an interrupt at the spawn has a token for
        # teardown rather than leaving unowned Wine processes and gamescope behind (#578).
        state = {
            "pid": os.getpid(),
            "start_ticks": process_start(os.getpid()),
            "gamescope": None,
            "gamescope_start": None,
            "token": token,
            "started": started,
            "runtime_dir": str(runtime),
            "manual_launcher": args.manual_launcher,
            "wine": {"PROTONPATH": wine["PROTONPATH"]} if wine.get("PROTONPATH") else {},
            "link": str(link),
            "headless_addon": str(session_addon),
        }
        state_file().write_text(json.dumps(state))
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
        state["gamescope"] = gamescope.pid
        state["gamescope_start"] = process_start(gamescope.pid)
        state_file().write_text(json.dumps(state))
        genv = child_env(token)
        state.update(display=genv["DISPLAY"], gamescope_socket=genv["GAMESCOPE_WAYLAND_DISPLAY"])
        state_file().write_text(json.dumps(state))
        print(f"starting: display {state['display']}, log {STATE_DIR / 'session.log'}", flush=True)

        nudge = functools.partial(at_character_select, state, args.manual_launcher)
        try:
            ready_shot = wait_for_world(before, args.timeout, nudge=nudge, require_marker=True)
        except ClientError as error:
            frame = shot(state, STATE_DIR / "failed.png")
            raise ClientError(f"{error}; last frame: {frame}") from None
        state["ready"] = time.time()
        state_file().write_text(json.dumps(state))
        ready = time.monotonic()
        print(f"READY in the world after {time.time() - started:.0f} s ({ready_shot.name})", flush=True)
        # !!ForeverHeadless performs the parked-character preflight before its ordinary readiness screenshot.
        # No eval or reload is needed here: wait_for_world only returns after that handshake succeeds.
        print("CHARACTER_PREFLIGHT passed", flush=True)
        if after_ready:
            return after_ready(state)
        while gamescope.poll() is None:
            reason = session_end_reason(time.monotonic(), launched, ready, last_job_mark(ready))
            if reason is None and (STATE_DIR / STOP).exists():
                reason = "`down` asked"
            if reason is None:
                time.sleep(1)
                continue
            # A job is never cut off: take the job lock, then decide again with the job's own end recorded. A job
            # that just ended clears the idle reason, so the session stays up for the next one.
            job, job_token = acquire_job(None, f"the session's end ({reason})")
            reason = session_end_reason(time.monotonic(), launched, ready, last_job_mark(ready))
            if reason is None and (STATE_DIR / STOP).exists():
                reason = "`down` asked"
            if reason is None:
                release_job(job, job_token, ended=False)
                job = job_token = None
                continue
            print(f"forever_client: the session is ending: {reason}", flush=True)
            break
        else:
            raise ClientError("the client exited on its own")
        return 0
    except KeyboardInterrupt:
        return 0
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


def down() -> int:
    """Stop the resident session once the job in flight, if any, has finished, or clean up after a dead owner.

    A live session is asked to stop: one in the world through the stop marker its resident loop reads between jobs, so
    the job in flight finishes first, and one still starting through its own SIGTERM teardown, bound to the start
    identity it recorded so a reused pid is never signalled. Once that process is gone it can no longer run its own
    teardown, so `down` does the same work itself: the token-owned Wine processes, gamescope from `state["gamescope"]`,
    the dev addon link and the state file (#578). A pid that no longer exists must not crash `down`.
    """
    state = load_state()
    started = state.get("owner_start", state.get("start_ticks"))
    owner = {"pid": state.get("pid"), "started": started}
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
        link = Path(state["link"]) if state.get("link") else CLIENT / "Interface/AddOns" / ADDON.name
        teardown(state.get("gamescope"), state.get("wine") or {}, link, state)
        state_file().unlink(missing_ok=True)
    return 0


def start_serve(manual_launcher: bool) -> subprocess.Popen:
    """Start the resident session detached, its lines in serve.log, and hand back the process to watch."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "FOREVER_CLIENT_JOB"}
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
        state = current_session()
        if state and state.get("ready"):
            return state
        if state is None and child is None and not session_lock_held():
            child = start_serve(manual_launcher)
        if child is not None and child.poll() is not None:
            # Our serve exited before READY. Another agent's serve may hold the lock now: wait for that one instead.
            if not session_lock_held():
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
    label = (args.label or Path(command[0]).name)[:80]
    handle, token = acquire_job(args.timeout, label)
    try:
        state = ensure_session(args.timeout, args.manual_launcher)
        recover_links()
        env = {
            **os.environ,
            "XDG_RUNTIME_DIR": state["runtime_dir"],
            "FOREVER_CLIENT_DISPLAY": state["display"],
            "FOREVER_CLIENT_JOB": token,
        }
        return subprocess.run(command, env=env, check=False).returncode
    finally:
        release_job(handle, token)


def start_holder(handle, token: str, ttl: float) -> subprocess.Popen:
    """Start the detached process that keeps the job lock until release, the ttl, or the session's end.

    The lock's open file description is handed to the child, so it stays held after this process exits: flock is
    released only when every descriptor of that description is closed.
    """
    env = {k: v for k, v in os.environ.items() if k != "FOREVER_CLIENT_JOB"}
    log = open(STATE_DIR / SERVE_LOG, "a")
    command = [sys.executable, str(Path(__file__).resolve()), "lease-hold", str(handle.fileno()), token, str(ttl)]
    try:
        return subprocess.Popen(
            command,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            pass_fds=(handle.fileno(),),
        )
    finally:
        log.close()


def lease(args: argparse.Namespace) -> int:
    """Hold the job lock for an interactive agent and print its token, leaving a detached holder to keep it.

    The holder releases the lock at `release TOKEN`, at the ttl, or when the session ends. The record names the
    holder, not this short-lived process, so a waiter reports a live pid and the expiry.
    """
    if not 0 < args.ttl <= LEASE_MAX:
        raise ClientError(f"--ttl takes 1 to {LEASE_MAX} s")
    label = (args.label or "a lease")[:80]
    handle, token = acquire_job(args.timeout, label, ttl=args.ttl)
    try:
        ensure_session(args.timeout, args.manual_launcher)
        holder = start_holder(handle, token, args.ttl)
    except BaseException:
        release_job(handle, token, ended=False)
        raise
    write_job_record(
        {
            "pid": holder.pid,
            "start_ticks": process_start(holder.pid),
            "token": token,
            "label": label,
            "started": time.time(),
            "expires": time.time() + args.ttl,
            "lease": True,
        }
    )
    handle.close()
    print(token, flush=True)
    return 0


def lease_hold(fd: int, token: str, ttl: float) -> int:
    """Keep the inherited job lock until `release TOKEN`, the ttl, or the session's end.

    The lock arrives as an open file description, so this process holds it without taking it again; the flock is
    released when the process exits and every descriptor of that description is closed.
    """
    handle = os.fdopen(fd, "a+")
    expires = time.monotonic() + ttl
    stopped = {"stop": False}

    def on_signal(_signum, _frame):
        stopped["stop"] = True

    previous = {signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)}
    for signum in previous:
        signal.signal(signum, on_signal)
    try:
        while not stopped["stop"] and time.monotonic() < expires and current_session() is not None:
            time.sleep(1)
    finally:
        restore_handlers(previous)
        release_job(handle, token)
    return 0


def release(token: str) -> int:
    """End a lease: signal its holder, which releases the job lock and its record on the way out."""
    record = job_holder()
    if record is None:
        raise ClientError("no job or lease holds the client")
    if record.get("token") != token:
        raise ClientError(f"that token is not the holder's: {describe_job()}")
    if not record.get("lease"):
        raise ClientError(f"that token is a job's, not a lease's: {describe_job()}")
    try:
        os.kill(record["pid"], signal.SIGTERM)
    except (ProcessLookupError, KeyError, TypeError):
        raise ClientError("the lease's holder is already gone") from None
    # The holder removes its record before it releases the lock, so the record going away is the lease ending. A
    # holder whose pid lingers as a zombie (its parent has not reaped it) has already done both.
    deadline = time.monotonic() + LOGOUT_WAIT
    while time.monotonic() < deadline:
        current = read_job_record()
        if current is None or current.get("token") != token:
            return 0
        time.sleep(0.2)
    raise ClientError(f"the lease's holder {record['pid']} did not release the client within {LOGOUT_WAIT} s")


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
    CONFIG.write_text(json.dumps({"umu_run": script, "env": env}, indent=1, sort_keys=True))
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
    raise ClientError(
        f"DevSmokeDB.eval holds the run {_text(seen.get('run'))!r}, not this snippet's {token!r}: the snippet's own "
        "result was not saved (did the inbox load, and is !!DevSmoke linked and loaded?)"
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


JOB_VERBS = {"shot", "click", "scroll", "key", "slash", "reload", "eval", "errors"}


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
    if not state.get("ready") and not launcher_verb(state, args.verb, getattr(args, "button", None)):
        raise ClientError("the session is not in the world yet: wait for `up` to print READY")
    if args.verb == "shot":
        print(shot(state, args.path or STATE_DIR / f"shot-{int(time.time())}.png"))
    elif args.verb == "click":
        click(state, args.x, args.y, args.button)
    elif args.verb == "scroll":
        scroll(state, args.x, args.y, args.ticks)
    elif args.verb == "key":
        press(state, args.keys)
    elif args.verb == "slash":
        slash(state, args.command)
    elif args.verb == "reload":
        print(f"reloaded ({reload(state).name})")
    elif args.verb == "eval":
        tool = devsmoke_eval()
        cleared = False
        try:
            try:
                # An eval is not a proof flow: it must not schedule a ready screenshot that would race the reload
                # saving its result (#588).
                written = tool.write_snippet(args.file, addons=CLIENT / "Interface/AddOns", capture=False)
            except tool.EvalError as error:
                raise ClientError(str(error)) from None
            print(f"wrote {written['chunk']} from {written['snippet']} ({written['lines']} lines)", flush=True)
            # This reload runs the snippet once. Clearing the inbox before the next reload keeps that reload from
            # running it a second time; that reload saves the first run's result for the reader (#580, #588).
            reload(state)
            clear_eval_inbox()
            cleared = True
            report, ok = eval_result(state, written["token"])
            print(report)
            return 0 if ok else 1
        finally:
            if not cleared:
                clear_eval_inbox(quiet=True)
    elif args.verb == "errors":
        # A shared session's log holds every job's lines: read from where this job's own work started.
        completed = errors({**state, "started": job_started()}, args.addon)
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        return completed.returncode
    return 0


def main(argv: Sequence[str] | None = None) -> int:
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
        p.add_argument("command", nargs=argparse.REMAINDER)
    p = sub.add_parser("lease", help="hold the job lock for an interactive agent and print its token")
    p.add_argument("--ttl", type=float, default=LEASE_TTL, help=f"seconds to hold it, at most {LEASE_MAX}")
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
    p = sub.add_parser("lease-hold")
    p.add_argument("fd", type=int)
    p.add_argument("token")
    p.add_argument("ttl", type=float)
    sub.add_parser("down")
    sub.add_parser("status")
    sub.add_parser("capture-env")
    for name in ("reload", "shot", "click", "scroll", "key", "slash", "eval", "errors"):
        p = sub.add_parser(name)
        p.add_argument("--timeout", type=float, default=600, help="seconds to wait for the job in flight")
        if name == "shot":
            p.add_argument("path", nargs="?", type=Path)
        elif name == "click":
            p.add_argument("x", type=int)
            p.add_argument("y", type=int)
            p.add_argument("--button", default="1", choices=("1", "3"))
        elif name == "scroll":
            p.add_argument("x", type=int)
            p.add_argument("y", type=int)
            p.add_argument("ticks", type=int, help="wheel-up ticks (zoom in) when positive, wheel-down when negative")
        elif name == "key":
            p.add_argument("keys", nargs="+")
        elif name == "slash":
            p.add_argument("command")
        elif name == "eval":
            p.add_argument("file", type=Path, help="the Lua snippet to run through !!DevSmoke at the next reload")
        elif name == "errors":
            p.add_argument("--addon")
    p = sub.add_parser("sv")
    p.add_argument("addon")
    p = sub.add_parser("build-dev", help="write test-artifacts/<repo>-dev from a ref")
    p.add_argument("repo", help="the repository under ~/drive/proj/wow")
    p.add_argument("ref")
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
    p.add_argument(
        "--flow-click",
        action="append",
        default=[],
        metavar="NAME=X,Y",
        help="left click X,Y (screenshot coordinates) for the flow called NAME, after its reload's world screenshot "
        "and before its ready screenshot; a flow that needs a real click to open a protected window",
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
        if args.verb in ("up", "serve"):
            return up(args)
        if args.verb in ("job", "run"):
            return job(args)
        if args.verb == "lease":
            return lease(args)
        if args.verb == "release":
            return release(args.token)
        if args.verb == "lease-hold":
            return lease_hold(args.fd, args.token, args.ttl)
        if args.verb == "down":
            return down()
        if args.verb == "capture-env":
            return capture_env()
        if args.verb == "status":
            print(json.dumps(load_state(), indent=1))
            return 0
        if args.verb == "build-dev":
            # A hand link follows this build, so a record a stopped session left is replayed before it.
            recover_links()
            root = WORKSPACE / args.repo
            commit = git(root, "rev-parse", "--verify", f"{args.ref}^{{commit}}")
            release_tag = tag_name(root, commit)
            if release_tag:
                # A ref at a release tag is that release: point the client back at the store build instead.
                print(
                    f"{args.repo}: {args.ref} is release {release_tag}; "
                    "run: wowaddon --flavor forever sync after removing its dev link"
                )
                return 0
            build_dev(args.repo, commit, repo_root=root)
            return 0
        if args.verb == "smoke":
            return smoke(args)
        if args.verb == "proof":
            return proof(args)
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
        return 2


if __name__ == "__main__":
    sys.exit(main())
