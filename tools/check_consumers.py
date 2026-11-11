"""Check every consuming Forever addon's copy of core's development tooling against this repo.

Each consumer carries a byte-identical copy of the files tools/check_core_shared.py lists in VENDORED: the project
rules and the dead-code gate. This gate is what stops the copies drifting: it compares each repo's main branch (or a
local checkout) with this repo's copy and names every mismatch. Consumers are compared from this repo (a private one
needs `GH_TOKEN` to be readable, and is otherwise reported as missing rather than crashing); `--local` supports an
offline check against local clones.

Once per consumer, deduplicated from VENDORED, two more checks follow the copies, because a consumer's own config
drifts the same way:

- `tools/forever-core.txt`, when the consumer carries it, must name core's latest published release tag, so the
  addon's specs and CI test against the core a player runs. The tag comes from the GitHub API, read with the same
  token as the files; with `--local` it is this checkout's newest `v*` tag from `git describe`.
- `.pkgmeta`, when the consumer's root TOC lists ForeverCore in `## Dependencies`, must ship ForeverCore inside the
  addon's own zip, because a store update does not reliably deliver a required dependency: CurseForge can skip it on
  an update, and the packager sends Wago no dependency list at all. So `externals:` must download
  `ForeverCore-<pin>-forever.zip` from the release the consumer's `tools/forever-core.txt` names, `move-folders:` must
  place it at `ForeverCore` beside the addon's own folder, and `required-dependencies:` must not list `forevercore`, so
  one owner holds the folder.
- The same root TOC must carry `## X-Forever-Core: <pin>`, the tag the bundled folder is, so a player's other Forever
  addon can name a sibling whose core is out of date. It must agree with `tools/forever-core.txt`.

Those three copies are compared by `forever_tools.core_pin`, the same function the vendored package check runs in each
consumer, so this gate and a consumer's own CI agree on the rule.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from check_core_shared import CONSUMER_ROOT, VENDORED, source

CORE_ROOT = Path(__file__).resolve().parent.parent
TOOLING = CORE_ROOT / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))

from forever_tools import core_pin  # noqa: E402

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


def latest_tag(local):
    """Core's newest published release tag, or None when it cannot be read and the pin check must be skipped."""
    if local:
        return local_latest_tag()
    try:
        with urllib.request.urlopen(
            authorized("https://api.github.com/repos/cjber/forever-core/releases/latest"), timeout=60
        ) as response:
            return json.loads(response.read())["tag_name"]
    except (OSError, urllib.error.URLError, TimeoutError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"Could not read forever-core's latest release ({error}); skipping the pin check.")
        return None


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
        print(f"Could not read this checkout's newest v* tag ({shown.stderr.strip()}); skipping the pin check.")
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


def requires_core(toc):
    """Whether a TOC's `## Dependencies` header lists ForeverCore."""
    for line in toc.decode("utf-8", "replace").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## dependencies:"):
            return FOREVER_CORE in (name.strip().lower() for name in stripped.split(":", 1)[1].split(","))
    return False


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
    """Every consumer's pin names core's latest release."""
    failures = []
    if not pins:
        return failures
    latest = latest_tag(local)
    if latest is None:
        return failures
    for repo in sorted(pins):
        pin = pins[repo]
        if pin != latest:
            failures.append(
                f"{repo}: {consumer_path(repo, PIN_PATH)}: pin {pin or '(empty)'}, core's latest release is {latest}"
            )
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
    if toc is None or not requires_core(toc):
        return []
    package = pkgmeta_field(pkgmeta, "package-as")
    toc_path = consumer_path(repo, f"{package}.toc")
    blocks = pkgmeta_blocks(pkgmeta)
    failures = [
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
    if FOREVER_CORE in block_entries(blocks.get("required-dependencies", [])):
        failures.append(
            f"{repo}: {path}: `required-dependencies:` lists `- forevercore`, but the zip ships ForeverCore;"
            " one owner for the folder"
        )
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--branch", default="main", help="the consumers' branch to compare (default: main)")
    parser.add_argument("--local", type=Path, help="compare checkouts under this directory instead of GitHub")
    arguments = parser.parse_args(argv)

    failures = []
    comparisons = 0
    for path, consumers in VENDORED.items():
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
