#!/usr/bin/env python3
"""Verify local release-readiness gates for Dan."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_windows
from scripts import release_artifacts
from scripts.smoke_windows_cli import _run_cli_smoke, validate_cli_smoke_output
from scripts.verify_windows_build import expected_executable, verify_target


@dataclass
class ReadinessCheck:
    name: str
    ok: bool
    detail: str
    blocker: bool = True
    remediation: str | None = None


def _check_release_version_sync() -> ReadinessCheck:
    try:
        version = build_windows.validate_release_versions()
    except Exception as exc:
        return ReadinessCheck("version_sync", False, str(exc))
    return ReadinessCheck("version_sync", True, f"release version synchronized: {version}")


def _check_packaged_target(target: str) -> ReadinessCheck:
    try:
        detail = verify_target(target)
    except Exception as exc:
        return ReadinessCheck(f"{target}_package", False, str(exc))
    return ReadinessCheck(f"{target}_package", True, detail)


def _check_cli_smoke() -> ReadinessCheck:
    executable = expected_executable("cli")
    try:
        returncode, output = _run_cli_smoke(executable)
        validate_cli_smoke_output(returncode, output)
    except Exception as exc:
        return ReadinessCheck("cli_smoke", False, str(exc))
    return ReadinessCheck("cli_smoke", True, "packaged CLI smoke test passed")


def _check_local_installer_tool() -> ReadinessCheck:
    iscc = build_windows.find_iscc()
    if iscc is None:
        return ReadinessCheck(
            "installer_tool",
            False,
            "Inno Setup (ISCC.exe) is not installed locally; installer compilation cannot be verified on this workstation.",
            remediation="Install Inno Setup 6.x from https://jrsoftware.org/isdl.php, then rerun this check.",
        )
    return ReadinessCheck("installer_tool", True, f"found ISCC.exe at {iscc}")


def _check_installer_artifact() -> ReadinessCheck:
    try:
        release_version = build_windows.validate_release_versions()
    except Exception as exc:
        return ReadinessCheck("installer_artifact", False, str(exc))

    artifact = build_windows.expected_installer_artifact(release_version)
    if not artifact.exists():
        return ReadinessCheck(
            "installer_artifact",
            False,
            f"Windows installer artifact is missing: {artifact}",
            remediation="Run `python scripts/build_windows.py --installer-only` after the GUI bundle is built, then rerun this check.",
        )

    size_mb = artifact.stat().st_size / (1024 * 1024)
    return ReadinessCheck(
        "installer_artifact",
        True,
        f"verified installer artifact: {artifact.name} ({size_mb:.2f} MB)",
    )


def _check_release_integrity_artifacts() -> ReadinessCheck:
    try:
        version = build_windows.validate_release_versions()
        artifacts = release_artifacts.collect_release_artifacts(version)
        manifest = release_artifacts.build_release_manifest(version, artifacts)
    except Exception as exc:
        return ReadinessCheck(
            "release_integrity",
            False,
            str(exc),
            remediation="Run `python scripts/release_artifacts.py` after the GUI, CLI, and installer artifacts exist, then rerun this check.",
        )

    expected_checksums = [
        f"{entry['sha256']} *{entry['filename']}"
        for entry in manifest["artifacts"]  # type: ignore[index]
    ]

    checksum_path = release_artifacts.CHECKSUM_FILE
    manifest_path = release_artifacts.MANIFEST_FILE
    if not checksum_path.exists() or not manifest_path.exists():
        return ReadinessCheck(
            "release_integrity",
            False,
            f"Release integrity artifacts are missing: {checksum_path}, {manifest_path}",
            remediation="Run `python scripts/release_artifacts.py` to generate SHA256SUMS.txt and release-manifest.json, then rerun this check.",
        )

    checksum_lines = checksum_path.read_text(encoding="utf-8").strip().splitlines()
    if checksum_lines != expected_checksums:
        return ReadinessCheck(
            "release_integrity",
            False,
            f"Release checksum file is stale or mismatched: {checksum_path}",
            remediation="Re-run `python scripts/release_artifacts.py` after the latest build outputs are in place.",
        )

    return ReadinessCheck(
        "release_integrity",
        True,
        f"verified release integrity artifacts: {checksum_path.name}, {manifest_path.name}",
    )


def _check_local_signing_tool() -> ReadinessCheck:
    sign_tool = build_windows.find_signtool()
    if sign_tool is None:
        return ReadinessCheck(
            "signing_tool",
            False,
            "signtool.exe was not found locally; signed Windows artifacts cannot be produced on this workstation.",
            remediation=(
                "Install the Windows SDK signing tools or provide an explicit --sign-tool path when building signed artifacts."
            ),
        )
    return ReadinessCheck("signing_tool", True, f"found signtool.exe at {sign_tool}")


def _check_signing_material() -> ReadinessCheck:
    cert_path = os.environ.get("DAN_SIGN_PFX", "").strip()
    cert_password = os.environ.get("DAN_SIGN_PFX_PASSWORD", "").strip()

    if not cert_path or not cert_password:
        return ReadinessCheck(
            "signing_material",
            False,
            "Signing certificate material is not configured (DAN_SIGN_PFX / DAN_SIGN_PFX_PASSWORD).",
            remediation=(
                "Set DAN_SIGN_PFX to a local .pfx path and DAN_SIGN_PFX_PASSWORD to its password, then rerun this check."
            ),
        )

    cert_file = Path(cert_path).expanduser().resolve()
    if not cert_file.exists():
        return ReadinessCheck(
            "signing_material",
            False,
            f"Configured signing certificate file does not exist: {cert_file}",
            remediation="Point DAN_SIGN_PFX at a real .pfx file, then rerun this check.",
        )

    return ReadinessCheck("signing_material", True, f"signing certificate configured: {cert_file}")


def collect_release_readiness() -> list[ReadinessCheck]:
    return [
        _check_release_version_sync(),
        _check_packaged_target("gui"),
        _check_packaged_target("cli"),
        _check_cli_smoke(),
        _check_local_installer_tool(),
        _check_installer_artifact(),
        _check_release_integrity_artifacts(),
        _check_local_signing_tool(),
        _check_signing_material(),
    ]


def render_release_readiness(checks: list[ReadinessCheck]) -> str:
    blockers = [check for check in checks if not check.ok and check.blocker]
    lines = [
        "Dan Release Readiness",
        f"Checks:   {len(checks)}",
        f"Passing:  {sum(1 for check in checks if check.ok)}",
        f"Blocking: {len(blockers)}",
        "",
    ]

    for check in checks:
        status = "PASS" if check.ok else "BLOCK"
        lines.append(f"[{status}] {check.name}: {check.detail}")

    if blockers:
        remediation_steps = [check for check in blockers if check.remediation]
        lines.append("")
        lines.append("Release is not yet locally ready to ship.")
        if remediation_steps:
            lines.append("")
            lines.append("Recommended next steps:")
            for check in remediation_steps:
                lines.append(f"- {check.name}: {check.remediation}")
    else:
        lines.append("")
        lines.append("Release is locally ready to ship.")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Dan's local release-readiness gates.")
    return parser.parse_args()


def main() -> int:
    parse_args()
    checks = collect_release_readiness()
    print(render_release_readiness(checks))
    return 1 if any(not check.ok and check.blocker for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
