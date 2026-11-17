#!/usr/bin/env bash
# Update scenarios U1..U5 on both apps, one run at a time. Extra args (e.g. --a ID --a-name N) pass through.
set -euo pipefail
cd "$(dirname "$0")/../.."
for app in wowup curseforge; do
  for v in "U1 no" "U2 no" "U3 no" "U4 no" "U5 no" "U5 yes"; do
    set -- $v "$@"
    echo "=== $app $1 remove-deps=$2"
    timeout 1500 uv run --project tools --frozen --group dev python -m tools.manager_lifecycle.run --app "$app" --scenario "$1" --remove-deps "$2" "${@:3}" 2>&1 | /usr/bin/grep -v '^  '
    shift 2
  done
done
