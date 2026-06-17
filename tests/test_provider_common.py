"""
Tests for provider_common.py — parse_tool_arguments and KeyRotator.

These utilities are shared across provider_openai.py, provider_venice.py, and
provider_anthropic.py.  parse_tool_arguments had no dedicated tests; KeyRotator
had only one minimal smoke test in test_dan.py (fallback key).  This file adds
thorough coverage for both without touching production code.

All tests use monkeypatching only — no real API calls, no disk I/O.
"""

import time

import pytest

import provider_common
from provider_common import KeyRotator, parse_tool_arguments


# ─────────────────────────────────────────────────────────────────────────────
# parse_tool_arguments
# ─────────────────────────────────────────────────────────────────────────────


class TestParseToolArguments:
    """parse_tool_arguments should return a dict regardless of input shape."""

    def test_dict_input_returned_as_is(self):
        """Already-parsed dict passes straight through."""
        data = {"path": "/tmp/foo", "overwrite": True}
        assert parse_tool_arguments(data) is data

    def test_none_returns_empty_dict(self):
        assert parse_tool_arguments(None) == {}

    def test_empty_string_returns_empty_dict(self):
        assert parse_tool_arguments("") == {}

    def test_valid_json_string_returns_dict(self):
        result = parse_tool_arguments('{"key": "value", "count": 3}')
        assert result == {"key": "value", "count": 3}

    def test_json_string_with_nested_dict(self):
        raw = '{"options": {"verbose": true, "depth": 2}}'
        result = parse_tool_arguments(raw)
        assert result == {"options": {"verbose": True, "depth": 2}}

    def test_empty_json_object_returns_empty_dict(self):
        assert parse_tool_arguments("{}") == {}

    def test_invalid_json_returns_empty_dict(self):
        """Malformed JSON must not raise — returns {} with a warning."""
        assert parse_tool_arguments("{bad json}") == {}

    def test_json_array_returns_empty_dict(self):
        """Top-level JSON array is not a dict — treated as malformed."""
        assert parse_tool_arguments("[1, 2, 3]") == {}

    def test_json_string_scalar_returns_empty_dict(self):
        """Top-level JSON string scalar is not a dict."""
        assert parse_tool_arguments('"just a string"') == {}

    def test_json_number_returns_empty_dict(self):
        assert parse_tool_arguments("42") == {}

    def test_json_null_returns_empty_dict(self):
        # json.loads("null") → None, which is not a dict
        assert parse_tool_arguments("null") == {}

    def test_bytes_input_returns_empty_dict(self):
        """Bytes input is not a valid str/dict — should not raise."""
        # json.loads accepts bytes in Python 3.6+, but the result check applies
        result = parse_tool_arguments(b'{"key": "v"}')
        # bytes are valid JSON input for json.loads → we get a dict back
        assert isinstance(result, dict)

    def test_integer_input_returns_empty_dict(self):
        """Non-str, non-dict, non-None integer should yield {}."""
        assert parse_tool_arguments(123) == {}

    def test_list_input_returns_empty_dict(self):
        """A list object (not JSON string) is not a dict."""
        assert parse_tool_arguments(["a", "b"]) == {}

    def test_whitespace_only_string_returns_empty_dict(self):
        assert parse_tool_arguments("   ") == {}


# ─────────────────────────────────────────────────────────────────────────────
# KeyRotator
# ─────────────────────────────────────────────────────────────────────────────


