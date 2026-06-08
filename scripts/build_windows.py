#!/usr/bin/env python3
"""Build Dan for Windows using a repeatable PyInstaller workflow."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = ROOT / "dist" / "windows"
WORK_ROOT = ROOT / "build" / "pyinstaller"
SPEC_ROOT = ROOT / "build" / "spec"

GUI_TARGET = "gui"
CLI_TARGET = "cli"
ALL_TARGET = "all"

CORE_PYINSTALLER_ARGS = [
    "--noconfirm",
    "--clean",
    "--onedir",
    "--collect-all",
    "customtkinter",
]

OPTIONAL_IMPORTS = {
    "vision": ["image_tools"],
    "ml": ["ml_tools"],
}

DEFAULT_EXCLUDES = {
    "vision": ["cv2", "easyocr", "image_tools", "librosa", "sounddevice"],
    "ml": ["ml_tools", "pandas", "scipy", "sklearn", "tensorflow", "torch", "transformers"],
}


def entrypoint_for(target: str) -> Path:
    if target == GUI_TARGET:
        return ROOT / "dan_gui_modern.py"
    if target == CLI_TARGET:
        return ROOT / "Dan.py"
    raise ValueError(f"Unsupported target: {target}")


def app_name_for(target: str) -> str:
    if target == GUI_TARGET:
        return "Dan"
    if target == CLI_TARGET:
        return "DanCLI"
    raise ValueError(f"Unsupported target: {target}")


def build_command(
    target: str,
    *,
    include_vision: bool = False,
    include_ml: bool = False,
) -> list[str]:
    entrypoint = entrypoint_for(target)
    app_name = app_name_for(target)
    target_dist = DIST_ROOT / app_name
    target_work = WORK_ROOT / app_name

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        *CORE_PYINSTALLER_ARGS,
        "--name",
        app_name,
        "--distpath",
        str(target_dist),
        "--workpath",
        str(target_work),
        "--specpath",
        str(SPEC_ROOT),
        "--paths",
        str(ROOT),
    ]

    if target == GUI_TARGET:
        command.append("--windowed")
    else:
        command.append("--console")

    excluded_modules: list[str] = []
    if not include_vision:
        excluded_modules.extend(DEFAULT_EXCLUDES["vision"])
    if not include_ml:
        excluded_modules.extend(DEFAULT_EXCLUDES["ml"])

    for module_name in excluded_modules:
        command.extend(["--exclude-module", module_name])

    if include_vision:
        for hidden_import in OPTIONAL_IMPORTS["vision"]:
            command.extend(["--hidden-import", hidden_import])
    if include_ml:
        for hidden_import in OPTIONAL_IMPORTS["ml"]:
            command.extend(["--hidden-import", hidden_import])

    command.append(str(entrypoint))
    return command


def run_build(command: list[str], *, dry_run: bool) -> int:
    print("Build command:")
    print(" ".join(command))

    if dry_run:
        print("Dry run only. Build was not executed.")
        return 0

    SPEC_ROOT.mkdir(parents=True, exist_ok=True)
    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(command, cwd=str(ROOT), check=False)
    return completed.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Dan for Windows with PyInstaller in a repeatable portable layout."
    )
    parser.add_argument(
        "--target",
        choices=[GUI_TARGET, CLI_TARGET, ALL_TARGET],
        default=GUI_TARGET,
        help="Which entry point to package. 'gui' is the supported desktop shell.",
    )
    parser.add_argument(
        "--with-vision",
        action="store_true",
        help="Bundle the optional vision tool module if its runtime dependencies are installed.",
    )
    parser.add_argument(
        "--with-ml",
        action="store_true",
        help="Bundle the optional ML tool module if its runtime dependencies are installed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the PyInstaller command(s) without executing them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = [args.target] if args.target != ALL_TARGET else [GUI_TARGET, CLI_TARGET]

    for target in targets:
        exit_code = run_build(
            build_command(
                target,
                include_vision=args.with_vision,
                include_ml=args.with_ml,
            ),
            dry_run=args.dry_run,
        )
        if exit_code != 0:
            return exit_code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
