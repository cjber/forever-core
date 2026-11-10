"""Check docs/curseforge.md against the store page template (wow-forever-addon/store-page.md, WFA-11).

Each addon's CI runs this through tools/check_store_page.py, so a page that leaves a part out fails the build. The
repository comes from the root TOC's `## X-Website`, and the title the pitch opens with from its `## Title`.

python3 tools/check_store_page.py          # check docs/curseforge.md
python3 tools/check_store_page.py --words  # also print its prose word count
"""

import argparse
import re
import sys
from pathlib import Path

__all__ = ["FILE", "MAX_IMAGES", "MAX_WORDS", "MIN_IMAGES", "check", "main", "words"]

FILE = "docs/curseforge.md"
MIN_IMAGES, MAX_IMAGES = 3, 6
MIN_FEATURES, MAX_FEATURES = 3, 8
MAX_WORDS = 1000
DISCORD = "https://discord.gg/FpHugGxRJY"
SPONSOR = (
    "Free, with nothing locked behind it. If it saves you time, you can [sponsor me on GitHub]"
    "(https://github.com/sponsors/cjber), which takes no fees, or [buy me a coffee on Ko-fi](https://ko-fi.com/cjber)."
    f" For help and each day's release notes, [join me on Discord]({DISCORD})."
)
AI_LINE = "Built with AI assistance."
FAMILY = re.compile(r"<!-- forever-family:start -->.*?<!-- forever-family:end -->", re.DOTALL)
FAMILY_TOKEN = "<!-- forever-family -->"

# Prose words as WFA-10/11 count them: link text counts; the family block, code, images and markup do not.
NOT_PROSE = [
    FAMILY,
    re.compile(r"^ {0,3}```.*?^ {0,3}```", re.DOTALL | re.MULTILINE),
    re.compile(r"<!--.*?-->", re.DOTALL),
    re.compile(r"`[^`\n]*`"),  # code spans quote the game
    re.compile(r"!\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])"),  # images, inline or by reference
    re.compile(r"^ {0,3}\[[^\]]+\]:.*$", re.MULTILINE),  # link reference definitions
    re.compile(r"<[^>]+>"),
]
LINK = re.compile(r"\[([^\]]*)\](?:\([^)]*\)|\[[^\]]*\])")
URL = re.compile(r"\bhttps?://\S+")  # a bare address, once links have become their text
WORD = re.compile(r"[^\W_]+(?:['’.-][^\W_]+)*")
COLOUR = re.compile(r"\|c[0-9a-fA-F]{8}|\|r")


def words(text: str) -> int:
    """The page's prose word count, as check_copy.py --words prints it."""
    for pattern in NOT_PROSE:
        text = pattern.sub(" ", text)
    return len(WORD.findall(URL.sub(" ", LINK.sub(r"\1", text))))


def _toc(root: Path) -> dict[str, str]:
    tocs = sorted(root.glob("*.toc"))
    if not tocs:
        return {}
    fields = {}
    for line in tocs[0].read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"##\s*([\w-]+)\s*:\s*(.*)", line)
        if match:
            fields.setdefault(match.group(1), match.group(2).strip())
    return fields


