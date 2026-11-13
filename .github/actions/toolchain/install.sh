#!/usr/bin/env bash
# Install one release tool from tools/toolchain.json into <prefix>, verifying its sha256.
#
#   install.sh <tool> <prefix>
#
# Only a release asset is handled: the entry's url template, its version and its sha256. Lua and LuaJIT are built from
# source by build.sh instead, because their pin is a commit rather than a release.
#
# TOOLCHAIN_MANIFEST must name the manifest to read: the calling repository's tools/toolchain.json, which the action
# resolves from its `manifest` input.
set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "usage: $0 <tool> <prefix>" >&2
    exit 2
fi

if [ -z "${TOOLCHAIN_MANIFEST:-}" ]; then
    echo "install.sh: TOOLCHAIN_MANIFEST must name the repository's tools/toolchain.json" >&2
    exit 2
fi

tool=$1
prefix=$2
manifest=$TOOLCHAIN_MANIFEST
work=${TOOLCHAIN_WORK:-"${RUNNER_TEMP:-${TMPDIR:-/tmp}}/toolchain-downloads"}

read -r version url sha256 < <(python3 - "$manifest" "$tool" <<'PY'
import json
import sys

entry = json.load(open(sys.argv[1], encoding="utf-8"))["tools"][sys.argv[2]]
print(entry["version"], entry["url"].format(version=entry["version"]), entry["sha256"])
PY
)

mkdir -p "$work" "$prefix/bin"
archive="$work/$(basename "$url")"
if [ ! -f "$archive" ]; then
    curl --retry 8 --retry-delay 5 --retry-all-errors --connect-timeout 20 --max-time 300 -sSfL \
        -o "$archive.part" "$url"
    mv "$archive.part" "$archive"
fi
echo "$sha256  $archive" | sha256sum -c -

unpacked=$(mktemp -d)
trap 'command rm -rf "$unpacked"' EXIT
case "$url" in
*.zip)
    unzip -q -o "$archive" -d "$unpacked"
    ;;
*.tar.gz | *.tgz)
    tar -xzf "$archive" -C "$unpacked"
    ;;
*)
    echo "install.sh: $tool: $url is neither a zip nor a tar.gz" >&2
    exit 1
    ;;
esac

# A release that ships a bin/ tree keeps it whole (LuaLS); one that ships a single binary puts it on the prefix's PATH.
if [ -d "$unpacked/bin" ]; then
    cp -R "$unpacked"/. "$prefix"/
else
    cp -R "$unpacked"/. "$prefix/bin"/
fi
find "$prefix/bin" -type f -exec chmod 0755 {} +

echo "$tool $version installed in $prefix"
