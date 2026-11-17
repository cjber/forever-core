"""A private Hyprland nested inside the user's, for a job client that a Hyprland plugin such as deskpilot drives.

Adapted from cjber/deskpilot's scripts/nested.py (MIT, Copyright (c) cjber): the compositor's own window opens silently
on a hidden special workspace of the user's session and is refused if it lands anywhere else. Inside it, a headless
output renders on its own timer, so it needs no frames from the parent. It reads a minimal config of its own, so none
of the user's autostarts run, and HYPRLAND_NO_SD_* keep it out of the user's systemd environment.

Differences from the original: the headless output sits at the origin at the client's size, with no gaps or borders,
so its pixels are the XWayland root's coordinates and one tiled window fills it; the run directory lives under the
caller's state directory; `start` also reports the nested XWayland DISPLAY; and `stop` takes the record `start`
returned, so a caller that outlived its own process can still stop exactly the compositor it started.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path

RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "hypr"
WORKSPACE = "special:forever-client"
OUTPUT = "FOREVER"
START_WAIT = 15
DISPLAY_WAIT = 10


class NestedError(Exception):
    """The nested compositor could not be started, inspected or stopped as asked."""


def config(width: int, height: int) -> str:
    # The parent window's own output gets no frames while it is on a hidden workspace, and `grim -o` captures every
    # output that intersects the one named, so the two never overlap. The headless output is the one at the origin,
    # which puts its pixels at the same XWayland root coordinates a screenshot of it shows.
    return f"""
hl.monitor({{ output = "", mode = "1280x800", position = "{width + 10000}x0", scale = 1 }})
hl.monitor({{ output = "{OUTPUT}", mode = "{width}x{height}", position = "0x0", scale = 1 }})
hl.config({{
    general = {{ gaps_in = 0, gaps_out = 0, border_size = 0 }},
    decoration = {{ rounding = 0 }},
    misc = {{ disable_hyprland_logo = true, disable_splash_rendering = true }},
    animations = {{ enabled = false }},
}})
"""


def alive(signature: str) -> bool:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        try:
            sock.connect(str(RUNTIME / signature / ".socket.sock"))
        except OSError:
            return False
    return True


def hyprctl(signature: str, *args: str) -> str:
    env = {**os.environ, "HYPRLAND_INSTANCE_SIGNATURE": signature}
    found = subprocess.run(["hyprctl", *args], env=env, capture_output=True, text=True, check=False, timeout=10)
    if found.returncode != 0:
        raise NestedError(f"hyprctl {' '.join(args)} failed: {found.stdout.strip() or found.stderr.strip()}")
    return found.stdout


def user_instance(environ: Mapping[str, str] = os.environ) -> str:
    """The Hyprland that owns this shell's WAYLAND_DISPLAY; other live instances, nested ones included, are not it."""
    found = subprocess.run(["hyprctl", "-j", "instances"], capture_output=True, text=True, check=False, timeout=10)
    try:
        listed = json.loads(found.stdout)
    except ValueError:
        raise NestedError(f"hyprctl lists no Hyprland instances: {found.stderr.strip()}") from None
    display = environ.get("WAYLAND_DISPLAY")
    own = [i["instance"] for i in listed if i.get("wl_socket") == display and alive(i["instance"])]
    if len(own) != 1:
        raise NestedError(f"no live Hyprland owns WAYLAND_DISPLAY={display}: run this from a Hyprland session")
    return own[0]


