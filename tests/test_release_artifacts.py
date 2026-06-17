import json
from pathlib import Path

from scripts import release_artifacts


def test_collect_release_artifacts_requires_all_outputs(monkeypatch, tmp_path):
    version = "2.5.1"
    gui = tmp_path / "Dan.exe"
    cli = tmp_path / "DanCLI.exe"
    installer = tmp_path / "Dan-2.5.1-setup.exe"
    gui.write_text("gui", encoding="utf-8")
    cli.write_text("cli", encoding="utf-8")

    monkeypatch.setattr(
        release_artifacts,
        "expected_release_artifacts",
        lambda _version: [
            release_artifacts.ReleaseArtifact("gui_exe", gui),
            release_artifacts.ReleaseArtifact("cli_exe", cli),
            release_artifacts.ReleaseArtifact("installer", installer),
        ],
    )

    try:
        release_artifacts.collect_release_artifacts(version)
    except FileNotFoundError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected collect_release_artifacts() to fail when installer is missing")

    assert "installer" in message
    assert str(installer) in message


def test_build_release_manifest_hashes_files(tmp_path):
    artifact = tmp_path / "Dan.exe"
    artifact.write_text("dan-artifact", encoding="utf-8")
    manifest = release_artifacts.build_release_manifest(
        "2.5.1",
        [release_artifacts.ReleaseArtifact("gui_exe", artifact)],
    )

    assert manifest["project"] == "Dan"
    assert manifest["version"] == "2.5.1"
    entry = manifest["artifacts"][0]
    assert entry["label"] == "gui_exe"
    assert entry["filename"] == "Dan.exe"
    assert entry["size_bytes"] == artifact.stat().st_size
    assert len(entry["sha256"]) == 64


def test_write_release_artifacts_writes_checksum_and_manifest(monkeypatch, tmp_path):
    release_dir = tmp_path / "release"
    checksum_path = release_dir / "SHA256SUMS.txt"
    manifest_path = release_dir / "release-manifest.json"
    monkeypatch.setattr(release_artifacts, "RELEASE_ARTIFACTS_DIR", release_dir)
    monkeypatch.setattr(release_artifacts, "CHECKSUM_FILE", checksum_path)
    monkeypatch.setattr(release_artifacts, "MANIFEST_FILE", manifest_path)

    manifest = {
        "project": "Dan",
        "version": "2.5.1",
        "generated_from": str(tmp_path),
        "artifacts": [
            {
                "label": "gui_exe",
                "path": str(tmp_path / "Dan.exe"),
                "filename": "Dan.exe",
                "size_bytes": 123,
                "sha256": "a" * 64,
            }
        ],
    }

    written_checksum, written_manifest = release_artifacts.write_release_artifacts(manifest)

    assert written_checksum == checksum_path
    assert written_manifest == manifest_path
    assert checksum_path.read_text(encoding="utf-8") == f"{'a' * 64} *Dan.exe\n"
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest
