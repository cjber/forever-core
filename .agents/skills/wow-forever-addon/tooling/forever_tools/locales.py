"""Check an addon's translations against its English template (WFA-34), never executing them.

Every addon keys its phrases through `L["..."]` and commits a template, `Locales/phrases.txt`, holding each key with its
English text. A translation is `Locales/<locale>.lua`: `local _, ns = ...`, the guard
`if GetLocale() ~= "<locale>" then return end`, `local L = ns.L`, then `L["key"] = "text"` (or `L.KEY = "text"`) for
each line it translates. A line it leaves out falls back to English, so a gap is reported as coverage and only fails
under `--release`. `check` fails on:

- a file LuaJIT can't parse (`luajit` must be installed; CI installs it from apt), a statement this module can't read
  as that layout or in that order, or a key assigned twice;
- a key the template doesn't have;
- a translated line whose format placeholders (`%s`, `%d`, `%.1f`, `%2$s`, ...) differ from English in kind, count
  or order (positional ones may reorder), or one that `string.format` would reject;
- a line whose colour, texture, atlas or link escapes (`|cAARRGGBB`, `|r`, `|T...|t`, `|A...|a`, `|H...|h`) differ
  from English in payload or count, close a colour before opening it, or whose grammar (`|4`) or newline count
  differs;
- a translation that a root TOC doesn't load after the English file, or whose `GetLocale` guard names another locale.

    python3 tools/check_locales.py             # check every Locales/<locale>.lua and print each locale's coverage
    python3 tools/check_locales.py --release   # also fail when a shipped locale is below 100% (WFA-16)
"""

import argparse
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .lua import LuaSyntaxError, Token, tokenize
from .luadata import LuaDataError, unescape

__all__ = ["LOCALES", "Policy", "check", "escapes", "main", "parse", "placeholders"]

# The client languages besides English (WFA-34); a file for any other code is refused.
LOCALES = ("deDE", "esES", "esMX", "frFR", "itIT", "koKR", "ptBR", "ruRU", "zhCN", "zhTW")
# Lua 5.1's string.format: flags, a width and precision of at most two digits each, and its conversions; WoW's own
# string.format also takes a position (`%2$s`). The space flag is left out: in UI text "5% cut" is a literal percent
# sign, and no addon line uses `% d`.
SPEC = re.compile(r"%(?:(\d+)\$)?([-+#0]*)(\d*)(?:\.(\d*))?([a-zA-Z%])")
CONVERSIONS = set("cdiouxXeEfgGqs")
# Escapes whose payload must survive translation unchanged, and those only counted.
PAYLOAD = re.compile(r"\|c[0-9a-fA-F]{8}|\|r|\|T[^|]*\|t|\|A[^|]*\|a|\|H[^|]*\|h")
COUNTED = {"|4": "|4", "\n": "newline"}
DECIMAL = re.compile(r"\\(\d{1,3})")


@dataclass(frozen=True)
class Policy:
    """`locales`: the folder of translations, relative to the addon root. `template`: the English template in it.
    `english`: the English file, which is not a translation and must load before every one."""

    locales: str = "Locales"
    template: str = "phrases.txt"
    english: str = "enUS.lua"


@dataclass(frozen=True)
class Entry:
    text: str
    line: int


class LocaleError(ValueError):
    pass


DEFAULT = Policy()


def parse(source: str) -> tuple[str | None, dict[str, Entry]]:
    """A translation file's `GetLocale` guard and its lines. The layout is fixed: `local <name>, ns = ...`, the guard
    `if GetLocale() ~= "<locale>" then return end` and `local L = ns.L`, each once and in that order, before any
    `L["key"] = "text"` or `L.KEY = "text"` (a `;` may end a statement). Anything else raises LocaleError."""
    try:
        tokens, _ = tokenize(source)
    except LuaSyntaxError as error:
        raise LocaleError(f"syntax error at line {error}") from error
    locale, entries, i, stage = None, {}, 0, 0  # stage: 0 start, 1 after ns, 2 after the guard, 3 after L

    def at(offset: int) -> Token:
        return tokens[min(i + offset, len(tokens) - 1)]

    def texts(*expected: str) -> bool:
        return all(at(n).text == want for n, want in enumerate(expected))

    def advance(step: int, line: int, want: int, what: str) -> None:
        nonlocal i, stage
        if stage != want:
            raise LocaleError(f"line {line}: {what} must come once, in the order ns, GetLocale guard, L")
        i, stage = i + step, want + 1

    while at(0).text != "<eof>":
        line = at(0).line
        if at(0).text == ";":
            i += 1
        elif at(0).text == "local" and at(1).kind == "name" and texts("local", at(1).text, ",", "ns", "=", "..."):
            advance(6, line, 0, "`local _, ns = ...`")
        elif texts("if", "GetLocale", "(", ")", "~=") and at(5).kind == "string":
            if not texts("if", "GetLocale", "(", ")", "~=", at(5).text, "then", "return", "end"):
                raise LocaleError(f"line {line}: the GetLocale guard must be `if ... then return end`")
            locale = _string(at(5))
            advance(9, line, 1, "the GetLocale guard")
        elif texts("local", "L", "=", "ns", ".", "L"):
            advance(6, line, 2, "`local L = ns.L`")
        elif texts("L", "[") and at(2).kind == "string" and texts("L", "[", at(2).text, "]", "="):
            key = _string(at(2))
            i += 5
            _entry(key, line, stage, entries, tokens, i)
            i = _skip_value(tokens, i)
        elif texts("L", ".") and at(2).kind == "name" and at(3).text == "=":
            key = at(2).text
            i += 4
            _entry(key, line, stage, entries, tokens, i)
            i = _skip_value(tokens, i)
        else:
            raise LocaleError(f'line {line}: expected L["key"] = "text", found {at(0).text!r}')
    if stage < 3:
        raise LocaleError("the file needs `local _, ns = ...`, the GetLocale guard and `local L = ns.L`")
    return locale, entries


