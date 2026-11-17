"""Launch, stop and reset the addon manager apps in isolated state dirs.

Each app runs under its own HOME and XDG dirs, a private D-Bus session (so no file chooser,
keyring or notification reaches the real desktop) and its own Xvfb display.
"""

import json
import os
import shutil
import signal
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path
from typing import TypedDict

ROOT = Path(os.environ.get("MANAGER_LIFECYCLE_ROOT", "~/.cache/agent-scratch/manager-lifecycle")).expanduser().resolve()
FAKE = (
    Path(os.environ.get("MANAGER_LIFECYCLE_CLIENT", str(ROOT / "fakewow" / "World of Warcraft"))).expanduser().resolve()
)
FOREVER = FAKE / "_forever_"
ADDONS = FOREVER / "Interface" / "AddOns"
METADATA = Path(os.environ.get("MANAGER_LIFECYCLE_METADATA", str(ROOT / "metadata"))).expanduser().resolve()
STATE = Path(os.environ.get("MANAGER_LIFECYCLE_STATE", str(ROOT / "state"))).expanduser().resolve()
LOGS = Path(os.environ.get("MANAGER_LIFECYCLE_LOGS", str(ROOT / "logs"))).expanduser().resolve()


class AppConfig(TypedDict):
    bin: Path
    port: int
    userdata: str


APPS: dict[str, AppConfig] = {
    "wowup": {
        "bin": Path(
            os.environ.get("MANAGER_LIFECYCLE_WOWUP_BIN", str(ROOT / "dl/wux/squashfs-root/wowup-cf"))
        ).expanduser(),
        "port": 9301,
        "userdata": "config/WowUpCf",
    },
    "curseforge": {
        "bin": Path(
            os.environ.get("MANAGER_LIFECYCLE_CF_BIN", str(ROOT / "dl/cfx/squashfs-root/curseforge"))
        ).expanduser(),
        "port": 9302,
        "userdata": "config/CurseForge",
    },
}


def validate_paths():
    """Only reset marked disposable storage, never a checkout or a live installation."""
    repo = Path(__file__).resolve().parents[2]
    for path in (ROOT, FAKE, STATE, LOGS):
        if path == repo or repo in path.parents or path in repo.parents:
            raise ValueError(f"Harness storage must be outside the repository: {path}")
    for path in (FAKE, STATE, LOGS):
        if ROOT not in path.parents:
            raise ValueError(f"Reset targets must be beneath MANAGER_LIFECYCLE_ROOT: {path}")
    for target in (FAKE, STATE):
        if METADATA == target or target in METADATA.parents:
            raise ValueError(f"Metadata must be outside reset targets: {METADATA}")
    marker = ROOT / ".manager-lifecycle-disposable"
    if not marker.is_file():
        raise ValueError(f"Create {marker} in a dedicated scratch folder before running")
    for exe in FAKE.rglob("Wow.exe"):
        if exe.stat().st_size:
            raise ValueError(f"Refusing to reset a client containing a game executable: {exe}")


_OWNED: dict[str, subprocess.Popen] = {}


CHANNELS = {"release": 0, "beta": 1, "alpha": 2}


def state_dir(app):
    return STATE / app


def reset_fake_client():
    """Recreate empty AddOns with flavor files from the configured metadata fixture."""
    validate_paths()
    if FAKE.exists():
        shutil.rmtree(FAKE)
    (ADDONS).mkdir(parents=True)
    (FOREVER / "WTF").mkdir()
    (FOREVER / "Wow.exe").touch()
    for name in (".build.info", ".product.db"):
        src = METADATA / name
        if src.exists():
            shutil.copyfile(src, FAKE / name)
    src = METADATA / "_forever_" / ".flavor.info"
    if src.exists():
        shutil.copyfile(src, FOREVER / ".flavor.info")
    else:
        (FOREVER / ".flavor.info").write_text("Product Flavor!STRING:0\nwowf\n")


def reset_app_state(app):
    validate_paths()
    d = state_dir(app)
    if d.exists():
        shutil.rmtree(d)
    for sub in ("home", "config", "data", "cache"):
        (d / sub).mkdir(parents=True)


def seed_wowup(channel):
    """WowUp on Linux adds a client only through a file chooser; write the record it would write."""
    ud = state_dir("wowup") / APPS["wowup"]["userdata"]
    ud.mkdir(parents=True, exist_ok=True)
    prefs_path = ud / "preferences.json"
    prefs = json.loads(prefs_path.read_text()) if prefs_path.exists() else {}
    prefs["telemetry_enabled"] = "false"
    prefs["forever_default_addon_channel"] = str(CHANNELS[channel])
    prefs["wow_installations"] = [
        {
            "id": str(uuid.uuid4()),
            "clientType": 10,  # WowClientType.Forever in wowup-lib-core
            "defaultAddonChannelType": CHANNELS[channel],
            "defaultAutoUpdate": False,
            "label": "Forever",
            "displayName": "Forever",
            "location": str(FOREVER / "Wow.exe"),
            "selected": True,
        }
    ]
    prefs_path.write_text(json.dumps(prefs, indent=1))


def env_for(app):
    d = state_dir(app)
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("DBUS_SESSION_BUS_ADDRESS", "WAYLAND_DISPLAY", "DISPLAY", "XAUTHORITY")
    }
    env.update(
        HOME=str(d / "home"),
        XDG_CONFIG_HOME=str(d / "config"),
        XDG_DATA_HOME=str(d / "data"),
        XDG_CACHE_HOME=str(d / "cache"),
        XDG_SESSION_TYPE="x11",
        ELECTRON_OZONE_PLATFORM_HINT="x11",
    )
    return env


def start(app, extra_args=(), ready_port=None, ready_type="page"):
    cfg = APPS[app]
    logs = LOGS
    logs.mkdir(parents=True, exist_ok=True)
    log = open(logs / f"{app}.log", "ab")
    cmd = [
        "dbus-run-session",
        "--",
        "xvfb-run",
        "-a",
        "-f",
        str(state_dir(app) / "Xauthority"),
        "-s",
        "-screen 0 1400x1000x24",
        str(cfg["bin"]),
        "--no-sandbox",
        f"--remote-debugging-port={cfg['port']}",
        *extra_args,
    ]
    p = subprocess.Popen(
        cmd, env=env_for(app), stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True
    )
    log.close()
    _OWNED[app] = p
    (logs / f"{app}.pid").write_text(str(p.pid))
    port = ready_port or cfg["port"]
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as r:
                if any(t["type"] == ready_type for t in json.load(r)):
                    return p.pid
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError(f"{app} exposed no {ready_type} target on port {port}")


def group_pids(pgid):
    out = subprocess.run(["ps", "-eo", "pid=,pgid=,stat="], capture_output=True, text=True, check=True).stdout
    return [
        int(pid)
        for pid, group, state in (line.split() for line in out.splitlines())
        if int(group) == pgid and not state.startswith("Z")
    ]


def stop(app):
    pidfile = LOGS / f"{app}.pid"
    if not pidfile.exists():
        return []
    pgid = int(pidfile.read_text())
    owned = _OWNED.get(app)
    if owned is None or owned.pid != pgid:
        if group_pids(pgid):
            raise RuntimeError(f"Refusing to stop an app not started by this run: {pidfile}")
        pidfile.unlink()
        return []
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if not group_pids(pgid):
            break
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            break
        for _ in range(20):
            if not group_pids(pgid):
                break
            time.sleep(0.5)
    left = group_pids(pgid)
    if not left:
        owned.wait(timeout=5)
        _OWNED.pop(app, None)
        pidfile.unlink()
    return left
