"""Generate `Data/Credits.lua` and the store pages' thanks sentence from an addon's `THIRD_PARTY.md` (WFA-31, WFA-33).

The credits page in ForeverCore reads one file per addon, `ns.Credits`, and this is its only writer. Two explicit
sections carry the data, each a Markdown table `| Who | What | Notes |`:

    ## Players

    | Who | What | Notes |
    |---|---|---|
    | [Brainc3ll](https://github.com/Brainc3ll) | The French translation | |
    | Someone | Reported the tracker drift (#99) | |

    ## Inspired by

    | Who | What | Notes |
    |---|---|---|
    | Questie | The objective-tracker layout | |

Rows are taken as written; nothing is guessed from their text. A Markdown backslash escape before ASCII punctuation
becomes the plain character, as CommonMark says, so `Sol\\_Deus` and `Sol_Deus` name one player. In `Who`, a Markdown
link keeps only its visible text. In `What`, links are reduced to their text and issue references such as `(#99)` or
`(cjber/x#12, #3)` are removed, so the in-game line reads cleanly. `Notes` is for the reader of the file and never
reaches the game. A section that is missing is an empty list, and the addon's author is never listed (WFA-33).

The same run writes one sentence, "Thanks to A, B and everyone who reported a bug or asked for a feature.", between
`<!-- forever-credits:start -->` and `<!-- forever-credits:end -->` in `README.md` (inside its `## Credits`) and
`docs/curseforge.md`, listing every `## Players` name in table order. The markers use `forever_tools.family`'s
handling. A file without the markers is left alone, except that `--check` fails a `README.md` without them.

Run it from the addon's root after editing `THIRD_PARTY.md`, and add `Data\\Credits.lua` to the TOC:

    python3 tools/forever_tools/credits.py            # write Data/Credits.lua and both blocks
    python3 tools/forever_tools/credits.py --check    # fail when the file or a block is stale

The addon passes the table to `ForeverCore.Credits.Register("The Addon's Title", ns.Credits)` once it loads.
"""

import argparse
import re
import sys
from pathlib import Path

# Run directly from an addon root (`python3 tools/forever_tools/credits.py`) as well as imported as a module.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forever_tools.family import blocks as marked_blocks  # noqa: E402
from forever_tools.fsio import atomic_write  # noqa: E402
from forever_tools.generated import compare  # noqa: E402
from forever_tools.luadata import ESCAPES  # noqa: E402

__all__ = [
    "BLOCK_END",
    "BLOCK_FILES",
    "BLOCK_START",
    "OUTPUT",
    "SOURCE",
    "main",
    "parse",
    "read",
    "render",
    "render_block",
    "sentence",
    "unescape",
]

SOURCE = "THIRD_PARTY.md"
OUTPUT = "Data/Credits.lua"
BLOCK_START = "<!-- forever-credits:start -->"
BLOCK_END = "<!-- forever-credits:end -->"
BLOCK_FILES = ("README.md", "docs/curseforge.md")
# README carries the credits section, so its markers are required; the store page's are optional.
BLOCK_REQUIRED = ("README.md",)
BLOCK_HINT = "place the markers where the credits sentence goes, then run python3 tools/forever_tools/credits.py"
EMPTY_SENTENCE = "Thanks to everyone who reports a bug or asks for a feature."
# The heading that starts each table, by the key the Lua file uses.
SECTIONS = {"players": "## Players", "inspired": "## Inspired by"}
COLUMNS = 3
HEADER = ("who", "what", "notes")
COLUMN_WIDTH = 120
TAB_WIDTH = 4

HEADING = re.compile(r"^(#{1,2})\s")
SEPARATOR = re.compile(r"^:?-{3,}:?$")
INLINE_LINK = re.compile(r"!?\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)")
REFERENCE_LINK = re.compile(r"!?\[([^\]]*)\]\[[^\]]*\]")
ISSUE_REF = re.compile(r"\s*\([^()]*#[0-9]+[^()]*\)")
# CommonMark: a backslash escapes any ASCII punctuation character, and the backslash itself is removed.
PUNCTUATION_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")
QUOTED = {value: "\\" + key for key, value in ESCAPES.items() if key != "'"}


def lua_string(text: str) -> str:
    """A Lua 5.1 quoted string, with the escapes `luadata` can read back."""
    return '"' + "".join(QUOTED.get(char, char) for char in text) + '"'


def unescape(text: str) -> str:
    """`text` with CommonMark's backslash escapes resolved: a backslash before ASCII punctuation is removed."""
    return PUNCTUATION_ESCAPE.sub(r"\1", text)


def cells(line: str) -> list[str]:
    """The cells of one Markdown table row, keeping an escaped `\\|` inside a cell."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    parts, current, index = [], [], 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text) and text[index + 1] == "|":
            # A table cell may hold an escaped pipe, which must not split the row; every other escape is resolved
            # after the split, as CommonMark does.
            current.append("|")
            index += 2
            continue
        if char == "|":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    return [unescape(part.strip()) for part in parts]


def unlink(text: str) -> str:
    """`text` with Markdown links reduced to their visible text."""
    text = INLINE_LINK.sub(r"\1", text)
    return REFERENCE_LINK.sub(r"\1", text)


def clean_what(text: str) -> str:
    """A `What` cell as the in-game line: no link syntax and no issue references."""
    text = unlink(text)
    text = ISSUE_REF.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip().rstrip(",;:").strip()


def table(lines: list[str]) -> list[list[str]]:
    """Every data row of the first Markdown table in `lines`, its header and separator left out."""
    rows: list[list[str]] = []
    started = False
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if started:
                break
            continue
        started = True
        row = cells(stripped)
        if len(row) < COLUMNS:
            row += [""] * (COLUMNS - len(row))
        if all(SEPARATOR.fullmatch(cell) for cell in row if cell):
            continue
        if [cell.casefold() for cell in row[:COLUMNS]] == list(HEADER):
            continue
        rows.append(row[:COLUMNS])
    return rows


def parse(text: str) -> dict[str, list[dict[str, str]]]:
    """The two credit lists in `THIRD_PARTY.md`'s text; a missing section is an empty list."""
    sections: dict[str, list[str]] = {key: [] for key in SECTIONS}
    current: str | None = None
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading:
            current = next((key for key, title in SECTIONS.items() if line.strip() == title), None)
            continue
        if current:
            sections[current].append(line)

    credits: dict[str, list[dict[str, str]]] = {}
    for key, lines in sections.items():
        entries = []
        for row in table(lines):
            name = unlink(row[0]).strip()
            if not name:
                continue
            entries.append({"name": name, "what": clean_what(row[1])})
        credits[key] = entries
    return credits


