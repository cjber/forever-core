"""Run every `tests/*_spec.lua` (or another `--pattern`) under LuaJIT in parallel and report each one in glob order.

Specs are independent processes, so they run on every core at once. Each spec's output is held until it finishes and
printed in glob order with its time, so the log reads as a serial run would. Every spec runs even after one fails; the
exit status is 1 when any failed, and the failures are named at the end. A spec that shares a fixture with others
must create it atomically (write a unique temporary file, then rename), since two specs may create it at once.

    python3 -m tools.forever_tools.specs            # from the repository root
    python3 -m tools.forever_tools.specs --jobs 1   # one at a time
    python3 -m tools.forever_tools.specs --pattern 'tests/sim/*_spec.lua'

A consumer's specs load ForeverCore from `$FOREVER_CORE`, else the sibling `../forever-core` checkout, and must load
the release `tools/forever-core.txt` pins, as CI does. When that checkout is not at the pin (another branch, or local
edits), the runner exports the pinned tag from it once into `$XDG_CACHE_HOME/forever-core/<tag>-<commit>` (fetching
the tag from `origin` when the checkout lacks it) and points `FOREVER_CORE` there, saying so. A checkout it cannot
place, or a tag it cannot find, stops the run before any spec. `FOREVER_CORE_UNPINNED=1` runs against the checkout
as it is, for testing a consumer against unreleased core work.
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PATTERN = "tests/*_spec.lua"
PIN_PATH = "tools/forever-core.txt"
UNPINNED = "FOREVER_CORE_UNPINNED"
# "<tag> <commit>" in an export, so a later run reuses it only for that exact release.
EXPORT_MARKER = ".forever-core-commit"


class PinError(RuntimeError):
    """The specs cannot be given the ForeverCore release the consumer pins."""


def git(source: Path, *args: str) -> str | None:
    """Git's output in `source`, stripped, or None when the command fails."""
    done = subprocess.run(
        ["git", "-C", str(source), *args], stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False
    )
    return done.stdout.strip() if done.returncode == 0 else None


def pinned_commit(source: Path, pin: str) -> str:
    """The commit `pin` names in `source`, fetching the tag from its origin when the checkout lacks it."""
    # The tag itself: a branch or another revision with the pin's name is not the release.
    tag = f"refs/tags/{pin}^{{commit}}"
    commit = git(source, "rev-parse", "--verify", "-q", tag)
    if not commit:
        git(source, "fetch", "-q", "origin", f"refs/tags/{pin}:refs/tags/{pin}")
        commit = git(source, "rev-parse", "--verify", "-q", tag)
    if not commit:
        raise PinError(f"ForeverCore {pin} ({PIN_PATH}) is not a tag in {source} or its origin")
    return commit


def extract(tar: tarfile.TarFile, staging: Path) -> None:
    """Extract a `git archive` safely on every supported Python: the "data" filter where it exists (3.12, and 3.10.12
    and 3.11.4 on), else only regular files and folders that stay inside `staging`."""
    if hasattr(tarfile, "data_filter"):
        tar.extractall(staging, filter="data")
        return
    root = staging.resolve()
    for member in tar.getmembers():
        inside = (root / member.name).resolve()
        if not (member.isfile() or member.isdir()) or (inside != root and root not in inside.parents):
            raise PinError(f"refusing to extract {member.name!r} from the ForeverCore archive")
    tar.extractall(staging)


