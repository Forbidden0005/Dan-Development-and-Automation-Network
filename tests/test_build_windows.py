from pathlib import Path

from scripts import build_windows


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