def read(root: Path) -> dict[str, list[dict[str, str]]]:
    """The credits in `root`'s `THIRD_PARTY.md`."""
    path = root / SOURCE
    if not path.is_file():
        raise SystemExit(f"{SOURCE} is missing: the credits generator reads its ## Players and ## Inspired by tables")
    return parse(path.read_text(encoding="utf-8"))


def display_width(line: str) -> int:
    """A generated line's width with tabs counted as the column width the family's StyLua config uses."""
    return len(line) + line.count("\t") * (TAB_WIDTH - 1)


def entry_lines(entry: dict[str, str]) -> list[str]:
    """One table row, expanded the way StyLua formats a long one (`--check` runs StyLua over the result)."""
    compact = f"\t\t{{ name = {lua_string(entry['name'])}, what = {lua_string(entry['what'])} }},"
    if display_width(compact) <= COLUMN_WIDTH:
        return [compact]
    return [
        "\t\t{",
        f"\t\t\tname = {lua_string(entry['name'])},",
        f"\t\t\twhat = {lua_string(entry['what'])},",
        "\t\t},",
    ]


def render(credits: dict[str, list[dict[str, str]]]) -> str:
    """The whole generated Lua file, header comment included."""
    players = credits.get("players", [])
    inspired = credits.get("inspired", [])
    lines = [
        "-- Generated by tools/forever_tools/credits.py from THIRD_PARTY.md.",
        "-- Do not edit: change THIRD_PARTY.md and run the generator.",
        "local _, ns = ...",
        "",
        "ns.Credits = {",
    ]
    for key, entries in (("players", players), ("inspired", inspired)):
        if not entries:
            lines.append(f"\t{key} = {{}},")
            continue
        lines.append(f"\t{key} = {{")
        for entry in entries:
            lines.extend(entry_lines(entry))
        lines.append("\t},")
    lines.append("}")
    return "\n".join(lines) + "\n"


def sentence(players: list[dict[str, str]]) -> str:
    """The thanks sentence: every name once, in table order, then the invitation to report or ask."""
    names = list(dict.fromkeys(entry["name"] for entry in players if entry["name"]))
    if not names:
        return EMPTY_SENTENCE
    return f"Thanks to {', '.join(names)} and everyone who reported a bug or asked for a feature."


def render_block(players: list[dict[str, str]]) -> str:
    """The generated block, markers included."""
    return "\n".join([BLOCK_START, "", sentence(players), "", BLOCK_END])


def block_problems(root: Path, block: str) -> list[str]:
    """Why README.md or docs/curseforge.md is out of date; a store page with no markers is left alone."""
    problems = []
    for name, _path, text, where in marked_blocks(root, BLOCK_FILES, BLOCK_START, BLOCK_END, BLOCK_HINT):
        required = name in BLOCK_REQUIRED
        if where is None:
            if required:
                problems.append(f"{name}: missing; it must carry the credits block")
            continue
        if isinstance(where, str):
            if not required and BLOCK_START not in text and BLOCK_END not in text:
                continue
            problems.append(f"{name}: {where}")
            continue
        if text[where[0] : where[1]].replace("\r\n", "\n") != block:
            line = text.count("\n", 0, where[0]) + 1
            problems.append(f"{name}:{line}: the credits block differs from forever_tools.credits; run without --check")
    return problems


def block_fix(root: Path, block: str) -> list[str]:
    """Rewrite each well-formed block in the file's own line endings; return the files changed."""
    changed = []
    for name, path, text, where in marked_blocks(root, BLOCK_FILES, BLOCK_START, BLOCK_END, BLOCK_HINT):
        if where is None or isinstance(where, str):
            continue
        wanted = block.replace("\n", "\r\n") if "\r\n" in text else block
        if text[where[0] : where[1]] != wanted:
            atomic_write(path, text[: where[0]] + wanted + text[where[1] :])
            changed.append(name)
    return changed


def main(root: Path, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Data/Credits.lua from THIRD_PARTY.md.")
    parser.add_argument("--check", action="store_true", help="fail instead of writing when the file is stale")
    arguments = parser.parse_args(argv)
    data = read(root)
    generated = render(data)
    block = render_block(data["players"])
    path = root / OUTPUT
    if arguments.check:
        existing = path.read_bytes() if path.is_file() else None
        compare(
            {OUTPUT: generated.encode()},
            {OUTPUT: existing} if existing is not None else {},
            f"{OUTPUT} is stale; run python3 tools/forever_tools/credits.py",
        )
        problems = block_problems(root, block)
        for problem in problems:
            print(problem, file=sys.stderr)
        if problems:
            return 1
        print(f"credits: {OUTPUT} is up to date")
        return 0
    atomic_write(path, generated)
    print(f"credits: wrote {OUTPUT}")
    for name in block_fix(root, block):
        print(f"{name}: credits block rewritten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path.cwd()))
