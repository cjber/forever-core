"""Check this machine against every tool pin the gate uses, and say how to fix each one that is off.

The pins are read from the repository itself, never retyped here: `toolchain.json` (StyLua, gitleaks,
lua-language-server, LuaJIT, luacheck and the Ketho WoW API annotations revision) and `pyproject.toml`'s
`[dependency-groups] dev` (ruff, ty, zizmor, actionlint-py), the two files CI and the scripts read. `tools/typecheck.sh`
stops at its first problem; this reports them all, one line each with its fix, then exits 1 if any tool the gate needs
is missing or at the wrong version.
Screenshot prerequisites (Pillow at the pin in `tools/screenshots.py` or pyproject.toml's dev group, and the shared
renderer in `FOREVER_CORE`) are reported but never fail it.

    python3 tools/doctor.py
"""

import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Finding", "Tool", "check", "dev_group", "main", "pins"]

DEFAULT_ANNOTATIONS = ".types/vscode-wow-api"
DEPENDENCY = re.compile(r'^\s*"([A-Za-z0-9_.\-]+)==([^"]+)"', re.MULTILINE)


@dataclass(frozen=True)
class Tool:
    """A command the gate runs: `version` is the pin, None when any version passes."""

    name: str
    command: tuple[str, ...]
    version: str | None
    fix: str
    pattern: str = r"(\d+\.\d+(?:\.\d+)?)"


@dataclass
class Finding:
    ok: bool
    text: str
    fix: str = ""
    optional: bool = False


@dataclass
class Pins:
    tools: list[Tool] = field(default_factory=list)
    annotations: tuple[str, str] | None = None  # (checkout directory, revision)
    pillow: str | None = None
    missing: list[str] = field(default_factory=list)


def linux() -> bool:
    return sys.platform.startswith("linux")


def first(pattern: str, text: str) -> str | None:
    """The first non-empty group of the first match."""
    match = re.search(pattern, text, re.MULTILINE)
    return next((group for group in match.groups() if group), None) if match else None


def dev_group(path: Path) -> dict[str, str]:
    """The `[dependency-groups] dev` pins in pyproject.toml, as name -> version.

    Parsed line by line rather than with tomllib: the tooling still supports Python 3.10, which has no TOML module,
    and the group holds only `"name==version"` strings.
    """
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    section = re.search(r"^\[dependency-groups\]\s*$([\s\S]*?)(?=^\[|\Z)", text, re.MULTILINE)
    if section is None:
        return {}
    group = re.search(r"^dev\s*=\s*\[([\s\S]*?)^\]", section.group(1), re.MULTILINE)
    return dict(DEPENDENCY.findall(group.group(1))) if group else {}


def annotations_directory(root: Path) -> str:
    """Where tools/typecheck.sh checks the annotations out, or the family default."""
    typecheck = root / "tools/typecheck.sh"
    text = typecheck.read_text(encoding="utf-8") if typecheck.is_file() else ""
    return first(r"^annotations=['\"]?([^'\"\s]+)", text) or DEFAULT_ANNOTATIONS


