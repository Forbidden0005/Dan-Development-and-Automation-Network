"""Runtime resilience tests for secure tools."""

import asyncio
import importlib
import sys


def test_tools_secure_imports_without_aiofiles(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "aiofiles", None)
    sys.modules.pop("tools_secure", None)

    import tools_secure

    monkeypatch.setattr(
        tools_secure,
        "_path_validator",
        tools_secure.SecurePathValidator(allowed_roots=[str(tmp_path)]),
    )

    file_path = tmp_path / "demo.txt"
    file_path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = asyncio.run(tools_secure.read_file_async(str(file_path), offset=1, limit=1))

    assert "2 | two" in result
    assert tools_secure.aiofiles is None

    importlib.reload(tools_secure)
