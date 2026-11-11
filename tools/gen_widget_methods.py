"""Generate forever_tools' widget-method data from the pinned client API annotations.

The lint in `forever_tools/widget_handlers.py` refuses a widget method that takes parameters passed straight as a
script handler, so it needs the set of such methods the client declares on its widgets. That set comes from the
Ketho/vscode-wow-api checkout `tools/typecheck.sh` pins (`revision=`, `.types/vscode-wow-api`,
`Annotations/Core/Widget/**`), never a hand list. A method that declares no parameters ignores the handler's
arguments, so it is not part of the set.

    python3 tools/gen_widget_methods.py                    # the checkout tools/typecheck.sh fetches
    python3 tools/gen_widget_methods.py --annotations DIR  # another checkout at the same revision

It writes `forever_tools/widget_methods.txt`, whose header records the revision. Re-run it when the pin moves, and
commit the data with the pin.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents/skills/wow-forever-addon/tooling"))
from forever_tools import fsio, widget_handlers  # noqa: E402

ANNOTATIONS = ROOT / ".types/vscode-wow-api"
DATA = ROOT / ".agents/skills/wow-forever-addon/tooling/forever_tools" / widget_handlers.METHODS
TYPECHECK = ROOT / "tools/typecheck.sh"


def pinned_revision() -> str:
    """The annotation revision tools/typecheck.sh pins, the commit the data must come from."""
    match = re.search(r"^revision=([0-9a-f]{40})$", TYPECHECK.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise SystemExit(f"{TYPECHECK} names no pinned annotation revision")
    return match.group(1)


def git(directory: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(directory), *args], text=True).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--annotations", type=Path, default=ANNOTATIONS, help="a vscode-wow-api checkout")
    args = parser.parse_args(argv)

    if not (args.annotations / ".git").exists():
        raise SystemExit(f"{args.annotations} is not a checkout; run tools/typecheck.sh once to fetch it")
    revision = pinned_revision()
    if git(args.annotations, "rev-parse", "HEAD") != revision:
        raise SystemExit(f"{args.annotations} is not at the pinned revision {revision}")
    if git(args.annotations, "status", "--porcelain"):
        raise SystemExit(f"{args.annotations} has uncommitted changes")

    methods = widget_handlers.annotation_methods(args.annotations / widget_handlers.ANNOTATIONS)
    if not methods:
        raise SystemExit(f"{args.annotations / widget_handlers.ANNOTATIONS} declares no widget methods with parameters")
    fsio.publish({DATA: widget_handlers.render(methods, revision)})
    print(f"{DATA.relative_to(ROOT)}: {len(methods)} widget methods that take parameters from {revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
