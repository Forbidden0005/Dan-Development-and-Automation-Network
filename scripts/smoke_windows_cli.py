#!/usr/bin/env python3
"""Run a packaged CLI smoke test against the built DanCLI executable."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_windows_build import expected_executable


def _run_cli_smoke(executable: Path) -> tuple[int, str]:
    command = [str(executable), "--doctor", "--target", "cli"]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    output = completed.stdout + completed.stderr
    return completed.returncode, output


def validate_cli_smoke_output(returncode: int, output: str) -> None:
    if returncode != 0:
        raise RuntimeError(f"Packaged CLI smoke test failed with exit code {returncode}.\n{output}")
    if "Startup blockers:     0" not in output:
        raise RuntimeError("Packaged CLI smoke test did not report zero startup blockers.\n" + output)
    if "pyinstaller" in output.lower():
        raise RuntimeError("Packaged CLI smoke test leaked build-only dependency guidance.\n" + output)
    if "Imported packages are not declared in requirements: scripts" in output:
        raise RuntimeError("Packaged CLI smoke test misclassified local scripts imports.\n" + output)


def main() -> int:
    executable = expected_executable("cli")
    returncode, output = _run_cli_smoke(executable)
    validate_cli_smoke_output(returncode, output)
    print("cli: packaged smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
