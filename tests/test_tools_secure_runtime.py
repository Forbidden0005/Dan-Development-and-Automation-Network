"""Runtime resilience tests for secure tools."""

import asyncio
import sys


def test_tools_secure_imports_without_aiofiles(monkeypatch, tmp_path):
    original_tools_secure = sys.modules.get("tools_secure")

    with monkeypatch.context() as missing_modules:
        missing_modules.setitem(sys.modules, "aiofiles", None)
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

        sys.modules.pop("tools_secure", None)

    if original_tools_secure is not None:
        sys.modules["tools_secure"] = original_tools_secure
    else:
        import tools_secure

        assert tools_secure.aiofiles is not None