def _entry(key: str, line: int, stage: int, entries: dict[str, Entry], tokens: list[Token], i: int) -> None:
    if stage < 3:
        raise LocaleError(f"line {line}: {key!r} comes before `local L = ns.L` and the GetLocale guard")
    if tokens[i].kind != "string":
        raise LocaleError(f"line {line}: {key!r} must be assigned a string")
    parts = [_string(tokens[i])]
    while tokens[i + 1].text == ".." and tokens[i + 2].kind == "string":
        i += 2
        parts.append(_string(tokens[i]))
    if key in entries:
        raise LocaleError(f"line {line}: {key!r} is assigned twice (first at line {entries[key].line})")
    entries[key] = Entry("".join(parts), line)


def _skip_value(tokens: list[Token], i: int) -> int:
    i += 1
    while tokens[i].text == ".." and tokens[i + 1].kind == "string":
        i += 2
    return i


def _string(token: Token) -> str:
    """A string token's text. Decimal escapes are bytes, as in Lua, so `caf\\195\\169` reads as UTF-8 `café`."""
    try:
        text = unescape(token.text)
    except LuaDataError as error:
        raise LocaleError(f"line {token.line}: {error}") from error
    if token.text[0] != "[" and any(int(code) > 127 for code in DECIMAL.findall(token.text)):
        try:
            return text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            raise LocaleError(f"line {token.line}: decimal escapes that aren't UTF-8") from None
    return text


def placeholders(text: str) -> tuple[list[tuple[int | None, str]], list[str]]:
    """Each format placeholder in order as (position or None, conversion), `%%` left out; and every placeholder that
    `string.format` would reject (an unknown conversion, or a width or precision past two digits)."""
    found, bad = [], []
    for match in SPEC.finditer(text):
        position, _, width, precision, conversion = match.groups()
        if conversion == "%":
            if match.group(0) != "%%":
                bad.append(match.group(0))
            continue
        if conversion not in CONVERSIONS or len(width) > 2 or len(precision or "") > 2:
            bad.append(match.group(0))
            continue
        found.append((int(position) if position else None, "d" if conversion == "i" else conversion))
    if text.replace("%%", "").count("%") > len(found) + len(bad):
        bad.append("%")
    return found, bad


def _order(found: list[tuple[int | None, str]]) -> list[str] | None:
    """The conversions in argument order: positional ones sorted by position, which must run 1..n with no gap."""
    if not any(position for position, _ in found):
        return [conversion for _, conversion in found]
    if not all(position for position, _ in found):
        return None
    by_position = {}
    for position, conversion in found:
        if by_position.setdefault(position, conversion) != conversion:
            return None
    if sorted(by_position) != list(range(1, len(by_position) + 1)):
        return None
    return [by_position[n] for n in range(1, len(by_position) + 1)]


def escapes(text: str) -> tuple[Counter, list[str]]:
    """(each UI escape with its payload, and each counted escape, by how often it occurs; the colour and link escapes
    in order). `||` is a literal bar, not an escape."""
    text = text.replace("||", "")
    tokens = PAYLOAD.findall(text)
    counts = Counter(tokens)
    for escape, name in COUNTED.items():
        counts[name] = text.count(escape)
    return counts, tokens


def _balanced(tokens: list[str]) -> bool:
    depth = 0
    for token in tokens:
        if token.startswith("|c"):
            depth += 1
        elif token == "|r":
            if depth == 0:
                return False
            depth -= 1
    return True


