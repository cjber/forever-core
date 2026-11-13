#!/usr/bin/env python3
"""Generate script_types.lua: the scripts each widget type supports, from the pinned vscode-wow-api annotations.

The client source (Blizzard_SharedXML/UI.xsd) lists every script name once, but not which widget type supports
which one, and Blizzard_APIDocumentationGenerated declares SetScript with an opaque ScriptTypeName. The annotations
Ketho/vscode-wow-api carries hold that table: Annotations/Core/Widget/UIType/ScriptType.lua spells every alias per
widget (each script's owning type is in the trailing comment), and the widget files declare SetScript with the
namespace's script alias. We resolve those aliases into the set of names, and only the set each class itself
declares: widgets.lua unions it along its own TYPES hierarchy, so CheckButton gets Button's scripts with no second
copy here.

    # fetch the annotations the way tools/typecheck.sh does, then regenerate:
    bash tools/typecheck.sh
    python3 .agents/skills/wow-forever-addon/tooling/forever_sim/gen_script_types.py
    python3 .agents/skills/wow-forever-addon/tooling/forever_sim/sync.py manifest

The revision is toolchain.json's annotations commit (run from the repository root), the same pin tools/typecheck.sh
fetches; the generator refuses a different checkout, so the data file and the type check always describe the same
client.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_SOURCE = Path(".types/vscode-wow-api")
DEFAULT_MANIFEST = Path("toolchain.json")
OUTPUT = Path(__file__).resolve().with_name("script_types.lua")


ALIAS = re.compile(r"^---@alias\s+(\w+)\s*(.*)$")
CONTINUATION = re.compile(r"^---\|(.*)$")
CLASS = re.compile(r"^---@class\s+(\w+)(?:\s*:\s*(.*))?\s*$")
FUNCTION = re.compile(r"^function\s+(\w+):SetScript\s*\(\s*(\w+)")
PARAMETER = re.compile(r"^---@param\s+(\w+)\s+(\w+)")
STRING = re.compile(r'"([^"]+)"')
IDENTIFIER = re.compile(r"^[A-Za-z_]\w*$")


def aliases_from(text: str) -> dict[str, list[tuple[str, str]]]:
    """Every ---@alias in ScriptType.lua, as (kind, value) tokens: ("script", name) or ("alias", name)."""
    aliases: dict[str, list[tuple[str, str]]] = {}
    current = None
    for line in text.splitlines():
        match = ALIAS.match(line)
        if match:
            current = match.group(1)
            aliases.setdefault(current, [])
            tokens = match.group(2)
        else:
            match = CONTINUATION.match(line)
            if not match or current is None:
                continue
            tokens = match.group(1)
        for token in tokens.split("|"):
            token = token.split("#", 1)[0].strip()
            quoted = STRING.fullmatch(token)
            if quoted:
                aliases[current].append(("script", quoted.group(1)))
            elif IDENTIFIER.fullmatch(token):
                aliases[current].append(("alias", token))
    return aliases


def classes_from(root: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Every widget class's bases, and the script alias its own SetScript declaration names."""
    bases: dict[str, list[str]] = {}
    declared: dict[str, str] = {}
    for path in sorted(root.rglob("*.lua")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            match = CLASS.match(line)
            if match:
                name = match.group(1)
                if name[:1].isupper():
                    bases.setdefault(name, [])
                    for base in (match.group(2) or "").split(","):
                        base = base.strip()
                        if base and base not in bases[name]:
                            bases[name].append(base)
            match = FUNCTION.match(line)
            if match:
                owner, argument = match.group(1), match.group(2)
                for previous in reversed(lines[max(0, index - 8) : index]):
                    parameter = PARAMETER.match(previous)
                    if parameter and parameter.group(1) == argument:
                        if parameter.group(2).startswith("Script"):
                            declared[owner] = parameter.group(2)
                        break
                    if FUNCTION.match(previous) or CLASS.match(previous):
                        break
    return bases, declared


def scripts_for(alias: str, aliases: dict[str, list[tuple[str, str]]], seen: set[str] | None = None) -> set[str]:
    """Expand one alias to its script names, following alias references (ScriptFrame -> ScriptType -> ...)."""
    seen = seen or set()
    if alias in seen or alias not in aliases:
        return set()
    seen.add(alias)
    scripts: set[str] = set()
    for kind, value in aliases[alias]:
        if kind == "script":
            scripts.add(value)
        else:
            scripts |= scripts_for(value, aliases, seen)
    return scripts


def own_scripts(name: str, aliases: dict[str, list[tuple[str, str]]], declared: dict[str, str]) -> set[str]:
    """The set a class declares itself: its SetScript alias, else the Script<Class> alias the annotations name."""
    alias = declared.get(name)
    if alias is None and "Script" + name in aliases:
        alias = "Script" + name
    return scripts_for(alias, aliases) if alias else set()


def revision(source: Path) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"cannot read {source}: {error}") from error


