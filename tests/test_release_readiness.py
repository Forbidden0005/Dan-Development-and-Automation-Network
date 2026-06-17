from scripts import release_readiness


def test_render_release_readiness_reports_blockers():
    checks = [
        release_readiness.ReadinessCheck("version_sync", True, "ok"),
        release_readiness.ReadinessCheck(
            "installer_tool",
            False,
            "missing iscc",
            remediation="install inno setup",
        ),
    ]

    rendered = release_readiness.render_release_readiness(checks)

    assert "Blocking: 1" in rendered
    assert "[PASS] version_sync: ok" in rendered
    assert "[BLOCK] installer_tool: missing iscc" in rendered
    assert "not yet locally ready to ship" in rendered
    assert "Recommended next steps:" in rendered
    assert "- installer_tool: install inno setup" in rendered


def test_render_release_readiness_reports_ready_when_all_pass():
    checks = [
        release_readiness.ReadinessCheck("version_sync", True, "ok"),
        release_readiness.ReadinessCheck("signing_material", True, "configured"),
    ]

    rendered = release_readiness.render_release_readiness(checks)

    assert "Blocking: 0" in rendered
    assert "locally ready to ship" in rendered


def test_collect_release_readiness_includes_expected_checks(monkeypatch):
    monkeypatch.setattr(
        release_readiness,
        "_check_release_version_sync",
        lambda: release_readiness.ReadinessCheck("version_sync", True, "ok"),
    )
    monkeypatch.setattr(
        release_readiness,
        "_check_packaged_target",
        lambda target: release_readiness.ReadinessCheck(f"{target}_package", True, target),
    )
    monkeypatch.setattr(
        release_readiness,
        "_check_cli_smoke",
        lambda: release_readiness.ReadinessCheck("cli_smoke", True, "ok"),
    )
    monkeypatch.setattr(
        release_readiness,
        "_check_local_installer_tool",
        lambda: release_readiness.ReadinessCheck("installer_tool", False, "missing"),
    )
    monkeypatch.setattr(
        release_readiness,
        "_check_installer_artifact",
        lambda: release_readiness.ReadinessCheck("installer_artifact", True, "ok"),
    )
    monkeypatch.setattr(
        release_readiness,
        "_check_release_integrity_artifacts",
        lambda: release_readiness.ReadinessCheck("release_integrity", True, "ok"),
    )
    monkeypatch.setattr(
        release_readiness,
        "_check_local_signing_tool",
        lambda: release_readiness.ReadinessCheck("signing_tool", False, "missing"),
    )
    monkeypatch.setattr(
        release_readiness,
        "_check_signing_material",
        lambda: release_readiness.ReadinessCheck("signing_material", False, "missing"),
    )

    checks = release_readiness.collect_release_readiness()

    assert [check.name for check in checks] == [
        "version_sync",
        "gui_package",
        "cli_package",
        "cli_smoke",
        "installer_tool",
        "installer_artifact",
        "release_integrity",
        "signing_tool",
        "signing_material",
    ]


def test_signing_material_check_requires_env(monkeypatch):
    monkeypatch.delenv("DAN_SIGN_PFX", raising=False)
    monkeypatch.delenv("DAN_SIGN_PFX_PASSWORD", raising=False)

    check = release_readiness._check_signing_material()

    assert check.ok is False
    assert "not configured" in check.detail
    assert "DAN_SIGN_PFX" in check.remediation
