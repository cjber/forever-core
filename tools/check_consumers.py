"""Check every consuming Forever addon's copy of core's development tooling against this repo.

Each consumer carries a byte-identical copy of the files tools/check_core_shared.py lists in VENDORED: the project
rules and the dead-code gate. This gate is what stops the copies drifting: it compares each repo's main branch (or a
local checkout) with this repo's copy and names every mismatch. Consumers are compared from this repo (a private one
needs `GH_TOKEN` to be readable, and is otherwise reported as missing rather than crashing); `--local` supports an
offline check against local clones.

Once per consumer, deduplicated from VENDORED, a few more checks follow the copies, because a consumer's own config
drifts the same way:

- `tools/forever-core.txt`, when the consumer carries it, must name core's latest published release tag, so the
  addon's specs and CI test against the core a player runs. The tag comes from `forever_tools.core_pin.latest_release`,
  the same read every consumer's package and release gates use; with `--local` it is this checkout's newest `v*` tag
  from `git describe`. A latest release that cannot be read fails this gate rather than skipping the check.
- `.pkgmeta`, when the consumer's root TOC names ForeverCore in `## OptionalDeps`, must retain its pinned fallback
  during standalone dependency adoption: `externals:` downloads `ForeverCore-<pin>-forever.zip` from the release the
  consumer's `tools/forever-core.txt` names and `move-folders:` places it beside the addon's own folder. The sync adds
  `forevercore` under `required-dependencies`; bundle-only consumers remain valid during adoption. Removal needs the
  per-manager lifecycle evidence in docs/dependency-transition.md, since metadata alone does not prove ownership.
- The same root TOC must carry `## X-Forever-Core: <pin>`, the tag the bundled folder is, so a player's other Forever
  addon can name a sibling whose core is out of date. It must agree with `tools/forever-core.txt`.
- Each published consumer's own `release.yml`, which is not a vendored file, must still run the pin gate directly above
  its BigWigs packager, so a core release that lands after CI is caught before the upload.
- The step that runs `tools/check_package.py` in a consumer's own `ci.yml` must carry an authenticated GitHub token.
  That check reads core's latest published release through `forever_tools.core_pin`; an anonymous read shares the
  runner address's hourly limit and fails the package job with no code cause, so `tools/sync_consumers.py` adds
  `GH_TOKEN: ${{ github.token }}` to the step's `env:` and this gate refuses a workflow that drops it.

Those shared copies are compared by `forever_tools.core_pin`, the same function the vendored package check runs in each
consumer, so this gate and a consumer's own CI agree on the rule.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple
from urllib.parse import quote

from check_core_shared import CONSUMER_ROOT, VENDORED, source

CORE_ROOT = Path(__file__).resolve().parent.parent
TOOLING = CORE_ROOT / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))

from forever_tools import core_pin  # noqa: E402
from forever_tools import sync as tooling_sync  # noqa: E402

TOOLING_PACKAGE = TOOLING / "forever_tools"

# The shared comparison and the names tools/sync_consumer_prs.py rewrites the same bundle with.
PIN_PATH = core_pin.PIN_PATH
PKGMETA = core_pin.PKGMETA
CORE_FOLDER = core_pin.CORE_FOLDER
CORE_EXTERNAL = core_pin.CORE_EXTERNAL
EXTERNAL_TAG = core_pin.EXTERNAL_TAG
TOC_CORE_FIELD = core_pin.TOC_CORE_FIELD
compare = core_pin.compare
core_external = core_pin.core_external
pkgmeta_field = core_pin.pkgmeta_field

FOREVER_CORE = "forevercore"
VISUAL_WORKFLOW = ".github/workflows/visual-proof.yml"
RELEASE_WORKFLOW = ".github/workflows/release.yml"
# The step `tools/sync_consumers.py` inserts directly above the packager. It is the consumer's own file, so this gate
# verifies the step is still there and still last before the upload rather than comparing its bytes.
RELEASE_GATE = "Verify the ForeverCore pin is core's latest release"
RELEASE_GATE_COMMAND = "tools.forever_tools.core_pin --latest"
# The workflow file and the step that reads core's latest published release. The token is the one environment entry
# `tools/sync_consumers.py` adds to that step, so the read is authenticated and never shares the anonymous limit.
CI_WORKFLOW = ".github/workflows/ci.yml"
PACKAGE_STEP = "tools/check_package.py"
PACKAGE_TOKEN = "GH_TOKEN: ${{ github.token }}"

STEPS = re.compile(r"^(?P<indent>[ \t]*)steps:[ \t]*(?P<value>.*)$")
# The suite's dedicated package step: the command must start a line, so a script that only echoes or comments the path
# is not mistaken for the check itself.
PACKAGE_COMMAND = re.compile(r"^python3?[ \t]+tools/check_package\.py(?:[ \t]|$)")
TOKEN_ENTRY = re.compile(r"^(?:GH_TOKEN|GITHUB_TOKEN)[ \t]*:[ \t]*(?P<value>.*)$")


class UnsupportedEnv(ValueError):
    """A step's `env:` is not the block mapping this gate and the sync know how to read and edit."""


