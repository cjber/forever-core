#!/usr/bin/env python3
"""Run the WoW: Forever client on a private GPU display for agents to test the addons in the real game.

The client runs under gamescope's headless backend: it renders on the real GPU into a display of its own, so no
window reaches the desktop and the player's mouse and keyboard are never touched. Every verb talks to that display
only: screenshots through `gamescopectl`, input through `xdotool` on gamescope's nested X server.

    forever_client.py up                  # start, wait until in the world, print READY, hold until stopped
    forever_client.py run -- <command>    # up, run the command with the session's display, then stop
    forever_client.py down                # stop the session and everything it started
    forever_client.py status
    forever_client.py shot [PATH]         # PNG of what the client shows now
    forever_client.py click X Y           # left click at a point in the 1920x1080 frame
    forever_client.py key Return          # xdotool key names
    forever_client.py type "text"
    forever_client.py slash "/reload"     # open chat, type a slash command, send it
    forever_client.py reload              # /reload and wait for the world to load again
    forever_client.py sv ADDON            # print an addon's SavedVariables (after a reload, they are current)
    forever_client.py errors [--addon X]  # reload, then the Lua errors this session raised (forever_errors.py)
    forever_client.py capture-env         # record the Wine environment from a client Lutris started

One Battle.net account means one client: `up` holds an exclusive lock for the session's lifetime and refuses to
start while any process uses the Wine prefix, which is how a player's own running client is left alone. `--wait`
queues behind another agent's session instead of failing.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
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
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "forever-client"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "forever-client/env.json"
ADDON = Path(__file__).resolve().parent / "!!ForeverHeadless"
WIDTH, HEIGHT = 1920, 1080

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


def prefix_users(prefix: Path = PREFIX, exclude: Iterable[int] = ()) -> list[int]:
    """Processes running in the Wine prefix: a player's client, its launcher, or a wineserver left behind."""
    skip = set(exclude)
    return [p for p in pids() if p not in skip and read_environ(p).get("WINEPREFIX") == str(prefix)]


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


def shot(state: Mapping, path: Path) -> Path:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GAMESCOPE_WAYLAND_DISPLAY": state["gamescope_socket"]}
    subprocess.run(["gamescopectl", "screenshot", str(path)], env=env, check=True, capture_output=True)
    for _ in range(50):
        if path.exists() and path.stat().st_size > 0:
            return path
        time.sleep(0.1)
    raise ClientError(f"gamescope wrote no screenshot to {path}")


def slash(state: Mapping, command: str) -> None:
    x(state, "key", "Return")
    time.sleep(0.3)
    x(state, "type", "--delay", "40", command)
    time.sleep(0.2)
    x(state, "key", "Return")


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


def teardown(gamescope: subprocess.Popen | None, wine: Mapping[str, str], link: Path | None) -> None:
    if gamescope and gamescope.poll() is None:
        os.killpg(gamescope.pid, signal.SIGTERM)
        try:
            gamescope.wait(20)
        except subprocess.TimeoutExpired:
            os.killpg(gamescope.pid, signal.SIGKILL)
    # The lock and the prefix check make every process in the prefix this session's: end them all.
    server = Path(wine.get("WINE", "wine")).with_name("wineserver")
    subprocess.run([str(server), "-k"], env={**os.environ, **wine, "WINEPREFIX": str(PREFIX)}, check=False)
    for p in prefix_users():
        try:
            os.kill(p, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if link and link.is_symlink():
        link.unlink()
    state_file().unlink(missing_ok=True)


def up(args: argparse.Namespace, after_ready=None) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(STATE_DIR / "lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | (0 if args.wait else fcntl.LOCK_NB))
    except BlockingIOError:
        held = state_file().read_text() if state_file().exists() else "{}"
        raise ClientError(f"another agent's session holds the client: {held}; pass --wait to queue") from None
    users = prefix_users()
    if users:
        game = client_pid()
        who = (
            f"the player's client is running (Wow.exe, pid {game})"
            if game
            else f"{len(users)} Wine processes still run in it"
        )
        raise ClientError(
            f"the Wine prefix {PREFIX} is in use: {who}. "
            "A second client would log the first one out, so no session starts."
        )
    if not CONFIG.exists():
        raise ClientError(
            f"no Wine environment recorded: run `forever_client.py capture-env` while Lutris runs the client ({CONFIG})"
        )
    wine = json.loads(CONFIG.read_text())

    link = CLIENT / "Interface/AddOns" / ADDON.name
    gamescope: subprocess.Popen | None = None
    stop = {"signal": None}

    def on_signal(signum, _frame):
        stop["signal"] = signum
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    log = open(STATE_DIR / "session.log", "w")
    try:
        if not link.exists():
            link.symlink_to(ADDON)
        env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")}
        env.update(wine)
        token = uuid.uuid4().hex
        env.update({"WINEPREFIX": str(PREFIX), "FOREVER_CLIENT_SESSION": token})
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
                wine["WINE"],
                str(LAUNCHER),
                *LAUNCH_ARGS,
            ],
            cwd=LAUNCHER.parent,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        genv = child_env(token)
        state = {
            "pid": os.getpid(),
            "gamescope": gamescope.pid,
            "display": genv["DISPLAY"],
            "gamescope_socket": genv["GAMESCOPE_WAYLAND_DISPLAY"],
            "started": started,
        }
        state_file().write_text(json.dumps(state))
        print(f"starting: display {state['display']}, log {STATE_DIR / 'session.log'}", flush=True)

        def at_character_select():
            # Enter at the character list enters the world with the last character; before then it does nothing.
            if client_pid():
                x(state, "key", "Return")

        try:
            ready = wait_for_world(before, args.timeout, nudge=at_character_select)
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
        return 0
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        teardown(gamescope, wine, link)
        print("stopped: gamescope, Wine and the dev addon link are gone", flush=True)


def down() -> int:
    state = load_state()
    os.kill(state["pid"], signal.SIGTERM)
    for _ in range(60):
        if not state_file().exists():
            return 0
        time.sleep(0.5)
    raise ClientError(f"session {state['pid']} did not stop within 30 s")


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
        p.add_argument("--timeout", type=float, default=600, help="seconds to reach the world")
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
    p.add_argument("--button", default="1")
    p = sub.add_parser("key")
    p.add_argument("keys", nargs="+")
    p = sub.add_parser("type")
    p.add_argument("text")
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
                env = {**os.environ, "FOREVER_CLIENT_DISPLAY": state["display"]}
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
        if args.verb == "shot":
            print(shot(state, args.path or STATE_DIR / f"shot-{int(time.time())}.png"))
        elif args.verb == "click":
            x(state, "mousemove", str(args.x), str(args.y), "click", args.button)
        elif args.verb == "key":
            x(state, "key", *args.keys)
        elif args.verb == "type":
            x(state, "type", "--delay", "40", args.text)
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
