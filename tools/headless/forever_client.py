#!/usr/bin/env python3
"""Run the WoW: Forever client on a private GPU display for agents to test the addons in the real game.

The client runs under gamescope's headless backend: it renders on the real GPU into a display of its own, so no
window reaches the desktop and the player's mouse and keyboard are never touched. Every verb talks to that display
only: screenshots through `gamescopectl`, input through `xdotool` on gamescope's nested X server. The host also
needs `tesseract` on PATH to locate the launcher's visible Play control from the private screenshot.

    forever_client.py up                  # start, wait until in the world, print READY, hold until stopped
    forever_client.py up --manual-launcher # inspect and left-click the private launcher instead of OCR
    forever_client.py run -- <command>    # up, run the command with the session's display, then stop
    forever_client.py down                # stop the session and everything it started
    forever_client.py status
    forever_client.py shot [PATH]         # PNG of what the client shows now
    forever_client.py click X Y           # left click at a point in the 1920x1080 frame (after a fresh shot)
    forever_client.py key Escape          # Return, Escape or BackSpace
    forever_client.py slash "/fgf"        # open chat, type a Forever addon's slash command, send it
    forever_client.py reload              # /reload and wait for the world to load again
    forever_client.py sv ADDON            # print an addon's SavedVariables (after a reload, they are current)
    forever_client.py eval FILE           # write FILE into !!DevSmoke's inbox, reload, print DevSmokeDB.eval
    forever_client.py errors [--addon X]  # reload, then the Lua errors this session raised (forever_errors.py)
    forever_client.py capture-env         # record the launch from the player's client started in Faugus
    forever_client.py build-dev REPO REF  # test-artifacts/<repo>-dev from a ref, the dev build rebuild-dev.sh made
    forever_client.py smoke --repo R --ref SHA  # build that commit, selftest it, post the headless-smoke status

`smoke` is the release gate: it builds the dev archive of the commit a release would ship, links its addon folders
over the client's, runs `/forever selftest` and `errors --addon` for each of them, and posts the result on that exact
commit as the `headless-smoke` commit status, which `tools/release_check.py` requires and `tools/smoke_queue.py`
fills in. It starts the client the way `up` does, and `--manual-launcher` is passed through to it, so while launcher
OCR is not finding Play (cjber/forever-core#547) an agent runs `smoke --manual-launcher` in the background, takes
`shot` and clicks Play itself. Exit 0 is a clean commit, 1 a recorded failure, 3 means the client is in use (the
player's game or another session) so nothing is posted and a caller retries later. The AddOns folder is shared: every
slot the smoke borrows is put back exactly as it was, including a store install it moved aside.

One Battle.net account means one client: `up` holds an exclusive lock for the session's lifetime and refuses to
start while any process uses the Wine prefix, which is how a player's own running client is left alone. `--wait`
queues behind another agent's session instead of failing, and keeps waiting until the lock is free and the
previous session's Wine processes have gone, or `--timeout` passes.

The client is for testing the Forever addons' interface, never for playing, and the verbs hold to that:

- Interface only. There is no free typing: `slash` sends only the Forever addons' own commands (read from their
  `SLASH_` globals) and the UI debugging ones in UI_COMMANDS, `key` sends only UI_KEYS, and `click` needs a
  screenshot taken since the last input, so every click aims at UI the agent has just seen. `slash` puts the
  keyboard back in the chat box first, so a focused addon EditBox cannot swallow the command.
- `--manual-launcher` (`up`, `run`, `smoke`) disables OCR clicks and permits shots and left clicks before READY,
  only while the game process is absent. Inspect each private screenshot before clicking. Never click Uninstall or
  change credentials.
- Short sessions. A session ends after MAX_SESSION at the latest, and every ending (the test returning, a failure,
  a signal, the cap) logs the character out and stops the client.
- Human pace. Inputs are at least INPUT_GAP apart, across invocations, and slash commands type at TYPE_DELAY_MS.
"""

from __future__ import annotations

import argparse
import fcntl
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
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

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
STATUS_LIMIT = 140

