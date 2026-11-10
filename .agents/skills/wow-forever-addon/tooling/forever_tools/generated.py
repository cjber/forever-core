"""The generated-data gate: regenerate in a disposable tree, require fresh and byte-stable output, report what moved.

Each addon supplies which files its generators own and how to run them; this runs them twice (the second pass
offline from the first pass's inputs, never from its outputs), so a pass proves freshness and the next proves
the bytes do not depend on the run. The two passes run at the same time in separate scratch trees; when the first
pass changes its inputs, the second is run again afterwards from those inputs. A stale file comes with a semantic
report of what the new data adds, removes and changes, not only its name.
"""

import argparse
import filecmp
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from .report import Hint, Subset, build_report

Outputs = Mapping[str, bytes]


def input_cache(root: Path, cache: str = "tools/.cache") -> Path:
    """The main checkout's cache, so every git worktree of the repository shares one set of inputs."""
    common = subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root, text=True
    ).strip()
    return Path(common).parent / cache


def copy_tracked(root: Path, scratch: Path) -> None:
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    for name in filter(None, tracked):
        source = root / name
        if source.is_file():
            target = scratch / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def copy_back(source: Path, target: Path) -> None:
    """Copy into `target` each file under `source` that is new or changed, leaving unchanged ones alone.

    A changed file is replaced through a temporary sibling, never written in place, so a read-only file (a git pack,
    0444) is replaced rather than refused. A top-level `.scratch` folder is never copied.
    """
    for folder, directories, files in os.walk(source):
        here = Path(folder)
        if here == source:
            directories[:] = [name for name in directories if name != ".scratch"]
        destination = target / here.relative_to(source)
        destination.mkdir(parents=True, exist_ok=True)
        for name in files:
            new, old = here / name, destination / name
            if old.is_file() and filecmp.cmp(new, old, shallow=True):
                continue
            partial = destination / f".{name}.partial"
            shutil.copy2(new, partial)
            os.replace(partial, old)


def lua_texts(expected: Outputs, actual: Outputs) -> dict[str, tuple[str | None, str | None]]:
    """Each generated Lua file as (old text, new text); None marks a file absent on that side."""

    def text(data: bytes | None) -> str | None:
        return None if data is None else data.decode("utf-8", errors="replace")

    return {
        name: (text(expected.get(name)), text(actual.get(name)))
        for name in sorted(expected.keys() | actual.keys())
        if name.endswith(".lua")
    }


def semantic_report(
    expected: Outputs, actual: Outputs, hints: Mapping[str, Hint] | None = None, subsets: Iterable[Subset] = ()
) -> str:
    return build_report(lua_texts(expected, actual), hints, subsets)


def compare(
    expected: Outputs,
    actual: Outputs,
    label: str,
    hints: Mapping[str, Hint] | None = None,
    subsets: Iterable[Subset] = (),
) -> None:
    changed = sorted(name for name in expected.keys() | actual.keys() if expected.get(name) != actual.get(name))
    if changed:
        raise SystemExit(
            f"{label}:\n" + "\n".join(changed) + "\n\n" + semantic_report(expected, actual, hints, subsets)
        )


def same_tree(left: Path, right: Path) -> bool:
    """Whether two directories hold the same files with the same bytes; two missing directories are the same."""
    if not left.is_dir() or not right.is_dir():
        return left.is_dir() == right.is_dir()

    def files(top: Path) -> set[Path]:
        return {Path(folder, name).relative_to(top) for folder, _, names in os.walk(top) for name in names}

    names = files(left)
    return names == files(right) and all(filecmp.cmp(left / name, right / name, shallow=True) for name in names)


