"""Check this machine against every tool pin the gate uses, and say how to fix each one that is off.

The pins are read from the repository itself, never retyped here: `.github/workflows/ci.yml` (StyLua, ruff,
actionlint, zizmor, gitleaks, lua-language-server, the apt packages) and `tools/typecheck.sh` (the LuaLS version
and the Ketho WoW API annotations checkout). `tools/typecheck.sh` stops at its first problem; this reports them
all, one line each with its fix, then exits 1 if any tool the gate needs is missing or at the wrong version.
Screenshot prerequisites (Pillow at the pin in `tools/screenshots.py` and the shared renderer in
`FOREVER_CORE`) are reported but never fail it.

    python3 tools/doctor.py
"""

import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Finding", "Tool", "check", "main", "pins"]


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


def pins(root: Path) -> Pins:
    """Every pin in ci.yml and typecheck.sh, and the screenshot Pillow pin, as tools to check."""
    ci_path, typecheck_path = root / ".github/workflows/ci.yml", root / "tools/typecheck.sh"
    ci = ci_path.read_text(encoding="utf-8") if ci_path.is_file() else ""
    typecheck = typecheck_path.read_text(encoding="utf-8") if typecheck_path.is_file() else ""
    found = Pins()
    if not ci_path.is_file():
        found.missing.append(".github/workflows/ci.yml: not found, so no CI pins were read")
    if not typecheck_path.is_file():
        found.missing.append("tools/typecheck.sh: not found, so no typecheck pins were read")
    stylua = first(r"stylua-action@\S+[^\n]*\n(?:[ \t]+[^\n]*\n)*?[ \t]+version:\s*['\"]?([\d.]+)", ci)
    if stylua:
        found.tools.append(
            Tool("stylua", ("stylua", "--version"), stylua, f"cargo install stylua --locked --version {stylua}")
        )
    for name, pattern, command, fix in (
        ("ruff", r"\bruff(?:==|@)([\d.]+)", ("ruff", "--version"), "pipx install ruff=={v}"),
        ("zizmor", r"\bzizmor(?:==|@)([\d.]+)", ("zizmor", "--version"), "pipx install zizmor=={v}"),
        (
            "actionlint",
            r"(?:\bactionlint-py==(\d+\.\d+\.\d+)|actionlint/releases/download/v([\d.]+)/)",
            ("actionlint", "--version"),
            "pipx install actionlint-py (the {v} release)",
        ),
        (
            "shellcheck",
            r"\bshellcheck-py==(\d+\.\d+\.\d+)",
            ("shellcheck", "--version"),
            "pipx install shellcheck-py (the {v} release)",
        ),
    ):
        version = first(pattern, ci)
        if version:
            found.tools.append(Tool(name, command, version, fix.format(v=version)))
    shfmt = first(r"\bshfmt-py==([\d.]+)", ci)
    if shfmt:
        found.tools.append(Tool("shfmt", ("shfmt", "--version"), None, f"pipx install shfmt-py=={shfmt}"))
    gitleaks = first(r"(?:gitleaks/releases/download/v|GITLEAKS_VERSION:\s*['\"]?)(\d+\.\d+\.\d+)", ci)
    if gitleaks:
        fix = (
            f"download gitleaks_{gitleaks}_linux_x64.tar.gz from github.com/gitleaks/gitleaks/releases/tag/v{gitleaks}"
            if linux()
            else f"brew install gitleaks (then check `gitleaks version` says {gitleaks})"
        )
        found.tools.append(Tool("gitleaks", ("gitleaks", "version"), gitleaks, fix))
    luals = first(r"(?:lua-language-server/releases/download/|LUALS_VERSION:\s*['\"]?)(\d+\.\d+\.\d+)", ci) or first(
        r"--version\)\"? != ['\"]?(\d+\.\d+\.\d+)", typecheck
    )
    if luals:
        found.tools.append(
            Tool(
                "lua-language-server",
                ("lua-language-server", "--version"),
                luals,
                f"unpack github.com/LuaLS/lua-language-server/releases/tag/{luals} and put its bin/ on PATH",
            )
        )
    packages = set(re.findall(r"apt-get install -y ([^\n&|;]+)", ci))
    wanted = {word for line in packages for word in line.split()}
    if "luajit" in wanted:
        fix = "sudo apt-get install -y luajit" if linux() else "brew install luajit"
        found.tools.append(Tool("luajit", ("luajit", "-v"), None, fix))
    if "lua-check" in wanted or re.search(r"^\s*-? ?run: luacheck", ci, re.MULTILINE):
        fix = "sudo apt-get install -y lua-check" if linux() else "brew install luarocks && luarocks install luacheck"
        found.tools.append(Tool("luacheck", ("luacheck", "--version"), None, fix))
    revision = first(r"^revision=['\"]?([0-9a-f]{40})", typecheck)
    directory = first(r"^(?:annotations|library)=['\"]?([^'\"\s]+)", typecheck)
    if revision and directory:
        if "$" in directory:
            found.missing.append(f"tools/typecheck.sh: the annotations path {directory} is not a plain path to check")
        else:
            found.annotations = (directory, revision)
    screenshots = root / "tools/screenshots.py"
    if screenshots.is_file():
        text = screenshots.read_text(encoding="utf-8")
        found.pillow = first(r"PILLOW\s*=\s*['\"]([\d.]+)['\"]", text) or first(r"pillow==([\d.]+)", text) or ""
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
        findings.append(Finding(False, "Pillow: not installed (tools/screenshots.py only)", fix, optional=True))
    elif pillow and installed != pillow:
        text = f"Pillow: {installed}, tools/screenshots.py pins {pillow} for byte-identical PNGs"
        findings.append(Finding(False, text, fix, optional=True))
    else:
        findings.append(Finding(True, f"Pillow: {installed}"))
    core = Path(os.environ.get("FOREVER_CORE", Path(__file__).resolve().parents[3] / "forever-core")).expanduser()
    renderer = core / "tools" / "wowmock" / "wowmock.py"
    if not renderer.is_file():
        findings.append(
            Finding(
                False,
                f"FOREVER_CORE: shared renderer not found at {renderer} (tools/screenshots.py only)",
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