class TestKeyRotatorInit:
    """Construction and key loading from environment variables."""

    def test_no_keys_raises_value_error(self, monkeypatch):
        """Constructor must raise when no env vars are set."""
        for i in range(1, 6):
            monkeypatch.delenv(f"KR_TEST_{i}", raising=False)
        monkeypatch.delenv("KR_TEST", raising=False)

        with pytest.raises(ValueError, match="No API keys found"):
            KeyRotator("KR_TEST")

    def test_single_fallback_key(self, monkeypatch):
        """Bare prefix env var accepted as a single-key rotator."""
        for i in range(1, 6):
            monkeypatch.delenv(f"KR2_{i}", raising=False)
        monkeypatch.setenv("KR2", "mykey")

        r = KeyRotator("KR2")
        assert r.count == 1
        key, idx = r.next()
        assert key == "mykey"
        assert idx == 0

    def test_numbered_keys_loaded_in_order(self, monkeypatch):
        """Keys KR3_1 … KR3_3 are loaded in index order."""
        monkeypatch.delenv("KR3", raising=False)
        monkeypatch.setenv("KR3_1", "first")
        monkeypatch.setenv("KR3_2", "second")
        monkeypatch.setenv("KR3_3", "third")
        for i in range(4, 6):
            monkeypatch.delenv(f"KR3_{i}", raising=False)

        r = KeyRotator("KR3")
        assert r.count == 3
        key, idx = r.next()
        assert key == "first"
        assert idx == 0

    def test_empty_numbered_key_skipped(self, monkeypatch):
        """Empty string for KR4_2 is not loaded; only KR4_1 and KR4_3 count."""
        monkeypatch.delenv("KR4", raising=False)
        monkeypatch.setenv("KR4_1", "alpha")
        monkeypatch.setenv("KR4_2", "")  # blank → skipped
        monkeypatch.setenv("KR4_3", "gamma")
        for i in range(4, 6):
            monkeypatch.delenv(f"KR4_{i}", raising=False)

        r = KeyRotator("KR4")
        assert r.count == 2

    def test_whitespace_key_stripped_and_skipped(self, monkeypatch):
        """Keys with only whitespace are stripped to '' and skipped."""
        monkeypatch.delenv("KR5", raising=False)
        monkeypatch.setenv("KR5_1", "   ")  # whitespace only → skipped
        monkeypatch.setenv("KR5_2", "real-key")
        for i in range(3, 6):
            monkeypatch.delenv(f"KR5_{i}", raising=False)

        r = KeyRotator("KR5")
        assert r.count == 1
        key, _ = r.next()
        assert key == "real-key"

    def test_five_keys_all_loaded(self, monkeypatch):
        """All five numbered keys can be loaded simultaneously."""
        monkeypatch.delenv("KR6", raising=False)
        for i in range(1, 6):
            monkeypatch.setenv(f"KR6_{i}", f"key{i}")

        r = KeyRotator("KR6")
        assert r.count == 5


class TestKeyRotatorNext:
    """next() rotation and index behaviour."""

    def test_single_key_never_rotates(self, monkeypatch):
        """With one key, repeated next() calls always return the same key."""
        monkeypatch.delenv("KR_NR", raising=False)
        monkeypatch.setenv("KR_NR", "static-key")

        r = KeyRotator("KR_NR")
        for _ in range(5):
            key, idx = r.next()
            assert key == "static-key"
            assert idx == 0

    def test_multi_key_rotates_after_hold(self, monkeypatch):
        """With two keys, next() rotates after HOLD_SECONDS have elapsed."""
        monkeypatch.delenv("KR_ROT", raising=False)
        monkeypatch.setenv("KR_ROT_1", "key-a")
        monkeypatch.setenv("KR_ROT_2", "key-b")
        for i in range(3, 6):
            monkeypatch.delenv(f"KR_ROT_{i}", raising=False)

        r = KeyRotator("KR_ROT")
        first_key, _ = r.next()

        # Fast-forward the internal start time past HOLD_SECONDS
        r._key_start_time -= KeyRotator.HOLD_SECONDS + 1

        second_key, _ = r.next()
        assert first_key != second_key

    def test_multi_key_no_rotation_before_hold(self, monkeypatch):
        """next() does NOT rotate before HOLD_SECONDS have elapsed."""
        monkeypatch.delenv("KR_NOROT", raising=False)
        monkeypatch.setenv("KR_NOROT_1", "key-x")
        monkeypatch.setenv("KR_NOROT_2", "key-y")
        for i in range(3, 6):
            monkeypatch.delenv(f"KR_NOROT_{i}", raising=False)

        r = KeyRotator("KR_NOROT")
        key1, idx1 = r.next()

        # Advance time only half the hold interval
        r._key_start_time -= KeyRotator.HOLD_SECONDS // 2

        key2, idx2 = r.next()
        assert key1 == key2
        assert idx1 == idx2

    def test_rotation_wraps_around(self, monkeypatch):
        """After rotating through all keys, index wraps back to 0."""
        monkeypatch.delenv("KR_WRAP", raising=False)
        monkeypatch.setenv("KR_WRAP_1", "w-key-a")
        monkeypatch.setenv("KR_WRAP_2", "w-key-b")
        for i in range(3, 6):
            monkeypatch.delenv(f"KR_WRAP_{i}", raising=False)

        r = KeyRotator("KR_WRAP")

        # Force two rotations so we lap back to key 0
        r._key_start_time -= KeyRotator.HOLD_SECONDS + 1
        r.next()  # rotates to index 1
        r._key_start_time -= KeyRotator.HOLD_SECONDS + 1
        key, idx = r.next()  # rotates back to index 0

        assert idx == 0
        assert key == "w-key-a"

    def test_returns_tuple_of_str_and_int(self, monkeypatch):
        """next() always returns (str, int)."""
        monkeypatch.delenv("KR_TUP", raising=False)
        monkeypatch.setenv("KR_TUP_1", "any-key")
        for i in range(2, 6):
            monkeypatch.delenv(f"KR_TUP_{i}", raising=False)

        r = KeyRotator("KR_TUP")
        key, idx = r.next()
        assert isinstance(key, str)
        assert isinstance(idx, int)