PREFIX = Path.home() / "Games/battlenet"
CLIENT = PREFIX / "drive_c/Program Files (x86)/World of Warcraft/_forever_"
LAUNCHER = PREFIX / "drive_c/Program Files (x86)/Battle.net/Battle.net.exe"
LAUNCH_ARGS = ["--exec=launch_uid wowf"]
# Battle.net ignores --exec once it is logged in, so the session presses the visible Play control on the WoW: Forever
# page that --exec opens. The target is read from the private gamescope screenshot, in its own pixel coordinates.
# The account's Battle.net region: the launcher logs in here before it can start the game.
BATTLE_NET = ("eu.actual.battle.net", 1119)
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "forever-client"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "forever-client/env.json"
ADDON = Path(__file__).resolve().parent / "!!ForeverHeadless"
WIDTH, HEIGHT = 1920, 1080
MAX_SESSION = 30 * 60
WAIT_POLL = 1.0  # how often a `--wait` queue checks the lock and the Wine prefix
LOGOUT_WAIT = 60  # /quit outside an inn counts down 20 s before the client exits
INPUT_GAP = 1.5
TYPE_DELAY_MS = "120"
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


# --- session state ---------------------------------------------------------------------------------------------


def state_file() -> Path:
    return STATE_DIR / "session.json"


def load_state() -> dict:
    try:
        return json.loads(state_file().read_text())
    except (OSError, ValueError):
        raise ClientError("no headless session is running: start one with `forever_client.py up`") from None


def screenshots() -> set[Path]:
    folder = CLIENT / "Screenshots"
    return set(folder.glob("*")) if folder.is_dir() else set()


def wait_for_world(before: set[Path], timeout: float, nudge=None) -> Path:
    """Block until the dev addon's screenshot appears: the world has loaded. `nudge` runs every 15 s meanwhile."""
    deadline, next_nudge = time.monotonic() + timeout, time.monotonic() + 20
    while time.monotonic() < deadline:
        new = screenshots() - before
        if new:
            return max(new, key=lambda p: p.stat().st_mtime)
        if nudge and time.monotonic() >= next_nudge:
            nudge()
            next_nudge = time.monotonic() + 15
        time.sleep(1)
    raise ClientError(f"the world did not load within {timeout:.0f} s")


# --- display verbs ---------------------------------------------------------------------------------------------


def x(state: Mapping, *args: str) -> None:
    subprocess.run(["xdotool", *args], env={**os.environ, "DISPLAY": state["display"]}, check=True)


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


def press_play(state: dict) -> None:
    """Find and click the visible Play label in the launcher's current screenshot.

    Battle.net changes its page layout with the gamescope size and can show a login
    dialog before the game page. A fixed point therefore either misses Play or clicks
    another control. OCR is bounded to the private gamescope screenshot, so the
    click remains screenshot-bound like the public ``click`` verb.
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
    ocr = subprocess.run(
        ["tesseract", str(image), "stdout", "--psm", "11", "tsv"],
        capture_output=True,
        text=True,
        check=False,
    )
    if ocr.returncode != 0:
        raise ClientError(f"could not read the Battle.net Play target: {ocr.stderr.strip()}")
    targets = []
    for line in ocr.stdout.splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) != 12 or fields[11].strip().casefold() != "play":
            continue
        try:
            left, top, width, height = (int(fields[i]) for i in (6, 7, 8, 9))
            confidence = float(fields[10])
        except (ValueError, TypeError):
            continue
        if confidence >= 0 and width > 0 and height > 0:
            targets.append((left, top, width, height, confidence))
    if not targets:
        # The launcher can still be painting its signed-in page. The startup loop
        # retries within its existing deadline; never click an unobserved target.
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


def reload(state: Mapping, timeout: float = 120) -> Path:
    before = screenshots()
    slash(state, "/reload")
    return wait_for_world(before, timeout)


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
            link_record_path().write_text(json.dumps(records))
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


def client_in_use() -> str | None:
    """Why no session can start now, or None: the player's client, another session's lock, or Wine in the prefix."""
    users = prefix_users()
    if users:
        return prefix_who(users)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        lock = open(STATE_DIR / "lock", "w")
    except OSError:
        return None
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return "another session holds the client"
    finally:
        lock.close()
    return None


def stop_handlers() -> dict[int, object]:
    """Turn SIGTERM and SIGINT into a KeyboardInterrupt so a smoke puts the AddOns links back before it exits."""
    previous = {signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGINT)}

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


def smoke_description(counts: Mapping[str, int]) -> str:
    """The commit status's text: the error count, or that the addon folders are clean."""
    total = sum(counts.values())
    if not total:
        folders = len(counts)
        return f"clean: no Lua errors in {folders} addon folder{'s' if folders != 1 else ''}"
    named = ", ".join(f"{count} {name}" for name, count in counts.items() if count)
    return f"{total} Lua error{'s' if total != 1 else ''}: {named}"[:STATUS_LIMIT]


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