def export(source: Path, pin: str, commit: str, target: Path) -> None:
    """Extract `commit`'s tree from `source` into `target` in one rename, so a parallel run never reads half of it."""
    archive = subprocess.run(
        ["git", "-C", str(source), "archive", "--format=tar", commit],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        raise PinError(f"could not export ForeverCore {commit} from {source}: {archive.stderr.decode().strip()}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    try:
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            extract(tar, staging)
        (staging / EXPORT_MARKER).write_text(f"{pin} {commit}\n", encoding="utf-8")
        try:
            staging.rename(target)
        except OSError:
            if (target / EXPORT_MARKER).is_file():
                return  # another run exported the same commit first
            raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def core_for(root: Path, environ) -> tuple[str | None, str]:
    """The FOREVER_CORE the specs should load, and a line saying why, or (None, "") to leave the environment alone.

    A checkout without a pin (ForeverCore itself, or an addon without core) is left alone. Otherwise the checkout
    `FOREVER_CORE` names (relative to the root), or the sibling `forever-core`, is used as it is when its HEAD is the
    pinned commit with no tracked edits; any other state loads an export of
    the pin instead. The cache is reused only when its marker names the same tag and commit.
    """
    pin_file = root / PIN_PATH
    if not pin_file.is_file():
        return None, ""
    pin = pin_file.read_text(encoding="utf-8").strip()
    if not pin:
        raise PinError(f"{PIN_PATH} is empty")
    source = Path(environ.get("FOREVER_CORE") or root.parent / "forever-core").expanduser()
    if not source.is_absolute():
        source = root / source
    if environ.get(UNPINNED) == "1":
        return str(source), f"ForeverCore: {UNPINNED}=1, specs load {source} as it is, not the pinned {pin}"
    if not source.is_dir():
        raise PinError(f"ForeverCore checkout not found at {source}: set FOREVER_CORE to a cjber/forever-core checkout")
    if not (source / "ForeverCore.toc").is_file():
        raise PinError(f"{source} has no ForeverCore.toc: set FOREVER_CORE to a cjber/forever-core checkout")
    top = git(source, "rev-parse", "--show-toplevel")
    if not top or Path(top).resolve() != source.resolve():
        raise PinError(f"{source} is not a git checkout, so which ForeverCore it holds is unknown; the pin is {pin}")
    commit = pinned_commit(source, pin)
    head = git(source, "rev-parse", "HEAD")
    edited = git(source, "status", "--porcelain", "--untracked-files=no")
    if head == commit and edited == "":
        return str(source), ""
    cache = Path(environ.get("XDG_CACHE_HOME") or Path.home() / ".cache").expanduser() / "forever-core"
    target = cache / f"{pin}-{commit}"
    marker = target / EXPORT_MARKER
    if not marker.is_file():
        export(source, pin, commit, target)
    if marker.read_text(encoding="utf-8").split() != [pin, commit]:
        raise PinError(f"{target} does not hold ForeverCore {pin} ({commit}); delete it and run again")
    state = "has local edits" if head == commit else f"is at {git(source, 'describe', '--tags', '--always') or head}"
    return str(target), f"ForeverCore: {source} {state}, not the pinned {pin}; specs load {target}"


def run(root: Path, interpreter: str, spec: str, env=None) -> tuple[int, str, float]:
    started = time.monotonic()
    done = subprocess.run(
        [interpreter, spec],
        cwd=root,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = done.stdout.decode("utf-8", errors="replace")
    return done.returncode, output, time.monotonic() - started


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="specs at once (default: every core)")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="the repository root (default: here)")
    parser.add_argument("--pattern", default=PATTERN, help=f"the specs, relative to the root (default: {PATTERN})")
    parser.add_argument("--interpreter", default="luajit", help="what runs each spec (default: luajit)")
    args = parser.parse_args(argv)
    specs = sorted(str(path.relative_to(args.root)) for path in args.root.glob(args.pattern))
    if not specs:
        print(f"No specs match {args.pattern} under {args.root}", file=sys.stderr)
        return 1
    env = dict(os.environ)
    try:
        core, note = core_for(args.root.resolve(), env)
    except PinError as error:
        print(f"{error}; no spec ran", file=sys.stderr)
        return 1
    if core is not None:
        env["FOREVER_CORE"] = core
    if note:
        print(note, flush=True)
    started = time.monotonic()
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = [pool.submit(run, args.root, args.interpreter, spec, env) for spec in specs]
        for spec, result in zip(specs, results, strict=True):
            code, output, seconds = result.result()
            status = "ok" if code == 0 else f"FAILED (exit {code})"
            print(f"== {spec} {status} in {seconds:.1f}s", flush=True)
            if output:
                print(output, end="" if output.endswith("\n") else "\n", flush=True)
            if code != 0:
                failed.append(spec)
    elapsed = time.monotonic() - started
    print(f"{len(specs)} specs, {len(failed)} failed, {elapsed:.1f}s with {max(1, args.jobs)} at once")
    if failed:
        print("Failed:\n" + "\n".join(f"  {spec}" for spec in failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
