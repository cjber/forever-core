#!/usr/bin/env bash
# Profile one headless session. Link !!DevPerf and !!DevSmoke in the client's Interface/AddOns first.
# The /forever command belongs to a consumer addon; forever_client.py checks its SLASH_ registration before sending.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

python3 "$here/forever_client.py" slash "/forever selftest"
command sleep 30
python3 "$here/forever_client.py" slash "/forever perf after-selftest"
python3 "$here/forever_client.py" slash "/forever perf scenario tooltips"
command sleep 15
python3 "$here/forever_client.py" slash "/forever perf scenario mappins"
command sleep 15
command sleep 60
python3 "$here/forever_client.py" slash "/forever perf idle"
python3 "$here/forever_client.py" reload
python3 "$here/../forever_perf.py"
