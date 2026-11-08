"""Read the Forever addons' error journals and file or update GitHub issues.

After a reload or a logout the client writes each addon's journal to its SavedVariables, BugGrabber writes its own
errors to `!BugGrabber.lua`, the `!!DevSmoke` dev addon writes each `/forever selftest` run to `!!DevSmoke.lua`, and
the client writes `Logs/taint.log`. This tool reads all four, groups the entries
by repository and signature and prints a table. `--file` opens or comments on one issue per signature, with the
signature hash in the body, so the same error never opens a second issue.

    python3 tools/forever_errors.py
    python3 tools/forever_errors.py --since 1762500000 --addon AdventureGuideForever
    python3 tools/forever_errors.py --file --dry-run
    python3 tools/forever_errors.py --json
    python3 tools/forever_errors.py --include-stale

A group last seen before its addon's installed TOC is stale: it cannot describe the code installed now, so it is
hidden, does not fail the gate and is not filed unless `--include-stale` asks for it.

The exit status is the release gate: 1 when a live entry remains after `--since` and `--addon`, 0 otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Addon folder to GitHub repository. This is the only place the mapping lives.
FOLDERS: dict[str, str] = {
    "AdventureGuideForever": "cjber/adventure-guide-forever",
    "ShortestPathForever": "cjber/shortest-path-forever",
    "SkillUpForever": "cjber/skillup-forever",
    "TweaksForever": "cjber/tweaks-forever",
    "LegacyForever": "cjber/legacy-forever",
    "CommissionsForever": "cjber/commissions-forever",
    "FieldGuideForever": "cjber/field-guide-forever",
    "ForeverCore": "cjber/forever-core",
    "LibAHTab": "cjber/tweaks-forever",
}

OWNER = "cjber"
LABEL = "error-report"
LABEL_COLOR = "B60205"
LABEL_DESCRIPTION = "Automated Lua error report"
DEFAULT_WTF = (
    Path.home() / "Games" / "battlenet" / "drive_c" / "Program Files (x86)" / "World of Warcraft" / "_forever_" / "WTF"
)
LOG_CONTEXT_LINES = 20
MAX_BODY_TEXT = 4000
ISSUE_LIST_LIMIT = 200

_ESCAPES = {
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
    '"': '"',
    "'": "'",
    "\n": "\n",
}
_NUMBER = re.compile(r"0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_ADDON_PATH = re.compile(r"Interface[/\\]AddOns[/\\]([A-Za-z0-9_]+)[/\\]")
_TAINT_STAMP = re.compile(r"^(\d{1,2})/(\d{1,2}) (\d{1,2}):(\d{2}):(\d{2})\.(\d{3})\s+(.*)$")
_ADDRESS = re.compile(r"0x[0-9a-fA-F]+")
_DIGITS = re.compile(r"\d+(?:\.\d+)?")
_COUNT_MARKER = re.compile(r"forever-errors:.*?\bcount=(\d+)")


class LuaSyntaxError(ValueError):
    """The file left the Lua subset the client writes into SavedVariables."""


# --------------------------------------------------------------------------------------------------
# Lua table reader


@dataclass(frozen=True)
class Token:
    kind: str
    value: object
    line: int


def _read_quoted(text: str, start: int, line: int) -> tuple[str, int, int]:
    quote = text[start]
    index = start + 1
    pieces: list[str] = []
    while index < len(text):
        char = text[index]
        if char == quote:
            return "".join(pieces), index + 1, line
        if char == "\n":
            raise LuaSyntaxError(f"unterminated string at line {line}")
        if char != "\\":
            pieces.append(char)
            index += 1
            continue
        index += 1
        if index >= len(text):
            raise LuaSyntaxError(f"unterminated escape at line {line}")
        escape = text[index]
        if escape in _ESCAPES:
            pieces.append(_ESCAPES[escape])
            index += 1
        elif escape.isdigit():
            digits = ""
            while len(digits) < 3 and index < len(text) and text[index].isdigit():
                digits += text[index]
                index += 1
            pieces.append(chr(int(digits)))
        elif escape == "x":
            digits = text[index + 1 : index + 3]
            if len(digits) != 2 or any(char not in "0123456789abcdefABCDEF" for char in digits):
                raise LuaSyntaxError(f"bad hex escape at line {line}")
            pieces.append(chr(int(digits, 16)))
            index += 3
        elif escape == "z":
            index += 1
            while index < len(text) and text[index] in " \t\r\n":
                if text[index] == "\n":
                    line += 1
                index += 1
        else:
            pieces.append(escape)
            index += 1
    raise LuaSyntaxError(f"unterminated string at line {line}")


def _read_long_string(text: str, start: int, line: int) -> tuple[str, int, int]:
    end = text.find("]]", start + 2)
    if end < 0:
        raise LuaSyntaxError(f"unterminated long string at line {line}")
    value = text[start + 2 : end]
    return value, end + 2, line + value.count("\n")


def _tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    line = 1
    size = len(text)
    while index < size:
        char = text[index]
        if char in " \t\r":
            index += 1
            continue
        if char == "\n":
            line += 1
            index += 1
            continue
        if text.startswith("--", index):
            if text.startswith("--[[", index):
                end = text.find("]]", index + 4)
                if end < 0:
                    raise LuaSyntaxError(f"unterminated comment at line {line}")
                line += text.count("\n", index, end + 2)
                index = end + 2
            else:
                end = text.find("\n", index)
                index = size if end < 0 else end
            continue
        if char.isalpha() or char == "_":
            end = index + 1
            while end < size and (text[end].isalnum() or text[end] == "_"):
                end += 1
            tokens.append(Token("name", text[index:end], line))
            index = end
            continue
        if char in "\"'":
            value, index, line = _read_quoted(text, index, line)
            tokens.append(Token("string", value, line))
            continue
        if text.startswith("[[", index):
            value, index, line = _read_long_string(text, index, line)
            tokens.append(Token("string", value, line))
            continue
        if char.isdigit() or (char == "." and index + 1 < size and text[index + 1].isdigit()):
            match = _NUMBER.match(text, index)
            if match is None:
                raise LuaSyntaxError(f"bad number at line {line}")
            spelling = match.group(0)
            if spelling[:2].lower() == "0x":
                value: object = int(spelling, 16)
            elif any(marker in spelling for marker in ".eE"):
                value = float(spelling)
            else:
                value = int(spelling)
            tokens.append(Token("number", value, line))
            index = match.end()
            continue
        if char in "{}[]=,;-.":
            tokens.append(Token("symbol", char, line))
            index += 1
            continue
        raise LuaSyntaxError(f"unexpected {char!r} at line {line}")
    tokens.append(Token("eof", None, line))
    return tokens


class _Parser:
    def __init__(self, tokens: Sequence[Token]) -> None:
        self.tokens = tokens
        self.index = 0

    def _peek(self) -> Token:
        return self.tokens[self.index]

    def _next(self) -> Token:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def _expect_symbol(self, symbol: str) -> None:
        token = self._next()
        if token.kind != "symbol" or token.value != symbol:
            raise LuaSyntaxError(f"expected {symbol!r} at line {token.line}")

    def parse(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        while self._peek().kind != "eof":
            name = self._next()
            if name.kind != "name":
                raise LuaSyntaxError(f"expected a global name at line {name.line}")
            self._expect_symbol("=")
            values[str(name.value)] = self._value()
            if self._peek().kind == "symbol" and self._peek().value == ";":
                self._next()
        return values

    def _value(self) -> Any:
        token = self._peek()
        if token.kind in ("string", "number"):
            self._next()
            return token.value
        if token.kind == "name":
            self._next()
            if token.value == "true":
                return True
            if token.value == "false":
                return False
            if token.value == "nil":
                return None
            raise LuaSyntaxError(f"unexpected name {token.value!r} at line {token.line}")
        if token.kind == "symbol" and token.value == "{":
            return self._table()
        if token.kind == "symbol" and token.value == "-":
            self._next()
            value = self._value()
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise LuaSyntaxError(f"minus without a number at line {token.line}")
            return -value
        raise LuaSyntaxError(f"unexpected value at line {token.line}")

    def _table(self) -> dict[object, Any]:
        self._expect_symbol("{")
        table: dict[object, Any] = {}
        position = 1
        while True:
            token = self._peek()
            if token.kind == "symbol" and token.value == "}":
                self._next()
                return table
            if token.kind == "eof":
                raise LuaSyntaxError(f"unterminated table at line {token.line}")
            key: object | None = None
            if token.kind == "symbol" and token.value == "[":
                self._next()
                key_token = self._next()
                if key_token.kind == "symbol" and key_token.value == "-":
                    number_token = self._next()
                    if number_token.kind != "number":
                        raise LuaSyntaxError(f"bad table key at line {number_token.line}")
                    key = -number_token.value
                elif key_token.kind in ("string", "number"):
                    key = key_token.value
                else:
                    raise LuaSyntaxError(f"bad table key at line {key_token.line}")
                self._expect_symbol("]")
                self._expect_symbol("=")
            elif token.kind == "name" and self.index + 1 < len(self.tokens):
                following = self.tokens[self.index + 1]
                if following.kind == "symbol" and following.value == "=":
                    key = self._next().value
                    self._next()
            if key is None:
                key = position
                position += 1
            table[key] = self._value()
            following = self._peek()
            if following.kind == "symbol" and following.value in (",", ";"):
                self._next()
            elif following.kind == "symbol" and following.value == "}":
                continue
            else:
                raise LuaSyntaxError(f"expected a table separator at line {following.line}")


def parse_lua(text: str) -> dict[str, Any]:
    """Read the SavedVariables subset: assignments of strings, numbers, booleans, nil and tables."""
    return _Parser(_tokenize(text)).parse()


def load_lua(path: Path) -> dict[str, Any]:
    return parse_lua(path.read_text(encoding="utf-8", errors="replace"))


def table_values(table: object) -> list[Any]:
    """A table's values, numeric keys in order, so an array keeps the client's order."""
    if not isinstance(table, dict):
        return []
    keys = list(table)
    if all(isinstance(key, int) for key in keys):
        keys.sort()
    return [table[key] for key in keys]


# --------------------------------------------------------------------------------------------------
# Entries


@dataclass(frozen=True)
class Entry:
    source: str
    folder: str
    repo: str
    signature: str
    kind: str
    message: str
    stack: str
    count: int
    first_seen: float | None
    last_seen: float | None
    version: str
    build: str
    locale: str
    addons: tuple[str, ...] = ()


@dataclass(frozen=True)
class LogLine:
    when: datetime | None
    text: str
    raw: str


def folder_for_global(name: str) -> str | None:
    """The addon folder a SavedVariables global belongs to, such as AdventureGuideForeverDB."""
    if not name.endswith("DB"):
        return None
    folder = name[:-2]
    return folder if folder in FOLDERS else None


def folder_in(text: str) -> str | None:
    """The first of our addon folders named by an Interface/AddOns path in text."""
    for match in _ADDON_PATH.finditer(text):
        if match.group(1) in FOLDERS:
            return match.group(1)
    return None


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, (dict, list, tuple)):
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def _timestamp(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return float(text)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def normalise(text: str) -> str:
    """Numbers and addresses out, so one error seen twice has one signature."""
    return _DIGITS.sub("N", _ADDRESS.sub("0xADDR", text))


def signature_for(kind: str, message: str, stack: str) -> str:
    """A stable signature for a source that has none, such as BugGrabber or taint.log."""
    frame = ""
    for line in stack.splitlines():
        if line.strip():
            frame = line.strip()
            break
    return f"{kind}|{normalise(message.strip())}|{normalise(frame)}"


def signature_hash(signature: str) -> str:
    return hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]


def _journal_entries(folder: str, data: dict[object, Any]) -> list[Entry]:
    errors = data.get("errors")
    entries: list[Entry] = []
    for raw in table_values(errors):
        if not isinstance(raw, dict):
            continue
        kind = _text(raw.get("kind")) or "error"
        message = _text(raw.get("message"))
        stack = _text(raw.get("stack"))
        signature = _text(raw.get("signature")) or signature_for(kind, message, stack)
        addons = tuple(str(item) for item in table_values(raw.get("addons")) if isinstance(item, str))
        entries.append(
            Entry(
                source="journal",
                folder=folder,
                repo=FOLDERS[folder],
                signature=signature,
                kind=kind,
                message=message,
                stack=stack,
                count=max(_as_int(raw.get("count"), 1), 1),
                first_seen=_timestamp(raw.get("firstSeen")),
                last_seen=_timestamp(raw.get("lastSeen")),
                version=_text(raw.get("version")),
                build=_text(raw.get("build")),
                locale=_text(raw.get("locale")),
                addons=addons,
            )
        )
    return entries


def _buggrabber_entries(root: Path, warnings: list[str]) -> list[Entry]:
    entries: list[Entry] = []
    for path in sorted(root.rglob("!BugGrabber.lua")):
        try:
            variables = load_lua(path)
        except (OSError, LuaSyntaxError) as error:
            warnings.append(f"{path}: {error}")
            continue
        data = variables.get("BugGrabberDB")
        if not isinstance(data, dict):
            continue
        for raw in table_values(data.get("errors")):
            if not isinstance(raw, dict):
                continue
            message = _text(raw.get("message"))
            stack = _text(raw.get("stack"))
            locals_text = _text(raw.get("locals"))
            folder = folder_in(message) or folder_in(stack) or folder_in(locals_text)
            if folder is None:
                continue
            kind = "buggrabber"
            last_seen = _timestamp(raw.get("time"))
            entries.append(
                Entry(
                    source="buggrabber",
                    folder=folder,
                    repo=FOLDERS[folder],
                    signature=signature_for(kind, message, stack),
                    kind=kind,
                    message=message,
                    stack=stack,
                    count=max(_as_int(raw.get("counter"), 1), 1),
                    first_seen=last_seen,
                    last_seen=last_seen,
                    version="",
                    build="",
                    locale="",
                )
            )
    return entries


def _smoke_entries(data: dict[object, Any], warnings: list[str]) -> list[Entry]:
    """Every failed surface in the !!DevSmoke dev addon's runs (`/forever selftest`), one entry per surface.

    A surface is labelled "<AddonFolder> <command>", so its folder is the label's first word; the world map surface
    belongs to whichever of our folders its error names.
    """
    entries: list[Entry] = []
    for run in table_values(data.get("runs")):
        if not isinstance(run, dict):
            continue
        started = _timestamp(run.get("started"))
        for result in table_values(run.get("results")):
            if not isinstance(result, dict) or result.get("ok") is not False:
                continue
            surface = _text(result.get("surface"))
            lines = [_text(line) for line in table_values(result.get("errors"))]
            message = lines[0] if lines else "failed"
            stack = "\n".join(lines[1:])
            first_word = surface.split(" ", 1)[0]
            folder = first_word if first_word in FOLDERS else folder_in(message) or folder_in(stack)
            if folder is None:
                warnings.append(f"DevSmoke: {surface} failed and names none of our folders: {message}")
                continue
            kind = "smoke"
            entries.append(
                Entry(
                    source="smoke",
                    folder=folder,
                    repo=FOLDERS[folder],
                    signature=signature_for(kind, f"{surface}: {message}", stack),
                    kind=kind,
                    message=f"{surface}: {message}",
                    stack=stack,
                    count=1,
                    first_seen=started,
                    last_seen=started,
                    version="",
                    build=_text(run.get("build")),
                    locale="",
                )
            )
    return entries


def _log_datetime(
    reference: datetime,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int,
    millisecond: int,
) -> datetime | None:
    """The taint log has no year, so take the current one and roll back across New Year."""
    try:
        when = datetime(reference.year, month, day, hour, minute, second, millisecond * 1000)
    except ValueError:
        return None
    if when - reference > timedelta(days=1):
        try:
            when = when.replace(year=reference.year - 1)
        except ValueError:
            return None
    return when


def read_taint_log(path: Path, reference: datetime | None = None) -> list[LogLine]:
    if not path.is_file():
        return []
    reference = reference or datetime.now()
    lines: list[LogLine] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _TAINT_STAMP.match(raw)
        if match is None:
            lines.append(LogLine(None, raw, raw))
            continue
        month, day, hour, minute, second, millisecond = (int(part) for part in match.groups()[:6])
        lines.append(
            LogLine(
                _log_datetime(reference, month, day, hour, minute, second, millisecond),
                match.group(7),
                raw,
            )
        )
    return lines


def _taint_entries(lines: Sequence[LogLine]) -> list[Entry]:
    entries: list[Entry] = []
    for line in lines:
        folder = folder_in(line.text)
        if folder is None:
            continue
        message = line.text.strip()
        signature = signature_for("taint", message, "")
        when = line.when.timestamp() if line.when is not None else None
        entries.append(
            Entry(
                source="taint",
                folder=folder,
                repo=FOLDERS[folder],
                signature=signature,
                kind="taint",
                message=message,
                stack="",
                count=1,
                first_seen=when,
                last_seen=when,
                version="",
                build="",
                locale="",
            )
        )
    return entries


def _journal_log_lines(data: dict[object, Any]) -> list[LogLine]:
    lines: list[LogLine] = []
    for raw in table_values(data.get("log")):
        text = _text(raw).strip()
        if text:
            lines.append(LogLine(None, text, text))
    return lines


@dataclass(frozen=True)
class Loaded:
    entries: tuple[Entry, ...]
    log_lines: tuple[LogLine, ...]
    warnings: tuple[str, ...]


def load_sources(wtf: Path, logs: Path, reference: datetime | None = None) -> Loaded:
    """Read every Forever journal, BugGrabber and taint.log under the client's WTF and Logs folders."""
    entries: list[Entry] = []
    warnings: list[str] = []
    journal_log: list[LogLine] = []
    for path in sorted(wtf.rglob("SavedVariables/*.lua")):
        try:
            variables = load_lua(path)
        except (OSError, LuaSyntaxError) as error:
            warnings.append(f"{path}: {error}")
            continue
        smoke = variables.get("DevSmokeDB")
        if isinstance(smoke, dict):
            entries.extend(_smoke_entries(smoke, warnings))
        for name, data in variables.items():
            folder = folder_for_global(name)
            if folder is None or not isinstance(data, dict) or "errors" not in data:
                continue
            entries.extend(_journal_entries(folder, data))
            journal_log.extend(_journal_log_lines(data))
    entries.extend(_buggrabber_entries(wtf, warnings))
    log_lines = journal_log + read_taint_log(logs / "taint.log", reference)
    entries.extend(_taint_entries(log_lines))
    return Loaded(tuple(entries), tuple(log_lines), tuple(warnings))