@contextmanager
def scratch_tree(root: Path, shared: Path, cache: str, prefix: str, temporary_root: Path | None) -> Iterator[Path]:
    """A disposable copy of the tracked tree, seeded with an independent copy of the shared input cache."""
    with tempfile.TemporaryDirectory(prefix=prefix, dir=temporary_root) as temporary:
        scratch = Path(temporary)
        try:
            copy_tracked(root, scratch)
            if shared.is_dir():
                shutil.copytree(shared, scratch / cache, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".scratch"))
        except OSError as error:
            reason = error.args[0][0][2] if isinstance(error, shutil.Error) and error.args[0] else str(error)
            raise SystemExit(
                f"Cannot prepare generated-data scratch at {scratch}: {reason}\n"
                f"Input cache: {shared}\nSet TMPDIR to a writable filesystem with room for an independent cache copy."
            ) from error
        yield scratch


def check_generated(
    root: Path,
    *,
    outputs: Callable[[Path], Outputs],
    regenerate: Callable[[Path, bool], None],
    offline: bool,
    success: str,
    hints: Mapping[str, Hint] | None = None,
    subsets: Iterable[Subset] = (),
    cache: str = "tools/.cache",
    prefix: str = "regenerate-",
) -> None:
    """Regenerate twice in scratch copies of the tracked tree, seeded with the shared input cache.

    `regenerate(scratch, offline)` removes the generated files and runs every generator; it must touch nothing outside
    `scratch`, because the two passes run at the same time. The first pass (online unless `offline`) proves the
    committed files are fresh. The second, offline, runs in its own tree from the same cache. It counts only when the
    first pass left the inputs byte-identical, so both read the same inputs; otherwise, or when it fails, it runs again
    after the first pass, from that pass's inputs, as a serial gate would. An online first pass copies the inputs it
    downloaded or changed back into the shared cache (`copy_back`), so later runs work offline. Scratch lives in the
    ignored shared cache, avoiding limited system tmpfs. An explicit TMPDIR, TEMP or TMP keeps the platform's
    temporary-directory selection.
    """
    shared = input_cache(root, cache)
    temporary_root = None
    if not any(os.environ.get(name) for name in ("TMPDIR", "TEMP", "TMP")):
        temporary_root = shared / ".scratch"
        temporary_root.mkdir(parents=True, exist_ok=True)

    def replay(scratch: Path) -> bool:
        try:
            regenerate(scratch, True)
        except (subprocess.CalledProcessError, OSError, SystemExit):
            return False
        return True

    with (
        scratch_tree(root, shared, cache, prefix, temporary_root) as fresh,
        scratch_tree(root, shared, cache, prefix, temporary_root) as second,
    ):
        expected = outputs(fresh)
        with ThreadPoolExecutor(max_workers=1) as pool:
            replayed = pool.submit(replay, second)
            regenerate(fresh, offline)
            replayed_ok = replayed.result()
        if not offline and (fresh / cache).is_dir():
            copy_back(fresh / cache, shared)
        generated = outputs(fresh)
        compare(expected, generated, "Stale generated files; run the canonical generators", hints, subsets)
        if replayed_ok and same_tree(fresh / cache, second / cache):
            again = outputs(second)
        else:
            regenerate(fresh, True)
            again = outputs(fresh)
        compare(generated, again, "Regeneration is not byte-for-byte reproducible", hints, subsets)
    print(success)


def data_report(
    root: Path,
    files: Iterable[str],
    *,
    hints: Mapping[str, Hint] | None = None,
    subsets: Iterable[Subset] = (),
    argv: list[str] | None = None,
) -> None:
    """Print the semantic report between a git revision's generated files and the working tree's."""
    parser = argparse.ArgumentParser(description=data_report.__doc__)
    parser.add_argument("--base", default="HEAD", help="the revision the working tree is compared with")
    args = parser.parse_args(argv)
    pairs: dict[str, tuple[str | None, str | None]] = {}
    for name in files:
        shown = subprocess.run(["git", "show", f"{args.base}:{name}"], cwd=root, capture_output=True, check=False)
        before = shown.stdout.decode("utf-8", errors="replace") if shown.returncode == 0 else None
        path = root / name
        pairs[name] = (before, path.read_text(encoding="utf-8") if path.exists() else None)
    print(build_report(pairs, hints, subsets))