def process_birth(pid: int) -> str | None:
    """A process's kernel start time, or None after exit, including a zombie waiting for its parent."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else fields[19]
    except (OSError, IndexError):
        return None


def start(parent: str, scratch: Path, width: int, height: int) -> dict:
    """Start a nested Hyprland in a hidden special workspace of `parent` and return its record."""
    scratch.mkdir(parents=True, exist_ok=True)
    # One directory per run, so two runs never share a pid file or config.
    run = Path(tempfile.mkdtemp(prefix="run-", dir=scratch))
    conf, pidfile, log = run / "hyprland.lua", run / "pid", run / "log"
    conf.write_text(config(width, height))
    launcher = run / "run.sh"
    launcher.write_text(
        f"#!/bin/sh\necho $$ > '{pidfile}'\nexec env -u DISPLAY HYPRLAND_NO_SD_VARS=1 "
        f"HYPRLAND_NO_SD_NOTIFY=1 HYPRLAND_NO_CRASHREPORTER=1 Hyprland -c '{conf}' > '{log}' 2>&1\n"
    )
    launcher.chmod(0o755)
    before = {p.name for p in RUNTIME.iterdir()} if RUNTIME.is_dir() else set()
    record = {"run": str(run), "parent": parent}
    # Watch the parent's events before launching, so the nested window's placement is seen as it opens.
    events = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        events.connect(str(RUNTIME / parent / ".socket2.sock"))
        events.settimeout(0.2)
        # The Lua table form: the "[workspace ...]" string prefix is ignored by 0.57's exec_cmd.
        hyprctl(parent, "dispatch", f'hl.dsp.exec_cmd("{launcher}", {{ workspace = "{WORKSPACE} silent" }})')
        record.update(started(events, run, before, width, height, parent))
        return record
    except BaseException as error:
        try:
            stop(record)
        except Exception as cleanup:
            error.add_note(f"nested cleanup failed: {cleanup}")
        raise
    finally:
        events.close()


def started(events: socket.socket, run: Path, before: set[str], width: int, height: int, parent: str) -> dict:
    pidfile = run / "pid"
    deadline, buffer, placed, signature = time.monotonic() + START_WAIT, "", False, None
    while time.monotonic() < deadline and not (placed and signature):
        with contextlib.suppress(TimeoutError):
            buffer += events.recv(65536).decode(errors="replace")
        *lines, buffer = buffer.split("\n")
        for line in lines:
            if line.startswith("openwindow>>") and line.split(",")[2] == "aquamarine":
                if line.split(",")[1] != WORKSPACE:
                    raise NestedError(f"the nested window opened outside {WORKSPACE} ({line}); it was stopped")
                placed = True
        new = [n for n in {p.name for p in RUNTIME.iterdir()} - before if alive(n)]
        # Match the compositor to this launcher, rather than another concurrently started nested instance.
        with contextlib.suppress(OSError, ValueError):
            pid = int(pidfile.read_text())
            instances = json.loads(hyprctl(parent, "-j", "instances"))
            signature = next((i["instance"] for i in instances if i.get("pid") == pid and i["instance"] in new), None)
    if not (placed and signature):
        raise NestedError(f"the nested Hyprland did not come up; see {run / 'log'}")
    pid = int(pidfile.read_text())
    birth = process_birth(pid)
    record = {"signature": signature, "pid": pid, "birth": birth}
    (run / "record.json").write_text(json.dumps(record))
    clients = json.loads(hyprctl(parent, "-j", "clients"))
    own_windows = [c for c in clients if c.get("pid") == pid]
    if not own_windows or any(c.get("workspace", {}).get("name") != WORKSPACE for c in own_windows):
        raise NestedError(f"the nested compositor's own window is not on {WORKSPACE}; it was stopped")
    hyprctl(signature, "output", "create", "headless", OUTPUT)
    for _ in range(50):
        if any(m["name"] == OUTPUT for m in json.loads(hyprctl(signature, "-j", "monitors"))):
            break
        time.sleep(0.1)
    else:
        raise NestedError(f"the nested Hyprland made no {OUTPUT} output")
    hyprctl(signature, "dispatch", f'hl.dsp.focus({{ monitor = "{OUTPUT}" }})')
    wayland = next(
        i["wl_socket"] for i in json.loads(hyprctl(signature, "-j", "instances")) if i["instance"] == signature
    )
    display = xwayland_display(signature, run)
    return {**record, "wayland": wayland, "output": OUTPUT, "display": display, "origin": xwayland_origin(display)}


def xwayland_display(signature: str, run: Path) -> str:
    """The nested compositor's XWayland DISPLAY, read from a child it starts, which inherits it."""
    target = run / "display"
    hyprctl(signature, "dispatch", f'hl.dsp.exec_cmd("sh -c \'printf %s \\"$DISPLAY\\" > {target}\'")')
    deadline = time.monotonic() + DISPLAY_WAIT
    while time.monotonic() < deadline:
        with contextlib.suppress(OSError):
            display = target.read_text().strip()
            if display:
                return display
        time.sleep(0.1)
    raise NestedError("the nested Hyprland reported no XWayland DISPLAY")


