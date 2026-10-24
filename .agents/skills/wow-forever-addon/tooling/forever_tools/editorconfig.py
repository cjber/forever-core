"""The family's `.editorconfig`, and a check that a repository's copy agrees with its StyLua and ruff settings.

StyLua and ruff format Lua and Python, but an editor also writes Markdown, YAML, TOC and XML files that nothing
reformats. `TEMPLATE` is the one `.editorconfig` every addon commits; `check` fails when a repository's copy drops
a section the template has, or when its Lua or Python indent and width disagree with `stylua.toml` and `ruff.toml`
(so changing one without the other fails in CI, not in a contributor's editor).

    python3 tools/check_editorconfig.py          # check .editorconfig
    python3 tools/check_editorconfig.py --print  # print the template, to start a copy
"""

import argparse
import configparser
import re
import sys
from pathlib import Path

__all__ = ["TEMPLATE", "check", "main", "parse"]

LUA, PY = "{*.lua,.luacheckrc}", "*.py"

TEMPLATE = """\
# Editor defaults for the WoW: Forever addons (cjber/forever-core .agents/skills/wow-forever-addon/tooling,
# forever_tools.editorconfig).
# StyLua and ruff still format Lua and Python; tools/check_editorconfig.py keeps these sections in step with them.
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

# .luacheckrc is Lua and .pkgmeta is YAML, neither with the extension.
[{*.lua,.luacheckrc}]
indent_style = tab
indent_size = 4
max_line_length = 120

[*.py]
indent_style = space
indent_size = 4
max_line_length = 120

[*.{toc,xml}]
indent_style = tab
indent_size = 4

[{*.yml,*.yaml,*.json,.pkgmeta}]
indent_style = space
indent_size = 2

[*.md]
indent_style = space
indent_size = 2
# A Markdown line break is two trailing spaces.
trim_trailing_whitespace = false

[*.{png,gif,tga,blp,ttf}]
charset = unset
end_of_line = unset
insert_final_newline = unset
trim_trailing_whitespace = unset
"""


class _Parser(configparser.ConfigParser):
    """Keys compared case-insensitively, as EditorConfig does."""

    def optionxform(self, optionstr: str) -> str:
        return optionstr.lower()


def parse(text: str) -> dict[str, dict[str, str]]:
    """Sections as {glob: {key: value}}, keys and values lower-cased as EditorConfig compares them."""
    # A repeated section is legal EditorConfig; later keys win, as they do for an editor.
    parser = _Parser(interpolation=None, comment_prefixes=("#", ";"), inline_comment_prefixes=None, strict=False)
    parser.read_string("[__preamble__]\n" + text)
    return {
        name: {key: value.strip().lower() for key, value in parser[name].items()}
        for name in parser.sections()
        if name != "__preamble__"
    }


def toml_value(text: str, key: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(key)}\s*=\s*['\"]?([^'\"\s#]+)", text, re.MULTILINE)
    return match[1] if match else None


def check(root: Path) -> list[str]:
    path = root / ".editorconfig"
    if not path.is_file():
        return [".editorconfig: missing; start it from `tools/check_editorconfig.py --print`"]
    try:
        have = parse(path.read_text(encoding="utf-8"))
    except configparser.Error as error:
        return [f".editorconfig: {error}"]
    want = parse(TEMPLATE)
    problems = []
    for section, keys in want.items():
        for key, value in keys.items():
            found = have.get(section, {}).get(key)
            if found is None:
                problems.append(f".editorconfig [{section}]: {key} is missing (the family uses {value})")
            elif found != value and section not in {LUA, PY}:  # those two follow stylua and ruff below
                problems.append(f".editorconfig [{section}]: {key} = {found}, the family uses {value}")
    lua = have.get(LUA, {})
    stylua = root / "stylua.toml"
    if stylua.is_file():
        text = stylua.read_text(encoding="utf-8")
        style = {"tabs": "tab", "spaces": "space"}.get((toml_value(text, "indent_type") or "Tabs").lower())
        expected = {
            "indent_style": style,
            "indent_size": toml_value(text, "indent_width") or "4",
            "max_line_length": toml_value(text, "column_width") or "120",
        }
        for key, value in expected.items():
            if lua.get(key) != value:
                problems.append(f".editorconfig [{LUA}]: {key} = {lua.get(key)}, stylua.toml says {value}")
    python = have.get(PY, {})
    ruff = next((p for p in (root / "ruff.toml", root / "tools/ruff.toml") if p.is_file()), None)
    if ruff is not None:
        text = ruff.read_text(encoding="utf-8")
        expected = {
            "indent_style": "space",
            "indent_size": toml_value(text, "indent-width") or "4",
            "max_line_length": toml_value(text, "line-length") or "88",
        }
        for key, value in expected.items():
            if python.get(key) != value:
                problems.append(f".editorconfig [{PY}]: {key} = {python.get(key)}, {ruff.name} says {value}")
    return problems


def main(root: Path, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--print", action="store_true", help="print the family template")
    args = parser.parse_args(argv)
    if args.print:
        sys.stdout.write(TEMPLATE)
        return 0
    problems = check(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(".editorconfig: agrees with the family template, stylua.toml and ruff.toml")
    return 0
