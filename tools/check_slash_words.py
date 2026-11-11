"""Refuse a slash command the client already owns.

The chat box runs the client's own secure commands before any addon's (`SLASH_*` aliases in `SlashCmdList`). A word
such as `/ma` is therefore the client's main assist even when an addon assigns `SLASH_MYADDON1 = "/ma"`: the addon
handler never runs and the player sees the client command instead. The client's words are listed in
tools/client_slash_words.txt, generated from the pinned build's GlobalStrings in every shipped locale.

Every addon Lua file is read, outside tests/, tools/, types/, docs/, Libs/ and dot folders, and a `SLASH_<KEY><n>`
assignment whose word the client defines fails, naming the file, line, word and the client key that owns it.

    python3 tools/check_slash_words.py                 this repository
    python3 tools/check_slash_words.py FILE...         only these files
    python3 tools/check_slash_words.py --refresh       rewrite tools/client_slash_words.txt from wago.tools
"""

import argparse
import csv
import io
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_client_load import SKIPPED_DIRS  # noqa: E402

WORDS_FILE = Path(__file__).resolve().with_name("client_slash_words.txt")
BUILD = "1.60.1.70425"
LOCALES = ("enUS", "deDE", "esES", "esMX", "frFR", "itIT", "koKR", "ptBR", "ruRU", "zhCN", "zhTW")
URL = "https://wago.tools/db2/GlobalStrings/csv?build={build}&locale={locale}"
USER_AGENT = "forever-core (+https://github.com/cjber/forever-core)"
SLASH_GLOBAL = re.compile(r"^SLASH_[A-Z0-9_]+$")


def _tokenize(source):
    """forever_tools.lua's lexer: tools/forever_tools in a consumer, the skill pack's tooling in forever-core."""
    tools = Path(__file__).resolve().parent
    for base in (tools, tools.parent / ".agents/skills/wow-forever-addon/tooling"):
        if (base / "forever_tools" / "lua.py").is_file():
            if str(base) not in sys.path:
                sys.path.insert(0, str(base))
            break
    from forever_tools.lua import tokenize

    return tokenize(source)[0]


def _symbol(token, text):
    return token.kind in ("symbol", "keyword") and token.text == text


def _string_value(token):
    """The text of a short string literal; None for a long string, whose contents are never a slash word."""
    text = token.text
    if text[:1] in ("'", '"'):
        return text[1:-1]
    return None


def addon_files(root):
    """Every Lua file the addon could ship: outside tests, tools, types, docs, Libs and dot folders."""
    files = []
    for path in sorted(root.rglob("*.lua")):
        parts = path.relative_to(root).parts
        if not path.is_file() or parts[0] in SKIPPED_DIRS or any(part.startswith(".") for part in parts):
            continue
        files.append(path)
    return files


def client_words(path=WORDS_FILE):
    """word -> the client keys that define it, from the generated list."""
    words = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        word, _, keys = line.partition(" ")
        words[word] = tuple(keys.split(","))
    return words


def lua_slash_words(tokens):
    """(line, global name, word) for every `SLASH_<KEY><n> = "..."` assignment in one file."""
    found = []
    for at, token in enumerate(tokens):
        if token.kind != "name" or not SLASH_GLOBAL.match(token.text):
            continue
        if not _symbol(tokens[at + 1], "="):
            continue
        value = tokens[at + 2]
        if value.kind == "string" and at + 3 < len(tokens) and _symbol(tokens[at + 3], ".."):
            continue
        word = _string_value(value)
        if word and word.startswith("/"):
            found.append((token.line, token.text, word))
    return found


def check(files, owned, root):
    """Print every finding as `file:line: message`; return whether any was found."""
    failed = False
    for path in files:
        try:
            source = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as error:
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
            continue
        try:
            assignments = lua_slash_words(_tokenize(source))
        except ValueError as error:  # forever_tools.lua.LuaSyntaxError
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
            continue
        shown = path.resolve().relative_to(root.resolve()) if path.resolve().is_relative_to(root.resolve()) else path
        for line, name, word in assignments:
            keys = owned.get(word.lower())
            if not keys:
                continue
            print(
                f'{shown}:{line}: slash-words: {name} = "{word}" is the client\'s own command, '
                f"{', '.join(keys)}; the chat box runs it first and never reaches this addon"
            )
            failed = True
    return failed


def download(url):
    last = None
    for attempt in range(6):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read()
            if not data.strip() or data.lstrip().startswith(b"<"):
                raise ValueError(f"expected CSV, got empty data or HTML from {url}")
            return data
        except Exception as error:  # noqa: BLE001 - network errors of every kind are retried
            last = error
            time.sleep(2 ** (attempt + 1))
    raise SystemExit(f"could not download {url}: {last}")


def refresh(path=WORDS_FILE):
    """Rewrite the pinned list from the build's GlobalStrings in every shipped locale."""
    words = {}
    for locale in LOCALES:
        data = download(URL.format(build=BUILD, locale=locale))
        for row in csv.DictReader(io.StringIO(data.decode("utf-8"), newline="")):
            key = row.get("BaseTag") or ""
            word = row.get("TagText_lang") or ""
            if key.startswith("SLASH_") and word.startswith("/"):
                words.setdefault(word.lower(), set()).add(key)
    header = [
        f"# Slash words the Forever client's GlobalStrings define, build {BUILD}.",
        "# Generated by tools/check_slash_words.py --refresh from wago.tools, every shipped locale unioned.",
        "# One word per line, lowercased, then the client keys that define it. Vendored from cjber/forever-core;",
        "# regenerate it there.",
        "# rule-ignore: file-size-no-growth - generated client data, one word per line",
    ]
    lines = [f"{word} {','.join(sorted(keys))}" for word, keys in sorted(words.items())]
    path.write_text("\n".join(header + lines) + "\n", encoding="utf-8")
    print(f"{path.name}: {len(words)} client slash words from build {BUILD}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--refresh", action="store_true", help="rewrite tools/client_slash_words.txt from wago.tools")
    arguments = parser.parse_args(argv)
    if arguments.refresh:
        return refresh()
    root = Path(__file__).resolve().parent.parent
    files = arguments.files or addon_files(root)
    if check(files, client_words(), root):
        return 1
    print(f"Slash word check: {len(files)} Lua files checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
