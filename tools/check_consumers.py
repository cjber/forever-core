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
  the same read every consumer's release gate uses; with `--local` it is this checkout's newest `v*` tag
  from `git describe`. A latest release that cannot be read fails this gate rather than skipping the check.
- `.pkgmeta`, when the root TOC opts in with `## X-Forever-Core-Embed: 1`, ships core only under `Libs/ForeverCore/`:
  no ForeverCore `externals:` entry, no top-level `move-folders:` rule, `forevercore` under `embedded-libraries:` and
  not under `required-dependencies:`, and `## X-Forever-Core:` equal to the pin (docs/dependency-transition.md).
- `.pkgmeta`, when the consumer's root TOC names ForeverCore in `## OptionalDeps` without opting in to the embed, keeps
  the bridge bundle until its embed release: `externals:` downloads `ForeverCore-<pin>-forever.zip` from the release
  the consumer's `tools/forever-core.txt` names and `move-folders:` places it beside the addon's own folder.
- The same root TOC must carry `## X-Forever-Core: <pin>`, the tag the bundled folder is, so a player's other Forever
  addon can name a sibling whose core is out of date. It must agree with `tools/forever-core.txt`.
- Each published consumer's own `release.yml`, which is not a vendored file, must still run the pin gate directly above
  its BigWigs packager, so a core release that lands after CI is caught before the upload.
- TOCs and release workflows must not retain the retired Wago store ID or upload credential.
- The same `release.yml` must carry core's own "Tag a manual release" step unchanged, the one that peels a signed tag
  and tags a workflow-changing commit with the PAT; `tools/sync_consumers.py` copies it in.
- A consumer that vendors the client-call lint must run it from its own `tools/typecheck.sh`.
- A consumer whose root TOC opts in with `## X-Forever-Core-Embed: 1` must run `python3 -m tools.forever_tools.embed`
  before every BigWigs packager step in its `release.yml` and `ci.yml`, so the zip it uploads and the package CI
  checks both carry `Libs/ForeverCore/` (docs/dependency-transition.md).


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
from urllib.parse import quote

from check_core_shared import CONSUMER_ROOT, VENDORED, check_gate_invocations, source

CORE_ROOT = Path(__file__).resolve().parent.parent
TOOLING = CORE_ROOT / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))

from forever_tools import core_pin  # noqa: E402
from forever_tools import pkgmeta as pkgmeta_reader  # noqa: E402
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
# The step a manual release tags its commit with. It is the same shell in every repo, so core's own release.yml is its
# source and each consumer's copy must match it once reindented.
TAG_STEP = "Tag a manual release"


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

    The GitHub API read is `forever_tools.core_pin.latest_release`, the function every consumer's release
    gate calls, so both release checks agree on the tag and fail when it cannot be read.
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


def read_pkgmeta(repo, branch, local):
    """The consumer's packager policy as `(path, text, error)`: `.pkgmeta`, else `pkgmeta.yaml`, as the packager reads.

    A consumer with neither is `(.pkgmeta path, None, None)`; a read that fails is that file's path and the reason.
    """
    for name in pkgmeta_reader.FILES:
        path = consumer_path(repo, name)
        data, error = read_consumer(repo, path, branch, local)
        if error:
            return path, None, error
        if data is not None:
            return path, data.decode("utf-8", "replace"), None
    return consumer_path(repo, PKGMETA), None, None


def root_toc_names(repo, branch, local):
    """The `.toc` file names in the consumer's root folder."""
    folder = CONSUMER_ROOT.get(repo, "")
    if local:
        return [path.name for path in (local / repo / folder).glob("*.toc")]
    suffix = f"/{folder}" if folder else ""
    listing = remote_json(f"https://api.github.com/repos/cjber/{repo}/contents{suffix}?ref={branch}")
    return [entry["name"] for entry in listing if entry.get("type") == "file" and entry["name"].endswith(".toc")]


