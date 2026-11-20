#!/usr/bin/env bash
# Turn this disposable checkout into the wrapped standalone right before the packager runs:
#
#     tools/wrap_standalone.sh <version>
#
# An unwrapped standalone publishes ForeverCore at file load, so the loader can only adopt it as legacy, and a consumer
# embedding a newer core would run on the older runtime (#946). The wrapped build joins the loader's election, so the
# newest copy wins whichever is installed. <version> (a tag, v optional) sets the copy's build number; the TOC keeps
# the ## Version the toc_version step wrote. tools/check_release_archive.py refuses a zip without the loader header.
set -euo pipefail
version=${1:?usage: tools/wrap_standalone.sh <version>}
staged="$(mktemp -d)/ForeverCore"
python3 tools/build_embedded_core.py --standalone --output "$staged" --folder ForeverCore \
  --version "${version#v}" --saved-variable ForeverCoreDB
# bundle.json records the build's digests for the generated-bundle checks; the store package leaves it out.
rm -- "$staged/bundle.json"
cp -a "$staged/." .
