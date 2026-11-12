#!/usr/bin/env python3
"""Run the WoW: Forever client on a private GPU display for agents to test the addons in the real game.

The client runs under gamescope's headless backend: it renders on the real GPU into a display of its own, so no
window reaches the desktop and the player's mouse and keyboard are never touched. Every verb talks to that display
only: screenshots through `gamescopectl`, input through `xdotool` on gamescope's nested X server. The host also
needs `tesseract` on PATH to locate the launcher's visible Play control from the private screenshot.

    forever_client.py up                  # start, wait until in the world, print READY, hold until stopped
    forever_client.py run -- <command>    # up, run the command with the session's display, then stop
    forever_client.py down                # stop the session and everything it started
    forever_client.py status
    forever_client.py shot [PATH]         # PNG of what the client shows now
    forever_client.py click X Y           # left click at a point in the 1920x1080 frame (after a fresh shot)
    forever_client.py key Escape          # Return, Escape or BackSpace
    forever_client.py slash "/fgf"        # open chat, type a Forever addon's slash command, send it
    forever_client.py reload              # /reload and wait for the world to load again
    forever_client.py sv ADDON            # print an addon's SavedVariables (after a reload, they are current)
    forever_client.py errors [--addon X]  # reload, then the Lua errors this session raised (forever_errors.py)
    forever_client.py capture-env         # record the Wine environment from a client Lutris started

One Battle.net account means one client: `up` holds an exclusive lock for the session's lifetime and refuses to
start while any process uses the Wine prefix, which is how a player's own running client is left alone. `--wait`
queues behind another agent's session instead of failing, and keeps waiting until the lock is free and the
previous session's Wine processes have gone, or `--timeout` passes.

The client is for testing the Forever addons' interface, never for playing, and the verbs hold to that:

- Interface only. There is no free typing: `slash` sends only the Forever addons' own commands (read from their
  `SLASH_` globals) and the UI debugging ones in UI_COMMANDS, `key` sends only UI_KEYS, and `click` needs a
  screenshot taken since the last input, so every click aims at UI the agent has just seen. `slash` puts the
  keyboard back in the chat box first, so a focused addon EditBox cannot swallow the command.
- Short sessions. A session ends after MAX_SESSION at the latest, and every ending (the test returning, a failure,
  a signal, the cap) logs the character out and stops the client.
- Human pace. Inputs are at least INPUT_GAP apart, across invocations, and slash commands type at TYPE_DELAY_MS.
"""

from __future__ import annotations

import argparse
import fcntl
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
import time
import uuid
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

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

# The Wine environment Lutris gives the client, minus what belongs to one run or to the desktop. DISPLAY and
# WAYLAND_DISPLAY above all: the session's own come from gamescope, and an inherited Wayland socket would let Wine
# open a window on the player's desktop.
KEEP_PREFIXES = ("WINE", "DXVK_", "VKD3D_", "__GL", "__GLX", "PROTON_", "STAGING_", "LD_", "VK_")
DROP = {"WINESERVERSOCKET", "WINEPRELOADRESERVE", "WINELOADERNOEXEC", "DISPLAY", "WAYLAND_DISPLAY"}


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
            if env.get("WINEPREFIX") == str(prefix):
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
        if env.get("WINEPREFIX") != str(PREFIX) or env.get("FOREVER_CLIENT_SESSION") != token:
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
    return next(
        (p for p in pids() if "Wow.exe" in cmdline(p) and read_environ(p).get("WINEPREFIX") == str(PREFIX)), None
    )


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


def send(state: Mapping, *args: str) -> None:
    """One input action, at least INPUT_GAP after the last one from any invocation."""
    wait = INPUT_GAP - (time.time() - mark("last-input"))
    if wait > 0:
        time.sleep(wait)
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
    send(state, "mousemove", str(px), str(py), "click", button)


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


def press_play(state: Mapping) -> None:
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
        raise ClientError("tesseract is required to locate Battle.net's Play control")
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
        return
    if len(targets) != 1:
        raise ClientError(f"expected one visible Play target in the Battle.net screenshot, found {len(targets)}")
    left, top, width, height, _ = targets[0]
    x(state, "mousemove", str(left + width // 2), str(top + height // 2))
    time.sleep(0.5)
    x(state, "click", "1")


def reload(state: Mapping, timeout: float = 120) -> Path:
    before = screenshots()
    slash(state, "/reload")
    return wait_for_world(before, timeout)


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
    server = Path(wine.get("WINE", "wine")).with_name("wineserver").resolve()
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
            f"no Wine environment recorded: run `forever_client.py capture-env` while Lutris runs the client ({CONFIG})"
        )
    wine = json.loads(CONFIG.read_text())

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
        env.pop("WINEPREFIX", None)
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
                # starts, so the child waits for the whole Wine session instead: the launcher, then `wineserver -w`.
                "sh",
                "-c",
                'WINEPREFIX="$1" "$2" "$3" "$4"; export WINEPREFIX="$1"; exec "$5" -w',
                "forever-client",
                str(PREFIX),
                wine["WINE"],
                str(LAUNCHER),
                *LAUNCH_ARGS,
                str(Path(wine["WINE"]).with_name("wineserver")),
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
        }
        genv = child_env(token)
        state.update(display=genv["DISPLAY"], gamescope_socket=genv["GAMESCOPE_WAYLAND_DISPLAY"])
        state_file().write_text(json.dumps(state))
        print(f"starting: display {state['display']}, log {STATE_DIR / 'session.log'}", flush=True)

        def at_character_select():
            # Enter at the character list enters the world with the last character; before then it does nothing.
            if client_pid():
                x(state, "key", "Return")
            else:
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


def capture_env() -> int:
    pid = client_pid()
    if not pid:
        raise ClientError("no client is running: start it from Lutris once, then run capture-env")
    env = wine_env(read_environ(pid))
    if "WINE" not in env:
        raise ClientError(f"process {pid} has no WINE variable; is it a Lutris launch?")
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(env, indent=1, sort_keys=True))
    print(f"recorded {len(env)} variables from {pid} to {CONFIG}")
    return 0


def saved_variables(addon: str) -> list[Path]:
    account = CLIENT / "WTF/Account"
    return sorted(account.glob(f"*/SavedVariables/{addon}.lua")) + sorted(
        account.glob(f"*/*/*/SavedVariables/{addon}.lua")
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    for name in ("up", "run"):
        p = sub.add_parser(name)
        p.add_argument("--wait", action="store_true", help="queue behind another agent's session")
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
    p = sub.add_parser("errors")
    p.add_argument("--addon")
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
        state = load_state()
        if not state.get("ready"):
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
        elif args.verb == "errors":
            reload(state)
            tool = Path(__file__).resolve().parents[1] / "forever_errors.py"
            cmd = [sys.executable, str(tool), "--since", str(state["started"])]
            if args.addon:
                cmd += ["--addon", args.addon]
            return subprocess.run(cmd, check=False).returncode
        return 0
    except ClientError as error:
        print(f"forever_client: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
