import importlib.util
from pathlib import Path


def _load_with_server():
    path = Path(__file__).resolve().parents[1] / "scripts" / "with_server.py"
    spec = importlib.util.spec_from_file_location("with_server", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_server_command_without_shell_features_uses_argv():
    with_server = _load_with_server()

    args = with_server._server_command_args("python -m http.server")

    assert args == ["python", "-m", "http.server"]


def test_server_command_without_shell_features_handles_quoted_args():
    with_server = _load_with_server()

    args = with_server._server_command_args('python "server app.py"')

    assert args == ["python", "server app.py"]


def test_server_command_with_shell_features_uses_explicit_shell(monkeypatch):
    with_server = _load_with_server()

    monkeypatch.setattr(with_server.platform, "system", lambda: "Windows")
    monkeypatch.setenv("COMSPEC", "C:\\Windows\\System32\\cmd.exe")

    args = with_server._server_command_args("cd backend && python server.py")

    assert args == [
        "C:\\Windows\\System32\\cmd.exe",
        "/d",
        "/s",
        "/c",
        "cd backend && python server.py",
    ]