def _compare(english: str, translated: str) -> list[str]:
    problems = []
    want, english_bad = placeholders(english)
    have, bad = placeholders(translated)
    if english_bad or not (want or "%%" in english):
        # Not a format string: a literal % in the translation is fine, a placeholder is not.
        if have:
            problems.append(f"placeholders {[c for _, c in have]} here but none in English")
    elif bad:
        problems.append(f"string.format would reject {', '.join(bad)}")
    elif _order(want) != _order(have):
        gap = any(p for p, _ in have) and _order(have) is None
        problems.append(
            f"placeholders {[c for _, c in want]} in English but {[c for _, c in have]} here"
            + (" (positions must run 1..n, each with one conversion)" if gap else "")
        )
    (english_counts, _), (translated_counts, order) = escapes(english), escapes(translated)
    for escape in sorted(set(english_counts) | set(translated_counts)):
        if english_counts[escape] != translated_counts[escape]:
            shown = escape if escape in COUNTED.values() else repr(escape)
            problems.append(f"{english_counts[escape]} {shown} in English but {translated_counts[escape]} here")
    if not _balanced(order):
        problems.append("a |r closes a colour before a |c opens it")
    return problems


def _toc_problems(root: Path, path: str, english: str) -> list[str]:
    """Why some root TOC doesn't load `path` after `english` (forward-slash paths), or nothing."""
    problems = []
    for toc in sorted(root.glob("*.toc")):
        lines = [
            line.strip().replace("\\", "/").lower()
            for line in toc.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if path.lower() not in lines:
            problems.append(f"not loaded by {toc.name}; list it after {english}")
        elif english.lower() not in lines or lines.index(english.lower()) > lines.index(path.lower()):
            problems.append(f"{toc.name} loads it before {english}; move it after")
    return problems


def _luajit_problems(paths: list[Path]) -> list[str]:
    luajit = shutil.which("luajit")
    if luajit is None:
        return ["luajit: not found; install it (CI installs it from apt) so each translation is parsed as Lua"]
    script = "for _, path in ipairs(arg) do local ok, err = loadfile(path) if not ok then print(err) end end"
    # `luajit - <paths>` reads the program from stdin and passes the paths in `arg`; loadfile only parses.
    result = subprocess.run([luajit, "-", *map(str, paths)], input=script, capture_output=True, text=True, check=False)
    problems = [line for line in result.stdout.splitlines() + result.stderr.splitlines() if line.strip()]
    if result.returncode and not problems:
        problems.append(f"luajit: exited {result.returncode} while parsing the translations")
    return problems


def check(root: Path, policy: Policy = DEFAULT, release: bool = False) -> tuple[list[str], list[str]]:
    """(problems, coverage lines) for the translations under `root`. With `release`, a locale below 100% fails."""
    folder = root / policy.locales
    template = folder / policy.template
    problems, coverage = [], []
    try:
        _, reference = parse(template.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"{policy.locales}/{policy.template}: missing"], []
    except LocaleError as error:
        return [f"{policy.locales}/{policy.template}: {error}"], []
    paths = sorted(path for path in folder.glob("*.lua") if path.name != policy.english)
    problems += _luajit_problems(paths) if paths else []
    english = f"{policy.locales}/{policy.english}"
    for path in paths:
        name = f"{policy.locales}/{path.name}"
        if path.stem not in LOCALES:
            problems.append(f"{name}: {path.stem} is not a client language ({', '.join(LOCALES)})")
            continue
        problems += [f"{name}: {problem}" for problem in _toc_problems(root, name, english)]
        try:
            locale, entries = parse(path.read_text(encoding="utf-8"))
        except (LocaleError, UnicodeDecodeError) as error:
            problems.append(f"{name}: {error}")
            continue
        if locale != path.stem:
            problems.append(f"{name}: its GetLocale guard names {locale!r}, not {path.stem!r}")
        for key, entry in entries.items():
            if key not in reference:
                problems.append(f"{name}:{entry.line}: {key!r} is not in {policy.template}; regenerate or remove it")
                continue
            problems += [
                f"{name}:{entry.line}: {key!r}: {problem}" for problem in _compare(reference[key].text, entry.text)
            ]
        translated = sum(1 for key in entries if key in reference)
        share = 100 * translated // len(reference) if reference else 100
        coverage.append(f"{path.stem}: {translated} of {len(reference)} lines ({share}%)")
        if release and translated < len(reference):
            missing = sorted(set(reference) - set(entries))
            problems.append(f"{name}: {len(missing)} line(s) untranslated, such as {missing[0]!r}; translate them")
    shipped = {path.stem for path in paths}
    coverage += [f"{code}: no file, so English" for code in LOCALES if code not in shipped]
    return problems, coverage


def main(root: Path, policy: Policy = DEFAULT, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release", action="store_true", help="also fail when a shipped locale is below 100%%")
    args = parser.parse_args(argv)
    problems, coverage = check(root, policy, release=args.release)
    for line in coverage:
        print(line)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"locales: every translation matches {policy.locales}/{policy.template}")
    return 0
