"""Read the table constructors of a generated Lua data file (never executing it).

Supports what the generators emit: nested tables, string and number keys, strings joined with `..`, numbers,
booleans and nil. Anything else raises LuaDataError so a report never describes data it did not read.
"""

import re
from dataclasses import dataclass, field

from .lua import LuaSyntaxError, Token, tokenize

ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v", "\\": "\\", '"': '"', "'": "'"}
ESCAPE = re.compile(r"\\(\d{1,3}|\n|.)", re.DOTALL)
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
LONG_STRING = re.compile(r"\[(=*)\[(.*)\]\1\]", re.DOTALL)


class LuaDataError(ValueError):
    pass


@dataclass
class Table:
    """A Lua table: `array` holds positional values in order, `keyed` the explicit `[key] = value` and `name =` ones."""

    array: list = field(default_factory=list)
    keyed: dict = field(default_factory=dict)


def unescape(literal: str) -> str:
    if literal[0] == "[":
        match = LONG_STRING.fullmatch(literal)
        if not match:
            raise LuaDataError(f"bad long string {literal[:20]!r}")
        body = match[2]
        return body[1:] if body.startswith("\n") else body

    def replace(match: re.Match[str]) -> str:
        code = match[1]
        if code.isdigit():
            return chr(int(code))
        if code == "\n":
            return "\n"
        if code in ESCAPES:
            return ESCAPES[code]
        raise LuaDataError(f"unsupported escape \\{code}")

    return ESCAPE.sub(replace, literal[1:-1])


def number(text: str) -> int | float:
    if text.lower().startswith("0x"):
        return int(text, 16)
    return int(text) if re.fullmatch(r"\d+", text) else float(text)


class _Reader:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def take(self, expected: str | None = None) -> Token:
        token = self.current
        if expected is not None and token.text != expected:
            raise LuaDataError(f"{token.line}: expected {expected!r}, got {token.text!r}")
        if token.text == "<eof>":
            raise LuaDataError(f"{token.line}: unexpected end of file")
        self.pos += 1
        return token

    def value(self):
        token = self.current
        if token.text == "{":
            return self.table()
        if token.text == "-" and self.tokens[self.pos + 1].kind == "number":
            self.take()
            return -number(self.take().text)
        if token.kind == "number":
            return number(self.take().text)
        if token.kind == "string":
            text = unescape(self.take().text)
            while self.current.text == "..":
                self.take()
                if self.current.kind != "string":
                    raise LuaDataError(f"{self.current.line}: only strings can be joined with ..")
                text += unescape(self.take().text)
            return text
        if token.text in {"true", "false", "nil"}:
            self.take()
            return {"true": True, "false": False, "nil": None}[token.text]
        raise LuaDataError(f"{token.line}: unsupported value {token.text!r}")

    def table(self) -> Table:
        self.take("{")
        result = Table()
        while self.current.text != "}":
            if self.current.text == "[":
                self.take()
                key = self.value()
                self.take("]")
                self.take("=")
                result.keyed[key] = self.value()
            elif self.current.kind == "name" and self.tokens[self.pos + 1].text == "=":
                key = self.take().text
                self.take("=")
                result.keyed[key] = self.value()
            else:
                result.array.append(self.value())
            if self.current.text not in {",", ";"}:
                break
            self.take()
        self.take("}")
        return result


def parse_tables(source: str) -> tuple[dict[str, Table], list[str]]:
    """The top-level `name = {...}` assignments by dotted name (`ns.Data.forever`), and the header comments:
    the line comments before the first statement, where a generator states its sources and counts.

    Other statements (`local _, ns = ...`) are skipped; a table that cannot be read raises LuaDataError.
    """
    try:
        tokens, comments = tokenize(source)
    except LuaSyntaxError as error:
        raise LuaDataError(str(error)) from error
    reader = _Reader(tokens)
    tables: dict[str, Table] = {}
    while reader.current.text != "<eof>":
        token = reader.current
        if token.kind == "name" and not (reader.pos and tokens[reader.pos - 1].text in {".", ","}):
            cursor = reader.pos
            parts = [token.text]
            while tokens[cursor + 1].text == "." and tokens[cursor + 2].kind == "name":
                parts.append(tokens[cursor + 2].text)
                cursor += 2
            if tokens[cursor + 1].text == "=" and tokens[cursor + 2].text == "{":
                reader.pos = cursor + 2
                tables[".".join(parts)] = reader.table()
                continue
        reader.pos += 1
    first = tokens[0].line
    return tables, [comments[line] for line in sorted(comments) if line < first]
