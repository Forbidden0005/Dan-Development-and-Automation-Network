#!/usr/bin/env python3
"""Generate release integrity artifacts for Dan's Windows deliverables."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_windows


RELEASE_ARTIFACTS_DIR = ROOT / "dist" / "release"
CHECKSUM_FILE = RELEASE_ARTIFACTS_DIR / "SHA256SUMS.txt"
MANIFEST_FILE = RELEASE_ARTIFACTS_DIR / "release-manifest.json"


@dataclass
class ReleaseArtifact:
    label: str
    path: Path


def sha256_for(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_release_artifacts(version: str) -> list[ReleaseArtifact]:
    return [
        ReleaseArtifact("gui_exe", build_windows.bundled_executable_for(build_windows.GUI_TARGET)),
        ReleaseArtifact("cli_exe", build_windows.bundled_executable_for(build_windows.CLI_TARGET)),
        ReleaseArtifact("installer", build_windows.expected_installer_artifact(version)),
    ]


def collect_release_artifacts(version: str) -> list[ReleaseArtifact]:
    artifacts = expected_release_artifacts(version)
    missing = [artifact for artifact in artifacts if not artifact.path.exists()]
    if missing:
        details = ", ".join(f"{artifact.label}={artifact.path}" for artifact in missing)
        raise FileNotFoundError(
            "Release artifacts are missing. Build and verify the Windows outputs first: "
            f"{details}"
        )
    return artifacts


def build_release_manifest(version: str, artifacts: list[ReleaseArtifact]) -> dict[str, object]:
    artifact_entries = []
    for artifact in artifacts:
        resolved = artifact.path.resolve()
        artifact_entries.append(
            {
                "label": artifact.label,
                "path": str(resolved),
                "filename": resolved.name,
                "size_bytes": resolved.stat().st_size,
                "sha256": sha256_for(resolved),
            }
        )

    return {
        "project": "Dan",
        "version": version,
        "generated_from": str(ROOT),
        "artifacts": artifact_entries,
    }


def write_release_artifacts(manifest: dict[str, object]) -> tuple[Path, Path]:
    RELEASE_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    checksum_lines = [
        f"{entry['sha256']} *{entry['filename']}"
        for entry in manifest["artifacts"]  # type: ignore[index]
    ]
    CHECKSUM_FILE.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return CHECKSUM_FILE, MANIFEST_FILE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate release checksum and manifest artifacts.")
    return parser.parse_args()


def main() -> int:
    parse_args()
    version = build_windows.validate_release_versions()
    artifacts = collect_release_artifacts(version)
    manifest = build_release_manifest(version, artifacts)
    checksum_path, manifest_path = write_release_artifacts(manifest)
    print(f"Release version verified: {version}")
    print(f"Wrote checksum file: {checksum_path}")
    print(f"Wrote release manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
