"""Copy this repo's development tooling into the consumer addons' working trees.

Fixing a shared rule is one change here and one command, instead of eight hand-edited copies. Each target file is
overwritten only when its content differs, so a run on an up-to-date checkout touches nothing and every change is
visible in `git status` for the consumer's own PR.

The shared load warning is copied into each addon and wired into its TOC ahead of `Core/Require.lua`. It must
be available even when the loaded ForeverCore cannot provide the API the addon requires.

A consumer whose addon lives below its repo root (kiln-forever, whose repository also carries a bridge) gets every file
under the addon folder CONSUMER_ROOT names. The visual-proof workflow stays a root file and reaches only the published
addons; its job imports tools/forever_tools/visual_proof.py, so a rollout that changes it also carries the full
forever_tools sync, never the workflow alone.

The release workflow is not a vendored file: each addon keeps its own. A full sync therefore inserts the ForeverCore
release gate directly above the BigWigs packager step in every consumer that has one, idempotently, so a core release
that lands between CI and the upload is still caught. A workflow with no packager step (kiln-forever's own tar build)
is left alone and its exact step is printed for the maintainer.
"""

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path

from check_consumers import pkgmeta_field
from check_core_shared import CONSUMER_ROOT, VENDORED, source

CORE_ROOT = Path(__file__).resolve().parent.parent
WARNING_MODULE = "Core/ForeverRequire.lua"
LOAD_GUARD = "Core/Require.lua"
VISUAL_WORKFLOW = ".github/workflows/visual-proof.yml"
VISUAL_PROOF_MODULE = "tools/forever_tools/visual_proof.py"
RELEASE_WORKFLOW = ".github/workflows/release.yml"
RELEASE_GATE_NAME = "Verify the ForeverCore pin is core's latest release"
# The step every consumer's release workflow shares: the packager that builds the zip and uploads it. The gate goes
# immediately above it, so nothing but the packager runs between the check and the upload.
PACKAGER_STEP = re.compile(r"^(?P<indent>[ \t]*)- uses: BigWigsMods/packager@", re.MULTILINE)


def consumer_path(repo, path):
    """Where `repo` keeps the vendored `path`, relative to that consumer repo's root."""
    folder = CONSUMER_ROOT.get(repo)
    return f"{folder}/{path}" if folder else path


def digest(data):
    """The hex SHA-256 of `data`, to compare a copy with its source."""
    return hashlib.sha256(data).hexdigest()


def warning_toc_edit(root, repo):
    """Return the package TOC and its new contents, or None when it already loads the warning."""
    pkgmeta = root / consumer_path(repo, ".pkgmeta")
    package = pkgmeta_field(pkgmeta.read_text(encoding="utf-8"), "package-as")
    if not package:
        raise ValueError(f"{pkgmeta} does not name the addon in package-as")
    toc = root / consumer_path(repo, f"{package}.toc")
    text = toc.read_bytes().decode("utf-8")
    lines = text.splitlines(keepends=True)
    entries = [line.strip().replace("\\", "/") for line in lines]
    try:
        guard = entries.index(LOAD_GUARD)
    except ValueError as error:
        raise ValueError(f"{toc} does not load {LOAD_GUARD}") from error
    if WARNING_MODULE in entries[:guard]:
        return None
    newline = "\r\n" if lines[guard].endswith("\r\n") else "\n"
    warning = WARNING_MODULE.replace("/", "\\") + newline
    before = "".join(lines[:guard])
    after = "".join(line for line, entry in zip(lines[guard:], entries[guard:], strict=True) if entry != WARNING_MODULE)
    return toc, before + warning + after


def release_gate_step(indent="      "):
    """The release-workflow step that fails a stale pin immediately before the packager uploads."""
    return (
        f"{indent}# A ForeverCore release can land between this commit's CI and this upload, and the zip carries the\n"
        f"{indent}# core its pin names. The package job already gates the pin; run the same gate once more here, with\n"
        f"{indent}# nothing between it and the packager.\n"
        f"{indent}- name: {RELEASE_GATE_NAME}\n"
        f"{indent}  env:\n"
        f"{indent}    GH_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}\n"
        f"{indent}  run: python3 -m tools.forever_tools.core_pin --latest\n"
    )


