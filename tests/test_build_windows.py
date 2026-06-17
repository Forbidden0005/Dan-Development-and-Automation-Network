from pathlib import Path

from scripts import build_windows


def test_resolve_signing_config_returns_none_when_disabled():
    assert build_windows.resolve_signing_config(enabled=False) is None


def test_resolve_signing_config_requires_certificate_when_enabled(tmp_path):
    fake_signtool = tmp_path / "signtool.exe"
    fake_signtool.write_text("not-real", encoding="utf-8")

    try:
        build_windows.resolve_signing_config(enabled=True, sign_tool=str(fake_signtool))
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected resolve_signing_config() to fail without a certificate")

    assert "no certificate was configured" in message


def test_resolve_signing_config_uses_explicit_values(tmp_path):
    fake_signtool = tmp_path / "signtool.exe"
    fake_signtool.write_text("not-real", encoding="utf-8")
    fake_cert = tmp_path / "dan-signing.pfx"
    fake_cert.write_text("not-real", encoding="utf-8")

    signing = build_windows.resolve_signing_config(
        enabled=True,
        sign_tool=str(fake_signtool),
        certificate_file=str(fake_cert),
        certificate_password="secret",
        timestamp_url="https://timestamp.example.test",
    )

    assert signing is not None
    assert signing.sign_tool == fake_signtool.resolve()
    assert signing.certificate_file == fake_cert.resolve()
    assert signing.certificate_password == "secret"
    assert signing.timestamp_url == "https://timestamp.example.test"


def test_signing_command_uses_sha256_and_timestamp(tmp_path):
    fake_signtool = tmp_path / "signtool.exe"
    fake_signtool.write_text("not-real", encoding="utf-8")
    fake_cert = tmp_path / "dan-signing.pfx"
    fake_cert.write_text("not-real", encoding="utf-8")
    artifact = tmp_path / "Dan.exe"
    artifact.write_text("not-real", encoding="utf-8")

    signing = build_windows.SigningConfig(
        sign_tool=fake_signtool.resolve(),
        certificate_file=fake_cert.resolve(),
        certificate_password="secret",
        timestamp_url="https://timestamp.example.test",
    )

    command = build_windows.signing_command(signing, artifact.resolve())

    assert command[:2] == [str(fake_signtool.resolve()), "sign"]
    assert "/fd" in command
    assert "SHA256" in command
    assert "/tr" in command
    assert "https://timestamp.example.test" in command
    assert str(artifact.resolve()) == command[-1]


def test_validate_release_versions_matches_repo_sources():
    assert build_windows.validate_release_versions() == "2.5.1"


def test_validate_release_versions_reports_mismatch(tmp_path):
    config_file = tmp_path / "config.py"
    config_file.write_text('APP_VERSION = "2.5.1"\n', encoding="utf-8")

    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text('[project]\nversion = "2.5.2"\n', encoding="utf-8")

    installer_script = tmp_path / "Dan.iss"
    installer_script.write_text('#define MyAppVersion "2.5.1"\n', encoding="utf-8")

    try:
        build_windows.validate_release_versions(
            config_file=config_file,
            pyproject_file=pyproject_file,
            installer_script=installer_script,
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected validate_release_versions() to fail on version drift")

    assert "Release version mismatch" in message
    assert "config.py=2.5.1" in message
    assert "pyproject.toml=2.5.2" in message
    assert "installer/Dan.iss=2.5.1" in message


def test_validate_expected_version_allows_match():
    build_windows.validate_expected_version("2.5.1", "2.5.1")


def test_validate_expected_version_rejects_mismatch():
    try:
        build_windows.validate_expected_version("2.5.1", "2.5.2")
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected validate_expected_version() to fail on mismatch")

    assert "Expected 2.5.2" in message
    assert "resolved to 2.5.1" in message


def test_find_iscc_detects_localappdata_install(monkeypatch, tmp_path):
    local_app_data = tmp_path / "LocalAppData"
    iscc = local_app_data / "Programs" / "Inno Setup 6" / "ISCC.exe"
    iscc.parent.mkdir(parents=True)
    iscc.write_text("not-real", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    assert build_windows.find_iscc() == iscc


def test_gui_build_command_uses_supported_shell():
    command = build_windows.build_command("gui")

    assert command[:3] == [build_windows.sys.executable, "-m", "PyInstaller"]
    assert "--windowed" in command
    assert "--console" not in command
    assert str(Path("dan_gui_modern.py")) in command[-1]
    assert "Dan" in command
    assert "--exclude-module" in command
    assert "torch" in command
    assert "transformers" in command
    assert "pytest" in command
    assert "_pytest" in command
    assert "IPython" in command
    assert "black" in command
    assert "mypy" in command
    assert "prompt_toolkit" in command


def test_cli_build_command_uses_console_mode():
    command = build_windows.build_command("cli")

    assert "--console" in command
    assert "--windowed" not in command
    assert str(Path("Dan.py")) in command[-1]
    assert "DanCLI" in command


def test_optional_modules_are_opt_in():
    command = build_windows.build_command("gui", include_vision=True, include_ml=True)

    assert "--hidden-import" in command
    assert "image_tools" in command
    assert "ml_tools" in command
    assert "torch" not in command
    assert "transformers" not in command


def test_all_target_expands_to_gui_and_cli():
    targets = [build_windows.GUI_TARGET, build_windows.CLI_TARGET]

    assert build_windows.ALL_TARGET == "all"
    assert targets == ["gui", "cli"]
