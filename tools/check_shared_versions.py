"""Pin every shared file whose version number gates takeover to its version and its exact bytes.

A shared file is copied byte for byte into the consumer addons. A newer copy only takes over when its version number is
higher, so a change that forgets to raise it reaches no player: the copy that happened to load first stays in charge.
This check makes that impossible to forget. Each file's version line is read with an exact pattern and the file is
hashed, then both are compared with tools/shared_versions.json.

    python3 tools/check_shared_versions.py            check every pinned file
    python3 tools/check_shared_versions.py --record   rewrite the JSON from the current files

It fails when a file's sha256 changed but its version did not, when the version went down, and when a raise has not been
recorded yet. `--record` is the only way to accept a raised version, so the committed JSON always describes the current
bytes.

Core/Log.lua's LOG_VERSION and Core/LeaderboardsData.lua's VERSION are deliberately not pinned: neither selects which
copy is in charge. The shared log keeps one state table and a later copy updates its version in place, while the data
half has no takeover at all and the namespace simply keeps the copy its own addon loaded.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORD_FILE = Path("tools/shared_versions.json")

# Exact version-line patterns, one per shared file whose number gates a takeover. `local VERSION = N` alone would match
# more than one file, so each pattern names its field.
VERSION_LINES = {
    "Core/PeerStats.lua": (
        "MANAGER_VERSION",
        re.compile(r"^local MANAGER_VERSION = (\d+)$", re.MULTILINE),
    ),
    "UI/ForeverFamily.lua": (
        "VERSION",
        re.compile(r"^local VERSION = (\d+)$", re.MULTILINE),
    ),
    "UI/Leaderboards.lua": (
        "LEADERBOARDS_VERSION",
        re.compile(r"^local LEADERBOARDS_VERSION = (\d+)$", re.MULTILINE),
    ),
}


def measure(root, path):
    """The current (version, sha256) of a pinned file, refusing anything but one exact version line."""
    field, pattern = VERSION_LINES[path]
    source = (root / path).read_text(encoding="utf-8")
    found = pattern.findall(source)
    if len(found) != 1:
        raise ValueError(f"expected exactly one `local {field} = N` line, found {len(found)}")
    digest = hashlib.sha256((root / path).read_bytes()).hexdigest()
    return int(found[0]), digest


def record(root, record_path=None):
    """Write the current version and sha256 of every pinned file to the JSON record."""
    record_path = Path(record_path) if record_path is not None else root / RECORD_FILE
    data = {}
    for path in VERSION_LINES:
        version, digest = measure(root, path)
        data[path] = {"version": version, "sha256": digest}
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def check(root, record_path=None):
    """Every finding, each naming the file and why its pin failed."""
    record_path = Path(record_path) if record_path is not None else root / RECORD_FILE
    try:
        recorded = json.loads(record_path.read_text(encoding="utf-8"))
    except OSError as error:
        return [f"{record_path}: shared-version: cannot read the record ({error}); run --record"]
    except json.JSONDecodeError as error:
        return [f"{record_path}: shared-version: invalid JSON ({error}); run --record"]
    if not isinstance(recorded, dict):
        return [f"{record_path}: shared-version: the record must be a JSON object; run --record"]

    findings = []
    for path, (field, _) in VERSION_LINES.items():
        entry = recorded.get(path)
        if entry is None:
            findings.append(f"{path}: shared-version: not recorded; run tools/check_shared_versions.py --record")
            continue
        if not isinstance(entry, dict):
            findings.append(f"{path}: shared-version: the record entry must be an object; run --record")
            continue
        recorded_version = entry.get("version")
        recorded_digest = entry.get("sha256")
        if (
            not isinstance(recorded_version, int)
            or isinstance(recorded_version, bool)
            or not isinstance(recorded_digest, str)
        ):
            findings.append(
                f"{path}: shared-version: the record needs an integer version and a sha256; "
                "run tools/check_shared_versions.py --record"
            )
            continue
        try:
            version, digest = measure(root, path)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            findings.append(f"{path}: shared-version: {error}")
            continue
        if version < recorded_version:
            findings.append(
                f"{path}: shared-version: {field} went down from {recorded_version} to {version}; "
                "a takeover version never goes backwards"
            )
        elif version > recorded_version:
            findings.append(
                f"{path}: shared-version: {field} is {version} but the record has {recorded_version}; "
                "run tools/check_shared_versions.py --record"
            )
        elif digest != recorded_digest:
            findings.append(
                f"{path}: shared-version: sha256 changed but {field} stayed {version}; raise it and "
                "run tools/check_shared_versions.py --record"
            )

    for path in sorted(set(recorded) - set(VERSION_LINES)):
        findings.append(
            f"{path}: shared-version: recorded but no exact version line is pinned; "
            "remove it or add its pattern to tools/check_shared_versions.py"
        )
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--record", action="store_true", help="rewrite tools/shared_versions.json from the files")
    args = parser.parse_args(argv)
    if args.record:
        try:
            data = record(ROOT)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            print(f"shared-version: {error}", file=sys.stderr)
            return 1
        print(f"Shared version check: recorded {len(data)} files")
        return 0
    findings = check(ROOT)
    for finding in findings:
        print(finding)
    if findings:
        return 1
    print(f"Shared version check: {len(VERSION_LINES)} files pinned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
