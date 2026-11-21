"""Catch a screenshot left stale by a change to what it shows (WFA-9).

The PNGs under `docs/screenshots/` are rendered locally (`tools/screenshots.py` needs Pillow, wowmock and
wago.tools), so CI checks them against their scene dumps. A dump should cover only what its image draws:
its own render module and the data or Lua it reads. A change elsewhere then leaves the record unchanged.

Each addon names its scenes in `tools/check_screenshots.py`, mapping image names to functions returning dump bytes.
Use a slice of a simulated run's JSON or `files` over the sources an image reads. `record` writes the image and
dump hashes to `docs/screenshots/scenes/<image name>.sha256`. `check` recomputes the hashes and reports stale
screenshots and records. An existing `scenes.sha256` supplies entries missing from `scenes/` until the next
successful `--record` migrates them.

    python3 tools/check_screenshots.py           # CI: fail on a stale image
    python3 tools/check_screenshots.py --record  # after tools/screenshots.py: write per-scene records
"""

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

__all__ = ["RECORD_DIR", "check", "dump_json", "files", "main", "read", "record"]

RECORD_DIR = "scenes"
LEGACY_RECORD = "scenes.sha256"
IMAGES = ("*.png", "*.gif")

Scenes = Mapping[str, Callable[[], bytes]]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump_json(value: object) -> bytes:
    """A canonical encoding of a JSON-shaped dump, so key order and spacing never move its hash."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def files(root: Path, patterns: Iterable[str]) -> bytes:
    """A dump made of the files `patterns` match under `root`: each path with its sha256, in path order. A pattern
    that matches nothing raises, so a renamed source cannot silently drop out of a scene."""
    lines = []
    for pattern in patterns:
        matched = sorted(path for path in root.glob(pattern) if path.is_file())
        if not matched:
            raise ValueError(f"{pattern}: matches no file")
        lines += [f"{path.relative_to(root).as_posix()} {sha256(path.read_bytes())}" for path in matched]
    return "\n".join(sorted(set(lines))).encode()


def record_path(name: str) -> Path:
    return Path(RECORD_DIR) / f"{name}.sha256"


def read(folder: Path) -> dict[str, tuple[str, str]]:
    """Return {image: (image sha256, dump sha256)}, filling missing records from the legacy file."""
    entries = {}
    directory = folder / RECORD_DIR
    for path in directory.glob("*.sha256"):
        if path.is_file():
            name = path.name.removesuffix(".sha256")
            image, dump = path.read_text(encoding="utf-8").split()
            entries[name] = (image, dump)
    legacy = folder / LEGACY_RECORD
    if legacy.is_file():
        for line in legacy.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                name, image, dump = line.split()
                entries.setdefault(name, (image, dump))
    return entries


def record(folder: Path, scenes: Scenes, force: bool = False) -> list[str]:
    """Write the record for every scene from the images on disk and freshly computed dumps; returns the lines.

    An image whose dump moved while the image stayed byte for byte the same is the stale case `check` exists for, so
    it is refused unless `force` says a fresh render really drew the same pixels."""
    missing = sorted(name for name in scenes if not (folder / name).is_file())
    if missing:
        raise SystemExit(f"no image for {', '.join(missing)}; run tools/screenshots.py first")
    recorded = read(folder)
    entries, stale = {}, []
    for name in sorted(scenes):
        image, dump = sha256((folder / name).read_bytes()), sha256(scenes[name]())
        if name in recorded and recorded[name][0] == image and recorded[name][1] != dump:
            stale.append(name)
        entries[name] = (image, dump)
    if stale and not force:
        raise SystemExit(
            f"{', '.join(stale)}: what it shows changed but the image did not; run tools/screenshots.py, "
            "or pass --force if it rendered the same pixels"
        )
    for name, (image, dump) in entries.items():
        path = folder / record_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{image} {dump}\n", encoding="utf-8")
    current = {folder / record_path(name) for name in scenes}
    for path in (folder / RECORD_DIR).glob("*.sha256"):
        if path.is_file() and path not in current:
            path.unlink(missing_ok=True)
    (folder / LEGACY_RECORD).unlink(missing_ok=True)
    return [f"{name} {image} {dump}" for name, (image, dump) in entries.items()]


def check(folder: Path, scenes: Scenes) -> list[str]:
    """Every stale or unrecorded image, each as one line with what to run."""
    recorded = read(folder)
    problems = []
    images = {path.name for pattern in IMAGES for path in folder.glob(pattern)}
    for name in sorted(images - scenes.keys()):
        problems.append(f"{name}: no scene in tools/check_screenshots.py; name what it is drawn from")
    for name in sorted(scenes):
        path = folder / name
        if not path.is_file():
            problems.append(f"{name}: missing; run tools/screenshots.py")
            continue
        if name not in recorded:
            problems.append(f"{name}: not in {record_path(name).as_posix()}; run tools/check_screenshots.py --record")
            continue
        image_was, dump_was = recorded[name]
        image_now, dump_now = sha256(path.read_bytes()), sha256(scenes[name]())
        if dump_now != dump_was and image_now == image_was:
            problems.append(f"{name}: what it shows changed but the image did not; run tools/screenshots.py")
        elif dump_now != dump_was or image_now != image_was:
            problems.append(
                f"{name}: differs from {record_path(name).as_posix()}; run tools/check_screenshots.py --record"
            )
    for name in sorted(recorded.keys() - scenes.keys()):
        problems.append(
            f"{name}: recorded in {record_path(name).as_posix()} but no longer a scene; "
            "run tools/check_screenshots.py --record"
        )
    return problems


def main(folder: Path, scenes: Scenes, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--record", action="store_true", help=f"write records in {RECORD_DIR}/ from the images and dumps now"
    )
    parser.add_argument("--force", action="store_true", help="with --record: accept an image a fresh render left as is")
    args = parser.parse_args(argv)
    if args.record:
        lines = record(folder, scenes, args.force)
        print(f"Screenshots: recorded {len(lines)} images in {RECORD_DIR}/")
        return 0
    problems = check(folder, scenes)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"Screenshots: {len(scenes)} images match what they are drawn from")
    return 0
