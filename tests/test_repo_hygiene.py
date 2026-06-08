import subprocess
import sys
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


def test_scan_secrets_script_exists_and_is_importable():
    """scan_secrets.py must exist and parse without syntax errors."""
    script = Path(__file__).resolve().parents[1] / "scripts" / "scan_secrets.py"
    assert script.is_file(), "scripts/scan_secrets.py is missing"

    # Compile to bytecode to catch syntax errors without executing side effects
    source = script.read_text(encoding="utf-8")
    compile(source, str(script), "exec")  # raises SyntaxError if malformed


def test_scan_secrets_finds_no_real_secrets_in_tracked_files():
    """
    Run scan_secrets.py against tracked files and assert exit code 0.

    This test will FAIL if a real secret is accidentally committed. That is
    intentional — a failing test here means a secret needs to be rotated and
    removed from history.

    The test is skipped if git is unavailable (e.g., in a restricted CI env
    where git ls-files cannot run).
    """
    import shutil

    if shutil.which("git") is None:
        import pytest
        pytest.skip("git not available in this environment")

    script = Path(__file__).resolve().parents[1] / "scripts" / "scan_secrets.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"scan_secrets.py found potential secrets (exit {result.returncode}).\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_manual_auth_smoke_skip_does_not_open_auth_state(monkeypatch, capsys):
    import system_verification

    monkeypatch.delenv("DAN_VERIFICATION_API_KEY", raising=False)

    system_verification.test_authentication_system()

    output = capsys.readouterr().out
    assert "SKIP: Set DAN_VERIFICATION_API_KEY" in output
    assert "Auth state was not opened." in output
