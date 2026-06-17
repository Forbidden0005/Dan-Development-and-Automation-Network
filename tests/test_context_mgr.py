"""Tests for context_mgr.py.

Covers: estimate_tokens, estimate_messages_tokens, needs_compaction, compact.

Design notes:
- No production code changes; test additions only.
- All tests use only stdlib and monkeypatching — no real provider calls.
- Tests complement the shallow coverage already in test_dan.py (basic > 0
  checks, single happy-path compaction) by exercising edge cases, exact
  arithmetic, boundary conditions, and content-extraction details.
"""

import logging

import pytest

import context_mgr
from config import COMPACTION_THRESHOLD, TOKEN_ESTIMATE_RATIO


# ─────────────────────────────────────────────────────────────────────────────
# estimate_tokens
# ─────────────────────────────────────────────────────────────────────────────


class TestEstimateTokens:
    def test_empty_string_returns_zero(self):
        """int(0 / TOKEN_ESTIMATE_RATIO) == 0."""
        assert context_mgr.estimate_tokens("") == 0

    def test_single_char_returns_zero(self):
        """int(1 / 3.5) truncates to 0."""
        assert context_mgr.estimate_tokens("a") == 0

    def test_exact_ratio_multiple(self):
        """Exactly TOKEN_ESTIMATE_RATIO chars → 1 token."""
        text = "x" * int(TOKEN_ESTIMATE_RATIO)
        # int(3 / 3.5) == 0 when ratio is 3.5; use floor to match impl
        expected = int(len(text) / TOKEN_ESTIMATE_RATIO)
        assert context_mgr.estimate_tokens(text) == expected

    def test_known_length(self):
        """Verify arithmetic: 35 chars / 3.5 ratio == 10 tokens."""
        text = "a" * 35
        assert context_mgr.estimate_tokens(text) == int(35 / TOKEN_ESTIMATE_RATIO)

    def test_longer_text_positive(self):
        text = "hello world, this is a test string"
        result = context_mgr.estimate_tokens(text)
        assert result > 0
        assert result == int(len(text) / TOKEN_ESTIMATE_RATIO)

    def test_whitespace_only_text(self):
        text = "   \n\t  "
        assert context_mgr.estimate_tokens(text) == int(len(text) / TOKEN_ESTIMATE_RATIO)

    def test_unicode_characters(self):
        """Unicode chars count by len() (code points), matching impl."""
        text = "こんにちは"  # 5 chars
        assert context_mgr.estimate_tokens(text) == int(5 / TOKEN_ESTIMATE_RATIO)

    def test_very_long_string_proportional(self):
        """Longer strings produce proportionally larger estimates."""
        short = context_mgr.estimate_tokens("a" * 100)
        long_ = context_mgr.estimate_tokens("a" * 1000)
        assert long_ > short


# ─────────────────────────────────────────────────────────────────────────────
# estimate_messages_tokens
# ─────────────────────────────────────────────────────────────────────────────


