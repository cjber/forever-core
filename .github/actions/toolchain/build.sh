#!/usr/bin/env bash
# Build the pinned LuaJIT and luacheck into <prefix>, with no apt and no luarocks.
#
#   build.sh <prefix> [work-dir]
#
# Every source is a GitHub archive at the commit tools/toolchain.json pins, so the build needs no Ubuntu mirror and no
# luarocks.org. TOOLCHAIN_MANIFEST must name the manifest to read: the calling repository's tools/toolchain.json,
# which the action resolves from its `manifest` input.
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "usage: $0 <prefix> [work-dir]" >&2
    exit 2
fi

if [ -z "${TOOLCHAIN_MANIFEST:-}" ]; then
    echo "build.sh: TOOLCHAIN_MANIFEST must name the repository's tools/toolchain.json" >&2
    exit 2
fi

prefix=$1
work=${2:-"${RUNNER_TEMP:-${TMPDIR:-/tmp}}/lua-toolchain-build"}
manifest=$TOOLCHAIN_MANIFEST

# One pin table, read from the manifest: the LuaJIT commit, and the release, commit and repository of each Lua module.
declare -A pin
while IFS=$'\t' read -r key value; do
    pin[$key]=$value
done < <(python3 - "$manifest" <<'PY'
import json
import sys

tools = json.load(open(sys.argv[1], encoding="utf-8"))["tools"]
lua51 = tools["lua51"]
print(f"lua51_version\t{lua51['version']}")
print(f"lua51_url\t{lua51['url'].format(version=lua51['version'])}")
print(f"lua51_sha256\t{lua51['sha256']}")
for name in ("luajit", "luacheck", "argparse", "luafilesystem"):
    entry = tools[name]
    print(f"{name}_repo\t{entry['upstream']['repo']}")
    print(f"{name}_commit\t{entry['commit']}")
lua_branch = tools["luajit"]["upstream"]["branch"]
print(f"luajit_line\t{lua_branch.removeprefix('v')}")
PY
)

download() {
    local repo=$1 commit=$2 name=$3
    if [ ! -f "$work/$name.tar.gz" ]; then
        curl --retry 8 --retry-delay 5 --retry-all-errors --connect-timeout 20 --max-time 300 -sSfL \
            -o "$work/$name.tar.gz.part" "https://github.com/$repo/archive/$commit.tar.gz"
        mv "$work/$name.tar.gz.part" "$work/$name.tar.gz"
    fi
    tar -xzf "$work/$name.tar.gz" -C "$work"
}

mkdir -p "$work" "$prefix/bin" "$prefix/share/lua/5.1" "$prefix/lib/lua/5.1"

# PUC Lua 5.1.5 is the parser used by the game client. Keep it beside LuaJIT:
# LuaJIT is the execution harness, while this binary is the strict syntax gate.
lua51_archive="$work/lua-${pin[lua51_version]}.tar.gz"
if [ ! -f "$lua51_archive" ]; then
    curl --retry 8 --retry-delay 5 --retry-all-errors --connect-timeout 20 --max-time 300 -sSfL \
        -o "$lua51_archive.part" "${pin[lua51_url]}"
    mv "$lua51_archive.part" "$lua51_archive"
fi
echo "${pin[lua51_sha256]}  $lua51_archive" | sha256sum -c -
lua51_src="$work/lua-${pin[lua51_version]}"
if [ ! -x "$prefix/bin/luac5.1" ]; then
    tar -xzf "$lua51_archive" -C "$work"
    make -C "$lua51_src/src" clean >/dev/null
    make -C "$lua51_src/src" -j"$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN || echo 2)" \
        MYCFLAGS=-DLUA_USE_LINUX MYLIBS=-ldl luac
    install -m 0755 "$lua51_src/src/luac" "$prefix/bin/luac5.1"
fi

download "${pin[luajit_repo]}" "${pin[luajit_commit]}" luajit
luajit_src="$work/LuaJIT-${pin[luajit_commit]}"
make -C "$luajit_src" -j"$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN || echo 2)"
make -C "$luajit_src" install PREFIX="$prefix"

download "${pin[luacheck_repo]}" "${pin[luacheck_commit]}" luacheck
download "${pin[argparse_repo]}" "${pin[argparse_commit]}" argparse
download "${pin[luafilesystem_repo]}" "${pin[luafilesystem_commit]}" luafilesystem

luacheck_src="$work/luacheck-${pin[luacheck_commit]}"
argparse_src="$work/argparse-${pin[argparse_commit]}"
luafilesystem_src="$work/luafilesystem-${pin[luafilesystem_commit]}"

# luacheck and argparse are pure Lua; luafilesystem is one C file built against the LuaJIT headers just installed.
cp -R "$luacheck_src/src/luacheck" "$prefix/share/lua/5.1/"
install -m 0644 "$argparse_src/src/argparse.lua" "$prefix/share/lua/5.1/argparse.lua"
install -m 0644 "$luacheck_src/bin/luacheck.lua" "$prefix/share/lua/5.1/luacheck-bin.lua"
cc -O2 -fPIC -shared -I"$prefix/include/luajit-2.1" \
    -o "$prefix/lib/lua/5.1/lfs.so" "$luafilesystem_src/src/lfs.c"

# The wrapper points LuaJIT at this prefix, since the binary's compiled-in search paths are the build defaults.
cat > "$prefix/bin/luacheck" <<'EOF'
#!/bin/sh
set -eu
prefix=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
LUA_PATH="$prefix/share/lua/5.1/?.lua;$prefix/share/lua/5.1/?/init.lua;;"
LUA_CPATH="$prefix/lib/lua/5.1/?.so;;"
export LUA_PATH LUA_CPATH
exec "$prefix/bin/luajit" "$prefix/share/lua/5.1/luacheck-bin.lua" "$@"
EOF
chmod 0755 "$prefix/bin/luacheck"

echo "Lua toolchain installed in $prefix"
"$prefix/bin/luajit" -v
"$prefix/bin/luacheck" --version
