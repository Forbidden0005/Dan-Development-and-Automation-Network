#!/usr/bin/env python3
"""Verify the expected shape of a packaged Dan Windows build."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = ROOT / "dist" / "windows"

TARGET_LAYOUTS = {
    "gui": ("Dan", "Dan.exe"),
    "cli": ("DanCLI", "DanCLI.exe"),
}


def expected_executable(target: str) -> Path:
    try:
        folder_name, executable_name = TARGET_LAYOUTS[target]
    except KeyError as exc:
        raise ValueError(f"Unsupported target: {target}") from exc
    return DIST_ROOT / folder_name / folder_name / executable_name


def verify_target(target: str) -> str:
    executable = expected_executable(target)
    package_root = executable.parent

    if not package_root.exists():
        raise FileNotFoundError(f"Missing packaged directory: {package_root}")
    if not executable.exists():
        raise FileNotFoundError(f"Missing packaged executable: {executable}")

    internal_dir = package_root / "_internal"
    if not internal_dir.exists():
        raise FileNotFoundError(f"Missing PyInstaller support directory: {internal_dir}")

    size_mb = round(executable.stat().st_size / (1024 * 1024), 2)
    return f"{target}: verified {executable.name} ({size_mb} MB)"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the shape of a Dan Windows package.")
    parser.add_argument(
        "--target",
        choices=sorted(TARGET_LAYOUTS.keys()),
        default="gui",
        help="Packaged target to verify.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(verify_target(args.target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
