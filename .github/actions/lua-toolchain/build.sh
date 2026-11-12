#!/usr/bin/env bash
# Build the pinned LuaJIT and luacheck into <prefix>, with no apt and no luarocks.
#
#   build.sh <prefix> [work-dir]
#
# Every source is a GitHub archive at a pinned commit, so the build needs no Ubuntu mirror and no luarocks.org.
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "usage: $0 <prefix> [work-dir]" >&2
    exit 2
fi

prefix=$1
work=${2:-"${RUNNER_TEMP:-${TMPDIR:-/tmp}}/lua-toolchain-build"}

# The v2.1 commit behind Ubuntu's 2.1.0+git20231223.c525bcb package.
luajit_commit=c525bcb9024510cad9e170e12b6209aedb330f83
# lunarmodules/luacheck v1.1.2, luarocks/argparse 0.7.2 (the mpeterv/argparse repository's new home) and
# lunarmodules/luafilesystem v1.9.0.
luacheck_commit=418f48976c73be697fe64b0eba9ea9821ac9bca8
argparse_commit=a5ab54f8161f9f508b058411f64c2c72d974733b
luafilesystem_commit=a186cca5833691e830ed255e38ace8ff6b870dbf

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
lua51_sha256=2640fc56a795f29d28ef15e13c34a47e223960b0240e8cb0a82d9b0738695333
if [ ! -f "$work/lua-5.1.5.tar.gz" ]; then
    curl --retry 8 --retry-delay 5 --retry-all-errors --connect-timeout 20 --max-time 300 -sSfL \
        -o "$work/lua-5.1.5.tar.gz.part" https://www.lua.org/ftp/lua-5.1.5.tar.gz
    mv "$work/lua-5.1.5.tar.gz.part" "$work/lua-5.1.5.tar.gz"
fi
echo "$lua51_sha256  $work/lua-5.1.5.tar.gz" | sha256sum -c -
if [ ! -x "$prefix/bin/luac5.1" ]; then
    tar -xzf "$work/lua-5.1.5.tar.gz" -C "$work"
    make -C "$work/lua-5.1.5/src" -j"$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN || echo 2)" linux
    install -m 0755 "$work/lua-5.1.5/src/luac" "$prefix/bin/luac5.1"
fi

download LuaJIT/LuaJIT "$luajit_commit" luajit
luajit_src="$work/LuaJIT-$luajit_commit"
make -C "$luajit_src" -j"$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN || echo 2)"
make -C "$luajit_src" install PREFIX="$prefix"

download lunarmodules/luacheck "$luacheck_commit" luacheck
download luarocks/argparse "$argparse_commit" argparse
download lunarmodules/luafilesystem "$luafilesystem_commit" luafilesystem

luacheck_src="$work/luacheck-$luacheck_commit"
argparse_src="$work/argparse-$argparse_commit"
luafilesystem_src="$work/luafilesystem-$luafilesystem_commit"

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
