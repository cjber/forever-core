"""Check .release/ForeverCore against the TOC: every loaded file ships, no development folder does."""

import sys
from pathlib import Path

PACKAGE = Path(".release") / "ForeverCore"
DEV = ("tests", "tools", "docs", "types")


def toc_files():
    files = []
    for line in Path("ForeverCore.toc").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        files.append(line.replace("\\", "/"))
    return files


def main():
    if not PACKAGE.is_dir():
        raise SystemExit(f"{PACKAGE} is missing: the packager did not build a package")
    missing = [path for path in toc_files() if not (PACKAGE / path).is_file()]
    shipped = [str(path.relative_to(PACKAGE)) for path in PACKAGE.rglob("*") if path.is_file()]
    leaked = [path for path in shipped if path.split("/")[0] in DEV]
    for name in ("ForeverCore.toc", "LICENSE"):
        if not (PACKAGE / name).is_file():
            missing.append(name)
    problems = []
    if missing:
        problems.append("loaded but not packaged: " + ", ".join(missing))
    if leaked:
        problems.append("development files packaged: " + ", ".join(leaked))
    if problems:
        print("\n".join(problems))
        return 1
    print(f"package check: {len(shipped)} files, every TOC file present, no development folders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