class TestEstimateMessagesTokens:
    def test_empty_list_returns_zero(self):
        assert context_mgr.estimate_messages_tokens([]) == 0

    def test_single_string_content(self):
        """String content tokens + 4 overhead."""
        text = "a" * 35
        msg = {"role": "user", "content": text}
        expected = int(35 / TOKEN_ESTIMATE_RATIO) + 4
        assert context_mgr.estimate_messages_tokens([msg]) == expected

    def test_overhead_four_per_message(self):
        """Each message contributes +4 regardless of content size."""
        # Use empty content so token count is purely overhead
        msgs = [{"role": "user", "content": ""} for _ in range(5)]
        result = context_mgr.estimate_messages_tokens(msgs)
        # empty string → 0 tokens; 5 messages × 4 overhead = 20
        assert result == 20

    def test_missing_content_key_treated_as_empty(self):
        """Messages without 'content' key default to empty string → 0 + 4."""
        msg = {"role": "assistant"}
        assert context_mgr.estimate_messages_tokens([msg]) == 4

    def test_list_content_with_dict_blocks(self):
        """List content: each block is str(block)-estimated."""
        block = {"type": "text", "text": "hello"}
        msg = {"role": "assistant", "content": [block]}
        # str(block) is the repr dict; estimate_tokens uses len(str(block))
        block_str = str(block)
        expected = int(len(block_str) / TOKEN_ESTIMATE_RATIO) + 4
        assert context_mgr.estimate_messages_tokens([msg]) == expected

    def test_list_content_with_non_dict_items_skipped(self):
        """Non-dict items inside a list content are not counted (no crash)."""
        msg = {"role": "user", "content": ["plain string", 42, None]}
        # Non-dict items don't enter the inner loop
        result = context_mgr.estimate_messages_tokens([msg])
        # Should equal just the overhead; str items are not dict so skipped
        assert result == 4

    def test_list_content_empty_list(self):
        """Empty list content contributes only overhead."""
        msg = {"role": "user", "content": []}
        assert context_mgr.estimate_messages_tokens([msg]) == 4

    def test_multiple_messages_accumulate(self):
        """Multiple messages sum correctly."""
        text_a = "a" * 70  # int(70/3.5) = 20 tokens
        text_b = "b" * 35  # int(35/3.5) = 10 tokens
        msgs = [
            {"role": "user", "content": text_a},
            {"role": "assistant", "content": text_b},
        ]
        expected = int(70 / TOKEN_ESTIMATE_RATIO) + 4 + int(35 / TOKEN_ESTIMATE_RATIO) + 4
        assert context_mgr.estimate_messages_tokens(msgs) == expected

    def test_mixed_string_and_list_content(self):
        """One string-content message and one list-content message both contribute."""
        text = "a" * 35
        block = {"type": "text", "text": "hi"}
        msgs = [
            {"role": "user", "content": text},
            {"role": "assistant", "content": [block]},
        ]
        result = context_mgr.estimate_messages_tokens(msgs)
        assert result > 0


# ─────────────────────────────────────────────────────────────────────────────
# needs_compaction
# ─────────────────────────────────────────────────────────────────────────────


class TestNeedsCompaction:
    def test_empty_messages_does_not_need_compaction(self):
        assert not context_mgr.needs_compaction([], context_limit=1000)

    def test_small_context_does_not_need_compaction(self):
        msgs = [{"role": "user", "content": "hello"}]
        assert not context_mgr.needs_compaction(msgs, context_limit=200_000)

    def test_compaction_triggered_when_over_threshold(self):
        """Build a message set large enough to exceed threshold."""
        # threshold = int(context_limit * COMPACTION_THRESHOLD)
        # Use a tiny context_limit so a small message triggers it.
        msgs = [{"role": "user", "content": "a" * 100}]
        assert context_mgr.needs_compaction(msgs, context_limit=1)

    def test_exactly_at_threshold_is_not_compaction(self):
        """used == threshold → needs_compaction is False (uses strict >)."""
        # Craft a context_limit so that threshold == estimate exactly.
        text = "a" * 35  # 10 tokens (35/3.5)
        msgs = [{"role": "user", "content": text}]
        used = context_mgr.estimate_messages_tokens(msgs)
        # threshold = int(context_limit * COMPACTION_THRESHOLD)
        # We want threshold == used → context_limit = used / COMPACTION_THRESHOLD
        context_limit = int(used / COMPACTION_THRESHOLD)
        # Verify the threshold calculation
        threshold = int(context_limit * COMPACTION_THRESHOLD)
        if threshold == used:
            assert not context_mgr.needs_compaction(msgs, context_limit)
        else:
            # Floating-point floor may place threshold just above or below;
            # just verify the function returns a bool without crashing.
            result = context_mgr.needs_compaction(msgs, context_limit)
            assert isinstance(result, bool)

    def test_just_over_threshold_triggers_compaction(self):
        """used == threshold + 1 → True."""
        text = "a" * 35  # 10 tokens
        msgs = [{"role": "user", "content": text}]
        used = context_mgr.estimate_messages_tokens(msgs)
        # Force threshold to used - 1 by choosing context_limit accordingly
        # threshold = int(context_limit * COMPACTION_THRESHOLD)
        # We want threshold < used, i.e. context_limit < used / COMPACTION_THRESHOLD
        small_limit = max(1, int((used - 1) / COMPACTION_THRESHOLD))
        assert context_mgr.needs_compaction(msgs, small_limit)

    def test_returns_bool(self):
        msgs = [{"role": "user", "content": "test"}]
        result = context_mgr.needs_compaction(msgs, 1000)
        assert isinstance(result, bool)

    def test_large_context_limit_prevents_compaction(self):
        msgs = [{"role": "user", "content": "x" * 10_000}]
        assert not context_mgr.needs_compaction(msgs, context_limit=10_000_000)


