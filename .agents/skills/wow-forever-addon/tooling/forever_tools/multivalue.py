"""Reject accidental expansion of select() and listed multi-return calls in Lua 5.1 expression lists.

Parentheses force one value. Intentional expansion needs a trailing `-- multi-value: <reason>` on the line of
the final value, the call's closing parenthesis, or the closing delimiter.
"""

import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from .lua import LuaSyntaxError, Token, tokenize

__all__ = ["DEFAULT_RULES", "LuaSyntaxError", "Parser", "Rules", "check", "lua_files", "run"]


@dataclass(frozen=True)
class Rules:
    """Per-addon policy. `multi_return` names client functions and methods that return several values, flagged
    like select(); `spread_select` exempts select()'s own final argument, whose values it picks from."""

    multi_return: frozenset[str] = frozenset()
    spread_select: bool = False


DEFAULT_RULES = Rules()

# Pratt precedence preserves the distinction between select() and (select()):
# only a bare call can expand, including across newlines and inside nested calls.
PRECEDENCE = {
    "or": 1,
    "and": 2,
    "<": 3,
    ">": 3,
    "<=": 3,
    ">=": 3,
    "~=": 3,
    "==": 3,
    "..": 4,
    "+": 5,
    "-": 5,
    "*": 6,
    "/": 6,
    "%": 6,
    "^": 8,
}
BLOCK_END = {"end", "else", "elseif", "until", "<eof>"}
ALLOWED = re.compile(r"multi-value:\s*\S.*")
EXCLUDED_DIRS = frozenset({".git", ".claude", ".types", ".sift", ".release", ".cache"})