def xwayland_origin(display: str) -> list[int]:
    """Where the headless output sits in XWayland's root window.

    XWayland lays the outputs out by its own order, not by the compositor's positions, so an absolute XTEST point is
    the output's pixel plus this offset. `xrandr --listmonitors` names each output with its root geometry.
    """
    for _ in range(50):
        found = subprocess.run(
            ["xrandr", "--listmonitors"],
            env={**os.environ, "DISPLAY": display},
            capture_output=True,
            text=True,
            timeout=2,
        )
        for line in found.stdout.splitlines():
            words = line.split()
            if len(words) >= 3 and words[-1] == OUTPUT:
                _size, x, y = words[2].split("+")
                return [int(x), int(y)]
        time.sleep(0.1)
    raise NestedError(f"XWayland on {display} lists no {OUTPUT} output")


def window(record: Mapping, title: str) -> dict | None:
    """The nested compositor's window with this exact title, as deskpilot addresses it, or None."""
    for client in json.loads(hyprctl(str(record["signature"]), "-j", "clients")):
        if client.get("title") == title:
            return {"address": client["address"], "title": client["title"], "class": client.get("class")}
    return None


def running(record: Mapping) -> bool:
    """Whether the recorded compositor still runs and answers on its socket."""
    pid, birth = record.get("pid"), record.get("birth")
    if not isinstance(pid, int) or birth is None or process_birth(pid) != birth:
        return False
    return alive(str(record.get("signature")))


def stop(record: Mapping) -> None:
    """Stop only the recorded compositor, wait for it to exit, then remove its runtime and run directories."""
    run = Path(str(record.get("run", "")))
    with contextlib.suppress(OSError, ValueError):
        record = {**json.loads((run / "record.json").read_text()), **record}
    signature, pid, birth = record.get("signature"), record.get("pid"), record.get("birth")
    if not isinstance(pid, int):
        with contextlib.suppress(OSError, ValueError):
            pid = int((run / "pid").read_text())
            birth = process_birth(pid)
    if isinstance(signature, str) and alive(signature):
        # A wedged IPC socket must not prevent stopping the process whose birth time we recorded.
        listed = None
        with contextlib.suppress(NestedError, subprocess.TimeoutExpired, ValueError):
            listed = json.loads(hyprctl(signature, "-j", "instances"))
        if listed is not None and not any(i["instance"] == signature and i["pid"] == pid for i in listed):
            raise NestedError(f"{signature} does not belong to the run in {run}; refusing to stop it")
        with contextlib.suppress(NestedError, subprocess.TimeoutExpired):
            hyprctl(signature, "dispatch", "hl.dsp.exit()")
    if isinstance(pid, int) and birth is not None:
        for sig in (None, signal.SIGTERM, signal.SIGKILL):
            if sig is not None and process_birth(pid) == birth:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, sig)
            for _ in range(50):
                if process_birth(pid) != birth:
                    break
                time.sleep(0.1)
            else:
                continue
            break
        if process_birth(pid) == birth:
            raise NestedError(f"nested Hyprland {pid} did not exit; keeping {run}")
    if isinstance(signature, str) and signature:
        if alive(signature):
            raise NestedError(f"{signature} still accepts connections; keeping its runtime directory")
        runtime = RUNTIME / signature
        if runtime.parent == RUNTIME and runtime.is_dir() and not runtime.is_symlink():
            shutil.rmtree(runtime)
    if run.name.startswith("run-") and run.is_dir():
        shutil.rmtree(run)
