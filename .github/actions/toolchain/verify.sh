#!/usr/bin/env bash
# Check an installed tool against the version toolchain.json pins, so a stale cache cannot pass silently.
#
#   verify.sh <tool> <prefix>
#
# TOOLCHAIN_MANIFEST must name the manifest to check against: the calling repository's toolchain.json, which the action
# resolves from its `manifest` input.
set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "usage: $0 <tool> <prefix>" >&2
    exit 2
fi

if [ -z "${TOOLCHAIN_MANIFEST:-}" ]; then
    echo "verify.sh: TOOLCHAIN_MANIFEST must name the repository's toolchain.json" >&2
    exit 2
fi

tool=$1
prefix=$2
manifest=$TOOLCHAIN_MANIFEST

case "$tool" in
lua)
    read -r lua51 luacheck line < <(python3 - "$manifest" <<'PY'
import json
import sys

tools = json.load(open(sys.argv[1], encoding="utf-8"))["tools"]
branch = tools["luajit"]["upstream"]["branch"]
print(tools["lua51"]["version"], tools["luacheck"]["version"], branch.removeprefix("v"))
PY
    )
    "$prefix/bin/luajit" -v 2>&1 | grep -q "LuaJIT $line"
    "$prefix/bin/luacheck" --version | grep -q "^Luacheck: $luacheck$"
    "$prefix/bin/luac5.1" -v 2>&1 | grep -q "Lua $lua51"
    ;;
luals)
    version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["tools"]["luals"]["version"])' "$manifest")
    [ "$("$prefix/bin/lua-language-server" --version)" = "$version" ]
    ;;
stylua)
    version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["tools"]["stylua"]["version"])' "$manifest")
    [ "$("$prefix/bin/stylua" --version)" = "stylua $version" ]
    ;;
gitleaks)
    version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["tools"]["gitleaks"]["version"])' "$manifest")
    [ "$("$prefix/bin/gitleaks" version)" = "$version" ]
    ;;
*)
    echo "verify.sh: unknown tool $tool" >&2
    exit 2
    ;;
esac

echo "toolchain: $tool matches toolchain.json"
