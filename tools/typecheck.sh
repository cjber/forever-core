#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
annotations=.types/vscode-wow-api
revision=d0b5b51fac4c52c493371b9b18e66ce604ea4326
if [[ ! -d "$annotations/.git" ]]; then
    mkdir -p "$annotations"
    git -C "$annotations" init --quiet
    git -C "$annotations" remote add origin https://github.com/Ketho/vscode-wow-api.git
    git -C "$annotations" fetch --depth=1 origin "$revision"
    git -C "$annotations" checkout --quiet --detach FETCH_HEAD
fi
python3 - <<'PYTHON'
import sys
from pathlib import Path

sys.path.insert(0, ".agents/skills/wow-forever-addon/tooling")
from forever_sim.fetch import UI_REVISION, fetch_ui, git

cache = Path(".types/blizzard-ui")
target = cache / "wow-ui-source"
if (target / ".git").exists() and git(target, "status", "--porcelain"):
    raise SystemExit(f"Refusing to overwrite dirty Blizzard UI checkout: {target}")
source = fetch_ui(cache, offline=False)
if git(source, "rev-parse", "HEAD") != UI_REVISION or git(source, "status", "--porcelain"):
    raise SystemExit(f"Expected clean Blizzard UI checkout at {UI_REVISION}: {source}")
PYTHON
if [[ "$(git -C "$annotations" rev-parse HEAD)" != "$revision" ]] ||
    [[ -n "$(git -C "$annotations" status --porcelain)" ]]; then
    echo "Expected a clean WoW API checkout at $revision in $annotations" >&2
    exit 1
fi
if [[ "$(lua-language-server --version)" != 3.19.1 ]]; then
    echo "Install lua-language-server 3.19.1 to match CI." >&2
    exit 1
fi

# A fresh output path prevents a crashed server from reusing an earlier clean report.
report_dir=$(mktemp -d)
trap 'rm -rf "$report_dir"' EXIT
status=0
lua-language-server --check . --checklevel=Information --check_format=json \
    --check_out_path="$report_dir/check.json" --logpath="$report_dir" > "$report_dir/output.txt" 2>&1 || status=$?
python3 - "$report_dir" "$status" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

report_dir = Path(sys.argv[1])
report = report_dir / "check.json"
if not report.is_file():
    sys.exit("LuaLS did not produce a report:\n" + (report_dir / "output.txt").read_text())
results = json.loads(report.read_text()) or {}
count = 0
for uri, diagnostics in sorted(results.items()):
    path = Path(unquote(urlparse(uri).path)).relative_to(Path.cwd())
    for diagnostic in sorted(diagnostics, key=lambda d: d["range"]["start"]["line"]):
        line = diagnostic["range"]["start"]["line"] + 1
        message = diagnostic["message"].replace("\n", " ")
        print(f"{path}:{line}: {diagnostic['code']}: {message}")
        count += 1
if count or int(sys.argv[2]):
    if not count:
        print((report_dir / "output.txt").read_text())
    sys.exit(f"LuaLS: {count} diagnostics (exit {sys.argv[2]})")
print("LuaLS: no diagnostics")
PY
