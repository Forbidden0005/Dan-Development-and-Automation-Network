"""Tests for session_mgr.py.

Covers:
- _safe_session_stem: valid names, empty input, .json stripping, path traversal
  attempts, special characters, length truncation
- save: file creation, valid JSON, dangerous-filename sanitization, message count
- auto_save: file creation, no-op on empty messages, silent failure on I/O error
- load: found by name, not found, path-traversal prevention, corrupt file handling
- delete: success, not found, path-traversal prevention, auto-save files excluded
- list_sessions: excludes auto by default, includes with flag, sorted by updated
- format_sessions_table: no sessions, with sessions (column headers present)
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import session_mgr
from session_mgr import (
    _safe_session_stem,
    auto_save,
    delete,
    format_sessions_table,
    list_sessions,
    load,
    save,
)


# ---------------------------------------------------------------------------
# Fixture: redirect SESSIONS_DIR to a temp directory for each test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_sessions_dir(tmp_path):
    """Redirect every session_mgr operation to a throw-away temp directory."""
    sessions_tmp = tmp_path / "sessions"
    sessions_tmp.mkdir()
    with patch.object(session_mgr, "SESSIONS_DIR", sessions_tmp):
        yield sessions_tmp


# ---------------------------------------------------------------------------
# _safe_session_stem
# ---------------------------------------------------------------------------


class TestSafeSessionStem:
    def test_valid_alphanumeric(self):
        assert _safe_session_stem("mysession") == "mysession"

    def test_valid_with_underscores_and_dashes(self):
        assert _safe_session_stem("my-session_01") == "my-session_01"

    def test_strips_whitespace(self):
        assert _safe_session_stem("  hello  ") == "hello"

    def test_strips_json_extension(self):
        assert _safe_session_stem("mysession.json") == "mysession"

    def test_empty_string_returns_empty(self):
        assert _safe_session_stem("") == ""

    def test_whitespace_only_returns_empty(self):
        assert _safe_session_stem("   ") == ""

    def test_path_traversal_dotdot_slash_rejected(self):
        assert _safe_session_stem("../secrets") == ""

    def test_path_traversal_backslash_rejected(self):
        assert _safe_session_stem("..\\secrets") == ""

    def test_path_traversal_absolute_rejected(self):
        # A path that isn't just a filename (has directory component)
        # _safe_session_stem checks Path(stem).name == stem
        result = _safe_session_stem("/etc/passwd")
        assert result == ""

    def test_special_chars_stripped(self):
        # Only alnum + _ - . are kept
        result = _safe_session_stem("my session! @2024")
        assert " " not in result
        assert "!" not in result
        assert "@" not in result

    def test_truncated_to_80_chars(self):
        long_name = "a" * 100
        result = _safe_session_stem(long_name)
        assert len(result) <= 80

    def test_dots_allowed(self):
        assert _safe_session_stem("v2.5.1-notes") == "v2.5.1-notes"


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


class TestSave:
    def test_creates_file(self, isolated_sessions_dir):
        save([{"role": "user", "content": "hi"}], "anthropic", "claude-sonnet-4", name="test1")
        files = list(isolated_sessions_dir.glob("*.json"))
        assert len(files) == 1

    def test_saved_file_is_valid_json(self, isolated_sessions_dir):
        save([{"role": "user", "content": "hi"}], "anthropic", "claude-sonnet-4", name="valid")
        fp = isolated_sessions_dir / "valid.json"
        data = json.loads(fp.read_text())
        assert "messages" in data
        assert data["messages"][0]["role"] == "user"

    def test_returns_confirmation_string(self, isolated_sessions_dir):
        result = save([{"role": "user", "content": "x"}], "openai", "gpt-4o", name="confirm")
        assert "confirm" in result or "saved" in result.lower()

    def test_message_count_in_confirmation(self, isolated_sessions_dir):
        msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        result = save(msgs, "anthropic", "claude-sonnet-4", name="twomsgs")
        assert "2" in result

    def test_provider_and_model_stored(self, isolated_sessions_dir):
        save([{"role": "user", "content": "hi"}], "openai", "gpt-4o", name="pmtest")
        data = json.loads((isolated_sessions_dir / "pmtest.json").read_text())
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o"

    def test_dangerous_chars_sanitized_from_name(self, isolated_sessions_dir):
        # "../../evil" contains "/" which is stripped by the sanitizer, leaving "....evil".
        # The result is a plain filename — no path separators — so it stays inside
        # the sessions directory. This is the correct safe behavior: "/" is what
        # enables traversal, not "." alone.
        save([{"role": "user", "content": "x"}], "anthropic", "claude", name="../../evil")
        files = list(isolated_sessions_dir.glob("*.json"))
        assert len(files) == 1
        fname = files[0].name
        # No path separators survive sanitization
        assert "/" not in fname
        assert "\\" not in fname
        # The file is created inside the sessions directory (not above it)
        assert files[0].parent.resolve() == isolated_sessions_dir.resolve()

    def test_empty_name_falls_back_to_session_id(self, isolated_sessions_dir):
        save([{"role": "user", "content": "x"}], "anthropic", "claude", name="")
        files = list(isolated_sessions_dir.glob("*.json"))
        assert len(files) == 1

    def test_spaces_replaced_with_underscores(self, isolated_sessions_dir):
        save([{"role": "user", "content": "x"}], "anthropic", "claude", name="my session")
        files = list(isolated_sessions_dir.glob("*.json"))
        assert len(files) == 1
        assert " " not in files[0].name

    def test_overwrite_existing_file(self, isolated_sessions_dir):
        msgs1 = [{"role": "user", "content": "first"}]
        msgs2 = [{"role": "user", "content": "first"}, {"role": "assistant", "content": "second"}]
        save(msgs1, "anthropic", "claude", name="overwrite")
        save(msgs2, "anthropic", "claude", name="overwrite")
        data = json.loads((isolated_sessions_dir / "overwrite.json").read_text())
        assert len(data["messages"]) == 2


# ---------------------------------------------------------------------------
# auto_save
# ---------------------------------------------------------------------------


class TestAutoSave:
    def test_creates_auto_prefixed_file(self, isolated_sessions_dir):
        auto_save([{"role": "user", "content": "hi"}], "anthropic", "claude", "abc123")
        files = list(isolated_sessions_dir.glob("_auto_*.json"))
        assert len(files) == 1
        assert "_auto_abc123" in files[0].name

    def test_noop_on_empty_messages(self, isolated_sessions_dir):
        auto_save([], "anthropic", "claude", "abc123")
        files = list(isolated_sessions_dir.glob("*.json"))
        assert len(files) == 0

    def test_silent_on_io_error(self, isolated_sessions_dir):
        # Should not raise even if writing fails
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            try:
                auto_save([{"role": "user", "content": "x"}], "anthropic", "claude", "err1")
            except Exception:
                pytest.fail("auto_save raised an exception on I/O error")


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


class TestLoad:
    def test_load_existing_session(self, isolated_sessions_dir):
        msgs = [{"role": "user", "content": "hello"}]
        save(msgs, "anthropic", "claude", name="loadme")
        result = load("loadme")
        assert result is not None
        loaded_msgs, meta = result
        assert loaded_msgs[0]["content"] == "hello"

    def test_load_returns_none_for_missing(self, isolated_sessions_dir):
        assert load("nonexistent") is None

    def test_load_strips_json_extension(self, isolated_sessions_dir):
        msgs = [{"role": "user", "content": "x"}]
        save(msgs, "anthropic", "claude", name="exttest")
        result = load("exttest.json")
        assert result is not None

    def test_load_path_traversal_rejected(self, isolated_sessions_dir):
        # Attempting to load via path traversal should return None
        result = load("../some_other_file")
        assert result is None

    def test_load_empty_name_returns_none(self, isolated_sessions_dir):
        assert load("") is None

    def test_load_corrupt_file_returns_none(self, isolated_sessions_dir):
        (isolated_sessions_dir / "corrupt.json").write_text("not json at all!!!")
        result = load("corrupt")
        assert result is None

    def test_load_returns_metadata(self, isolated_sessions_dir):
        msgs = [{"role": "user", "content": "x"}]
        save(msgs, "openai", "gpt-4o", name="metacheck")
        _, meta = load("metacheck")
        assert meta["provider"] == "openai"
        assert meta["model"] == "gpt-4o"

    def test_load_auto_save_by_session_id(self, isolated_sessions_dir):
        msgs = [{"role": "user", "content": "autohello"}]
        auto_save(msgs, "anthropic", "claude", "sid999")
        # load("sid999") tries _auto_sid999.json as a candidate
        result = load("sid999")
        assert result is not None
        loaded_msgs, _ = result
        assert loaded_msgs[0]["content"] == "autohello"

    def test_load_stays_within_sessions_dir(self, isolated_sessions_dir, tmp_path):
        # Write a file one level above the sessions dir
        target = tmp_path / "secret.json"
        target.write_text(json.dumps({"messages": [{"role": "user", "content": "stolen"}]}))
        # Attempt to load it via traversal — should return None
        result = load("../secret")
        assert result is None


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_existing_session(self, isolated_sessions_dir):
        save([{"role": "user", "content": "x"}], "anthropic", "claude", name="todelete")
        assert delete("todelete") is True
        assert not (isolated_sessions_dir / "todelete.json").exists()

    def test_delete_nonexistent_returns_false(self, isolated_sessions_dir):
        assert delete("doesnotexist") is False

    def test_delete_empty_name_returns_false(self, isolated_sessions_dir):
        assert delete("") is False

    def test_delete_path_traversal_rejected(self, isolated_sessions_dir):
        assert delete("../evil") is False

    def test_delete_does_not_match_auto_save(self, isolated_sessions_dir):
        # auto_save creates _auto_abc.json; delete("abc") must not touch it
        auto_save([{"role": "user", "content": "x"}], "anthropic", "claude", "abc")
        result = delete("abc")
        assert result is False
        # The auto file should still exist
        assert (isolated_sessions_dir / "_auto_abc.json").exists()


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------


class TestListSessions:
    def test_empty_when_no_sessions(self, isolated_sessions_dir):
        assert list_sessions() == []

    def test_excludes_auto_by_default(self, isolated_sessions_dir):
        save([{"role": "user", "content": "x"}], "anthropic", "claude", name="real")
        auto_save([{"role": "user", "content": "x"}], "anthropic", "claude", "autoid")
        sessions = list_sessions()
        names = [s["name"] for s in sessions]
        assert "real" in names
        assert not any("_auto_" in n for n in names)

    def test_includes_auto_when_requested(self, isolated_sessions_dir):
        save([{"role": "user", "content": "x"}], "anthropic", "claude", name="real")
        auto_save([{"role": "user", "content": "x"}], "anthropic", "claude", "autoid")
        sessions = list_sessions(include_auto=True)
        names = [s["name"] for s in sessions]
        assert any("_auto_" in n for n in names)

    def test_sorted_by_updated_desc(self, isolated_sessions_dir):
        # Create two sessions with slightly different timestamps by writing directly
        t_old = time.time() - 100
        t_new = time.time()

        old = {"session_id": "a", "name": "older", "created": t_old, "updated": t_old,
               "provider": "x", "model": "y", "messages": []}
        new = {"session_id": "b", "name": "newer", "created": t_new, "updated": t_new,
               "provider": "x", "model": "y", "messages": []}

        (isolated_sessions_dir / "older.json").write_text(json.dumps(old))
        (isolated_sessions_dir / "newer.json").write_text(json.dumps(new))

        sessions = list_sessions()
        assert sessions[0]["name"] == "newer"
        assert sessions[1]["name"] == "older"

    def test_session_metadata_fields_present(self, isolated_sessions_dir):
        save([{"role": "user", "content": "x"}], "openai", "gpt-4o", name="fieldtest")
        sessions = list_sessions()
        assert len(sessions) == 1
        s = sessions[0]
        assert "name" in s
        assert "updated" in s
        assert "message_count" in s
        assert "provider" in s
        assert "model" in s
        assert "filename" in s

    def test_message_count_correct(self, isolated_sessions_dir):
        msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        save(msgs, "anthropic", "claude", name="countcheck")
        sessions = list_sessions()
        assert sessions[0]["message_count"] == 2

    def test_skips_corrupt_files_silently(self, isolated_sessions_dir):
        (isolated_sessions_dir / "corrupt.json").write_text("not json")
        sessions = list_sessions()
        assert sessions == []


# ---------------------------------------------------------------------------
# format_sessions_table
# ---------------------------------------------------------------------------


class TestFormatSessionsTable:
    def test_no_sessions_message(self, isolated_sessions_dir):
        out = format_sessions_table()
        assert "No saved sessions" in out

    def test_with_sessions_has_header(self, isolated_sessions_dir):
        save([{"role": "user", "content": "x"}], "anthropic", "claude", name="s1")
        out = format_sessions_table()
        # Header columns
        assert "NAME" in out
        assert "MSGS" in out

    def test_with_sessions_contains_session_name(self, isolated_sessions_dir):
        save([{"role": "user", "content": "x"}], "anthropic", "claude", name="mytest")
        out = format_sessions_table()
        assert "mytest" in out
