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
is left alone and its exact step is printed for the maintainer. The same full sync puts the bare version step
(`forever_tools.toc_version`) above every packager step in the release and CI workflows, so the zip's TOC never
carries the tag's `v`. A full sync also removes the retired Wago store
metadata, upload credential and store links from consumer-owned publishing files.

"""

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from check_consumers import CI_WORKFLOW, TAG_STEP, VERSION_COMMAND, pkgmeta_field, tag_step, uncommented, workflow_step
from check_core_shared import CONSUMER_ROOT, VENDORED, source

CORE_ROOT = Path(__file__).resolve().parent.parent
WARNING_MODULE = "Core/ForeverRequire.lua"
FONT_MANIFEST = "tools/font_bindings.json"
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


def font_digest_edit(root, repo, path, content):
    """`path`'s pinned font-binding digest refreshed to `content`, or None.

    `path` is core's file, vendored into `repo` by this sync, so the addon cannot review it; a digest the addon
    pins for it would otherwise fail the addon's typecheck on every core change to the file (#998). Only the
    digest moves: bindings, notes and every other producer stay exactly as the addon reviewed them.
    """
    manifest = root / consumer_path(repo, FONT_MANIFEST)
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    producers = data.get("producers")
    if not isinstance(producers, list):
        return None
    fresh = digest(content)
    stale = [p for p in producers if isinstance(p, dict) and p.get("source") == path and p.get("sha256") != fresh]
    if not stale:
        return None
    for producer in stale:
        producer["sha256"] = fresh
    return manifest, json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def release_gate_step(indent="      "):
    """The release-workflow step that fails a stale pin immediately before the packager uploads."""
    return (
        f"{indent}# A ForeverCore release can land between this commit's CI and this upload, and the zip carries the\n"
        f"{indent}# core its pin names. The package job compares the three copies offline; check --latest here,\n"
        f"{indent}# with nothing between it and the packager.\n"
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


def version_step(indent="      "):
    """The step that writes the bare version into the TOC, so the packager never fills in the tag's `v`."""
    return (
        f"{indent}# The packager fills @project-version@ with the tag, v and all; write the bare version first.\n"
        f"{indent}- name: Write the bare version into the TOC\n"
        f"{indent}  run: python3 -m {VERSION_COMMAND}\n"
    )


def version_step_edit(text):
    """`text` with the version step directly above each BigWigs packager step that has none before it, or None."""
    live = uncommented(text)  # a commented-out step does not run
    packagers = list(PACKAGER_STEP.finditer(live))
    command = f"python3 -m {VERSION_COMMAND}"
    previous, pieces = 0, []
    for packager in packagers:
        anchor = packager.start()
        if command not in live[previous:anchor]:
            # The pin gate stays the last step before the packager, so the version step goes above it and its comment.
            gate = text.rfind(f"- name: {RELEASE_GATE_NAME}\n", previous, anchor)
            if gate >= 0:
                anchor = text.rfind("\n", previous, gate) + 1
                while anchor > previous:
                    above = text.rfind("\n", previous, anchor - 1) + 1
                    if not text[above:anchor].lstrip().startswith("#"):
                        break
                    anchor = above
            pieces += [text[previous:anchor], version_step(packager["indent"])]
            previous = anchor
    updated = "".join(pieces) + text[previous:]
    return None if updated == text else updated


def sync_version_step(root, repo, dry_run):
    """Insert the version step above every packager step in `repo`'s release and CI workflows; count the files."""
    changed = 0
    for workflow in (RELEASE_WORKFLOW, CI_WORKFLOW):
        path = root / workflow
        if not path.is_file():
            continue
        updated = version_step_edit(path.read_text(encoding="utf-8"))
        if updated is None:
            continue
        changed += 1
        print(f"{repo}: {workflow}: the bare version step")
        if not dry_run:
            path.write_text(updated, encoding="utf-8")
    return changed


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


def without_wago_store(text):
    """Remove the retired publishing channel, preserving wago.tools data attribution.

    These are store metadata keys and Markdown store links, not a keyword filter over game-data sources.
    """
    text = re.sub(r"^##\s*X-Wago-ID\s*:.*(?:\n|$)", "", text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r"^[ \t]*WAGO_API_TOKEN\s*:.*(?:\n|$)", "", text, flags=re.MULTILINE)
    text = re.sub(r" or\s+\[Wago(?: Addons)?\]\(https://addons\.wago\.io/[^)]+\)", "", text)
    return text.replace("CurseForge and Wago install", "CurseForge installs").replace(
        "CurseForge and Wago", "CurseForge"
    )