def pins(root: Path) -> Pins:
    """Every pin in toolchain.json and pyproject.toml, and the screenshot Pillow pin, as tools to check."""
    manifest_path, pyproject_path = root / "toolchain.json", root / "pyproject.toml"
    found = Pins()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tools = manifest["tools"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        found.missing.append("toolchain.json: not found or unreadable, so no toolchain pins were read")
        tools = {}
    python_pins = dev_group(pyproject_path)
    if not pyproject_path.is_file():
        found.missing.append("pyproject.toml: not found, so no Python tool pins were read")
    for name, fix in (
        ("ruff", "uv sync --group dev"),
        ("ty", "uv sync --group dev"),
        ("zizmor", "uv sync --group dev"),
    ):
        if name in python_pins:
            found.tools.append(
                Tool(name, (name, "--version"), python_pins[name], f"{fix} (pyproject.toml pins {name})")
            )
    if "actionlint-py" in python_pins:
        # The wheel carries the upstream actionlint release as its first three parts; its fourth part is the wheel's.
        version = ".".join(python_pins["actionlint-py"].split(".")[:3])
        found.tools.append(
            Tool("actionlint", ("actionlint", "--version"), version, "uv sync --group dev (actionlint-py)")
        )
    if "stylua" in tools:
        stylua = tools["stylua"]
        found.tools.append(
            Tool(
                "stylua",
                ("stylua", "--version"),
                stylua["version"],
                f"cargo install stylua --locked --version {stylua['version']}",
            )
        )
    if "gitleaks" in tools:
        gitleaks = tools["gitleaks"]["version"]
        fix = (
            f"download gitleaks_{gitleaks}_linux_x64.tar.gz from github.com/gitleaks/gitleaks/releases/tag/v{gitleaks}"
            if linux()
            else f"brew install gitleaks (then check `gitleaks version` says {gitleaks})"
        )
        found.tools.append(Tool("gitleaks", ("gitleaks", "version"), gitleaks, fix))
    if "luals" in tools:
        luals = tools["luals"]["version"]
        found.tools.append(
            Tool(
                "lua-language-server",
                ("lua-language-server", "--version"),
                luals,
                f"unpack github.com/LuaLS/lua-language-server/releases/tag/{luals} and put its bin/ on PATH",
            )
        )
    if "luajit" in tools:
        fix = "sudo apt-get install -y luajit" if linux() else "brew install luajit"
        found.tools.append(Tool("luajit", ("luajit", "-v"), None, fix))
    if "luacheck" in tools:
        fix = "sudo apt-get install -y lua-check" if linux() else "brew install luarocks && luarocks install luacheck"
        found.tools.append(Tool("luacheck", ("luacheck", "--version"), tools["luacheck"]["version"], fix))
    annotations = tools.get("annotations")
    if annotations:
        found.annotations = (annotations_directory(root), annotations["commit"])
    pillow = ""
    screenshots = root / "tools/screenshots.py"
    if screenshots.is_file():
        text = screenshots.read_text(encoding="utf-8")
        pillow = first(r"PILLOW\s*=\s*['\"]([\d.]+)['\"]", text) or first(r"pillow==([\d.]+)", text) or ""
    found.pillow = pillow or python_pins.get("pillow")
    return found


def run(command: tuple[str, ...]) -> str | None:
    """The command's output, or None when it is not installed or fails to start."""
    if shutil.which(command[0]) is None:
        return None
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout + result.stderr


def check_tool(tool: Tool) -> Finding:
    output = run(tool.command)
    if output is None:
        return Finding(False, f"{tool.name}: not found on PATH", tool.fix)
    if tool.version is None:
        return Finding(True, f"{tool.name}: found")
    version = first(tool.pattern, output)
    if version != tool.version:
        return Finding(False, f"{tool.name}: {version or 'unknown version'}, CI pins {tool.version}", tool.fix)
    return Finding(True, f"{tool.name}: {version}")


def check_annotations(root: Path, directory: str, revision: str) -> Finding:
    checkout = root / directory
    if not (checkout / ".git").is_dir():
        return Finding(True, f"WoW API annotations: not fetched yet; tools/typecheck.sh fetches {revision[:12]}")
    head = run(("git", "-C", str(checkout), "rev-parse", "HEAD"))
    dirty = run(("git", "-C", str(checkout), "status", "--porcelain"))
    if (head or "").strip() != revision or (dirty or "").strip():
        return Finding(
            False,
            f"WoW API annotations: {directory} is not a clean checkout of {revision[:12]}",
            f"rm -rf {directory} && tools/typecheck.sh (it fetches the pinned revision)",
        )
    return Finding(True, f"WoW API annotations: {revision[:12]}")


def check_python() -> Finding:
    # An older Python cannot parse this file, so reaching here means 3.10 or newer.
    return Finding(True, f"python3: {'.'.join(map(str, sys.version_info[:3]))}")


def check_screenshots(pillow: str) -> list[Finding]:
    findings = []
    try:
        installed = importlib.metadata.version("pillow")
    except importlib.metadata.PackageNotFoundError:
        installed = None
    fix = f"python3 -m pip install --user pillow=={pillow}" if pillow else "python3 -m pip install --user pillow"
    if installed is None:
        findings.append(Finding(False, "Pillow: not installed (the rendering tools only)", fix, optional=True))
    elif pillow and installed != pillow:
        text = f"Pillow: {installed}, the gate pins {pillow} for byte-identical PNGs"
        findings.append(Finding(False, text, fix, optional=True))
    else:
        findings.append(Finding(True, f"Pillow: {installed}"))
    core = Path(os.environ.get("FOREVER_CORE", Path(__file__).resolve().parents[3] / "forever-core")).expanduser()
    renderer = core / "tools" / "wowmock" / "wowmock.py"
    if not renderer.is_file():
        findings.append(
            Finding(
                False,
                f"FOREVER_CORE: shared renderer not found at {renderer} (the rendering tools only)",
                "set FOREVER_CORE to the forever-core checkout",
                optional=True,
            )
        )
    else:
        findings.append(Finding(True, f"FOREVER_CORE: {core}"))
    return findings


def check(root: Path, extra: tuple[Tool, ...] = ()) -> list[Finding]:
    """Every finding, passing or not, in a fixed order: Python, the pinned tools, the annotations, screenshots."""
    found = pins(root)
    findings = [Finding(False, text, "restore the file from main") for text in found.missing]
    findings.append(check_python())
    findings += [check_tool(tool) for tool in (*found.tools, *extra)]
    if found.annotations:
        findings.append(check_annotations(root, *found.annotations))
    if found.pillow is not None:
        findings += check_screenshots(found.pillow)
    return findings


def main(root: Path, extra: tuple[Tool, ...] = ()) -> int:
    findings = check(root, extra)
    for finding in findings:
        mark = "ok  " if finding.ok else ("note" if finding.optional else "FAIL")
        print(f"{mark} {finding.text}")
        if not finding.ok:
            print(f"     fix: {finding.fix}")
    failures = [finding for finding in findings if not finding.ok and not finding.optional]
    if failures:
        print(f"doctor: {len(failures)} problem(s); fix them and run it again", file=sys.stderr)
        return 1
    print("doctor: this machine matches the gate's pins")
    return 0
