import pytest

from scripts import smoke_windows_cli


def test_validate_cli_smoke_output_accepts_clean_report():
    smoke_windows_cli.validate_cli_smoke_output(
        0,
        "Startup Doctor (Dan)\nStartup blockers:     0\nAdvisories:           0\n",
    )


def test_validate_cli_smoke_output_rejects_nonzero_exit():
    with pytest.raises(RuntimeError):
        smoke_windows_cli.validate_cli_smoke_output(1, "failed")


def test_validate_cli_smoke_output_rejects_build_only_leakage():
    with pytest.raises(RuntimeError):
        smoke_windows_cli.validate_cli_smoke_output(
            0,
            "Startup blockers:     0\nAdvisories: 1\nRuntime dependencies are missing: pyinstaller\n",
        )


def test_validate_cli_smoke_output_rejects_local_import_misclassification():
    with pytest.raises(RuntimeError):
        smoke_windows_cli.validate_cli_smoke_output(
            0,
            "Startup blockers:     0\nImported packages are not declared in requirements: scripts\n",
        )