class Parser:
    """Walk the grammar so nested calls and function bodies keep their own expression lists."""

    def __init__(self, source: str, rules: Rules = DEFAULT_RULES):
        self.tokens, self.comments = tokenize(source)
        self.rules = rules
        self.pos = 0
        self.hits: list[tuple[int, str]] = []

    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def take(self, expected: str | None = None) -> Token:
        token = self.current
        if expected is not None and token.text != expected:
            raise LuaSyntaxError(f"{token.line}: expected {expected!r}, got {token.text!r}")
        if token.text == "<eof>":
            raise LuaSyntaxError(f"{token.line}: unexpected end of file")
        self.pos += 1
        return token

    def accept(self, text: str) -> bool:
        if self.current.text != text:
            return False
        self.take()
        return True

    def name(self) -> Token:
        if self.current.kind != "name":
            raise LuaSyntaxError(f"{self.current.line}: expected a name")
        return self.take()

    def flag(self, call: Token | None, context: str, end_line: int, value_line: int | None = None) -> None:
        if call is None:
            return
        if any(ALLOWED.fullmatch(self.comments.get(line, "")) for line in (end_line, value_line, call.end_line)):
            return
        self.hits.append(
            (
                call.line,
                f"multi-value: {call.text}() expands as the last {context}; parenthesise it or add "
                "-- multi-value: <reason>",
            )
        )

    def expressions(self) -> Token | None:
        last = self.expression()
        while self.accept(","):
            last = self.expression()
        return last

    def function_body(self) -> None:
        self.take("(")
        if not self.accept(")"):
            while True:
                if self.accept("..."):
                    break
                self.name()
                if not self.accept(","):
                    break
            self.take(")")
        self.block()
        self.take("end")

    def arguments(self, spread: bool = False) -> Token:
        """Parse one call's arguments; the last token consumed, which ends the call."""
        if self.accept("("):
            argument = None if self.current.text == ")" else self.expressions()
            value_line = self.tokens[self.pos - 1].line
            end = self.take(")")
            if not spread:
                self.flag(argument, "call argument", end.line, value_line)
            return end
        if self.current.text == "{":
            self.table()
        elif self.current.kind == "string":
            self.take()
        else:
            raise LuaSyntaxError(f"{self.current.line}: expected call arguments")
        return self.tokens[self.pos - 1]

    def table(self) -> None:
        self.take("{")
        last = None
        value_line = None
        while self.current.text != "}":
            if self.accept("["):
                self.expression()
                self.take("]")
                self.take("=")
                self.expression()
                last = None
            elif self.current.kind == "name" and self.tokens[self.pos + 1].text == "=":
                self.take()
                self.take("=")
                self.expression()
                last = None
            else:
                last = self.expression()
            value_line = self.tokens[self.pos - 1].line
            if not (self.accept(",") or self.accept(";")):
                break
        end = self.take("}")
        self.flag(last, "table element", end.line, value_line)

    def multi(self, token: Token) -> Token | None:
        """`token` when a call through that name can return several values."""
        return token if token.text == "select" or token.text in self.rules.multi_return else None

    def expression(self, minimum: int = 0) -> Token | None:
        token = self.current
        last = None
        callee = None
        if token.text in {"not", "#", "-"}:
            self.take()
            self.expression(7)
        elif token.text == "function":
            self.take()
            self.function_body()
        elif token.text == "{":
            self.table()
        elif token.kind in {"number", "string"} or token.text in {"nil", "true", "false", "..."}:
            self.take()
        elif token.kind == "name" or token.text == "(":
            if self.accept("("):
                start = self.pos
                self.expression()
                inner = self.tokens[start : self.pos]
                while len(inner) >= 3 and inner[0].text == "(" and inner[-1].text == ")":
                    inner = inner[1:-1]
                if len(inner) == 1 and inner[0].text == "select":
                    callee = inner[0]
                self.take(")")
            else:
                callee = self.multi(self.take())
            while True:
                if self.accept(".") or self.accept(":"):
                    member = self.name()
                    callee = member if member.text in self.rules.multi_return else None
                    last = None
                elif self.accept("["):
                    self.expression()
                    self.take("]")
                    callee, last = None, None
                elif self.current.text in {"(", "{"} or self.current.kind == "string":
                    spread = self.rules.spread_select and callee is not None and callee.text == "select"
                    end = self.arguments(spread)
                    last = replace(callee, end_line=end.end_line) if callee else None
                    callee = None
                else:
                    break
        else:
            raise LuaSyntaxError(f"{token.line}: expected an expression, got {token.text!r}")
        while (precedence := PRECEDENCE.get(self.current.text, -1)) >= minimum:
            operator = self.take().text
            self.expression(precedence if operator in {"^", ".."} else precedence + 1)
            last = None
        return last

    def block(self) -> None:
        while self.current.text not in BLOCK_END:
            if self.accept(";") or self.accept("break"):
                continue
            if self.accept("return"):
                if self.current.text not in BLOCK_END | {";"}:
                    last = self.expressions()
                    self.accept(";")
                    self.flag(last, "return value", self.tokens[self.pos - 1].line)
                continue
            if self.accept("do"):
                self.block()
                self.take("end")
            elif self.accept("while"):
                self.expression()
                self.take("do")
                self.block()
                self.take("end")
            elif self.accept("repeat"):
                self.block()
                self.take("until")
                self.expression()
            elif self.accept("if"):
                self.expression()
                self.take("then")
                self.block()
                while self.accept("elseif"):
                    self.expression()
                    self.take("then")
                    self.block()
                if self.accept("else"):
                    self.block()
                self.take("end")
            elif self.accept("for"):
                self.name()
                while self.accept(","):
                    self.name()
                if not self.accept("="):
                    self.take("in")
                self.expressions()
                self.take("do")
                self.block()
                self.take("end")
            elif self.accept("function"):
                self.name()
                while self.accept("."):
                    self.name()
                if self.accept(":"):
                    self.name()
                self.function_body()
            elif self.accept("local"):
                if self.accept("function"):
                    self.name()
                    self.function_body()
                else:
                    self.name()
                    while self.accept(","):
                        self.name()
                    if self.accept("="):
                        self.expressions()
            else:
                self.expressions()
                if self.accept("="):
                    self.expressions()

    def check(self) -> list[tuple[int, str]]:
        self.block()
        if self.current.text != "<eof>":
            raise LuaSyntaxError(f"{self.current.line}: unexpected {self.current.text!r}")
        return sorted(self.hits)


def check(source: str, rules: Rules = DEFAULT_RULES) -> list[tuple[int, str]]:
    """`(line, message)` for each expanding call in `source`; a syntax error raises LuaSyntaxError."""
    return Parser(source, rules).check()


def lua_files(paths: list[Path], excluded: frozenset[str] = EXCLUDED_DIRS) -> list[Path]:
    """Every Lua file under `paths`, skipping tool, cache and worktree folders."""
    return sorted(
        {
            file
            for path in paths
            for file in (path.rglob("*.lua") if path.is_dir() else [path])
            if not excluded.intersection(file.parts)
        }
    )


def run(files: list[Path], rules: Rules = DEFAULT_RULES) -> int:
    """Print `path:line: message` per finding; unreadable or malformed files fail closed. Exit status 1 on any."""
    failed = False
    for path in files:
        try:
            hits = check(path.read_text(encoding="utf-8"), rules)
        except (OSError, UnicodeDecodeError, LuaSyntaxError) as error:
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
            continue
        for line, message in hits:
            print(f"{path}:{line}: {message}")
        failed |= bool(hits)
    if not failed:
        print(f"Multi-value lint: {len(files)} Lua files checked")
    return int(failed)
