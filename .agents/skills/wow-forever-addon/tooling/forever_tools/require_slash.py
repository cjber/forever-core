"""A stopped addon still answers its own slash command with the line that names the fix.

When ForeverCore is missing or fails, an addon's `Core/Require.lua` calls `ns.ForeverRequire(ready, slash)` and the
rest of its files stop. The second argument is the addon's slash words and their `SlashCmdList` key, so the stopped
addon claims them and repeats its one line; without it the player's `/command` reads "Unknown command"
(cjber/shortest-path-forever#996). Nothing in the TOC lists slash words, so this reads them from the addon's own Lua.

The rule covers the addon's own command: the `SlashCmdList` key named after its folder (`MacroAssistForever` registers
`MACROASSISTFOREVER`). Helper commands another addon may own (`/way`, `/rl`) are not claimed by a stopped addon. An
addon that registers its own command and calls `ns.ForeverRequire` must pass `{ key = "<KEY>", "/word", ... }` with
exactly the words it registers, in the order it numbers them.

    from forever_tools import require_slash
    require_slash.check(root, "MacroAssistForever")   # failures, each naming file:line and the fix
"""

import re
from pathlib import Path

__all__ = ["check", "registered", "required"]

# Folders holding no addon code of its own, as tools/check_slash_words.py reads them: tooling, the embedded library,
# specs, docs, type stubs and dot folders.
SKIP = {"Libs", "docs", "tests", "tools", "types"}
# `SLASH_<KEY><n> = "/word"`, with or without `_G.`. A conditional claim (`claim and "/way" or nil`) is not a literal
# word, so it never matches.
ASSIGN = re.compile(r'^[ \t]*(?:_G\.)?SLASH_([A-Z0-9_]+?)(\d+)[ \t]*=[ \t]*"([^"\n]+)"[ \t]*(?:--.*)?$', re.M)
# A call to the shared warning, never its definition.
CALL = re.compile(r"(?<!function )\bns\.ForeverRequire\(")
STRING = re.compile(r'"([^"\n]*)"')
KEY = re.compile(r'\bkey\s*=\s*"([^"\n]*)"')


def _lua_files(root):
    for path in sorted(Path(root).rglob("*.lua")):
        folders = path.relative_to(root).parts[:-1]
        if not SKIP.intersection(folders) and not any(folder.startswith(".") for folder in folders):
            yield path


def _line(text, offset):
    return text.count("\n", 0, offset) + 1


def registered(root, key):
    """The words the addon at `root` registers for `key`, in slash-number order, with where the first is set."""
    words = {}
    where = None
    for path in _lua_files(root):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for match in ASSIGN.finditer(text):
            if match.group(1) == key:
                words.setdefault(int(match.group(2)), match.group(3))
                where = where or f"{path.relative_to(root).as_posix()}:{_line(text, match.start())}"
    return [words[number] for number in sorted(words)], where


def _arguments(text, start):
    """The argument text of the call whose `(` is at `start`, split on top-level commas."""
    depth, parts, current = 0, [], []
    index = start + 1
    while index < len(text):
        char = text[index]
        if char in "({[":
            depth += 1
        elif char in ")}]":
            if depth == 0:
                break
            depth -= 1
        elif char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            index += 1
            continue
        elif char == '"':
            end = text.find('"', index + 1)
            current.append(text[index : end + 1])
            index = end + 1
            continue
        current.append(char)
        index += 1
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def _table(text, argument):
    """The table literal `argument` is, or is assigned to in the same file; None when neither."""
    if argument.startswith("{"):
        return argument
    name = re.escape(argument)
    match = re.search(rf"^[ \t]*(?:local[ \t]+)?{name}[ \t]*=[ \t]*(\{{[^{{}}]*\}})", text, re.M)
    return match.group(1) if match else None


def _words(table):
    key = KEY.search(table)
    without_key = KEY.sub("", table)
    return (key.group(1) if key else None), STRING.findall(without_key)


def required(key, words):
    """The literal the call must pass for `key` and `words`."""
    return "{ " + ", ".join([f'key = "{key}"'] + [f'"{word}"' for word in words]) + " }"


def check(root, folder):
    """Failures for the addon at `root` whose folder (and root TOC stem) is `folder`."""
    root = Path(root)
    key = folder.upper()
    words, where = registered(root, key)
    if not words:
        return []
    failures = []
    for path in _lua_files(root):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for match in CALL.finditer(text):
            at = f"{path.relative_to(root).as_posix()}:{_line(text, match.start())}"
            fix = (
                f"pass {required(key, words)} (the words {where} registers) as its second argument, so a stopped"
                f" addon answers {words[0]} with the line that names the fix"
            )
            arguments = _arguments(text, match.end() - 1)
            if len(arguments) < 2:
                failures.append(f"{at}: ns.ForeverRequire gets no slash words; {fix}")
                continue
            table = _table(text, arguments[1])
            if table is None:
                failures.append(
                    f"{at}: ns.ForeverRequire's slash words `{arguments[1]}` are not a table literal"
                    f" in {path.name}; {fix}"
                )
                continue
            named, passed = _words(table)
            if named != key or passed != words:
                failures.append(
                    f"{at}: ns.ForeverRequire's slash words {required(named or '?', passed)} differ from what"
                    f" the addon registers; {fix}"
                )
    return failures