def root_toc(repo, pkgmeta, branch, local, pkgmeta_path=PKGMETA):
    """`(package, TOC bytes, failure)` for the consumer's root TOC, chosen as the packager chooses it.

    `package-as` names the TOC. Without it the packager takes the shortest visible root TOC name, ties broken by name,
    and refuses a flavor-suffixed one (`forever_tools.pkgmeta.project_toc_files`), so this does the same. A consumer
    whose root TOC is not in the checkout has no packaging to check and is `(package, None, None)`; a TOC that cannot be
    listed or read is a failure, never a skipped check.
    """
    try:
        package = core_pin.policy_package(pkgmeta)
    except ValueError as error:
        return None, None, f"{repo}: {pkgmeta_path}: {error}"
    configured = bool(package)
    if not package:
        try:
            names = root_toc_names(repo, branch, local)
        except (OSError, urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError) as error:
            return (
                None,
                None,
                f"{repo}: {pkgmeta_path}: no `package-as`, and the root TOCs could not be listed: {error}",
            )
        try:
            name = core_pin.toc_name_for("", names)
        except ValueError as error:
            return None, None, f"{repo}: {pkgmeta_path}: {error}; set `package-as` or add a plain fallback TOC"
        if name is None:
            return None, None, None
        package = name[: -len(".toc")]
    path = consumer_path(repo, f"{package}.toc")
    data, error = read_consumer(repo, path, branch, local)
    if error:
        return package, None, f"{repo}: {path}: {error}"
    if data is None and configured:
        return package, None, f"{repo}: {pkgmeta_path}: `package-as: {package}` names {path}, which does not exist"
    return package, data, None


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
    path, pkgmeta, error = read_pkgmeta(repo, branch, local)
    if error:
        return [f"{repo}: {path}: {error}"]
    if pkgmeta is None:
        # No policy: the packager ships the shortest root TOC with no relations, so an opted-in TOC is a failure.
        package, toc, failure = root_toc(repo, "", branch, local, path)
        if failure:
            return [failure]
        if toc is not None and core_pin.embeds(toc):
            return [
                f"{repo}: {consumer_path(repo, f'{package}.toc')}: embeds ForeverCore, but the repository has no"
                f" {PKGMETA} or {pkgmeta_reader.FALLBACK}; the release would carry no embedded-libraries relation"
            ]
        return []
    package, toc, failure = root_toc(repo, pkgmeta, branch, local, path)
    if failure:
        return [failure]
    if toc is None:
        return []
    toc_path = consumer_path(repo, f"{package}.toc")
    problem = core_pin.embed_problem(toc, toc_path)
    if problem:
        return [f"{repo}: {problem}"]
    required, optional = toc_core(toc)
    blocks = pkgmeta_blocks(pkgmeta)
    ships = bool(core_pin.external_line(pkgmeta))
    declares = "forevercore" in block_entries(blocks.get("required-dependencies", []))
    failures = []
    if toc_names(toc, "X-Wago-ID"):
        failures.append(f"{repo}: {toc_path}: retired X-Wago-ID; run the core sync")
    if required:
        failures.append(
            f"{repo}: {toc_path}: lists ForeverCore in `## Dependencies`, so the client skips the addon when core is"
            " missing; move it to `## OptionalDeps` and keep the other names on that line"
        )
    embeds = core_pin.embeds(toc)
    if not (required or optional or ships or declares or embeds):
        return failures
    if not optional and not required:
        failures.append(
            f"{repo}: {toc_path}: a Forever addon with no `## OptionalDeps: ForeverCore`; add it so the client loads"
            " core first when it is installed and this addon still loads without it"
        )
    if embeds:
        try:
            root_tocs = root_toc_names(repo, branch, local)
        except (OSError, urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError) as error:
            return failures + [f"{repo}: the root TOCs could not be listed: {error}"]
        return failures + [
            f"{repo}: {failure}"
            for failure in check_embedded_packaging(
                pin or "", toc, pkgmeta, package, path=path, toc_path=toc_path, root_tocs=root_tocs
            )
        ]
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


external_ships_core = core_pin.external_ships_core


def check_embedded_packaging(pin, toc, pkgmeta, package, *, path, toc_path, root_tocs=()):
    """The embedded end state (`core_pin.embedded_packaging`, the same function each consumer's own gate runs)."""
    return core_pin.embedded_packaging(
        pin,
        toc,
        pkgmeta,
        package,
        root_tocs=root_tocs,
        pin_path=PIN_PATH,
        policy_path=path,
        toc_path=toc_path,
    )


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
    if "WAGO_API_TOKEN" in text:
        return [f"{repo}: {path}: retired WAGO_API_TOKEN; run the core sync"]
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