def annotations_revision(manifest: Path) -> str:
    """The annotations commit toolchain.json pins."""
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return data["tools"]["annotations"]["commit"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read the annotations pin from {manifest}: {error}") from error


def generate(source: Path, pinned: str) -> str:
    head = revision(source)
    if head != pinned:
        raise SystemExit(f"{source} is at {head}, not the pinned {pinned}; run bash tools/typecheck.sh")
    widget_root = source / "Annotations/Core/Widget"
    aliases = aliases_from((widget_root / "UIType/ScriptType.lua").read_text(encoding="utf-8"))
    bases, declared = classes_from(widget_root)

    # Some classes the annotations name only through their Script<Class> alias (Browser, Checkout); their alias is
    # as authoritative as a SetScript declaration, so generate them too.
    named = {name[6:] for name in aliases if name.startswith("Script") and name != "ScriptType"}
    entries: list[str] = []
    for name in sorted(set(bases) | set(declared) | named):
        scripts = own_scripts(name, aliases, declared)
        if not scripts:
            continue
        rows = []
        for script in sorted(scripts, key=str.lower):
            rows.append(f'\t\t{script.lower()} = "{script}",')
        entries.append("\t" + name + " = {\n" + "\n".join(rows) + "\n\t},")

    return (
        "-- Generated by gen_script_types.py from the pinned vscode-wow-api annotations, not by hand:\n"
        "--   Annotations/Core/Widget/UIType/ScriptType.lua (each alias, and the widget beside each script)\n"
        "--   Annotations/Core/Widget/**/*.lua (each class's SetScript alias)\n"
        f"-- at Ketho/vscode-wow-api {pinned}, the revision tools/typecheck.sh fetches.\n"
        "-- Each entry is the set that class declares itself, as lower-case name -> the client's spelling;\n"
        "-- widgets.lua unions it along TYPES, so a CheckButton inherits Button without a second copy here.\n"
        "-- Regenerate: bash tools/typecheck.sh &&\n"
        "--   python3 .agents/skills/wow-forever-addon/tooling/forever_sim/gen_script_types.py\n"
        "--   python3 .agents/skills/wow-forever-addon/tooling/forever_sim/sync.py manifest\n"
        "return {\n" + "\n".join(entries) + "\n}\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="the vscode-wow-api checkout")
    parser.add_argument(
        "--toolchain",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="the manifest holding the annotations pin (default: toolchain.json in the current directory)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=f"fail if {OUTPUT.name} is not current instead of writing it",
    )
    args = parser.parse_args(argv)

    text = generate(args.source, annotations_revision(args.toolchain))
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != text:
            raise SystemExit(f"{OUTPUT} is stale; run the generator without --check")
        print(f"{OUTPUT.name}: current")
        return 0
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"{OUTPUT.name}: wrote {text.count(' = {')} widget types")
    return 0


if __name__ == "__main__":
    sys.exit(main())
