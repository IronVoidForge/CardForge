from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence


def run(command: Sequence[str], *, required: bool = True) -> int:
    print("$ " + " ".join(command), flush=True)
    completed = subprocess.run(command, check=False)
    if completed.returncode and required:
        raise SystemExit(completed.returncode)
    return int(completed.returncode)


def run_optional(command: Sequence[str], binary: str, *, strict: bool) -> None:
    if shutil.which(binary) is None:
        message = f"Skipping {' '.join(command)} because {binary!r} is not installed."
        if strict:
            print(message)
            raise SystemExit(127)
        print(message)
        return
    run(command)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run CardForge quality gates.")
    parser.add_argument("--strict", action="store_true", help="Require optional tools such as ruff to be installed.")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args(argv)

    run([sys.executable, "scripts/check_format.py"])
    run([sys.executable, "-m", "compileall", "-q", "src", "tests"])
    run_optional(["ruff", "check", "src", "tests", "scripts"], "ruff", strict=args.strict)
    if not args.skip_tests:
        command = ["bash", "-lc", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider tests"]
        run(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
