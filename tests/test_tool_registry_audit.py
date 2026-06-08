"""Tests for tool_registry audit log and confirmation gate features.

These tests exercise the two security hardening additions:
  - ToolAuditLog (in security_utils) via tool_registry.execute_tool
  - Confirmation gate for Level 3 tools
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# ToolAuditLog unit tests
# ---------------------------------------------------------------------------


class TestToolAuditLog:
    """ToolAuditLog writes JSONL entries and never raises on I/O failure."""

    def _make_log(self, tmp_path: Path):
        from security_utils import ToolAuditLog

        return ToolAuditLog(log_dir=tmp_path)

    def test_record_creates_log_file(self, tmp_path):
        log = self._make_log(tmp_path)
        log.record("bash", ["command"], safety_level=3, outcome="success", duration_ms=12.5)

        assert log.log_path.exists()

    def test_record_writes_valid_jsonl(self, tmp_path):
        log = self._make_log(tmp_path)
        log.record("read_file", ["path"], safety_level=1, outcome="success", duration_ms=3.2)
        log.record("bash", ["command"], safety_level=3, outcome="error", duration_ms=5.0, error="oops")

        lines = log.log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

        first = json.loads(lines[0])
        assert first["tool_name"] == "read_file"
        assert first["safety_level"] == 1
        assert first["outcome"] == "success"
        assert "input_keys" in first
        assert "timestamp" in first
        assert "duration_ms" in first

        second = json.loads(lines[1])
        assert second["outcome"] == "error"
        assert second["error"] == "oops"

    def test_record_does_not_store_input_values(self, tmp_path):
        """Values (potentially sensitive) must never appear in the log."""
        log = self._make_log(tmp_path)
        log.record(
            "write_file",
            ["path", "content"],
            safety_level=2,
            outcome="success",
            duration_ms=1.0,
        )

        raw = log.log_path.read_text(encoding="utf-8")
        entry = json.loads(raw.strip())
        # Only keys should appear, not arbitrary values
        assert entry["input_keys"] == ["content", "path"]  # sorted

    def test_record_truncates_long_errors(self, tmp_path):
        log = self._make_log(tmp_path)
        long_error = "x" * 1000
        log.record("bash", ["command"], safety_level=3, outcome="error", duration_ms=1.0, error=long_error)

        entry = json.loads(log.log_path.read_text(encoding="utf-8").strip())
        assert len(entry["error"]) <= log._MAX_ERROR_LEN

    def test_record_is_silent_on_io_error(self, tmp_path):
        """Write failure must not raise or crash the caller."""
        log = self._make_log(tmp_path)
        # Make log_path unwritable by pointing it to a file that is a directory
        (tmp_path / "tool_audit.log").mkdir()

        # Must not raise
        log.record("bash", ["command"], safety_level=3, outcome="success", duration_ms=1.0)

    def test_multiple_records_append(self, tmp_path):
        log = self._make_log(tmp_path)
        for i in range(5):
            log.record(f"tool_{i}", [], safety_level=1, outcome="success", duration_ms=float(i))

        lines = log.log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 5


# ---------------------------------------------------------------------------
# tool_registry confirmation gate tests
# ---------------------------------------------------------------------------


class TestConfirmationGate:
    """execute_tool respects the confirmation gate for Level 3 tools."""

    def setup_method(self):
        """Reset registry state between tests."""
        import tool_registry

        # Clear gate and any test tools
        tool_registry.set_confirmation_gate(None)
        tool_registry._TOOLS.pop("_test_level3", None)
        tool_registry._TOOLS.pop("_test_level1", None)
        tool_registry._CACHED_SCHEMAS = None

    def _register_test_tools(self):
        import tool_registry

        tool_registry.register("_test_level3", "L3 tool", {}, lambda: "ran", safety_level=3)
        tool_registry.register("_test_level1", "L1 tool", {}, lambda: "ran", safety_level=1)

    def test_no_gate_allows_level3_tool(self, tmp_path):
        self._register_test_tools()
        import tool_registry

        with patch.object(tool_registry._get_audit_log(), "_write"):
            result = tool_registry.execute_tool("_test_level3", {})
        assert result == "ran"

    def test_gate_deny_blocks_level3_tool(self, tmp_path):
        self._register_test_tools()
        import tool_registry

        tool_registry.set_confirmation_gate(lambda name, inp, lvl: False)

        with patch("tool_registry._get_audit_log") as mock_log:
            mock_log.return_value = MagicMock()
            result = tool_registry.execute_tool("_test_level3", {})

        assert "denied" in result
        mock_log.return_value.record.assert_called_once()
        call_kwargs = mock_log.return_value.record.call_args.kwargs
        assert call_kwargs["outcome"] == "denied"

    def test_gate_allow_permits_level3_tool(self):
        self._register_test_tools()
        import tool_registry

        tool_registry.set_confirmation_gate(lambda name, inp, lvl: True)

        with patch("tool_registry._get_audit_log") as mock_log:
            mock_log.return_value = MagicMock()
            result = tool_registry.execute_tool("_test_level3", {})

        assert result == "ran"

    def test_gate_not_called_for_level1_tool(self):
        self._register_test_tools()
        import tool_registry

        calls = []
        tool_registry.set_confirmation_gate(lambda name, inp, lvl: calls.append(name) or True)

        with patch("tool_registry._get_audit_log") as mock_log:
            mock_log.return_value = MagicMock()
            tool_registry.execute_tool("_test_level1", {})

        assert "_test_level1" not in calls

    def test_gate_exception_denies_tool(self):
        self._register_test_tools()
        import tool_registry

        def bad_gate(name, inp, lvl):
            raise RuntimeError("gate exploded")

        tool_registry.set_confirmation_gate(bad_gate)

        with patch("tool_registry._get_audit_log") as mock_log:
            mock_log.return_value = MagicMock()
            result = tool_registry.execute_tool("_test_level3", {})

        assert "denied" in result

    def test_remove_gate_with_none(self):
        import tool_registry

        tool_registry.set_confirmation_gate(lambda n, i, l: False)
        tool_registry.set_confirmation_gate(None)
        assert tool_registry.get_confirmation_gate() is None


# ---------------------------------------------------------------------------
# Audit log integration via execute_tool
# ---------------------------------------------------------------------------


class TestAuditIntegration:
    """execute_tool writes the correct outcome to the audit log."""

    def setup_method(self):
        import tool_registry

        tool_registry.set_confirmation_gate(None)
        tool_registry._TOOLS.pop("_audit_ok", None)
        tool_registry._TOOLS.pop("_audit_fail", None)
        tool_registry._CACHED_SCHEMAS = None

    def test_success_recorded(self):
        import tool_registry

        tool_registry.register("_audit_ok", "ok", {}, lambda: "result", safety_level=1)

        with patch("tool_registry._get_audit_log") as mock_log:
            mock_log.return_value = MagicMock()
            tool_registry.execute_tool("_audit_ok", {})

        kw = mock_log.return_value.record.call_args.kwargs
        assert kw["outcome"] == "success"
        assert kw["tool_name"] == "_audit_ok"

    def test_error_recorded(self):
        import tool_registry

        def boom():
            raise ValueError("kaboom")

        tool_registry.register("_audit_fail", "fail", {}, boom, safety_level=2)

        with patch("tool_registry._get_audit_log") as mock_log:
            mock_log.return_value = MagicMock()
            result = tool_registry.execute_tool("_audit_fail", {})

        assert "Error" in result
        kw = mock_log.return_value.record.call_args.kwargs
        assert kw["outcome"] == "error"
        assert "kaboom" in kw["error"]

    def test_unknown_tool_not_recorded(self):
        import tool_registry

        with patch("tool_registry._get_audit_log") as mock_log:
            mock_log.return_value = MagicMock()
            result = tool_registry.execute_tool("_does_not_exist", {})

        assert "Unknown tool" in result
        mock_log.return_value.record.assert_not_called()