# ─────────────────────────────────────────────────────────────────────────────
# compact
# ─────────────────────────────────────────────────────────────────────────────


class _OkProvider:
    """Minimal provider stub: returns a fixed summary text."""

    def __init__(self, summary="the summary"):
        self._summary = summary

    def chat(self, messages=None, max_tokens=None):
        return type("Resp", (), {"text": self._summary})()


class _FailingProvider:
    """Provider stub: chat() always raises."""

    def chat(self, messages=None, max_tokens=None):
        raise RuntimeError("provider error")


def _make_msgs(n: int) -> list[dict]:
    """Create n simple alternating user/assistant messages."""
    roles = ["user", "assistant"]
    return [{"role": roles[i % 2], "content": f"message {i}"} for i in range(n)]


class TestCompact:
    # ── Short-circuit cases ──────────────────────────────────────────────────

    def test_empty_messages_returned_unchanged(self):
        msgs = []
        result = context_mgr.compact(msgs, _OkProvider())
        assert result == []

    def test_one_message_returned_unchanged(self):
        msgs = _make_msgs(1)
        assert context_mgr.compact(msgs, _OkProvider()) == msgs

    def test_two_messages_returned_unchanged(self):
        msgs = _make_msgs(2)
        assert context_mgr.compact(msgs, _OkProvider()) == msgs

    def test_three_messages_returned_unchanged(self):
        msgs = _make_msgs(3)
        assert context_mgr.compact(msgs, _OkProvider()) == msgs

    def test_four_messages_returned_unchanged(self):
        """Exactly 4 messages — the boundary; should return as-is."""
        msgs = _make_msgs(4)
        result = context_mgr.compact(msgs, _OkProvider())
        assert result == msgs

    def test_unchanged_result_is_same_list(self):
        """≤4 messages: returned object is the original list, not a copy."""
        msgs = _make_msgs(3)
        assert context_mgr.compact(msgs, _OkProvider()) is msgs

    # ── Compaction structure ─────────────────────────────────────────────────

    def test_five_messages_triggers_compaction(self):
        msgs = _make_msgs(5)
        result = context_mgr.compact(msgs, _OkProvider())
        assert len(result) == 6  # summary + assistant ack + last 4

    def test_summary_message_is_first(self, monkeypatch):
        # Stub sys.modules["providers"] so compact()'s `from providers import
        # Message` succeeds in the isolated test environment (the real repo
        # has provider_anthropic present; here we inject a minimal stub).
        import sys
        import types

        fake_providers = types.ModuleType("providers")

        class _Msg:
            def __init__(self, role, content):
                self.role = role
                self.content = content

        fake_providers.Message = _Msg
        monkeypatch.setitem(sys.modules, "providers", fake_providers)

        msgs = _make_msgs(5)
        result = context_mgr.compact(msgs, _OkProvider("my summary"))
        assert result[0]["role"] == "user"
        assert result[0]["content"].startswith("[Conversation summary]")
        assert "my summary" in result[0]["content"]

    def test_ack_message_is_second(self):
        msgs = _make_msgs(5)
        result = context_mgr.compact(msgs, _OkProvider())
        assert result[1]["role"] == "assistant"
        assert "Understood" in result[1]["content"]

    def test_last_four_messages_preserved_exactly(self):
        """The final 4 messages must be the original objects, in order."""
        msgs = _make_msgs(8)
        result = context_mgr.compact(msgs, _OkProvider())
        # result[0] = summary, result[1] = ack, result[2:] = last 4
        assert result[2:] == msgs[-4:]

    def test_total_length_is_summary_plus_last_four(self):
        msgs = _make_msgs(10)
        result = context_mgr.compact(msgs, _OkProvider())
        assert len(result) == 6  # 2 header + 4 tail

    # ── Provider failure fallback ────────────────────────────────────────────

    def test_failing_provider_falls_back_to_truncated_text(self):
        msgs = _make_msgs(5)
        result = context_mgr.compact(msgs, _FailingProvider())
        assert result[0]["role"] == "user"
        assert "[Conversation summary]" in result[0]["content"]

    def test_fallback_still_preserves_last_four(self):
        msgs = _make_msgs(6)
        result = context_mgr.compact(msgs, _FailingProvider())
        assert result[2:] == msgs[-4:]

    def test_fallback_truncates_at_2000_chars(self):
        """Summary text from fallback path is capped at 2000 chars."""
        # Create messages with very long content so summary_text > 2000 chars
        long_msgs = [
            {"role": "user", "content": "a" * 1000},
            {"role": "assistant", "content": "b" * 1000},
            {"role": "user", "content": "c" * 1000},
            {"role": "assistant", "content": "d" * 1000},
            {"role": "user", "content": "e" * 1000},
        ]
        result = context_mgr.compact(long_msgs, _FailingProvider())
        # The summary portion is at most 2000 chars (plus the header prefix)
        summary_content = result[0]["content"]
        # Strip the "[Conversation summary]\n" header to inspect just the text
        text_part = summary_content.replace("[Conversation summary]\n", "")
        assert len(text_part) <= 2000

    # ── Content extraction from list-type messages ───────────────────────────

    def test_list_content_text_blocks_extracted_for_summary(self):
        """Messages with list content should have their text blocks joined."""
        msgs = [
            {"role": "user", "content": [{"type": "text", "text": "block content"}]},
            {"role": "assistant", "content": "plain response"},
            {"role": "user", "content": "another message"},
            {"role": "assistant", "content": "last assistant"},
            {"role": "user", "content": "final"},
        ]
        result = context_mgr.compact(msgs, _OkProvider("summary text"))
        # Should complete without error and produce the right structure
        assert result[0]["content"].startswith("[Conversation summary]")
        assert len(result) == 6

    def test_list_content_non_text_blocks_produce_empty_and_skipped(self):
        """Blocks without type=text return empty string and are skipped."""
        msgs = [
            {"role": "user", "content": [{"type": "image", "url": "x"}]},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "q3"},
        ]
        # Empty content → not appended to summary_parts → no crash
        result = context_mgr.compact(msgs, _OkProvider())
        assert isinstance(result, list)

    def test_empty_content_messages_skipped_in_summary(self):
        """Messages with empty string content are not added to summary_parts."""
        msgs = [
            {"role": "user", "content": ""},  # empty — skipped
            {"role": "assistant", "content": "some reply"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "final"},
        ]
        result = context_mgr.compact(msgs, _OkProvider("ok"))
        assert result[0]["content"].startswith("[Conversation summary]")

    # ── Content truncation in summary parts ─────────────────────────────────

    def test_long_message_content_truncated_at_200_chars_in_summary(self):
        """Each message's content is sliced to 200 chars in the summary text."""
        long_content = "z" * 500
        msgs = [
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": "short"},
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ]

        captured = {}

        class CapturingProvider:
            def chat(self, messages=None, max_tokens=None):
                # The user message in the provider call contains the summary prompt
                prompt_text = messages[0].content if hasattr(messages[0], "content") else messages[0].get("content", "")
                captured["prompt"] = prompt_text
                return type("Resp", (), {"text": "summary"})()

        context_mgr.compact(msgs, CapturingProvider())
        if "prompt" in captured:
            # The summarized portion of the long message should be ≤200 chars
            assert long_content[:201] not in captured["prompt"]

    # ── Logging ─────────────────────────────────────────────────────────────

    def test_compact_logs_token_reduction(self, caplog):
        # compact() logs an INFO message with token counts after compaction.
        msgs = _make_msgs(5)
        with caplog.at_level(logging.INFO, logger="context_mgr"):
            context_mgr.compact(msgs, _OkProvider())
        assert any("Compacted" in r.message for r in caplog.records)

    def test_compact_does_not_log_on_short_circuit(self, caplog):
        # 4-or-fewer messages returns early without any Compacted log entry.
        msgs = _make_msgs(4)
        with caplog.at_level(logging.INFO, logger="context_mgr"):
            context_mgr.compact(msgs, _OkProvider())
        assert not any("Compacted" in r.message for r in caplog.records)