# --------------------------------------------------------------------------------------------------
# Grouping and display


@dataclass
class Group:
    repo: str
    signature: str
    kind: str
    message: str
    stack: str
    count: int
    live_count: int
    stale_count: int
    first_seen: float | None
    last_seen: float | None
    versions: tuple[str, ...]
    builds: tuple[str, ...]
    locales: tuple[str, ...]
    folders: tuple[str, ...]
    addons: tuple[str, ...]

    @property
    def hash(self) -> str:
        return signature_hash(self.signature)

    @property
    def stale(self) -> bool:
        """Every sighting predates the installed build, so it cannot describe the code installed now."""
        return self.live_count == 0 and self.stale_count > 0


def install_times(wtf: Path) -> dict[str, float]:
    """Each installed addon folder's build time, from its TOC's mtime, following symlinks."""
    addons = wtf.parent / "Interface" / "AddOns"
    times: dict[str, float] = {}
    for folder in FOLDERS:
        try:
            times[folder] = (addons / folder / f"{folder}.toc").stat().st_mtime
        except OSError:
            continue
    return times


def is_stale(entry: Entry, installs: Mapping[str, float]) -> bool:
    install = installs.get(entry.folder)
    return entry.last_seen is not None and install is not None and entry.last_seen < install


def _make_group(repo: str, signature: str, items: Sequence[Entry], installs: Mapping[str, float]) -> Group:
    first_seen = min((entry.first_seen for entry in items if entry.first_seen is not None), default=None)
    last_seen = max((entry.last_seen for entry in items if entry.last_seen is not None), default=None)
    live = [entry for entry in items if not is_stale(entry, installs)]
    stale = [entry for entry in items if is_stale(entry, installs)]
    live_count = sum(max(entry.count, 0) for entry in live)
    stale_count = sum(max(entry.count, 0) for entry in stale)
    return Group(
        repo=repo,
        signature=signature,
        kind=", ".join(sorted({entry.kind for entry in items if entry.kind})) or "error",
        message=next((entry.message for entry in items if entry.message), ""),
        stack=next((entry.stack for entry in items if entry.stack), ""),
        count=live_count + stale_count,
        live_count=live_count,
        stale_count=stale_count,
        first_seen=first_seen,
        last_seen=last_seen,
        versions=tuple(sorted({entry.version for entry in items if entry.version})),
        builds=tuple(sorted({entry.build for entry in items if entry.build})),
        locales=tuple(sorted({entry.locale for entry in items if entry.locale})),
        folders=tuple(sorted({entry.folder for entry in items})),
        addons=tuple(sorted({addon for entry in items for addon in entry.addons})),
    )


