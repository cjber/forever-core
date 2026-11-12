"""Verify human-recorded in-game visual proof for runtime UI changes."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from forever_tools import toc

PROOF = Path(".visual-proof.json")
SHA = re.compile(r"/raw/[0-9a-f]{40}/", re.IGNORECASE)
NON_RUNTIME_PREFIXES = ("docs/", ".github/", "tools/", "tests/", ".agents/", "CHANGELOG.md", "THIRD_PARTY")


def changed_files(base: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"], capture_output=True, text=True, check=True
    )
    return [line for line in result.stdout.splitlines() if line]


def requires_proof(root: Path, paths: list[str]) -> bool:
    graph = {path.relative_to(root).as_posix() for path in runtime_files(root)}
    return any(
        path in graph
        or path == "tools/forever-core.txt"
        or (path.startswith("media/") and path.endswith((".png", ".tga")))
        or (path.endswith((".lua", ".xml", ".toc")) and not path.startswith(NON_RUNTIME_PREFIXES))
        for path in paths
        if path != PROOF.as_posix()
    )


def runtime_files(root: Path) -> list[Path]:
    files = []
    for toc_path in toc.toc_files(root):
        files.extend(toc.loaded_files(toc_path, root))
    return sorted(set(files))


def input_digest(root: Path) -> str:
    files = runtime_files(root)
    pin = root / "tools/forever-core.txt"
    if pin.is_file():
        files.append(pin)
    digest = hashlib.sha256()
    for path in sorted(set(files), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def image_hash(url: str) -> str:
    if not SHA.search(url):
        raise ValueError(f"image URL is not pinned to a full commit SHA: {url}")
    request = Request(url, headers={"User-Agent": "forever-visual-proof"})
    with urlopen(request, timeout=20) as response:
        data = response.read()
        if response.status != 200 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(f"visual proof image is not a successful PNG: {url}")
        return hashlib.sha256(data).hexdigest()


def verify(root: Path, paths: list[str], proof_path: Path = PROOF) -> list[str]:
    if not requires_proof(root, paths):
        return []
    if not proof_path.is_file():
        return [f"{proof_path}: missing for runtime UI changes"]
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{proof_path}: invalid JSON: {error}"]
    if not isinstance(proof, dict):
        return [f"{proof_path}: top-level proof must be an object"]
    problems = []
    runtime = {path.relative_to(root).as_posix() for path in runtime_files(root)}
    changed_runtime = runtime.intersection(paths)
    if changed_runtime and proof.get("input_digest") != input_digest(root):
        problems.append("visual proof input_digest does not match the runtime TOC graph and Core pin")
    if not proof.get("client_build"):
        problems.append("visual proof needs client_build")
    if not isinstance(proof.get("candidate"), str) or not re.fullmatch(r"[0-9a-f]{64}", proof["candidate"]):
        problems.append("visual proof candidate must be the installed runtime SHA-256")
    if proof.get("runtime_sha256") != proof.get("input_digest"):
        problems.append("visual proof runtime_sha256 must equal the runtime input digest")
    flows = proof.get("flows")
    if (
        not isinstance(flows, list)
        or not flows
        or any(
            not isinstance(flow, dict) or not flow.get("name") or not flow.get("steps") or flow.get("result") != "pass"
            for flow in flows
        )
    ):
        problems.append("visual proof needs at least one passing flow")
    images = proof.get("images")
    if not isinstance(images, list) or not images:
        problems.append("visual proof needs full-SHA image evidence")
    else:
        for image in images:
            if not isinstance(image, dict) or not image.get("url") or not image.get("sha256"):
                problems.append("visual proof has malformed image evidence")
                continue
            try:
                actual = image_hash(image["url"])
                if actual != image["sha256"]:
                    problems.append(f"visual proof image hash mismatch: {image['url']}")
            except (OSError, ValueError) as error:
                problems.append(str(error))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args()
    problems = verify(Path("."), changed_files(args.base))
    if problems:
        print("\n".join(problems))
        return 1
    print("visual proof: not required or valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
