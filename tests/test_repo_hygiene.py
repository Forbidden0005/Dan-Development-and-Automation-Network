from pathlib import Path


def test_local_dan_state_ignore_pattern_is_repo_root_anchored():
    gitignore = Path(__file__).resolve().parents[1] / ".gitignore"
    patterns = gitignore.read_text(encoding="utf-8").splitlines()

    assert "Dan/" not in patterns
    assert "/Dan/" in patterns


def test_repo_local_tmp_directory_is_ignored():
    gitignore = Path(__file__).resolve().parents[1] / ".gitignore"
    patterns = gitignore.read_text(encoding="utf-8").splitlines()

    assert "/tmp/" in patterns