def group_entries(entries: Iterable[Entry], installs: Mapping[str, float] | None = None) -> list[Group]:
    buckets: dict[tuple[str, str], list[Entry]] = {}
    for entry in entries:
        buckets.setdefault((entry.repo, entry.signature), []).append(entry)
    known = installs or {}
    groups = [_make_group(repo, signature, items, known) for (repo, signature), items in buckets.items()]
    groups.sort(key=lambda group: (group.repo, -(group.last_seen or 0.0), group.signature))
    return groups


def keep_since(entries: Iterable[Entry], since: float) -> list[Entry]:
    """Keep entries last seen at or after since; an entry with no time cannot pass the gate."""
    return [entry for entry in entries if entry.last_seen is not None and entry.last_seen >= since]


def seen_text(value: float | None) -> str:
    return "-" if value is None else datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")


def _one_line(text: str, limit: int) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 3] + "..."


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n... (truncated)"


def format_table(groups: Sequence[Group]) -> str:
    if not groups:
        return "no Lua errors found"
    header = ("REPO", "SIGNATURE", "KIND", "COUNT", "STALE", "FIRST SEEN", "LAST SEEN", "VERSION", "MESSAGE")
    rows = [
        (
            group.repo,
            group.hash,
            group.kind,
            f"{group.live_count} live, {group.stale_count} stale",
            "yes" if group.stale else "-",
            seen_text(group.first_seen),
            seen_text(group.last_seen),
            ", ".join(group.versions) or "-",
            _one_line(group.message, 70) or "-",
        )
        for group in groups
    ]
    widths = [max(len(row[index]) for row in (header, *rows)) for index in range(len(header))]
    lines = []
    for row in (header, *rows):
        cells = [cell[:width].ljust(width) for cell, width in zip(row, widths, strict=True)]
        lines.append("  ".join(cells).rstrip())
    lines.append("")
    live = sum(group.live_count for group in groups)
    stale = sum(group.stale_count for group in groups)
    lines.append(f"{len(groups)} signature(s), {live} live, {stale} stale occurrence(s)")
    return "\n".join(lines)