EMBED_COMMAND = "tools.forever_tools.embed"
CI_WORKFLOW = ".github/workflows/ci.yml"


def check_embed(repo, branch, local):
    """An opted-in consumer embeds core before each packager step, in its release and in its CI package check.

    The embed step rewrites the checkout the packager zips. A packager step with no embed before it uploads, or checks,
    an addon that cannot run without the standalone ForeverCore, which is the case the embedded copy exists for.
    """
    _path, pkgmeta, error = read_pkgmeta(repo, branch, local)
    if error or pkgmeta is None:
        return []
    # An unreadable or unresolvable root TOC is check_packaging's failure; it is not reported twice.
    _package, toc, _failure = root_toc(repo, pkgmeta, branch, local)
    if toc is None or not core_pin.embeds(toc):
        return []
    failures = []
    for workflow in (RELEASE_WORKFLOW, CI_WORKFLOW):
        path = consumer_path(repo, workflow)
        data, error = read_consumer(repo, path, branch, local)
        if error:
            failures.append(f"{repo}: {path}: {error}")
            continue
        text = "" if data is None else data.decode("utf-8", "replace")
        jobs = workflow_steps(text)
        if not any(step_packages(step) for steps in jobs for step in steps):
            failures.append(f"{repo}: {path}: opts in to the embedded ForeverCore but runs no BigWigs packager")
        # Each job has its own fresh checkout, so the embed has to run in the packager's own job, earlier in its steps;
        # a comment or a step that never runs (`if: false`) embeds nothing.
        for steps in jobs:
            embedded = held = False
            for step in steps:
                if step_embeds(step):
                    embedded = True
                if step_runs(step, FLEET_COMMAND):
                    held = True
                if not step_packages(step):
                    continue
                if not embedded:
                    failures.append(
                        f"{repo}: {path}: a packager step with no `python3 -m {EMBED_COMMAND}` step before it in its"
                        " job; the TOC sets `## X-Forever-Core-Embed: 1`, so embed the pinned core first"
                    )
                if workflow == RELEASE_WORKFLOW and not held:
                    failures.append(
                        f"{repo}: {path}: a release packager step with no `python3 -m {FLEET_COMMAND}` step before it"
                        " in its job; a hand-run release or a pushed tag must hold until every Forever addon embeds"
                        " ForeverCore (cjber/forever-core#448)"
                    )
    return failures


# A step that never runs: GitHub evaluates `if:` and skips the step on a false literal.
NEVER = {"false", "${{ false }}", "${{false}}"}


FLEET_COMMAND = "tools.forever_tools.fleet"


def step_runs(step, module):
    """Whether a workflow step runs `python3 -m <module>` in a shell line that is not a comment."""
    return step.get("if", "").strip().casefold() not in NEVER and any(
        f"python3 -m {module}" in shell_code(line) for line in step.get("run", "").splitlines()
    )


def step_embeds(step):
    """Whether a workflow step runs the embed command."""
    return step_runs(step, EMBED_COMMAND)


def step_packages(step):
    """Whether a workflow step uses the BigWigs packager."""
    return step.get("if", "").strip().casefold() not in NEVER and step.get("uses", "").startswith(
        "BigWigsMods/packager@"
    )


def shell_code(line):
    """One shell line without its comment: a `#` that starts a word begins one."""
    return re.split(r"(?:^|\s)#", line, maxsplit=1)[0]


def yaml_value(value):
    """A plain YAML scalar's value without a trailing ` # comment` or its quotes."""
    value = re.split(r"\s#", value, maxsplit=1)[0].strip()
    return value[1:-1] if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"" else value


