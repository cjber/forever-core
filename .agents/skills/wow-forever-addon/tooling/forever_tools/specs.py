"""Run every `tests/*_spec.lua` (or another `--pattern`) under LuaJIT in parallel and report each one in glob order.

Specs are independent processes, so they run on every core at once. Each spec's output is held until it finishes and
printed in glob order with its time, so the log reads as a serial run would. Every spec runs even after one fails; the
exit status is 1 when any failed, and the failures are named at the end. A spec that shares a fixture with others
must create it atomically (write a unique temporary file, then rename), since two specs may create it at once.

    python3 -m tools.forever_tools.specs            # from the repository root
    python3 -m tools.forever_tools.specs --jobs 1   # one at a time
    python3 -m tools.forever_tools.specs --pattern 'tests/sim/*_spec.lua'
"""

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PATTERN = "tests/*_spec.lua"


def run(root: Path, interpreter: str, spec: str) -> tuple[int, str, float]:
    started = time.monotonic()
    done = subprocess.run(
        [interpreter, spec], cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    output = done.stdout.decode("utf-8", errors="replace")
    return done.returncode, output, time.monotonic() - started


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="specs at once (default: every core)")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="the repository root (default: here)")
    parser.add_argument("--pattern", default=PATTERN, help=f"the specs, relative to the root (default: {PATTERN})")
    parser.add_argument("--interpreter", default="luajit", help="what runs each spec (default: luajit)")
    args = parser.parse_args(argv)
    specs = sorted(str(path.relative_to(args.root)) for path in args.root.glob(args.pattern))
    if not specs:
        print(f"No specs match {args.pattern} under {args.root}", file=sys.stderr)
        return 1
    started = time.monotonic()
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = [pool.submit(run, args.root, args.interpreter, spec) for spec in specs]
        for spec, result in zip(specs, results, strict=True):
            code, output, seconds = result.result()
            status = "ok" if code == 0 else f"FAILED (exit {code})"
            print(f"== {spec} {status} in {seconds:.1f}s", flush=True)
            if output:
                print(output, end="" if output.endswith("\n") else "\n", flush=True)
            if code != 0:
                failed.append(spec)
    elapsed = time.monotonic() - started
    print(f"{len(specs)} specs, {len(failed)} failed, {elapsed:.1f}s with {max(1, args.jobs)} at once")
    if failed:
        print("Failed:\n" + "\n".join(f"  {spec}" for spec in failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