class StepEnv(NamedTuple):
    """A step's `env:` block: where it starts, whether it authenticates, and where a new entry goes."""

    index: int
    entry_indent: int
    token: bool
    token_line: int | None
    insert_at: int


class StepFields(NamedTuple):
    """The two fields of a step this gate reads, plus a reason an `env:` could not be read."""

    run: str | None
    env: StepEnv | None
    env_error: str | None


def token_value(line):
    """Accept the built-in Actions token, which is present even when fork secrets are unavailable."""
    match = TOKEN_ENTRY.match(line)
    if match is None:
        return False
    value = match["value"].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return value in ("${{ github.token }}", "${{ secrets.GITHUB_TOKEN }}")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def consumer_path(repo, path):
    """Where `repo` keeps the vendored `path`, relative to that consumer repo's root."""
    folder = CONSUMER_ROOT.get(repo)
    return f"{folder}/{path}" if folder else path


def authorized(url):
    """The request for `url`, with the token a private consumer needs; without one it answers 404."""
    request = urllib.request.Request(url)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    return request


def remote(repo, path, branch):
    url = f"https://raw.githubusercontent.com/cjber/{repo}/{branch}/{path}"
    with urllib.request.urlopen(authorized(url), timeout=60) as response:
        return response.read()


def remote_json(url):
    """One authenticated GitHub API response, decoded as JSON."""
    with urllib.request.urlopen(authorized(url), timeout=60) as response:
        return json.loads(response.read())


def latest_tag(local):
    """Core's newest published release tag, or `LatestReleaseUnavailable` when it cannot be read.

    The GitHub API read is `forever_tools.core_pin.latest_release`, the function every consumer's package and release
    gate calls, so this gate and a consumer's own CI agree on both the tag and how a failed read behaves: it fails.
    """
    if local:
        tag = local_latest_tag()
        if tag is None:
            raise core_pin.LatestReleaseUnavailable("this checkout has no readable newest v* tag")
        return tag
    return core_pin.latest_release()


def local_latest_tag():
    """Core's newest `v*` tag in this checkout, for `--local`, with no network."""
    shown = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", "--match", "v*"],
        cwd=CORE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if shown.returncode:
        print(f"Could not read this checkout's newest v* tag ({shown.stderr.strip()}).")
        return None
    return shown.stdout.strip() or None


def read_consumer(repo, path, branch, local):
    """One consumer file's bytes, or (None, None) when the consumer does not carry it.

    A read that fails for another reason is (None, reason), so each check names it in its own words.
    """
    if local:
        target = local / repo / path
        try:
            return (target.read_bytes() if target.is_file() else None), None
        except OSError as error:
            return None, f"could not be read: {error}"
    try:
        return remote(repo, path, branch), None
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None, None
        return None, f"could not be read: {error}"
    except (OSError, urllib.error.URLError, TimeoutError) as error:
        return None, f"could not be read: {error}"


def pkgmeta_blocks(text):
    """A `.pkgmeta`'s top-level keys, each with the indented lines under it, read line by line."""
    blocks = {}
    key = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[:1].isspace():
            key = stripped.partition(":")[0].strip()
            blocks.setdefault(key, [])
        elif key is not None:
            blocks[key].append(stripped)
    return blocks