def _raw(repo: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/cjber/{repo}/main/{path}"


def buttons(repo: str) -> str:
    """The button row that ends every page: Discord, GitHub Sponsors, Ko-fi."""
    return " ".join(
        f"[![{alt}]({_raw(repo, 'docs/' + image)})]({target})"
        for alt, image, target in (
            ("Join me on Discord", "discord-button.png", DISCORD),
            ("Sponsor me on GitHub", "github-sponsors-button.png", "https://github.com/sponsors/cjber"),
            ("Support me on Ko-fi", "kofi-button.png", "https://ko-fi.com/cjber"),
        )
    )


def source_line(repo: str) -> str:
    url = f"https://github.com/cjber/{repo}"
    return f"Source code and issues: [github.com/cjber/{repo}]({url}). Licence: GPL-3.0-or-later."


def _blocks(text: str) -> list[str]:
    """The page's paragraphs, headings and lists, with the family block as one FAMILY_TOKEN block."""
    text = FAMILY.sub(f"\n\n{FAMILY_TOKEN}\n\n", text)
    blocks = []
    for chunk in re.split(r"\n\s*\n", text):
        lines = [line.rstrip() for line in chunk.strip().splitlines()]
        # A heading on the line above its text is its own block.
        while lines and lines[0].startswith("#") and len(lines) > 1:
            blocks.append(lines.pop(0))
        if lines:
            blocks.append("\n".join(lines))
    return blocks


def check(root: Path) -> list[str]:
    path = root / FILE
    if not path.exists():
        return [f"{FILE}: missing; write it from wow-forever-addon/store-page.md"]
    text = path.read_text(encoding="utf-8")
    toc = _toc(root)
    website = re.fullmatch(r"https://github\.com/cjber/([\w.-]+)", toc.get("X-Website", ""))
    if not website or "Title" not in toc:
        return ["root .toc: needs `## Title` and `## X-Website: https://github.com/cjber/<repo>`"]
    repo, title = website.group(1), COLOUR.sub("", toc["Title"]).split(" - ")[0].strip()
    problems: list[str] = []
    blocks = _blocks(text)

    def where(predicate, what: str) -> int | None:
        found = [i for i, block in enumerate(blocks) if predicate(block)]
        if len(found) != 1:
            problems.append(f"{FILE}: {what} {'missing' if not found else 'appears more than once'}")
            return None
        return found[0]

    if not blocks or not blocks[0].startswith(title):
        problems.append(f"{FILE}: the pitch must open with the TOC title {title!r}")

    headings = [block[3:].strip() for block in blocks if block.startswith("## ")]
    if any(block.startswith("#") and not block.startswith("## ") for block in blocks):
        problems.append(f"{FILE}: use only `##` headings")
    if not (headings[:1] == ["Features"] and headings[-1:] == ["Usage"] and len(headings) in (2, 3)):
        problems.append(f"{FILE}: headings are {headings}; want Features, at most one more, then Usage")

    sponsor = where(lambda b: b == SPONSOR, "the sponsor sentence")
    features = where(lambda b: b == "## Features", "`## Features`")
    usage = where(lambda b: b == "## Usage", "`## Usage`")
    previews_line = re.compile(r"These images are generated previews of the .+ UI\.")
    previews = where(previews_line.fullmatch, "the previews line")
    family = where(lambda b: b == FAMILY_TOKEN, "the forever-family block")

    image = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    shots = [(i, match) for i, b in enumerate(blocks) if (match := image.fullmatch(b))]
    if not MIN_IMAGES <= len(shots) <= MAX_IMAGES:
        problems.append(f"{FILE}: {len(shots)} screenshots; want {MIN_IMAGES} to {MAX_IMAGES}")
    for i, match in shots:
        alt, url = match.groups()
        prefix = _raw(repo, "docs/screenshots/")
        if not url.startswith(prefix):
            problems.append(f"{FILE}: {url} is not under {prefix}")
        elif not (root / "docs/screenshots" / url[len(prefix) :]).is_file():
            problems.append(f"{FILE}: {url[len(prefix) :]} is not in docs/screenshots/")
        if not alt.strip():
            problems.append(f"{FILE}: {url} has no alt text, which titles it in the gallery")
        after = blocks[i + 1] if i + 1 < len(blocks) else ""
        if not after or after.startswith(("#", "!", "[!", "<!--", "These images")):
            problems.append(f"{FILE}: {url} has no caption below it (WFA-25)")
    if shots and features is not None and shots[-1][0] > features:
        problems.append(f"{FILE}: every screenshot goes above `## Features`")

    if features is not None:
        end = next((i for i in range(features + 1, len(blocks)) if blocks[i].startswith("## ")), len(blocks))
        bullets = [line for b in blocks[features + 1 : end] for line in b.splitlines() if line.startswith("- ")]
        if not MIN_FEATURES <= len(bullets) <= MAX_FEATURES:
            problems.append(f"{FILE}: {len(bullets)} feature bullets; want {MIN_FEATURES} to {MAX_FEATURES}")
        problems += [
            f"{FILE}: feature bullet must lead with a bold name ending in a full stop: {line[:60]}"
            for line in bullets
            if not re.match(r"- \*\*[^*]+\.\*\* \S", line)
        ]

    if usage is not None:
        section = blocks[usage + 1 : family if family is not None and family > usage else len(blocks)]
        lines = [line.removeprefix("- ") for b in section for line in b.splitlines()]
        if not any(re.match(r"For a bug report, paste `/\S+ report`\.", line) for line in lines):
            problems.append(f"{FILE}: `## Usage` needs the line: For a bug report, paste `/<command> report`.")
        form = f"https://github.com/cjber/{repo}/issues/new?template=translation.yml"
        translated = any(p.stem != "enUS" for p in (root / "Locales").glob("*.lua"))
        if translated and not any(line.startswith("Translated into") and form in line for line in lines):
            problems.append(
                f"{FILE}: the addon ships translations, so `## Usage` needs the translation line linking {form}"
            )

    tail = [source_line(repo), AI_LINE, buttons(repo)]
    if blocks[-3:] != tail:
        problems.append(f"{FILE}: the page must end with these three lines, exactly:\n" + "\n".join(tail))
    for image_name in ("discord-button.png", "github-sponsors-button.png", "kofi-button.png"):
        if not (root / "docs" / image_name).is_file():
            problems.append(f"docs/{image_name}: missing; run forever-core's tools/sync_consumers.py")

    order = [sponsor, shots[0][0] if shots else None, previews, features, usage, family]
    known = [i for i in order if i is not None]
    if known != sorted(known):
        want = "pitch, sponsor, screenshots, previews, Features, Usage, family"
        problems.append(f"{FILE}: parts out of order; want {want}")

    count = words(text)
    if count >= MAX_WORDS:
        problems.append(f"{FILE}: {count} prose words; keep it under {MAX_WORDS} (WFA-11)")
    return problems


def main(root: Path, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--words", action="store_true", help="print the page's prose word count")
    args = parser.parse_args(argv)
    if args.words and (root / FILE).exists():
        print(f"{FILE}: {words((root / FILE).read_text(encoding='utf-8'))} prose words, limit {MAX_WORDS}")
    problems = check(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"store page: {FILE} follows the template")
    return 0