def smoke(args: argparse.Namespace) -> int:
    """Build a repository's commit, test it in the client, and record the result as a commit status.

    Exit 0 is a clean commit and 1 a failure that was recorded; 3 means the client is in use, so nothing is posted and
    a caller retries later. A smoke that could not run at all (no checkout, no such ref) raises ClientError and posts
    nothing either. `--manual-launcher` reaches `up` unchanged, so the caller can take `shot` and click Play itself.
    """
    repo = args.repo
    if not SMOKE_REPO.fullmatch(repo):
        raise ClientError(f"--repo takes a repository name, not {repo!r}")
    root = WORKSPACE / repo
    if not root.is_dir():
        raise ClientError(f"no checkout of {repo} in {WORKSPACE}")
    commit = git(root, "rev-parse", "--verify", f"{args.ref}^{{commit}}")
    busy = client_in_use()
    if busy:
        print(f"client in use: {busy}; nothing posted on {repo}@{commit[:7]}", flush=True)
        return 3
    folder = build_dev(repo, commit, destination=BUILD_ROOT / f"{repo}-smoke", repo_root=root)
    folders = addon_folders(folder, package_name(root, commit))
    if not folders:
        raise ClientError(f"{folder} ships no addon folder")
    outcome: dict = {"counts": {}, "error": None}
    previous = stop_handlers()
    try:
        records = link_build(folders, addons_dir())
        try:

            def checks(state):
                slash(state, "/forever selftest")
                # The selftest is synchronous Lua; the reload `errors` makes settles it and writes SavedVariables.
                outcome["counts"] = smoke_counts(state, folders)
                return 0

            options = argparse.Namespace(wait=False, manual_launcher=args.manual_launcher, timeout=args.timeout)
            try:
                up(options, after_ready=checks)
            except ClientError as error:
                busy = client_in_use()
                if not outcome["counts"] and busy:
                    print(f"client in use: {busy}; nothing posted on {repo}@{commit[:7]}", flush=True)
                    return 3
                outcome["error"] = str(error)
        finally:
            restore_links(records)
    except KeyboardInterrupt:
        print(f"smoke of {repo}@{commit[:7]} stopped before it finished; nothing posted", file=sys.stderr)
        return 1
    finally:
        restore_handlers(previous)
    counts = outcome["counts"]
    if outcome["error"]:
        print(f"{repo}@{commit[:7]}: {outcome['error']}", file=sys.stderr)
    if not counts and not outcome["error"]:
        # `up` returns normally when a signal ends the session it holds, so a stopped smoke is not a result.
        print(f"smoke of {repo}@{commit[:7]} stopped before it finished; nothing posted", file=sys.stderr)
        return 1
    if not counts:
        description = f"no result: {outcome['error'] or 'the session ended before the checks ran'}"
        post_status(repo, commit, False, description)
        print(f"{repo}@{commit[:7]}: {description} ({SMOKE_CONTEXT} posted)", flush=True)
        return 1
    ok = not any(counts.values())
    description = smoke_description(counts)
    post_status(repo, commit, ok, description)
    print(f"{repo}@{commit[:7]}: {description} ({SMOKE_CONTEXT} posted)", flush=True)
    return 0 if ok else 1


# --- session lifecycle -----------------------------------------------------------------------------------------


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
    raise ClientError("gamescope started no client: see the session log")


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


def teardown(
    gamescope: subprocess.Popen | None, wine: Mapping[str, str], link: Path | None, state: Mapping | None
) -> None:
    token = state.get("token") if state else None
    require_owned_prefix(token)
    # Only a session in the world types /quit: at the character list Enter would enter the world instead.
    if state and state.get("ready") and gamescope and gamescope.poll() is None and client_pid():
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
    if gamescope and gamescope.poll() is None:
        gamescope.terminate()
        try:
            gamescope.wait(20)
        except subprocess.TimeoutExpired:
            gamescope.kill()
            gamescope.wait(20)
    if link and link.is_symlink():
        link.unlink()
    state_file().unlink(missing_ok=True)