def block_values(lines):
    """One `.pkgmeta` block's entries, lowercased: `- name` items as name -> "", `name: value` as name -> value."""
    values = {}
    for line in lines:
        if line.startswith("- "):
            name, value = line[2:].strip(), ""
        else:
            name, _, value = line.partition(":")
            name = name.strip()
        values[name.strip("'\"").lower()] = value.strip().strip("'\"")
    return values


def block_entries(lines):
    """The names in one `.pkgmeta` block, lowercased: `- name` items and the keys of `name: value` entries."""
    return list(block_values(lines))


def toc_names(toc, header):
    """The names in a TOC's `## <header>:` line, lowercased."""
    wanted = f"## {header}".lower()
    for line in toc.decode("utf-8", "replace").splitlines():
        name, separator, value = line.strip().partition(":")
        if separator and name.strip().lower() == wanted:
            return {part.strip().lower() for part in value.split(",")}
    return set()


def toc_core(toc):
    """Whether a TOC names ForeverCore in each dependency header: `(required, optional)`.

    Consumers declare `## OptionalDeps: ForeverCore` so the addon still loads without core and can say what is
    missing; `## Dependencies: ForeverCore` makes the client skip the addon entirely, so it is a failure.
    """
    return FOREVER_CORE in toc_names(toc, "Dependencies"), FOREVER_CORE in toc_names(toc, "OptionalDeps")


def root_toc(repo, pkgmeta, branch, local):
    """The consumer's root TOC text, or None when it cannot be told.

    The packager names the TOC after `package-as`, so that field gives its path; a `.pkgmeta` without it, or a TOC
    that cannot be read, leaves the packaging rule unchecked rather than guessing.
    """
    package = pkgmeta_field(pkgmeta, "package-as")
    if not package:
        return None
    path = consumer_path(repo, f"{package}.toc")
    data, error = read_consumer(repo, path, branch, local)
    if error:
        print(f"{repo}: {path}: {error}; the packaging check is skipped")
    return data


def read_pins(consumers, branch, local):
    """Every consumer's `tools/forever-core.txt` tag, with a failure for each pin that cannot be read."""
    pins = {}
    failures = []
    for repo in consumers:
        path = consumer_path(repo, PIN_PATH)
        data, error = read_consumer(repo, path, branch, local)
        if error:
            failures.append(f"{repo}: {path}: {error}")
        elif data is not None:
            pins[repo] = data.decode("utf-8", "replace").strip()
    return pins, failures


def check_pins(pins, local):
    """Every consumer's pin names core's latest release; an unreadable latest release is itself a failure."""
    failures = []
    if not pins:
        return failures
    try:
        latest = latest_tag(local)
    except core_pin.LatestReleaseUnavailable as error:
        return [f"forever-core: could not read the latest published release ({error}); the pin check cannot pass"]
    for repo in sorted(pins):
        pin = pins[repo]
        failures += [
            f"{repo}: {failure}"
            for failure in core_pin.compare_latest(pin, latest, pin_path=consumer_path(repo, PIN_PATH))
        ]
    return failures


