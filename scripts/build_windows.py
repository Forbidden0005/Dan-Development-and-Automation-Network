#!/usr/bin/env python3
"""Build Dan for Windows using a repeatable PyInstaller workflow."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = ROOT / "dist" / "windows"
WORK_ROOT = ROOT / "build" / "pyinstaller"
SPEC_ROOT = ROOT / "build" / "spec"
INSTALLER_DIR = ROOT / "installer"
INSTALLER_SCRIPT = INSTALLER_DIR / "Dan.iss"
INSTALLER_OUT = ROOT / "dist" / "installer"
CONFIG_FILE = ROOT / "config.py"
PYPROJECT_FILE = ROOT / "pyproject.toml"
DEFAULT_TIMESTAMP_URL = "http://timestamp.digicert.com"

# Common Windows SDK locations for signtool.exe.
SIGNTOOL_SEARCH_ROOTS = [
    Path(r"C:\Program Files (x86)\Windows Kits\10\bin"),
    Path(r"C:\Program Files\Windows Kits\10\bin"),
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
    "dev": ["IPython", "black", "ipykernel", "jedi", "mypy", "parso", "prompt_toolkit", "pytest", "_pytest"],
}

CONFIG_VERSION_PATTERN = re.compile(r'^APP_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)
INSTALLER_VERSION_PATTERN = re.compile(r'^#define\s+MyAppVersion\s+"([^"]+)"', re.MULTILINE)


class SigningConfig:
    def __init__(
        self,
        *,
        sign_tool: Path,
        certificate_file: Path,
        certificate_password: str,
        timestamp_url: str,
    ) -> None:
        self.sign_tool = sign_tool
        self.certificate_file = certificate_file
        self.certificate_password = certificate_password
        self.timestamp_url = timestamp_url


def read_release_versions(
    *,
    config_file: Path = CONFIG_FILE,
    pyproject_file: Path = PYPROJECT_FILE,
    installer_script: Path = INSTALLER_SCRIPT,
) -> dict[str, str]:
    config_text = config_file.read_text(encoding="utf-8")
    config_match = CONFIG_VERSION_PATTERN.search(config_text)
    if not config_match:
        raise ValueError(f"Could not find APP_VERSION in {config_file}")

    pyproject_data = tomllib.loads(pyproject_file.read_text(encoding="utf-8"))
    pyproject_version = pyproject_data.get("project", {}).get("version")
    if not pyproject_version:
        raise ValueError(f"Could not find [project].version in {pyproject_file}")

    installer_text = installer_script.read_text(encoding="utf-8")
    installer_match = INSTALLER_VERSION_PATTERN.search(installer_text)
    if not installer_match:
        raise ValueError(f"Could not find MyAppVersion in {installer_script}")

    return {
        "config.py": config_match.group(1),
        "pyproject.toml": pyproject_version,
        "installer/Dan.iss": installer_match.group(1),
    }


def validate_release_versions(
    *,
    config_file: Path = CONFIG_FILE,
    pyproject_file: Path = PYPROJECT_FILE,
    installer_script: Path = INSTALLER_SCRIPT,
) -> str:
    versions = read_release_versions(
        config_file=config_file,
        pyproject_file=pyproject_file,
        installer_script=installer_script,
    )
    unique_versions = set(versions.values())
    if len(unique_versions) != 1:
        details = ", ".join(f"{name}={version}" for name, version in versions.items())
        raise ValueError(
            "Release version mismatch. Keep config.py, pyproject.toml, and "
            f"installer/Dan.iss synchronized: {details}"
        )
    return next(iter(unique_versions))


def validate_expected_version(actual_version: str, expected_version: str | None) -> None:
    if expected_version is None:
        return
    if actual_version != expected_version:
        raise ValueError(
            "Release version mismatch against expected version. "
            f"Expected {expected_version}, but repo sources resolved to {actual_version}."
        )


def find_signtool() -> Path | None:
    found = shutil.which("signtool") or shutil.which("SignTool")
    if found:
        return Path(found)

    candidates: list[Path] = []
    for root in SIGNTOOL_SEARCH_ROOTS:
        if root.exists():
            candidates.extend(sorted(root.glob(r"*\x64\signtool.exe"), reverse=True))
    return candidates[0] if candidates else None


def iscc_candidates() -> list[Path]:
    candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 5\ISCC.exe"),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        candidates.extend(
            [
                Path(local_app_data) / "Programs" / "Inno Setup 6" / "ISCC.exe",
                Path(local_app_data) / "Programs" / "Inno Setup 5" / "ISCC.exe",
            ]
        )
    return candidates


def resolve_signing_config(
    *,
    enabled: bool,
    sign_tool: str | None = None,
    certificate_file: str | None = None,
    certificate_password: str | None = None,
    timestamp_url: str | None = None,
) -> SigningConfig | None:
    if not enabled:
        return None

    sign_tool_path = Path(sign_tool).resolve() if sign_tool else find_signtool()
    if sign_tool_path is None or not sign_tool_path.exists():
        raise ValueError(
            "Code signing requested, but signtool.exe was not found. "
            "Install the Windows SDK signing tools or pass --sign-tool."
        )

    cert_value = certificate_file or os.environ.get("DAN_SIGN_PFX")
    if not cert_value:
        raise ValueError(
            "Code signing requested, but no certificate was configured. "
            "Set DAN_SIGN_PFX or pass --sign-cert."
        )
    cert_path = Path(cert_value).resolve()
    if not cert_path.exists():
        raise ValueError(f"Configured signing certificate was not found: {cert_path}")

    password_value = certificate_password or os.environ.get("DAN_SIGN_PFX_PASSWORD")
    if not password_value:
        raise ValueError(
            "Code signing requested, but no certificate password was configured. "
            "Set DAN_SIGN_PFX_PASSWORD or pass --sign-password."
        )

    timestamp_value = (
        timestamp_url
        or os.environ.get("DAN_SIGN_TIMESTAMP_URL")
        or DEFAULT_TIMESTAMP_URL
    )
    return SigningConfig(
        sign_tool=sign_tool_path,
        certificate_file=cert_path,
        certificate_password=password_value,
        timestamp_url=timestamp_value,
    )


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
        # Wire in the application icon if it exists.
        # assets/README.md documents the format requirements.
        icon_path = ROOT / "assets" / "dan_icon.ico"
        if icon_path.exists():
            command.extend(["--icon", str(icon_path)])
    else:
        command.append("--console")

    excluded_modules: list[str] = []
    if not include_vision:
        excluded_modules.extend(DEFAULT_EXCLUDES["vision"])
    if not include_ml:
        excluded_modules.extend(DEFAULT_EXCLUDES["ml"])
    excluded_modules.extend(DEFAULT_EXCLUDES["dev"])

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


def bundled_executable_for(target: str) -> Path:
    app_name = app_name_for(target)
    return DIST_ROOT / app_name / app_name / f"{app_name}.exe"


def expected_installer_artifact(release_version: str) -> Path:
    return INSTALLER_OUT / f"Dan-{release_version}-setup.exe"


def latest_installer_artifact() -> Path | None:
    artifacts = sorted(INSTALLER_OUT.glob("Dan-*-setup.exe"))
    return artifacts[-1] if artifacts else None


def signing_command(signing: SigningConfig, artifact: Path) -> list[str]:
    return [
        str(signing.sign_tool),
        "sign",
        "/fd",
        "SHA256",
        "/td",
        "SHA256",
        "/f",
        str(signing.certificate_file),
        "/p",
        signing.certificate_password,
        "/tr",
        signing.timestamp_url,
        str(artifact),
    ]


def sign_artifact(artifact: Path, *, signing: SigningConfig, dry_run: bool) -> int:
    command = signing_command(signing, artifact)
    display_command = command.copy()
    if "/p" in display_command:
        password_index = display_command.index("/p") + 1
        if password_index < len(display_command):
            display_command[password_index] = "******"
    print("Signing command:")
    print(" ".join(display_command))

    if dry_run:
        print("Dry run only. Artifact was not signed.")
        return 0

    completed = subprocess.run(command, cwd=str(ROOT), check=False)
    return completed.returncode


def run_build(
    command: list[str],
    *,
    target: str,
    dry_run: bool,
    signing: SigningConfig | None,
) -> int:
    print("Build command:")
    print(" ".join(command))

    if dry_run:
        print("Dry run only. Build was not executed.")
        if signing is not None:
            return sign_artifact(
                bundled_executable_for(target),
                signing=signing,
                dry_run=True,
            )
        return 0

    SPEC_ROOT.mkdir(parents=True, exist_ok=True)
    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(command, cwd=str(ROOT), check=False)
    if completed.returncode != 0:
        return completed.returncode

    if signing is not None:
        artifact = bundled_executable_for(target)
        if not artifact.exists() and not dry_run:
            print(f"Built executable not found for signing: {artifact}")
            return 1
        return sign_artifact(artifact, signing=signing, dry_run=dry_run)
    return 0


def find_iscc() -> Path | None:
    """Return the path to ISCC.exe if Inno Setup is installed, or None."""
    for candidate in iscc_candidates():
        if candidate.exists():
            return candidate
    # Also check PATH
    found = shutil.which("iscc") or shutil.which("ISCC")
    return Path(found) if found else None


def build_installer(
    *,
    dry_run: bool,
    signing: SigningConfig | None,
    release_version: str,
) -> int:
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
        if signing is not None:
            return sign_artifact(
                expected_installer_artifact(release_version),
                signing=signing,
                dry_run=True,
            )
        return 0

    completed = subprocess.run(command, cwd=str(ROOT), check=False)
    if completed.returncode != 0:
        return completed.returncode

    artifact = latest_installer_artifact()
    if artifact is not None:
        print(f"\nInstaller created: {artifact}")
    if signing is not None:
        if artifact is None and not dry_run:
            print("Installer signing requested, but no installer artifact was produced.")
            return 1
        return sign_artifact(
            artifact or (INSTALLER_OUT / "Dan-unknown-setup.exe"),
            signing=signing,
            dry_run=dry_run,
        )
    return 0


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
    parser.add_argument(
        "--expect-version",
        help="Optional expected release version. Build fails if the synchronized repo version does not match it.",
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help=(
            "After building artifacts, sign the GUI exe, CLI exe, and/or installer with signtool. "
            "Reads DAN_SIGN_PFX, DAN_SIGN_PFX_PASSWORD, and optional DAN_SIGN_TIMESTAMP_URL by default."
        ),
    )
    parser.add_argument(
        "--sign-tool",
        help="Optional explicit path to signtool.exe. Default: auto-discover from PATH or Windows SDK.",
    )
    parser.add_argument(
        "--sign-cert",
        help="Optional explicit path to the .pfx code-signing certificate. Default: DAN_SIGN_PFX.",
    )
    parser.add_argument(
        "--sign-password",
        help="Optional explicit password for the .pfx certificate. Default: DAN_SIGN_PFX_PASSWORD.",
    )
    parser.add_argument(
        "--sign-timestamp-url",
        help=f"Optional RFC3161 timestamp URL. Default: DAN_SIGN_TIMESTAMP_URL or {DEFAULT_TIMESTAMP_URL}.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        release_version = validate_release_versions()
    except ValueError as exc:
        print(f"Release version check failed: {exc}")
        return 1
    try:
        validate_expected_version(release_version, args.expect_version)
    except ValueError as exc:
        print(f"Expected version check failed: {exc}")
        return 1
    try:
        signing = resolve_signing_config(
            enabled=args.sign,
            sign_tool=args.sign_tool,
            certificate_file=args.sign_cert,
            certificate_password=args.sign_password,
            timestamp_url=args.sign_timestamp_url,
        )
    except ValueError as exc:
        print(f"Signing configuration failed: {exc}")
        return 1

    print(f"Release version verified: {release_version}")
    if signing is not None:
        print(f"Code signing enabled: {signing.sign_tool}")

    if not args.installer_only:
        targets = [args.target] if args.target != ALL_TARGET else [GUI_TARGET, CLI_TARGET]

        for target in targets:
            exit_code = run_build(
                build_command(
                    target,
                    include_vision=args.with_vision,
                    include_ml=args.with_ml,
                ),
                target=target,
                dry_run=args.dry_run,
                signing=signing,
            )
            if exit_code != 0:
                return exit_code

    if args.installer or args.installer_only:
        exit_code = build_installer(
            dry_run=args.dry_run,
            signing=signing,
            release_version=release_version,
        )
        if exit_code != 0:
            return exit_code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
