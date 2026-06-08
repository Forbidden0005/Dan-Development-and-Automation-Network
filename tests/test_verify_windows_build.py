from pathlib import Path

import pytest

from scripts import verify_windows_build


def test_expected_executable_for_gui():
    path = verify_windows_build.expected_executable("gui")

    assert path.name == "Dan.exe"
    assert path.parts[-3:] == ("Dan", "Dan", "Dan.exe")


def test_expected_executable_for_cli():
    path = verify_windows_build.expected_executable("cli")

    assert path.name == "DanCLI.exe"
    assert path.parts[-3:] == ("DanCLI", "DanCLI", "DanCLI.exe")


def test_verify_target_requires_output_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_windows_build, "DIST_ROOT", tmp_path / "dist" / "windows")

    with pytest.raises(FileNotFoundError):
        verify_windows_build.verify_target("gui")


def test_verify_target_accepts_expected_layout(tmp_path, monkeypatch):
    dist_root = tmp_path / "dist" / "windows"
    package_root = dist_root / "Dan" / "Dan"
    package_root.mkdir(parents=True)
    (package_root / "_internal").mkdir()
    exe = package_root / "Dan.exe"
    exe.write_bytes(b"dan")

    monkeypatch.setattr(verify_windows_build, "DIST_ROOT", dist_root)

    result = verify_windows_build.verify_target("gui")

    assert "verified Dan.exe" in result
