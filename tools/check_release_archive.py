"""Exercise the built release zip before the packager can upload it (#203)."""

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLING = ROOT / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))
from forever_tools import lua51, package, widget_handlers  # noqa: E402


def check_archive(archive: Path, scratch: Path, cache: Path) -> list[str]:
    """Check the zip's runtime, never test support or runtime copied from the checkout."""
    with tempfile.TemporaryDirectory(prefix="release-archive-", dir=scratch) as temporary:
        extracted = Path(temporary)
        with zipfile.ZipFile(archive) as built:
            for member in built.infolist():
                target = (extracted / member.filename).resolve()
                if not target.is_relative_to(extracted) or member.filename.startswith("/"):
                    return [f"{archive}: unsafe archive member {member.filename}"]
            built.extractall(extracted)
            # Refuse a stale archive left beside a newly built package folder. The upload pass reuses this
            # archive with copying and zipping disabled; it never reconstructs a tested archive.
            archived = {member.filename: built.read(member) for member in built.infolist() if not member.is_dir()}
        current = {
            file.relative_to(archive.parent).as_posix(): file.read_bytes()
            for file in (archive.parent / "ForeverCore").rglob("*")
            if file.is_file()
        }
        if archived != current:
            return [f"{archive}: package folder differs from the built zip; rebuild before uploading"]
        problems = package.check(extracted, package.Policy(addons=("ForeverCore",)))
        folder = extracted / "ForeverCore"
        if problems:
            return problems
        problems += lua51.check(folder)
        problems += widget_handlers.check_root(folder)
        if problems:
            return problems
        result = subprocess.run(
            ["luajit", str(TOOLING / "forever_sim/run.lua")],
            cwd=folder,
            env={**os.environ, "FOREVER_SIM_CACHE": str(cache.resolve())},
            capture_output=True,
            text=True,
            timeout=package.SPEC_TIMEOUT,
        )
        if result.returncode:
            return [f"{archive}: packaged exercise failed:\n{result.stdout}{result.stderr}"]
        print(result.stdout, end="")
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, default=Path(".release"))
    args = parser.parse_args(argv)
    archives = sorted(args.release_dir.glob("*.zip"))
    if len(archives) != 1:
        parser.error(f"{args.release_dir}: expected one built ForeverCore release zip, found {len(archives)}")
    scratch = Path.home() / ".cache/agent-scratch/forever-release"
    scratch.mkdir(parents=True, exist_ok=True)
    cache = Path(os.environ.get("FOREVER_SIM_CACHE", "tools/.cache/forever_sim"))
    for archive in archives:
        try:
            problems = check_archive(archive, scratch, cache)
        except (OSError, zipfile.BadZipFile, subprocess.TimeoutExpired) as error:
            problems = [f"{archive}: {error}"]
        if problems:
            print("\n".join(problems), file=sys.stderr)
            return 1
        print(f"release archive: {archive.name} passed the packaged exercise")
        if output := os.environ.get("GITHUB_OUTPUT"):
            with Path(output).open("a", encoding="utf-8") as stream:
                stream.write(f"archive={archive.resolve()}\n")
                stream.write(f"archive_name={archive.name}\n")
                stream.write(f"archive_label={archive.stem.removeprefix('ForeverCore-')}\n")
                stream.write(f"sha256={hashlib.sha256(archive.read_bytes()).hexdigest()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