def group_json(group: Group) -> dict[str, object]:
    return {
        "repo": group.repo,
        "signature": group.signature,
        "signatureHash": group.hash,
        "kind": group.kind,
        "count": group.count,
        "liveCount": group.live_count,
        "staleCount": group.stale_count,
        "stale": group.stale,
        "firstSeen": group.first_seen,
        "lastSeen": group.last_seen,
        "firstSeenText": seen_text(group.first_seen),
        "lastSeenText": seen_text(group.last_seen),
        "versions": list(group.versions),
        "builds": list(group.builds),
        "locales": list(group.locales),
        "folders": list(group.folders),
        "message": group.message,
        "stack": group.stack,
    }


def addon_matches(folder: str, name: str) -> bool:
    """Accept a folder name, a repository name or its short form."""
    wanted = name.strip().lower()
    repo = FOLDERS[folder]
    return wanted in (folder.lower(), repo.lower(), repo.split("/", 1)[1].lower())


def addon_known(name: str) -> bool:
    return any(addon_matches(folder, name) for folder in FOLDERS)


# --------------------------------------------------------------------------------------------------
# Filing issues


class GhError(RuntimeError):
    """gh could not answer or refused a write."""


GhRunner = Callable[[list[str], str | None], tuple[int, str, str]]


def run_gh(args: list[str], stdin_text: str | None = None) -> tuple[int, str, str]:
    """Run gh with stdin from /dev/null, so no command can stop at a prompt."""
    if stdin_text is None:
        completed = subprocess.run(
            ["gh", *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        completed = subprocess.run(
            ["gh", *args],
            input=stdin_text,
            capture_output=True,
            text=True,
            check=False,
        )
    return completed.returncode, completed.stdout, completed.stderr


@dataclass(frozen=True)
class Issue:
    number: int
    body: str


class Gh:
    """The gh calls the filer makes, behind one injected runner so the tests fake the network."""

    def __init__(self, runner: GhRunner = run_gh) -> None:
        self.runner = runner

    def _json(self, args: list[str]) -> object:
        code, out, err = self.runner(args, None)
        if code:
            raise GhError(err.strip() or f"gh exited {code}")
        try:
            return json.loads(out or "[]")
        except json.JSONDecodeError as error:
            raise GhError(f"gh returned invalid JSON: {error}") from error

    def open_error_issues(self, repo: str) -> list[Issue]:
        data = self._json(
            [
                "issue",
                "list",
                "-R",
                repo,
                "--label",
                LABEL,
                "--state",
                "open",
                "--json",
                "number,body",
                "--limit",
                str(ISSUE_LIST_LIMIT),
            ]
        )
        issues = []
        for item in data if isinstance(data, list) else []:
            if isinstance(item, dict) and "number" in item:
                issues.append(Issue(_as_int(item.get("number")), _text(item.get("body"))))
        return issues

    def comments(self, repo: str, number: int) -> list[str]:
        data = self._json(["issue", "view", str(number), "-R", repo, "--json", "comments"])
        comments = data.get("comments") if isinstance(data, dict) else None
        return [_text(item.get("body")) for item in comments or [] if isinstance(item, dict)]

    def ensure_label(self, repo: str) -> None:
        try:
            names = {
                _text(item.get("name"))
                for item in self._json(["label", "list", "-R", repo, "--json", "name", "--limit", "200"])
                if isinstance(item, dict)
            }
        except GhError:
            names = set()
        if LABEL in names:
            return
        code, _, err = self.runner(
            ["label", "create", LABEL, "-R", repo, "--color", LABEL_COLOR, "--description", LABEL_DESCRIPTION],
            None,
        )
        if code:
            raise GhError(err.strip() or f"could not create the {LABEL} label in {repo}")

    def comment(self, repo: str, number: int, body: str) -> None:
        code, _, err = self.runner(
            ["issue", "comment", str(number), "-R", repo, "--body-file", "-"],
            body,
        )
        if code:
            raise GhError(err.strip() or f"could not comment on {repo}#{number}")

    def create(self, repo: str, title: str, body: str) -> int | None:
        code, out, err = self.runner(
            ["issue", "create", "-R", repo, "--title", title, "--body-file", "-", "--label", LABEL],
            body,
        )
        if code:
            raise GhError(err.strip() or f"could not create an issue in {repo}")
        tail = out.strip().rstrip("/").rsplit("/", 1)[-1]
        return int(tail) if tail.isdigit() else None


def find_issue(issues: Sequence[Issue], signature: str) -> Issue | None:
    for issue in issues:
        if signature in issue.body:
            return issue
    return None


def last_count(bodies: Sequence[str]) -> int | None:
    """The last count any comment recorded, so a repeat is only commented when the number rose."""
    found: int | None = None
    for body in bodies:
        for match in _COUNT_MARKER.finditer(body):
            found = int(match.group(1))
    return found


@dataclass(frozen=True)
class Decision:
    action: str
    group: Group
    issue: int | None = None
    reason: str = ""


def decide(group: Group, issues: Sequence[Issue], comments: Sequence[str]) -> Decision:
    issue = find_issue(issues, group.hash)
    if issue is None:
        return Decision("create", group)
    previous = last_count([issue.body, *comments])
    if previous is not None and group.count <= previous:
        return Decision("skip", group, issue.number, f"count {group.count} is not above the last comment's {previous}")
    return Decision("comment", group, issue.number, f"count {group.count}, last comment {previous or 0}")


def issue_title(group: Group) -> str:
    message = " ".join(group.message.split())
    return f"Lua error: {message[:80] or group.kind}"


def issue_body(group: Group, log_lines: Sequence[str] = ()) -> str:
    lines = [
        f"<!-- forever-errors: signature={group.hash} count={group.count} -->",
        f"Signature: `{group.hash}`",
        f"Kind: {group.kind}",
        f"Repository: {group.repo}",
        f"Addon folder: {', '.join(group.folders)}",
        f"Versions: {', '.join(group.versions) or 'unknown'}",
        f"Build: {', '.join(group.builds) or 'unknown'}",
        f"Locale: {', '.join(group.locales) or 'unknown'}",
        f"Occurrences: {group.live_count} live, {group.stale_count} stale",
        f"First seen: {seen_text(group.first_seen)}",
        f"Last seen: {seen_text(group.last_seen)}",
        "",
        "Message:",
        "```text",
        _clip(group.message, MAX_BODY_TEXT) or "(no message)",
        "```",
        "",
        "Stack:",
        "```lua",
        _clip(group.stack, MAX_BODY_TEXT) or "(no stack)",
        "```",
    ]
    if log_lines:
        lines.extend(
            [
                "",
                f"Taint log, the {len(log_lines)} lines before the last sighting:",
                "```text",
                *log_lines,
                "```",
            ]
        )
    return "\n".join(lines)


def comment_body(group: Group) -> str:
    return "\n".join(
        [
            f"<!-- forever-errors: count={group.count} -->",
            f"Seen again: {group.live_count} live, {group.stale_count} stale occurrences now, "
            f"last seen {seen_text(group.last_seen)}.",
            f"Signature: `{group.hash}`",
        ]
    )


def log_context(
    lines: Sequence[LogLine],
    last_seen: float | None,
    folder: str,
    limit: int = LOG_CONTEXT_LINES,
) -> list[str]:
    """The taint log lines up to the last sighting, ending at a line that names the folder."""
    if not lines:
        return []
    if last_seen is None:
        matching = [line for line in lines if folder in line.text]
        return [line.raw for line in matching[-limit:]]
    cutoff = datetime.fromtimestamp(last_seen)
    before = [line for line in lines if line.when is None or line.when <= cutoff]
    if not before:
        return []
    end = len(before) - 1
    for index in range(len(before) - 1, -1, -1):
        if folder in before[index].text:
            end = index
            break
    start = max(0, end - limit + 1)
    return [line.raw for line in before[start : end + 1]]


def file_groups(
    groups: Sequence[Group],
    gh: Gh,
    *,
    dry_run: bool = False,
    include_stale: bool = False,
    log_lines: Sequence[LogLine] = (),
    out: Callable[[str], None] = print,
) -> list[Decision]:
    """Create or update one issue per group; returns every decision, including the skips."""
    cache: dict[str, list[Issue]] = {}
    decisions: list[Decision] = []
    for group in groups:
        if group.stale and not include_stale:
            reason = "stale: seen before the installed build"
            decisions.append(Decision("skip", group, None, reason))
            out(f"skipped (stale: seen before the installed build): {group.repo} {group.hash}")
            continue
        if group.repo not in cache:
            cache[group.repo] = gh.open_error_issues(group.repo)
        issues = cache[group.repo]
        existing = find_issue(issues, group.hash)
        comments = gh.comments(group.repo, existing.number) if existing else []
        decision = decide(group, issues, comments)
        decisions.append(decision)
        if decision.action == "create":
            title = issue_title(group)
            if dry_run:
                out(f"would create {group.repo}: {title}")
                continue
            gh.ensure_label(group.repo)
            body = issue_body(group, log_context(log_lines, group.last_seen, group.folders[0]))
            number = gh.create(group.repo, title, body)
            out(f"created {group.repo}#{number if number is not None else '?'}: {title}")
        elif decision.action == "comment":
            if dry_run:
                out(f"would comment on {group.repo}#{decision.issue}: {decision.reason}")
                continue
            gh.comment(group.repo, int(decision.issue or 0), comment_body(group))
            out(f"commented on {group.repo}#{decision.issue}: {decision.reason}")
        else:
            out(f"skipped {group.repo}#{decision.issue}: {decision.reason}")
    return decisions


# --------------------------------------------------------------------------------------------------
# Command line


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wtf", type=Path, default=DEFAULT_WTF, help="the client's WTF folder")
    parser.add_argument("--logs", type=Path, help="the client's Logs folder (default: beside WTF)")
    parser.add_argument("--since", type=float, metavar="UNIX_TIME", help="keep entries last seen at or after this time")
    parser.add_argument("--addon", metavar="NAME", help="only this addon folder, repository or repository short name")
    parser.add_argument("--json", action="store_true", help="print the groups as JSON for agents")
    parser.add_argument("--file", action="store_true", dest="file_issues", help="create or update GitHub issues")
    parser.add_argument(
        "--include-stale",
        action="store_true",
        help="also show and file groups last seen before the installed build",
    )
    parser.add_argument("--dry-run", action="store_true", help="with --file, print what would happen and write nothing")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.dry_run and not arguments.file_issues:
        print("--dry-run needs --file", file=sys.stderr)
        return 2
    if arguments.addon and not addon_known(arguments.addon):
        print(f"unknown addon: {arguments.addon}", file=sys.stderr)
        return 2
    logs = arguments.logs if arguments.logs is not None else arguments.wtf.parent / "Logs"
    loaded = load_sources(arguments.wtf, logs)
    for warning in loaded.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    entries: Iterable[Entry] = loaded.entries
    if arguments.since is not None:
        entries = keep_since(entries, arguments.since)
    if arguments.addon:
        entries = [entry for entry in entries if addon_matches(entry.folder, arguments.addon or "")]
    all_groups = group_entries(entries, install_times(arguments.wtf))
    live_groups = [group for group in all_groups if not group.stale]
    shown = all_groups if arguments.include_stale else live_groups
    if arguments.json:
        print(json.dumps([group_json(group) for group in shown], indent=2))
    else:
        print(format_table(shown))
    if arguments.file_issues and all_groups:
        stream = sys.stderr if arguments.json else sys.stdout

        def out(line: str) -> None:
            print(line, file=stream)

        try:
            file_groups(
                all_groups,
                Gh(),
                dry_run=arguments.dry_run,
                include_stale=arguments.include_stale,
                log_lines=loaded.log_lines,
                out=out,
            )
        except GhError as error:
            print(f"gh failed: {error}", file=sys.stderr)
            return 2
    return 1 if live_groups else 0


if __name__ == "__main__":
    sys.exit(main())
