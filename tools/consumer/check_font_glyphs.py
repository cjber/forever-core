"""Check glyphs for reviewed widget bindings, or an explicit font selection."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# forever_tools is tools/forever_tools in a consumer and the skill pack's tooling in forever-core.
TOOLS = Path(__file__).resolve().parent
for _base in (TOOLS, TOOLS.parent / ".agents/skills/wow-forever-addon/tooling"):
    if (_base / "forever_tools" / "font_glyphs.py").is_file():
        if str(_base) not in sys.path:
            sys.path.insert(0, str(_base))
        break

from forever_tools.font_glyphs import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(ROOT))