def check_packaging(repo, pin, branch, local):
    """A consumer that requires core ships it in its own zip, from the release its pin names, and owns it once."""
    path = consumer_path(repo, PKGMETA)
    data, error = read_consumer(repo, path, branch, local)
    if error:
        return [f"{repo}: {path}: {error}"]
    if data is None:
        return []
    pkgmeta = data.decode("utf-8", "replace")
    toc = root_toc(repo, pkgmeta, branch, local)
    if toc is None:
        return []
    package = pkgmeta_field(pkgmeta, "package-as")
    toc_path = consumer_path(repo, f"{package}.toc")
    required, optional = toc_core(toc)
    blocks = pkgmeta_blocks(pkgmeta)
    ships = bool(core_pin.external_line(pkgmeta))
    declares = "forevercore" in block_entries(blocks.get("required-dependencies", []))
    failures = []
    if required:
        failures.append(
            f"{repo}: {toc_path}: lists ForeverCore in `## Dependencies`, so the client skips the addon when core is"
            " missing; move it to `## OptionalDeps` and keep the other names on that line"
        )
    if not (required or optional or ships or declares):
        return failures
    if not optional and not required:
        failures.append(
            f"{repo}: {toc_path}: a Forever addon with no `## OptionalDeps: ForeverCore`; add it so the client loads"
            " core first when it is installed and this addon still loads without it"
        )
    failures += [
        f"{repo}: {failure}"
        for failure in compare(
            pin or "",
            pkgmeta,
            toc.decode("utf-8", "replace"),
            pin_path=consumer_path(repo, PIN_PATH),
            pkgmeta_path=path,
            toc_path=toc_path,
            require_external=True,
        )
    ]
    moved = block_values(blocks.get("move-folders", []))
    if moved.get(f"{package}/{CORE_FOLDER}".lower()) != CORE_FOLDER:
        failures.append(
            f"{repo}: {path}: `move-folders:` must place ForeverCore at the zip's top level with"
            f" `{package}/{CORE_FOLDER}: {CORE_FOLDER}`"
        )
    # During standalone dependency adoption the pinned bundle remains the fallback for old installations.
    # Removal is gated by manager lifecycle proof, documented in docs/dependency-transition.md.
    return failures


def indent_of(line):
    """The leading whitespace width of a workflow line."""
    return len(line) - len(line.lstrip(" \t"))


def workflow_steps(lines):
    """Every step under a `steps:` block, as `(first, stop, indent)` line indexes.

    Only a `steps:` key opens a step list, so a `- run:` under a matrix or another list is never read as a step.
    `lines[first:stop]` is one step; the next item at the same indent or the job's next key ends it.
    """
    blocks = []
    steps_indent = step_indent = first = None
    for index, line in enumerate(lines):
        stripped = line.lstrip(" \t")
        if not stripped or stripped.startswith("#"):
            continue
        leading = indent_of(line)
        match = STEPS.match(line)
        if steps_indent is None and match is not None and not match["value"].strip():
            steps_indent, step_indent, first = leading, None, None
            continue
        if steps_indent is None:
            continue
        if leading <= steps_indent:
            if first is not None:
                blocks.append((first, index, step_indent))
            steps_indent = step_indent = first = None
            continue
        if stripped.startswith("- "):
            if step_indent is None:
                step_indent = leading
            if leading == step_indent:
                if first is not None:
                    blocks.append((first, index, step_indent))
                first = index
    if first is not None:
        blocks.append((first, len(lines), step_indent))
    return blocks


def _step_property(lines, index, stop, key_indent, value):
    """A property's value, folding a block scalar, and the line after it."""
    value = value.strip()
    if not value.startswith(("|", ">")):
        return value, index + 1
    content = []
    cursor = index + 1
    while cursor < stop:
        raw = lines[cursor]
        stripped = raw.lstrip(" \t")
        if not stripped:
            content.append("")
            cursor += 1
            continue
        if indent_of(raw) <= key_indent:
            break
        content.append(stripped.rstrip("\r\n"))
        cursor += 1
    return "\n".join(content), cursor


def _step_env(lines, start, stop, key_indent, env_index):
    """Read direct environment keys, preserving GH_TOKEN's precedence over GITHUB_TOKEN."""
    entry_indent = None
    tokens = {}
    token_lines = {}
    insert_at = start
    for cursor in range(start, stop):
        child = lines[cursor]
        stripped = child.lstrip(" \t")
        if not stripped.strip() or stripped.startswith("#"):
            continue
        if indent_of(child) <= key_indent:
            break
        if entry_indent is None:
            entry_indent = indent_of(child)
        insert_at = cursor + 1
        if indent_of(child) != entry_indent or not TOKEN_ENTRY.match(stripped):
            continue
        key, _, value = stripped.partition(":")
        if value.strip().startswith(("|", ">")):
            raise UnsupportedEnv("token block scalars need a built-in token expression")
        tokens[key] = token_value(stripped)
        token_lines[key] = cursor
    key = "GH_TOKEN" if "GH_TOKEN" in tokens else "GITHUB_TOKEN"
    return StepEnv(env_index, entry_indent or key_indent + 2, tokens.get(key, False), token_lines.get(key), insert_at)


