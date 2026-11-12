"""Verify human-recorded in-game visual proof for runtime UI changes."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

PROOF = Path(".visual-proof.json")
SHA = re.compile(r"/raw/[0-9a-f]{40}/", re.IGNORECASE)
DOC_PREFIXES = ("docs/", ".github/", "tools/", "tests/")


def changed_files(base: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"], capture_output=True, text=True, check=True
    )
    return [line for line in result.stdout.splitlines() if line]


def requires_proof(paths: list[str]) -> bool:
    return any(not path.startswith(DOC_PREFIXES) and path != PROOF.as_posix() for path in paths)


def input_digest(root: Path) -> str:
    toc = root / "ForeverCore.toc"
    files = [toc]
    for line in toc.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            candidate = root / line.replace("\\", "/")
            if candidate.is_file():
                files.append(candidate)
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
        return hashlib.sha256(response.read()).hexdigest()


def verify(root: Path, paths: list[str], proof_path: Path = PROOF) -> list[str]:
    if not requires_proof(paths):
        return []
    if not proof_path.is_file():
        return [f"{proof_path}: missing for runtime UI changes"]
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{proof_path}: invalid JSON: {error}"]
    problems = []
    if proof.get("input_digest") != input_digest(root):
        problems.append("visual proof input_digest does not match the runtime TOC graph and Core pin")
    if not proof.get("client_build") or not proof.get("candidate"):
        problems.append("visual proof needs client_build and candidate")
    flows = proof.get("flows")
    if not isinstance(flows, list) or not flows or any(flow.get("result") != "pass" for flow in flows):
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
