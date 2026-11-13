"""Fail text that spells the suite's shared addon as two words: it is ForeverCore, one word.

Every addon in the suite vendors this rule. It reads the checkout's text files for `Forever` followed by `Core` in
any case, two words separated by spaces or tabs, and names each placeholder:

    python3 tools/check_core_name.py             every text file in this checkout
    python3 tools/check_core_name.py --base REF  only the lines REF...HEAD adds

The full read skips CHANGELOG.md: its shipped entries are history and are never rewritten, so the file's old spelling
cannot keep the gate red. The `--base` read checks the lines a change adds, including a new CHANGELOG entry, and the
pull request workflows run that form so new text has to use one word. A repository name (`forever-core`) and a path
containing it are not text and never match: the rule is for the addon's name, not the slug.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

TWO_WORDS = re.compile(r"forever[ \t]+core", re.IGNORECASE)
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<line>\d+)(?:,\d+)? @@")
# Vendored tooling, generated caches, build output and VCS state are not the addon's text.
SKIP_DIRECTORIES = frozenset(
    {".git", ".cache", ".release", ".ruff_cache", ".mypy_cache", ".venv", "__pycache__", "dist", "node_modules", "venv"}
)
# Shipped changelog entries are history; the full read leaves the file alone and `--base` checks what a change adds.
HISTORY_FILES = frozenset({"CHANGELOG.md"})


def matches(line):
    """The two-word spelling in `line`, or None."""
    return TWO_WORDS.search(line)


def text_files(root):
    """Every text file under `root`, skipping the vendored caches, build output and shipped changelog history."""
    root = Path(root)
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or path.name in HISTORY_FILES or any(part in SKIP_DIRECTORIES for part in relative.parts):
            continue
        yield path


def check_tree(root):
    """Findings in every text file under `root`."""
    findings = []
    root = Path(root)
    for path in text_files(root):
        try:
            data = path.read_bytes()
        except OSError as error:
            findings.append(f"{path}: could not be read: {error}")
            continue
        if b"\0" in data:
            continue
        for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            found = matches(line)
            if found:
                location = path.relative_to(root).as_posix()
                findings.append(f"{location}:{number}: write ForeverCore, not {found.group(0)!r}")
    return findings


def added_lines(base, root):
    """Every line `base...HEAD` adds, as (path, line number, text); a git failure ends the check."""
    shown = subprocess.run(
        [
            "git",
            "diff",
            "--unified=0",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            f"{base}...HEAD",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if shown.returncode:
        raise SystemExit(f"git diff {base}...HEAD failed: {shown.stderr.strip()}")
    path = None
    number = 0
    added = []
    for line in shown.stdout.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            path = None if target == "/dev/null" else target[2:] if target.startswith("b/") else target
        elif line.startswith("@@"):
            found = HUNK.match(line)
            number = int(found["line"]) if found else 0
        elif path is not None and line.startswith("+"):
            added.append((path, number, line[1:]))
            number += 1
    return added


def check_added(base, root):
    """Findings in the lines `base...HEAD` adds."""
    return [
        f"{path}:{number}: write ForeverCore, not {found.group(0)!r}"
        for path, number, line in added_lines(base, root)
        if (found := matches(line))
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", help="check only the lines BASE...HEAD adds")
    arguments = parser.parse_args(argv)
    root = Path.cwd()
    if arguments.base is not None:
        if not arguments.base.strip():
            parser.error("--base needs a commit, so the added lines are exact")
        findings = check_added(arguments.base, root)
        scope = f"the lines {arguments.base}...HEAD adds"
    else:
        findings = check_tree(root)
        scope = "every text file"
    for finding in findings:
        print(finding)
    if findings:
        print(f"ForeverCore name: {len(findings)} two-word spelling(s) in {scope}; the addon is ForeverCore, one word")
        return 1
    print(f"ForeverCore name: {scope} spells the addon one word")
    return 0


if __name__ == "__main__":
    sys.exit(main())