def step_fields(lines, first, stop):
    """A step's `run` and `env`, read only at its own property indentation.

    A block scalar's body is folded into its property's value, so a script's own `run:` or `env:` text is never read
    as a property. An inline `env:` is reported through `env_error` instead of guessed at, because the sync cannot
    add an entry to it without rewriting the line.
    """
    key_indent = indent_of(lines[first]) + 2
    run = None
    env = None
    env_error = None
    head = lines[first].lstrip(" \t")[2:]
    index = first + 1
    if head and not head.startswith("#"):
        key, separator, value = head.partition(":")
        if separator:
            key = key.strip()
            value, index = _step_property(lines, first, stop, key_indent, value)
            if key == "run":
                run = value
            elif key == "env":
                if value:
                    env_error = "`env:` is an inline mapping"
                else:
                    env = _step_env(lines, index, stop, key_indent, first)
    while index < stop:
        raw = lines[index]
        stripped = raw.lstrip(" \t")
        if not stripped or stripped.startswith("#") or indent_of(raw) != key_indent:
            index += 1
            continue
        key, separator, value = stripped.partition(":")
        if not separator:
            index += 1
            continue
        key = key.strip()
        property_index = index
        value, index = _step_property(lines, index, stop, key_indent, value)
        if key == "run":
            run = value
        elif key == "env":
            if value:
                env_error = "`env:` is an inline mapping"
            else:
                env = _step_env(lines, index, stop, key_indent, property_index)
    return StepFields(run, env, env_error)


def package_command(value):
    """Whether a `run:` value actually invokes the suite's package check, not merely mentions it."""
    return any(PACKAGE_COMMAND.match(line) for line in value.splitlines())


def check_package_token(repo, branch, local):
    """Every step that runs `tools/check_package.py` carries an authenticated GitHub token.

    The package check reads core's latest published release, and an anonymous read shares the runner address's hourly
    GitHub limit. A step without `GH_TOKEN` or `GITHUB_TOKEN` in its own `env:` can pass on a quiet runner and fail
    with a 403 on a busy one, so this gate fails the workflow rather than the release.
    """
    path = CI_WORKFLOW
    data, error = read_consumer(repo, path, branch, local)
    if error:
        return [f"{repo}: {path}: {error}"]
    if data is None:
        return []
    lines = data.decode("utf-8", "replace").splitlines(keepends=True)
    failures = []
    for first, stop, _ in workflow_steps(lines):
        try:
            fields = step_fields(lines, first, stop)
        except UnsupportedEnv as error:
            failures.append(f"{repo}: {path}: {error}")
            continue
        if fields.run is None or not package_command(fields.run):
            continue
        if fields.env is not None and fields.env.token:
            continue
        reason = fields.env_error or "no `GH_TOKEN` or `GITHUB_TOKEN` in its `env:`"
        failures.append(
            f"{repo}: {path}: the step running `python3 {PACKAGE_STEP}` has no authenticated token ({reason});"
            f" add `env:` with `{PACKAGE_TOKEN}` to that step"
        )
    return failures


def check_release_gate(repo, branch, local):
    """A consumer's own release workflow runs the pin gate directly above the packager.

    The workflow is not vendorable: each addon keeps its own. This is the one check that the step `sync_consumers.py`
    inserts is still present and still the last thing before the upload, so a hand edit cannot quietly reopen the gap
    between a green CI run and a stale pin. A workflow with no BigWigs packager step (kiln-forever's own tar build)
    has no packager to gate and is left alone.
    """
    path = consumer_path(repo, RELEASE_WORKFLOW)
    data, error = read_consumer(repo, path, branch, local)
    if error:
        return [f"{repo}: {path}: {error}"]
    if data is None:
        return []
    text = data.decode("utf-8", "replace")
    packager = text.find("BigWigsMods/packager@")
    if packager < 0:
        return []
    gate = text.find(RELEASE_GATE)
    if gate < 0:
        return [
            f"{repo}: {path}: no ForeverCore pin gate; insert `- name: {RELEASE_GATE}` running"
            f" `python3 -m {RELEASE_GATE_COMMAND}` directly above the packager"
        ]
    if gate > packager:
        return [f"{repo}: {path}: the ForeverCore pin gate is after the packager; move it directly above the upload"]
    if text.find(RELEASE_GATE_COMMAND, gate, packager) < 0:
        return [
            f"{repo}: {path}: the ForeverCore pin gate must run `python3 -m {RELEASE_GATE_COMMAND}` directly above"
            " the packager"
        ]
    return []