def lock_holder() -> str:
    """The state of the session that holds the lock, for a waiter's message."""
    return state_file().read_text() if state_file().exists() else "{}"


def prefix_who(users: Sequence[int]) -> str:
    """Who is using the Wine prefix, for the sentence `up` prints when it refuses to start."""
    game = client_pid()
    return (
        f"the player's client is running (Wow.exe, pid {game})"
        if game
        else f"{len(users)} Wine processes still run in it"
    )


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


def up(args: argparse.Namespace, after_ready=None) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(STATE_DIR / "lock", "w")
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
    wine = launch["env"]

    link = CLIENT / "Interface/AddOns" / ADDON.name
    gamescope: subprocess.Popen | None = None
    state: dict | None = None
    stop = {"signal": None}

    def on_signal(signum, _frame):
        stop["signal"] = signum
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGALRM, on_signal)
    signal.alarm(MAX_SESSION)
    log = open(STATE_DIR / "session.log", "w")
    try:
        if not link.exists():
            link.symlink_to(ADDON)
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
        state = {
            "pid": os.getpid(),
            "gamescope": gamescope.pid,
            "token": token,
            "started": started,
            "runtime_dir": str(runtime),
            "manual_launcher": args.manual_launcher,
        }
        genv = child_env(token)
        state.update(display=genv["DISPLAY"], gamescope_socket=genv["GAMESCOPE_WAYLAND_DISPLAY"])
        state_file().write_text(json.dumps(state))
        print(f"starting: display {state['display']}, log {STATE_DIR / 'session.log'}", flush=True)

        def at_character_select():
            # Enter at the character list enters the world with the last character; before then it does nothing.
            if client_pid():
                send(state, "key", "Return")
            elif not args.manual_launcher:
                press_play(state)

        try:
            ready = wait_for_world(before, min(args.timeout, MAX_SESSION), nudge=at_character_select)
        except ClientError as error:
            frame = shot(state, STATE_DIR / "failed.png")
            raise ClientError(f"{error}; last frame: {frame}") from None
        state["ready"] = time.time()
        state_file().write_text(json.dumps(state))
        print(f"READY in the world after {time.time() - started:.0f} s ({ready.name})", flush=True)
        if after_ready:
            return after_ready(state)
        while gamescope.poll() is None:
            time.sleep(1)
        raise ClientError("the client exited on its own")
    except KeyboardInterrupt:
        if stop["signal"] == signal.SIGALRM:
            print(f"forever_client: the session reached its {MAX_SESSION // 60} min cap", file=sys.stderr)
            return 2
        return 0
    finally:
        signal.alarm(0)
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
            signal.signal(signum, signal.SIG_IGN)
        teardown(gamescope, wine, link, state)
        print("stopped: logged out, gamescope, Wine and the dev addon link are gone", flush=True)


def down() -> int:
    state = load_state()
    os.kill(state["pid"], signal.SIGTERM)
    # Teardown logs out (up to LOGOUT_WAIT), then gives gamescope 20 s and ends Wine.
    limit = LOGOUT_WAIT + 60
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if not state_file().exists():
            return 0
        time.sleep(0.5)
    raise ClientError(f"session {state['pid']} did not stop within {limit} s")


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


