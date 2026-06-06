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


def test_manual_verification_script_avoids_readiness_claims():
    script = Path(__file__).resolve().parents[1] / "system_verification.py"
    content = script.read_text(encoding="utf-8").lower()

    assert "production ready" not in content
    assert "enterprise-grade" not in content
    assert "all systems operational" not in content


def test_manual_auth_smoke_skip_does_not_open_auth_state(monkeypatch, capsys):
    import system_verification

    monkeypatch.delenv("DAN_VERIFICATION_API_KEY", raising=False)

    system_verification.test_authentication_system()

    output = capsys.readouterr().out
    assert "SKIP: Set DAN_VERIFICATION_API_KEY" in output
    assert "Auth state was not opened." in output
