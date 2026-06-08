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
INSTALLER_DIR = ROOT / "installer"
INSTALLER_SCRIPT = INSTALLER_DIR / "Dan.iss"
INSTALLER_OUT = ROOT / "dist" / "installer"

# Common Inno Setup install locations on Windows.
ISCC_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 5\ISCC.exe"),
]

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


def find_iscc() -> Path | None:
    """Return the path to ISCC.exe if Inno Setup is installed, or None."""
    for candidate in ISCC_CANDIDATES:
        if candidate.exists():
            return candidate
    # Also check PATH
    import shutil
    found = shutil.which("iscc") or shutil.which("ISCC")
    return Path(found) if found else None


def build_installer(*, dry_run: bool) -> int:
    """Compile the Inno Setup script to produce a Windows installer .exe.

    Requires Inno Setup 6.x to be installed.  Downloads available at:
    https://jrsoftware.org/isdl.php

    The GUI PyInstaller bundle (dist\\windows\\Dan\\) must exist before
    calling this.  Run ``python scripts/build_windows.py --target gui``
    first if it does not.
    """
    iscc = find_iscc()
    if iscc is None:
        print(
            "Inno Setup (ISCC.exe) not found.  Install it from "
            "https://jrsoftware.org/isdl.php and re-run with --installer."
        )
        return 1

    if not INSTALLER_SCRIPT.exists():
        print(f"Installer script not found: {INSTALLER_SCRIPT}")
        return 1

    gui_bundle = DIST_ROOT / "Dan"
    if not gui_bundle.exists() and not dry_run:
        print(
            f"GUI bundle not found at {gui_bundle}.\n"
            "Run 'python scripts/build_windows.py --target gui' first."
        )
        return 1

    INSTALLER_OUT.mkdir(parents=True, exist_ok=True)
    command = [str(iscc), str(INSTALLER_SCRIPT)]

    print("Installer command:")
    print(" ".join(command))

    if dry_run:
        print("Dry run only. Installer was not compiled.")
        return 0

    completed = subprocess.run(command, cwd=str(ROOT), check=False)
    if completed.returncode == 0:
        artifacts = list(INSTALLER_OUT.glob("Dan-*-setup.exe"))
        if artifacts:
            print(f"\nInstaller created: {artifacts[-1]}")
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
        "--installer",
        action="store_true",
        help=(
            "After building the GUI bundle, compile the Inno Setup installer script "
            "at installer/Dan.iss to produce dist/installer/Dan-<version>-setup.exe. "
            "Requires Inno Setup 6.x (https://jrsoftware.org/isdl.php)."
        ),
    )
    parser.add_argument(
        "--installer-only",
        action="store_true",
        help="Skip the PyInstaller build and only compile the Inno Setup script.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.installer_only:
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

    if args.installer or args.installer_only:
        exit_code = build_installer(dry_run=args.dry_run)
        if exit_code != 0:
            return exit_code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