def saved_eval() -> dict:
    """DevSmokeDB.eval from the newest SavedVariables file the client wrote for !!DevSmoke."""
    files = saved_variables("!!DevSmoke")
    if not files:
        raise ClientError("no SavedVariables for !!DevSmoke: the client writes them at a reload or logout")
    lua = load_tool("forever_errors", Path(__file__).resolve().parents[1] / "forever_errors.py")
    for path in sorted(files, key=lambda candidate: candidate.stat().st_mtime, reverse=True):
        try:
            variables = lua.load_lua(path)
        except (OSError, lua.LuaSyntaxError) as error:
            raise ClientError(f"could not read {path}: {error}") from None
        smoke = variables.get("DevSmokeDB")
        data = smoke.get("eval") if isinstance(smoke, dict) else None
        if isinstance(data, dict):
            return data
    raise ClientError("DevSmokeDB.eval is missing: the snippet did not run (is !!DevSmoke linked and loaded?)")


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    for name in ("up", "run"):
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
        if name == "run":
            p.add_argument("command", nargs=argparse.REMAINDER)
    sub.add_parser("down")
    sub.add_parser("status")
    sub.add_parser("capture-env")
    sub.add_parser("reload")
    p = sub.add_parser("shot")
    p.add_argument("path", nargs="?", type=Path)
    p = sub.add_parser("click")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("--button", default="1", choices=("1", "3"))
    p = sub.add_parser("key")
    p.add_argument("keys", nargs="+")
    p = sub.add_parser("slash")
    p.add_argument("command")
    p = sub.add_parser("sv")
    p.add_argument("addon")
    p = sub.add_parser("eval")
    p.add_argument("file", type=Path, help="the Lua snippet to run through !!DevSmoke at the next reload")
    p = sub.add_parser("errors")
    p.add_argument("--addon")
    p = sub.add_parser("build-dev", help="write test-artifacts/<repo>-dev from a ref")
    p.add_argument("repo", help="the repository under ~/drive/proj/wow")
    p.add_argument("ref")
    p = sub.add_parser("smoke", help="build the commit a release would ship, test it, and post its status")
    p.add_argument("--repo", required=True, help="the repository under ~/drive/proj/wow, such as legacy-forever")
    p.add_argument("--ref", required=True, help="the commit the next release would ship")
    p.add_argument("--timeout", type=float, default=600, help="seconds to reach the world")
    p.add_argument(
        "--manual-launcher",
        action="store_true",
        help="disable launcher OCR clicks; allow shot and fresh-screenshot left clicks before READY",
    )
    args = parser.parse_args(argv)

    try:
        if args.verb == "up":
            return up(args)
        if args.verb == "run":
            command = [c for c in args.command if c != "--"]
            if not command:
                raise ClientError("run needs a command after --")

            def run_command(state):
                env = {
                    **os.environ,
                    "XDG_RUNTIME_DIR": state["runtime_dir"],
                    "FOREVER_CLIENT_DISPLAY": state["display"],
                }
                return subprocess.run(command, env=env, check=False).returncode

            return up(args, after_ready=run_command)
        if args.verb == "down":
            return down()
        if args.verb == "capture-env":
            return capture_env()
        if args.verb == "status":
            print(json.dumps(load_state(), indent=1))
            return 0
        if args.verb == "build-dev":
            root = WORKSPACE / args.repo
            commit = git(root, "rev-parse", "--verify", f"{args.ref}^{{commit}}")
            release = tag_name(root, commit)
            if release:
                # A ref at a release tag is that release: point the client back at the store build instead.
                print(
                    f"{args.repo}: {args.ref} is release {release}; "
                    "run: wowaddon --flavor forever sync after removing its dev link"
                )
                return 0
            build_dev(args.repo, commit, repo_root=root)
            return 0
        if args.verb == "smoke":
            return smoke(args)
        state = load_state()
        launcher_action = state.get("manual_launcher") and (
            args.verb == "shot" or (args.verb == "click" and args.button == "1")
        )
        if not state.get("ready") and not launcher_action:
            raise ClientError("the session is not in the world yet: wait for `up` to print READY")
        if args.verb == "shot":
            print(shot(state, args.path or STATE_DIR / f"shot-{int(time.time())}.png"))
        elif args.verb == "click":
            click(state, args.x, args.y, args.button)
        elif args.verb == "key":
            press(state, args.keys)
        elif args.verb == "slash":
            slash(state, args.command)
        elif args.verb == "reload":
            print(f"reloaded ({reload(state).name})")
        elif args.verb == "sv":
            files = saved_variables(args.addon)
            if not files:
                raise ClientError(f"no SavedVariables for {args.addon}: it writes them at a reload or logout")
            for f in files:
                print(f"-- {f}\n{f.read_text(errors='replace')}")
        elif args.verb == "eval":
            tool = devsmoke_eval()
            try:
                written = tool.write_snippet(args.file, addons=CLIENT / "Interface/AddOns")
            except tool.EvalError as error:
                raise ClientError(str(error)) from None
            print(f"wrote {written['chunk']} from {written['snippet']} ({written['lines']} lines)", flush=True)
            reload(state)
            report, ok = format_eval(saved_eval())
            print(report)
            return 0 if ok else 1
        elif args.verb == "errors":
            completed = errors(state, args.addon)
            sys.stdout.write(completed.stdout)
            sys.stderr.write(completed.stderr)
            return completed.returncode
        return 0
    except ClientError as error:
        print(f"forever_client: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
