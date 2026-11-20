#!/usr/bin/env bash
# Turn this disposable checkout into the wrapped standalone, right before a release or CI exercise packages or loads it:
#
#     tools/wrap_standalone.sh [version]
#
# An unwrapped standalone publishes ForeverCore at file load, so the loader can only adopt it as legacy, and a consumer
# embedding a newer core would run on the older runtime (#946). The wrapped build joins the loader's election, so the
# newest copy wins whichever is installed. [version] (a tag, v optional) sets the copy's build number; without it, CI
# numbers the candidate as the next patch after the newest release tag, the version it would ship as, since a copy at
# an already released build with other bytes would tie with that release in the election. The TOC keeps its own
# ## Version. tools/check_release_archive.py refuses a release zip that is not wrapped.
set -euo pipefail
if [ $# -gt 0 ]; then
  version=${1#v}
else
  latest=$(git describe --tags --abbrev=0 --match 'v[0-9]*')
  latest=${latest#v}
  version="${latest%.*}.$((${latest##*.} + 1))"
fi
staged="$(mktemp -d)/ForeverCore"
python3 tools/build_embedded_core.py --standalone --output "$staged" --folder ForeverCore \
  --version "$version" --saved-variable ForeverCoreDB
# bundle.json records the build's digests for the generated-bundle checks; the store package leaves it out.
rm -- "$staged/bundle.json"
cp -a "$staged/." .
# The packager skips untracked files, so stage the generated load entries in this disposable checkout's index.
git add -f -- Begin.lua End.lua ForeverCoreReady.lua
