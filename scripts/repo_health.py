#!/usr/bin/env python3
"""Run the standard repository health audit for Dan."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import code_tools


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Dan's repo health audit.")
    parser.add_argument("path", nargs="?", default=str(ROOT), help="Project root to audit")
    parser.add_argument("--provider", default="", help="Provider to validate explicitly")
    parser.add_argument("--timeout", type=int, default=120, help="Per-check timeout in seconds")
    args = parser.parse_args()

    print(code_tools.repo_health(args.path, provider=args.provider, timeout=args.timeout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