def canonical_visual_workflow():
    """Failures in this repository's own visual-proof template, the file every consumer copies."""
    path = CORE_ROOT / source(VISUAL_WORKFLOW)
    if not path.is_file():
        return [f"forever-core: {source(VISUAL_WORKFLOW)}: missing"]
    return []


def blob_sha(data):
    """The Git blob object id for `data`, the same SHA a repository tree and the Contents API report."""
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def tooling_listing(repo, branch, local):
    """A consumer's forever_tools files as name -> Git blob SHA, from one read of the folder.

    Remote reads use the Contents API's directory listing, so 39 files cost one authenticated REST call per consumer
    instead of one per file. The listing carries each blob's object id, which is exact identity: no file body needs to
    be downloaded to compare it with the canonical producer file.
    """
    folder = consumer_path(repo, "tools/forever_tools")
    if local:
        base = local / repo / folder
        if not base.is_dir():
            return None, None
        try:
            return {path.name: blob_sha(path.read_bytes()) for path in base.iterdir() if path.is_file()}, None
        except OSError as error:
            return None, f"could not be read: {error}"
    url = f"https://api.github.com/repos/cjber/{repo}/contents/{quote(folder, safe='/')}?ref={quote(branch, safe='')}"
    try:
        listing = remote_json(url)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None, None
        return None, f"could not be read: {error}"
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return None, f"could not be read: {error}"
    if not isinstance(listing, list):
        return None, "could not be read: the Contents API did not return a directory listing"
    try:
        return {entry["name"]: entry["sha"] for entry in listing if entry.get("type") == "file"}, None
    except (AttributeError, KeyError, TypeError) as error:
        return None, f"could not be read: malformed directory listing ({error})"


def tooling_sync_problems(repo, branch, local):
    """Every file the canonical forever_tools MANIFEST lists, present and byte-identical in the consumer.

    The visual-proof job imports `visual_proof`, which imports `pkgmeta` and `toc`; checking the manifest the tooling
    sync already maintains keeps this from duplicating that import graph by hand. A consumer that took the workflow
    without the full tooling sync fails here instead of at the job's import.
    """
    manifest = tooling_sync.read_manifest(TOOLING_PACKAGE)
    folder = consumer_path(repo, "tools/forever_tools")
    listing, error = tooling_listing(repo, branch, local)
    if error:
        return [f"{repo}: {folder}: {error}"]
    if listing is None:
        return [f"{repo}: {folder}: missing; sync the full forever_tools package the visual-proof workflow imports"]
    failures = []
    for name in sorted(manifest["files"]):
        path = f"{folder}/{name}"
        canonical = TOOLING_PACKAGE / name
        if not canonical.is_file():
            failures.append(f"forever-core: {canonical}: missing from the canonical MANIFEST file map")
            continue
        expected = blob_sha(canonical.read_bytes())
        actual = listing.get(name)
        if actual is None:
            failures.append(
                f"{repo}: {path}: missing from the full forever_tools sync the visual-proof workflow imports"
            )
        elif actual != expected:
            failures.append(
                f"{repo}: {path}: {actual[:12]} here, {expected[:12]} in the canonical tooling; "
                "sync the full forever_tools package, not the workflow alone"
            )
    extras = sorted(set(listing) - set(manifest["files"]) - {"MANIFEST.json"})
    failures.extend(
        f"{repo}: {folder}/{name}: not in the canonical MANIFEST file map; sync the full forever_tools package"
        for name in extras
    )
    return failures


