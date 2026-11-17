#!/usr/bin/env bash
# Replay the manager lifecycle matrix (forever-core#650), one app at a time.
# Extra arguments go to every run, e.g.: ./run-all.sh --a 1795141 --channel alpha
set -euo pipefail
cd "$(dirname "$0")/../.."
free -h | head -2
for deps in no yes; do
  uv run --project tools --frozen --group dev python -m tools.manager_lifecycle.run --app wowup --remove-deps "$deps" "$@"
done
for v in "no no" "yes no" "no yes"; do
  read -r deps libs <<<"$v"
  uv run --project tools --frozen --group dev python -m tools.manager_lifecycle.run --app curseforge --remove-deps "$deps" --cf-libs-separate "$libs" "$@"
done

