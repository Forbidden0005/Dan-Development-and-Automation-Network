"""Runtime resilience tests for the async file reader.

These tests were originally written against ``tools_secure``.  Now that
``read_file_async`` lives in ``tools.py``, we import it from there.  We
patch ``tools._path_validator`` directly since that is the module where
``read_file_async`` executes.
"""

import asyncio

import tools
from security_utils import SecurePathValidator


def test_read_file_async_with_aiofiles_unavailable(monkeypatch, tmp_path):
    """read_file_async falls back to asyncio.to_thread when aiofiles is absent."""
    # Simulate aiofiles being unavailable at the module level.
    monkeypatch.setattr(tools, "_aiofiles", None)

    # Restrict path validation to tmp_path so the test is self-contained.
    monkeypatch.setattr(
        tools,
        "_path_validator",
        SecurePathValidator(allowed_roots=[str(tmp_path)]),
    )

    file_path = tmp_path / "demo.txt"
    file_path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = asyncio.run(tools.read_file_async(str(file_path), offset=1, limit=1))

    assert "2 | two" in result
    # Confirm the monkeypatch took effect (aiofiles was None during the call).
    assert tools._aiofiles is None


def test_read_file_async_nominal(monkeypatch, tmp_path):
    """read_file_async returns correct line-numbered output for a normal file."""
    monkeypatch.setattr(
        tools,
        "_path_validator",
        SecurePathValidator(allowed_roots=[str(tmp_path)]),
    )

    file_path = tmp_path / "hello.txt"
    file_path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    result = asyncio.run(tools.read_file_async(str(file_path)))

    assert "1 | alpha" in result
    assert "3 | gamma" in result