def check_visual_workflow(repo, branch, local):
    """A consumer's standalone workflow is present, canonical, and has the checker its job imports."""
    failures = []
    target = consumer_path(repo, VISUAL_WORKFLOW)
    data, error = read_consumer(repo, target, branch, local)
    if error:
        failures.append(f"{repo}: {target}: {error}")
    elif data is None:
        failures.append(
            f"{repo}: {target}: missing canonical visual-proof workflow; remove any inline visual-proof job, "
            "then run tools/sync_consumers.py"
        )
    else:
        expected_path = CORE_ROOT / source(VISUAL_WORKFLOW)
        if not expected_path.is_file():
            # `canonical_visual_workflow` already names the missing producer file.
            return failures
        expected = expected_path.read_bytes()
        if digest(data) != digest(expected):
            failures.append(
                f"{repo}: {target}: drifted from {source(VISUAL_WORKFLOW)}: "
                f"consumer {digest(data)[:12]} core {digest(expected)[:12]}"
            )
    return failures + tooling_sync_problems(repo, branch, local)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--branch", default="main", help="the consumers' branch to compare (default: main)")
    parser.add_argument("--local", type=Path, help="compare checkouts under this directory instead of GitHub")
    arguments = parser.parse_args(argv)

    failures = []
    comparisons = 0
    if VISUAL_WORKFLOW in VENDORED:
        failures += canonical_visual_workflow()
    for path, consumers in VENDORED.items():
        # The visual-proof copy gets its own message and migration check below, so a missing or drifted workflow names
        # the required status instead of only a digest.
        if path == VISUAL_WORKFLOW:
            continue
        mine = (CORE_ROOT / source(path)).read_bytes()
        for repo in consumers:
            comparisons += 1
            target = consumer_path(repo, path)
            try:
                if arguments.local:
                    theirs = (arguments.local / repo / target).read_bytes()
                else:
                    theirs = remote(repo, target, arguments.branch)
            except FileNotFoundError:
                failures.append(f"{repo}: {target}: missing here")
                continue
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    failures.append(
                        f"{repo}: {target}: missing from cjber/{repo}@{arguments.branch} "
                        "(not pushed yet, or a private repo without a token)"
                    )
                else:
                    failures.append(f"{repo}: {target}: could not be read: {error}")
                continue
            except (OSError, urllib.error.URLError, TimeoutError) as error:
                failures.append(f"{repo}: {target}: could not be read: {error}")
                continue
            if digest(theirs) != digest(mine):
                failures.append(f"{repo}: {target}: {digest(theirs)[:12]} here {digest(mine)[:12]}")

    # The copies are checked per file above; these two read the consumer's own config, once per repository.
    repos = sorted({repo for consumers in VENDORED.values() for repo in consumers})
    pins, pin_failures = read_pins(repos, arguments.branch, arguments.local)
    failures += pin_failures
    failures += check_pins(pins, arguments.local)
    for repo in repos:
        failures += check_packaging(repo, pins.get(repo), arguments.branch, arguments.local)
    for repo in VENDORED.get(VISUAL_WORKFLOW, ()):
        failures += check_visual_workflow(repo, arguments.branch, arguments.local)
    # The published addons are the ones with a visual-proof workflow, and every one of them packages with BigWigs.
    # Kiln Forever's own tar build has no packager to gate, so it is not in this list.
    for repo in VENDORED.get(VISUAL_WORKFLOW, ()):
        failures += check_release_gate(repo, arguments.branch, arguments.local)
    # Any consumer's own CI may run the package check; each such step must be authenticated, whether or not the addon
    # publishes a visual-proof workflow.
    for repo in repos:
        failures += check_package_token(repo, arguments.branch, arguments.local)

    if failures:
        print("Consumers differ from this repo:")
        for failure in failures:
            print(f"  {failure}")
        print(
            "Fix the copies with tools/sync_consumers.py; the sync-consumers workflow moves a lagging pin. "
            "Then commit in the consumer repos."
        )
        return 1
    print(f"{comparisons} shared file copies match their consumer repos; pins and packaging agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