def workflow_steps(text):
    """Every job's steps under a workflow's top-level `jobs:`, each step its `uses`, `run` and `if` values.

    A `run: |` or `run: >` block is the lines indented under it. Comment lines are dropped. A workflow with no
    `jobs:` key has no jobs.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    start = next((index for index, line in enumerate(lines) if re.match(r"^jobs:\s*(#.*)?$", line)), None)
    if start is None:
        return []
    jobs = []
    job_indent = None
    steps_indent = None
    item_indent = None
    step = None
    block = None
    for line in lines[start + 1 :]:
        if not line.strip():
            if block is not None:
                step["run"] += "\n"
            continue
        width = len(line) - len(line.lstrip())
        if block is not None:
            if width > block:
                step["run"] += line.strip() + "\n"
                continue
            block = None
        if line.lstrip().startswith("#"):
            continue
        if width == 0:
            break
        if job_indent is None:
            job_indent = width
        if width == job_indent:
            jobs.append([])
            steps_indent = item_indent = step = None
            continue
        if not jobs:
            continue
        body = line.strip()
        if steps_indent is None:
            if re.match(r"^steps:\s*(#.*)?$", body):
                steps_indent = width
            continue
        if width <= steps_indent and not body.startswith("- "):
            steps_indent = item_indent = step = None
            if re.match(r"^steps:\s*(#.*)?$", body):
                steps_indent = width
            continue
        if body.startswith("- ") and (item_indent is None or width == item_indent):
            item_indent = width
            step = {}
            jobs[-1].append(step)
            body = body[2:].strip()
            width += 2
        if step is None:
            continue
        key, separator, value = body.partition(":")
        key = key.strip()
        if not separator or key not in ("uses", "run", "if"):
            continue
        value = value.strip()
        if key == "run" and value[:1] in ("|", ">"):
            step["run"] = ""
            block = width
        else:
            step[key] = yaml_value(value) if key != "run" else value
    return jobs


def workflow_step(text, name):
    """`(start, end, indent)` of the step `- name: <name>` in a workflow's text, or None when it has none.

    The step runs from its `- name:` line to the line before the next one at its indent or less: the next step, or
    the comment above it.
    """
    match = re.search(rf"^(?P<indent>[ \t]*)- name: {re.escape(name)}\n", text, re.MULTILINE)
    if match is None:
        return None
    indent = match["indent"]
    end = match.end()
    for line in text[end:].splitlines(keepends=True):
        body = line.lstrip(" \t")
        if body.strip() and len(line) - len(body) <= len(indent):
            break
        end += len(line)
    return match.start(), end, indent


def tag_step(indent):
    """Core's own manual-release tag step, reindented to `indent`."""
    text = (CORE_ROOT / RELEASE_WORKFLOW).read_text(encoding="utf-8")
    start, end, own = workflow_step(text, TAG_STEP)
    lines = text[start:end].splitlines(keepends=True)
    return "".join(indent + line[len(own) :] if line.startswith(own) else line for line in lines)


def check_tag_step(repo, branch, local):
    """A consumer's manual release tags its commit with core's own step, byte for byte once reindented."""
    path = consumer_path(repo, RELEASE_WORKFLOW)
    data, error = read_consumer(repo, path, branch, local)
    if error:
        return [f"{repo}: {path}: {error}"]
    if data is None:
        return []
    text = data.decode("utf-8", "replace")
    found = workflow_step(text, TAG_STEP)
    if found is None:
        return [f"{repo}: {path}: no `- name: {TAG_STEP}` step; run tools/sync_consumers.py"]
    start, end, indent = found
    if text[start:end] != tag_step(indent):
        return [f"{repo}: {path}: `{TAG_STEP}` differs from core's; run tools/sync_consumers.py"]
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


def check_consumer_gates(repo, branch, local):
    """Read only the consumer-owned typecheck gate, locally or remotely."""
    if repo not in VENDORED.get("tools/lint_client_calls.py", ()):
        return []
    path = consumer_path(repo, "tools/typecheck.sh")
    data, error = read_consumer(repo, path, branch, local)
    if error:
        return [f"{repo}: {path}: {error}"]
    return [
        f"{repo}: {failure}"
        for failure in check_gate_invocations(repo, data.decode("utf-8", "replace") if data is not None else "")
    ]


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
        failures += check_tag_step(repo, arguments.branch, arguments.local)
    # Any consumer's own CI may run the package check; each such step must be authenticated, whether or not the addon
    # publishes a visual-proof workflow.
    for repo in repos:
        failures += check_consumer_gates(repo, arguments.branch, arguments.local)
        failures += check_embed(repo, arguments.branch, arguments.local)

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
