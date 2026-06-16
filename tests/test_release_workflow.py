"""Guard tests for the tag-triggered release workflow (ROADMAP Phase 7.1).

These assert the structural contract of `.github/workflows/release.yml` so the
release path cannot silently regress: it must trigger on version tags, hold the
permission needed to publish, build the portable bundles via the existing build
script, verify and smoke-test them, and upload them as GitHub Release assets.
"""

from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
)


def _read() -> str:
    assert WORKFLOW.is_file(), ".github/workflows/release.yml is missing"
    return WORKFLOW.read_text(encoding="utf-8")


def test_release_workflow_exists():
    _read()


def test_release_workflow_triggers_on_version_tags():
    content = _read()
    assert "tags:" in content
    assert '"v*.*.*"' in content


def test_release_workflow_has_contents_write_permission():
    """Creating a release and uploading assets requires contents: write."""
    content = _read()
    assert "permissions:" in content
    assert "contents: write" in content


def test_release_workflow_runs_on_windows():
    content = _read()
    assert "windows-latest" in content


def test_release_workflow_builds_both_targets_via_build_script():
    content = _read()
    assert "scripts/build_windows.py --target gui" in content
    assert "scripts/build_windows.py --target cli" in content


def test_release_workflow_verifies_and_smoke_tests_packages():
    content = _read()
    assert "scripts/verify_windows_build.py --target gui" in content
    assert "scripts/verify_windows_build.py --target cli" in content
    assert "scripts/smoke_windows_cli.py" in content


def test_release_workflow_publishes_release_assets():
    content = _read()
    assert "softprops/action-gh-release@v2" in content
    assert "release-assets/*.zip" in content


def test_release_workflow_packages_expected_portable_bundles():
    content = _read()
    assert "dist/windows/Dan/Dan" in content
    assert "dist/windows/DanCLI/DanCLI" in content


def test_release_workflow_stays_portable_only():
    """Phase 7.1 ships portable artifacts only.

    Installer (.exe) and code-signing remain deferred-pending-approval in
    ROADMAP.md, so this workflow must not invoke them.
    """
    content = _read()
    assert "--installer" not in content
    assert "ISCC" not in content
    assert "signtool" not in content


def test_release_workflow_is_valid_yaml():
    """If PyYAML is available, confirm the workflow parses cleanly."""
    try:
        import yaml
    except ImportError:  # pragma: no cover - yaml not installed in this env
        import pytest

        pytest.skip("PyYAML not available in this environment")

    data = yaml.safe_load(_read())
    assert isinstance(data, dict)
    assert "jobs" in data
    assert "windows-release" in data["jobs"]
