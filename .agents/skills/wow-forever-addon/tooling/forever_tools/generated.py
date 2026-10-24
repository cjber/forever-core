"""The generated-data gate: regenerate in a disposable tree, require fresh and byte-stable output, report what moved.

Each addon supplies which files its generators own and how to run them; this runs them twice (the second pass
offline from the first pass's downloads, never from its outputs), so a pass proves freshness and the next proves
the bytes do not depend on the run. A stale file comes with a semantic report of what the new data adds, removes
and changes, not only its name.
"""

import argparse
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Mapping
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
    """Regenerate twice in a scratch copy of the tracked tree, seeded with the shared input cache.

    `regenerate(scratch, offline)` removes the generated files and runs every generator. An online first pass
    copies the inputs it downloaded back into the shared cache, so the second pass and later runs work offline.
    """
    with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
        scratch = Path(temporary)
        copy_tracked(root, scratch)
        shared = input_cache(root, cache)
        if shared.is_dir():
            shutil.copytree(shared, scratch / cache, dirs_exist_ok=True)
        expected = outputs(scratch)
        regenerate(scratch, offline)
        if not offline and (scratch / cache).is_dir():
            shutil.copytree(scratch / cache, shared, dirs_exist_ok=True)
        generated = outputs(scratch)
        compare(expected, generated, "Stale generated files; run the canonical generators", hints, subsets)
        regenerate(scratch, True)
        compare(generated, outputs(scratch), "Regeneration is not byte-for-byte reproducible", hints, subsets)
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
