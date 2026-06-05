"""Startup diagnostics tests."""

import importlib.util


def _spec_table(monkeypatch, available: set[str]):
    original = importlib.util.find_spec

    def fake_find_spec(name, package=None):
        if name in available:
            return object()
        return original(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)


def test_startup_doctor_flags_missing_provider_credentials(tmp_path, monkeypatch):
    import code_tools

    (tmp_path / "requirements-core.txt").write_text("openai>=1.0.0\n", encoding="utf-8")
    _spec_table(monkeypatch, {"openai"})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    report = code_tools.startup_doctor(str(tmp_path), provider="openai", target="cli")

    assert "Startup blockers:     1" in report
    assert "Provider 'openai' has no API key configured" in report
    assert code_tools.startup_blocked(str(tmp_path), provider="openai", target="cli") is True


def test_startup_doctor_ollama_cli_only_blocks_required_runtime(tmp_path, monkeypatch):
    import code_tools

    (tmp_path / "requirements-core.txt").write_text(
        "openai>=1.0.0\nanthropic>=0.39.0\ncustomtkinter>=5.2.0\nhttpx>=0.27.0\n",
        encoding="utf-8",
    )
    _spec_table(monkeypatch, {"httpx"})

    report = code_tools.startup_doctor(str(tmp_path), provider="ollama", target="cli")

    assert "Startup blockers:     0" in report
    assert "Startup-critical runtime dependencies are missing" not in report
    assert "Missing runtime packages:" in report
    assert "customtkinter" in report
    assert code_tools.startup_blocked(str(tmp_path), provider="ollama", target="cli") is False


def test_startup_doctor_keeps_missing_pytest_as_advisory(tmp_path, monkeypatch):
    import code_tools

    (tmp_path / "requirements-core.txt").write_text("httpx>=0.27.0\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("pytest>=8.0.0\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    _spec_table(monkeypatch, {"httpx"})

    report = code_tools.startup_doctor(str(tmp_path), provider="ollama", target="cli")

    assert "Startup blockers:     0" in report
    assert "Pytest is not installed" in report
    assert code_tools.startup_blocked(str(tmp_path), provider="ollama", target="cli") is False


def test_startup_doctor_flags_missing_gui_runtime(tmp_path, monkeypatch):
    import code_tools

    (tmp_path / "requirements-core.txt").write_text("customtkinter>=5.2.0\n", encoding="utf-8")
    _spec_table(monkeypatch, set())

    report = code_tools.startup_doctor(str(tmp_path), provider="ollama", target="gui")

    assert "GUI runtime imports are unavailable" in report
    assert "customtkinter" in report
    assert code_tools.startup_blocked(str(tmp_path), provider="ollama", target="gui") is True


def test_environment_doctor_scopes_runtime_install_guidance(tmp_path, monkeypatch):
    import code_tools

    (tmp_path / "requirements.txt").write_text("-r requirements-core.txt\n", encoding="utf-8")
    (tmp_path / "requirements-core.txt").write_text(
        "anthropic>=0.39.0\nopenai>=1.54.0\nhttpx>=0.27.0\naiofiles>=23.0.0\n"
        "ddgs>=0.1.0\ncustomtkinter>=5.2.0\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    _spec_table(monkeypatch, set())
    monkeypatch.setattr(code_tools, "_python_cmd", lambda: ["py"])

    report = code_tools.environment_doctor(str(tmp_path), provider="ollama")

    assert "Runtime dependencies are missing: httpx" in report
    assert "Feature-scoped runtime packages:" in report
    assert "Inactive provider SDKs" in report
    assert "Optional runtime accelerators" in report
    assert "GUI-only packages" in report
    assert "Suggested runtime fix:" in report
    assert "py -m pip install httpx" in report
    assert "py -m pip install anthropic openai" in report
    assert "py -m pip install aiofiles ddgs" in report
    assert "py -m pip install customtkinter" in report
