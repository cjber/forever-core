"""Check glyphs for reviewed widget bindings, or an explicit font selection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/wow-forever-addon/tooling"))
from forever_tools.font_glyphs import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(Path(__file__).resolve().parents[1]))