def release_gate_edit(root, repo):
    """`(path, updated_text, notice)` for `repo`'s release workflow.

    `updated_text` is None when nothing should be written: the gate is already present, there is no release workflow,
    or no packager step anchors the insertion. `notice` explains a workflow the sync cannot edit.
    """
    path = root / RELEASE_WORKFLOW
    if not path.is_file():
        return None, None, f"{repo}: no {RELEASE_WORKFLOW}; no release gate inserted"
    text = path.read_text(encoding="utf-8")
    if RELEASE_GATE_NAME in text:
        return path, None, None
    packager = PACKAGER_STEP.search(text)
    if packager is None:
        return (
            path,
            None,
            f"{repo}: {RELEASE_WORKFLOW} has no BigWigs packager step; add this before its upload:\n"
            f"{release_gate_step()}",
        )
    return path, text[: packager.start()] + release_gate_step(packager["indent"]) + text[packager.start() :], None


def sync_release_gate(root, repo, dry_run):
    """Insert the release gate into `repo`'s release workflow, returning whether it changed."""
    path, updated, notice = release_gate_edit(root, repo)
    if notice:
        print(notice)
    if path is None or updated is None:
        return 0
    print(f"{repo}: {RELEASE_WORKFLOW}")
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkouts", type=Path, help="the directory holding the consumer checkouts")
    parser.add_argument("--dry-run", action="store_true", help="report what would change and write nothing")
    parser.add_argument("--only", action="append", choices=VENDORED, help="sync only this shared path; may be repeated")
    arguments = parser.parse_args(argv)

    changed = 0
    selected = arguments.only or VENDORED.keys()
    for path in selected:
        consumers = VENDORED[path]
        origin = CORE_ROOT / source(path)
        for repo in consumers:
            root = arguments.checkouts / repo
            target = root / consumer_path(repo, path)
            if not root.is_dir():
                print(f"{repo}: not checked out under {arguments.checkouts}, skipped")
                continue
            content = origin.read_bytes()
            try:
                toc_edit = warning_toc_edit(root, repo) if path == WARNING_MODULE else None
            except (OSError, ValueError) as error:
                print(f"{repo}: {error}", file=sys.stderr)
                return 1
            if not (target.exists() and digest(target.read_bytes()) == digest(content)):
                changed += 1
                print(f"{repo}: {path}")
                if not arguments.dry_run:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(origin, target)
            if toc_edit is not None:
                toc, text = toc_edit
                changed += 1
                print(f"{repo}: {toc.relative_to(root)}")
                if not arguments.dry_run:
                    toc.write_bytes(text.encode("utf-8"))
    # A full sync also carries the release gate: that workflow is the addon's own, so it is inserted rather than
    # copied, and only when the maintainer asked for everything.
    if arguments.only is None:
        for repo in sorted({repo for consumers in VENDORED.values() for repo in consumers}):
            root = arguments.checkouts / repo
            if not root.is_dir():
                continue
            try:
                changed += sync_release_gate(root, repo, arguments.dry_run)
            except OSError as error:
                print(f"{repo}: {RELEASE_WORKFLOW}: {error}", file=sys.stderr)
                return 1
    if changed and not arguments.dry_run:
        print("Run each changed consumer's gates and open one PR per consumer for the shared tooling.")
    if changed and VISUAL_WORKFLOW in selected:
        print(
            f"The visual-proof workflow imports {VISUAL_PROOF_MODULE}; its PR must also carry the full forever_tools"
            " sync, or the job fails on import."
        )
    verb = "would change" if arguments.dry_run else "changed"
    print(f"{changed} file(s) {verb}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
