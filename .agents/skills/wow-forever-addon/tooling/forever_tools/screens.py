"""Catch a screenshot left stale by a change to what it shows (WFA-9).

The PNGs under `docs/screenshots/` are rendered locally (`tools/screenshots.py` needs Pillow, wowmock and
wago.tools), so CI cannot redraw them. It can redraw what they are drawn from: each scene's dump, the headless
layout or data `tools/screenshots.py` reads before drawing anything. `record` writes `docs/screenshots/scenes.sha256`
beside the PNGs, one line per image with its sha256 and its dump's; `check` recomputes the dumps and fails when one
moved but its image did not, when an image changed with no new record, or when an image and a record disagree.

Each addon names its scenes in a thin `tools/check_screenshots.py`: a mapping from image name to a function
returning that image's dump as bytes (a slice of a headless run's JSON, or `files` over the source an image reads).

    python3 tools/check_screenshots.py           # CI: fail on a stale image
    python3 tools/check_screenshots.py --record  # after tools/screenshots.py: write scenes.sha256
"""

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

__all__ = ["RECORD", "check", "dump_json", "files", "main", "read", "record"]

RECORD = "scenes.sha256"
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


def read(folder: Path) -> dict[str, tuple[str, str]]:
    """The record as {image: (image sha256, dump sha256)}; empty when there is none yet."""
    path = folder / RECORD
    if not path.is_file():
        return {}
    entries = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            name, image, dump = line.split()
            entries[name] = (image, dump)
    return entries


def record(folder: Path, scenes: Scenes, force: bool = False) -> list[str]:
    """Write the record for every scene from the images on disk and freshly computed dumps; returns the lines.

    An image whose dump moved while the image stayed byte for byte the same is the stale case `check` exists for, so
    it is refused unless `force` says a fresh render really drew the same pixels."""
    missing = sorted(name for name in scenes if not (folder / name).is_file())
    if missing:
        raise SystemExit(f"no image for {', '.join(missing)}; run tools/screenshots.py first")
    recorded = read(folder)
    lines, stale = [], []
    for name in sorted(scenes):
        image, dump = sha256((folder / name).read_bytes()), sha256(scenes[name]())
        if name in recorded and recorded[name][0] == image and recorded[name][1] != dump:
            stale.append(name)
        lines.append(f"{name} {image} {dump}")
    if stale and not force:
        raise SystemExit(
            f"{', '.join(stale)}: what it shows changed but the image did not; run tools/screenshots.py, "
            "or pass --force if it rendered the same pixels"
        )
    header = "# image sha256 dump-sha256; written by tools/check_screenshots.py --record, checked in CI\n"
    (folder / RECORD).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return lines


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
            problems.append(f"{name}: not in {RECORD}; run tools/check_screenshots.py --record")
            continue
        image_was, dump_was = recorded[name]
        image_now, dump_now = sha256(path.read_bytes()), sha256(scenes[name]())
        if dump_now != dump_was and image_now == image_was:
            problems.append(f"{name}: what it shows changed but the image did not; run tools/screenshots.py")
        elif dump_now != dump_was or image_now != image_was:
            problems.append(f"{name}: differs from {RECORD}; run tools/check_screenshots.py --record")
    for name in sorted(recorded.keys() - scenes.keys()):
        problems.append(f"{name}: recorded in {RECORD} but no longer a scene; run tools/check_screenshots.py --record")
    return problems


def main(folder: Path, scenes: Scenes, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--record", action="store_true", help=f"write {RECORD} from the images and dumps now")
    parser.add_argument("--force", action="store_true", help="with --record: accept an image a fresh render left as is")
    args = parser.parse_args(argv)
    if args.record:
        lines = record(folder, scenes, args.force)
        print(f"Screenshots: recorded {len(lines)} images in {RECORD}")
        return 0
    problems = check(folder, scenes)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"Screenshots: {len(scenes)} images match what they are drawn from")
    return 0