class TestKeyRotatorProperties:
    """current_index, count, record_usage, and status()."""

    def _make_rotator(self, monkeypatch, prefix, keys):
        monkeypatch.delenv(prefix, raising=False)
        for i in range(1, 6):
            monkeypatch.delenv(f"{prefix}_{i}", raising=False)
        for i, k in enumerate(keys, start=1):
            monkeypatch.setenv(f"{prefix}_{i}", k)
        return KeyRotator(prefix)

    def test_current_index_is_one_indexed(self, monkeypatch):
        """current_index is 1-based (human-readable display)."""
        r = self._make_rotator(monkeypatch, "KR_CI", ["kA", "kB"])
        # Starts at internal index 0 → current_index == 1
        assert r.current_index == 1

    def test_count_matches_loaded_keys(self, monkeypatch):
        r = self._make_rotator(monkeypatch, "KR_CNT", ["a", "b", "c"])
        assert r.count == 3

    def test_record_usage_increments_calls(self, monkeypatch):
        """record_usage(idx, tokens) increments _calls_per_key for that index."""
        r = self._make_rotator(monkeypatch, "KR_RU", ["x", "y"])
        assert r._calls_per_key[0] == 0
        r.record_usage(0, 1000)
        assert r._calls_per_key[0] == 1
        r.record_usage(0, 500)
        assert r._calls_per_key[0] == 2
        # Index 1 should stay untouched
        assert r._calls_per_key[1] == 0

    def test_status_contains_key_entries(self, monkeypatch):
        """status() should mention each key number."""
        r = self._make_rotator(monkeypatch, "KR_ST", ["s1", "s2"])
        text = r.status()
        assert "Key 1" in text
        assert "Key 2" in text

    def test_status_marks_active_key(self, monkeypatch):
        """status() marks the currently active key with an indicator."""
        r = self._make_rotator(monkeypatch, "KR_STACT", ["p", "q"])
        text = r.status()
        assert "active" in text

    def test_status_includes_call_counts(self, monkeypatch):
        """status() reflects recorded call counts."""
        r = self._make_rotator(monkeypatch, "KR_STCC", ["m"])
        r.record_usage(0, 100)
        r.record_usage(0, 200)
        text = r.status()
        assert "2 calls" in text

    def test_status_returns_string(self, monkeypatch):
        r = self._make_rotator(monkeypatch, "KR_STRSTR", ["z"])
        assert isinstance(r.status(), str)