def sync_store_channels(root, repo, dry_run):
    """Retire Wago in consumer-owned publishing files during a full sync."""
    addon = root / CONSUMER_ROOT.get(repo, "")
    paths = [root / RELEASE_WORKFLOW, root / "README.md", addon / "docs/curseforge.md", *sorted(addon.glob("*.toc"))]
    changed = 0
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8")
        updated = without_wago_store(text)
        if updated == text:
            continue
        changed += 1
        print(f"{repo}: {path.relative_to(root)}")
        if not dry_run:
            path.write_bytes(updated.encode("utf-8"))
    return changed


def sync_tag_step(root, repo, dry_run):
    """Replace `repo`'s manual-release tag step with core's own, returning whether it changed.

    A workflow without the step (Kiln Forever's own build) is left alone: it has no manual release to tag.
    """
    path = root / RELEASE_WORKFLOW
    if not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8")
    found = workflow_step(text, TAG_STEP)
    if found is None:
        return 0
    start, end, indent = found
    step = tag_step(indent)
    if text[start:end] == step:
        return 0
    print(f"{repo}: {RELEASE_WORKFLOW}: {TAG_STEP}")
    if not dry_run:
        path.write_text(text[:start] + step + text[end:], encoding="utf-8")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkouts", type=Path, help="the directory holding the consumer checkouts")
    parser.add_argument("--dry-run", action="store_true", help="report what would change and write nothing")
    parser.add_argument("--only", action="append", choices=VENDORED, help="sync only this shared path; may be repeated")
    parser.add_argument(
        "--consumer",
        action="append",
        metavar="REPO",
        help="sync only this consumer repository; may be repeated, and one consumer's error then stays its own",
    )
    arguments = parser.parse_args(argv)

    known_consumers = {repo for consumers in VENDORED.values() for repo in consumers}
    wanted = set(arguments.consumer or ())
    unknown = wanted - known_consumers
    if unknown:
        parser.error(f"unknown consumer(s): {', '.join(sorted(unknown))}")

    changed = 0
    failures = []
    selected = arguments.only or VENDORED.keys()
    for path in selected:
        consumers = VENDORED[path]
        origin = CORE_ROOT / source(path)
        for repo in consumers:
            if wanted and repo not in wanted:
                continue
            root = arguments.checkouts / repo
            target = root / consumer_path(repo, path)
            if not root.is_dir():
                print(f"{repo}: not checked out under {arguments.checkouts}, skipped")
                continue
            content = origin.read_bytes()
            try:
                toc_edit = warning_toc_edit(root, repo) if path == WARNING_MODULE else None
                if not (target.exists() and digest(target.read_bytes()) == digest(content)):
                    changed += 1
                    print(f"{repo}: {path}")
                    if not arguments.dry_run:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(origin, target)
                refreshed = font_digest_edit(root, repo, path, content)
                if refreshed is not None:
                    font_manifest, font_text = refreshed
                    changed += 1
                    print(f"{repo}: {font_manifest.relative_to(root)}: {path} digest")
                    if not arguments.dry_run:
                        font_manifest.write_text(font_text, encoding="utf-8")
                if toc_edit is not None:
                    toc, text = toc_edit
                    changed += 1
                    print(f"{repo}: {toc.relative_to(root)}")
                    if not arguments.dry_run:
                        toc.write_bytes(text.encode("utf-8"))
            except (OSError, ValueError) as error:
                # Reported against this consumer and the run carries on: one addon's missing file once stopped the
                # sync for every consumer after it (#976).
                print(f"{repo}: {path}: {error}", file=sys.stderr)
                failures.append(repo)
    # A full sync also carries the release gate: that workflow is the addon's own, so it is inserted rather than
    # copied, and only when the maintainer asked for everything.
    if arguments.only is None:
        for repo in sorted(known_consumers):
            if wanted and repo not in wanted:
                continue
            root = arguments.checkouts / repo
            if not root.is_dir():
                continue
            try:
                changed += sync_store_channels(root, repo, arguments.dry_run)
                changed += sync_release_gate(root, repo, arguments.dry_run)
                changed += sync_tag_step(root, repo, arguments.dry_run)
                changed += sync_version_step(root, repo, arguments.dry_run)
            except (OSError, ValueError) as error:
                print(f"{repo}: {RELEASE_WORKFLOW}: {error}", file=sys.stderr)
                failures.append(repo)
    if changed and not arguments.dry_run:
        print("Run each changed consumer's gates and open one PR per consumer for the shared tooling.")
    if changed and VISUAL_WORKFLOW in selected:
        print(
            f"The visual-proof workflow imports {VISUAL_PROOF_MODULE}; its PR must also carry the full forever_tools"
            " sync, or the job fails on import."
        )
    verb = "would change" if arguments.dry_run else "changed"
    print(f"{changed} file(s) {verb}.")
    if failures:
        failed = ", ".join(sorted(set(failures)))
        print(f"{len(set(failures))} consumer(s) failed and left the rest alone: {failed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
