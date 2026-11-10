"""Check the shared runtime and renderer against the suite's asset blacklist and identity icon rule."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents/skills/wow-forever-addon/tooling"))
from forever_tools import assets, identity  # noqa: E402


def main() -> int:
    runtime = [ROOT / "Core.lua", ROOT / "Expose.lua"]
    for folder in ("Core", "UI"):
        runtime.extend((ROOT / folder).rglob("*.lua"))
        runtime.extend((ROOT / folder).rglob("*.xml"))
    return int(identity.run(ROOT)) | assets.run([*runtime, *assets.renderer_files(ROOT)])


if __name__ == "__main__":
    raise SystemExit(main())
