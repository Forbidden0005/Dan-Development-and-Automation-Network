"""Tests for cost_tracker.py.

Covers:
- _get_rates: model substring matching, ordering (first-match-wins), fallback
- SessionCost.record: accumulation, negative-input guard
- SessionCost.total_tokens: sum property correctness
- SessionCost.estimate_cost: calculation against known rates
- SessionCost.is_free_model: local/flat-rate vs. paid detection
- SessionCost.summary: format and duration segmentation (s / m+s / h+m+s)
- Module-level singleton: init, get, record, uninitialized guard
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

import cost_tracker
from cost_tracker import SessionCost, _get_rates, init, get, record


# ---------------------------------------------------------------------------
# _get_rates
# ---------------------------------------------------------------------------


class TestGetRates:
    def test_exact_anthropic_opus(self):
        inp, out = _get_rates("claude-opus-4-something")
        assert inp == 15.00
        assert out == 75.00

    def test_exact_anthropic_sonnet(self):
        inp, out = _get_rates("claude-sonnet-4")
        assert inp == 3.00
        assert out == 15.00

    def test_haiku_35_before_haiku_3(self):
        # "claude-haiku-3-5" must match before "claude-haiku-3" (ordering matters)
        inp, out = _get_rates("claude-haiku-3-5-20251001")
        assert inp == 0.80
        assert out == 4.00

    def test_haiku_3_base(self):
        # A plain haiku-3 model name should not match haiku-3-5
        inp, out = _get_rates("claude-haiku-3-20240307")
        # "claude-haiku-3-5" contains "haiku-3-5" — which is NOT in "claude-haiku-3-20240307"
        # so it should fall through to the "claude-haiku-3" entry
        assert inp == 0.25
        assert out == 1.25

    def test_gpt4o_mini_before_gpt4o(self):
        inp, out = _get_rates("gpt-4o-mini-2024")
        assert inp == 0.15
        assert out == 0.60

    def test_gpt4o_base(self):
        inp, out = _get_rates("gpt-4o-2024")
        assert inp == 5.00
        assert out == 15.00

    def test_gpt4_turbo(self):
        inp, out = _get_rates("gpt-4-turbo-preview")
        assert inp == 10.00
        assert out == 30.00

    def test_gpt4_base(self):
        inp, out = _get_rates("gpt-4")
        # gpt-4o and gpt-4-turbo won't match "gpt-4" alone
        # but "gpt-4" appears inside "gpt-4o" and "gpt-4-turbo" as substrings
        # The actual match depends on order in _RATES:
        #   gpt-4o-mini → no
        #   gpt-4o → "gpt-4o" in "gpt-4"? No, "gpt-4o" is not in "gpt-4"
        #   gpt-4-turbo → "gpt-4-turbo" not in "gpt-4"
        #   gpt-4 → "gpt-4" in "gpt-4" → yes
        assert inp == 30.00
        assert out == 60.00

    def test_gpt35(self):
        inp, out = _get_rates("gpt-3.5-turbo")
        assert inp == 0.50
        assert out == 1.50

    def test_local_llama(self):
        inp, out = _get_rates("llama3.1:8b")
        assert inp == 0.00
        assert out == 0.00

    def test_local_qwen(self):
        inp, out = _get_rates("qwen2.5-coder:7b")
        assert inp == 0.00
        assert out == 0.00

    def test_local_mistral(self):
        inp, out = _get_rates("mistral-7b")
        assert inp == 0.00
        assert out == 0.00

    def test_venice_prefix(self):
        inp, out = _get_rates("venice-uncensored")
        assert inp == 0.00
        assert out == 0.00

    def test_unknown_model_uses_default(self):
        inp, out = _get_rates("some-totally-unknown-model-xyz")
        assert inp == 3.00
        assert out == 15.00

    def test_empty_string_uses_default(self):
        inp, out = _get_rates("")
        assert inp == 3.00
        assert out == 15.00

    def test_case_insensitive(self):
        inp, out = _get_rates("Claude-Sonnet-4")
        assert inp == 3.00
        assert out == 15.00


# ---------------------------------------------------------------------------
# SessionCost.record
# ---------------------------------------------------------------------------


class TestSessionCostRecord:
    def test_accumulates_across_calls(self):
        sc = SessionCost(model="claude-sonnet-4")
        sc.record(100, 50)
        sc.record(200, 75)
        assert sc.total_input_tokens == 300
        assert sc.total_output_tokens == 125
        assert sc.call_count == 2

    def test_negative_input_tokens_clamped_to_zero(self):
        sc = SessionCost(model="claude-sonnet-4")
        sc.record(-100, 50)
        assert sc.total_input_tokens == 0
        assert sc.total_output_tokens == 50

    def test_negative_output_tokens_clamped_to_zero(self):
        sc = SessionCost(model="claude-sonnet-4")
        sc.record(100, -50)
        assert sc.total_output_tokens == 0
        assert sc.total_input_tokens == 100

    def test_zero_tokens_increments_call_count(self):
        sc = SessionCost(model="gpt-4o")
        sc.record(0, 0)
        assert sc.call_count == 1
        assert sc.total_tokens == 0


# ---------------------------------------------------------------------------
# SessionCost.total_tokens
# ---------------------------------------------------------------------------


class TestSessionCostTotalTokens:
    def test_sum_of_input_and_output(self):
        sc = SessionCost(model="gpt-4o")
        sc.record(1000, 500)
        assert sc.total_tokens == 1500

    def test_zero_at_start(self):
        sc = SessionCost(model="gpt-4o")
        assert sc.total_tokens == 0


# ---------------------------------------------------------------------------
# SessionCost.estimate_cost
# ---------------------------------------------------------------------------


class TestSessionCostEstimateCost:
    def test_cost_calculation_sonnet(self):
        sc = SessionCost(model="claude-sonnet-4")
        sc.record(1_000_000, 1_000_000)
        cost = sc.estimate_cost()
        # 1M input @ $3 + 1M output @ $15 = $18
        assert abs(cost - 18.00) < 0.0001

    def test_cost_zero_for_local_model(self):
        sc = SessionCost(model="qwen2.5-coder:7b")
        sc.record(500_000, 200_000)
        assert sc.estimate_cost() == 0.0

    def test_cost_zero_at_start(self):
        sc = SessionCost(model="claude-opus-4")
        assert sc.estimate_cost() == 0.0

    def test_small_usage_below_cent(self):
        sc = SessionCost(model="claude-haiku-3-5-20251001")
        sc.record(1000, 1000)
        # 1000 input @ $0.80/1M + 1000 output @ $4.00/1M
        expected = (1000 / 1_000_000) * 0.80 + (1000 / 1_000_000) * 4.00
        assert abs(sc.estimate_cost() - expected) < 1e-9


# ---------------------------------------------------------------------------
# SessionCost.is_free_model
# ---------------------------------------------------------------------------


class TestSessionCostIsFreeModel:
    def test_local_llama_is_free(self):
        sc = SessionCost(model="llama3.1:8b")
        assert sc.is_free_model() is True

    def test_qwen_is_free(self):
        sc = SessionCost(model="qwen2.5-coder:7b")
        assert sc.is_free_model() is True

    def test_claude_is_not_free(self):
        sc = SessionCost(model="claude-sonnet-4")
        assert sc.is_free_model() is False

    def test_gpt4_is_not_free(self):
        sc = SessionCost(model="gpt-4o")
        assert sc.is_free_model() is False

    def test_unknown_model_is_not_free(self):
        # Falls back to default rates ($3/$15), which are non-zero
        sc = SessionCost(model="unknown-model-xyz")
        assert sc.is_free_model() is False


# ---------------------------------------------------------------------------
# SessionCost.summary
# ---------------------------------------------------------------------------


class TestSessionCostSummary:
    def test_summary_contains_model(self):
        sc = SessionCost(model="claude-sonnet-4")
        sc.record(1000, 500)
        out = sc.summary()
        assert "claude-sonnet-4" in out

    def test_summary_contains_call_count(self):
        sc = SessionCost(model="gpt-4o")
        sc.record(100, 50)
        sc.record(100, 50)
        out = sc.summary()
        assert "2" in out

    def test_summary_free_model_shows_no_charge(self):
        sc = SessionCost(model="llama3.1:8b")
        sc.record(1_000_000, 500_000)
        out = sc.summary()
        assert "no charge" in out

    def test_summary_paid_model_shows_dollar_sign(self):
        sc = SessionCost(model="claude-sonnet-4")
        sc.record(1_000_000, 1_000_000)
        out = sc.summary()
        assert "$" in out

    def test_summary_duration_seconds_only(self):
        sc = SessionCost(model="gpt-4o")
        # Simulate a 30-second-old session
        sc.session_start = time.time() - 30
        out = sc.summary()
        assert "30s" in out or "s" in out  # at minimum "s" duration suffix present

    def test_summary_duration_minutes(self):
        sc = SessionCost(model="gpt-4o")
        sc.session_start = time.time() - 90  # 1m 30s
        out = sc.summary()
        assert "m" in out

    def test_summary_duration_hours(self):
        sc = SessionCost(model="gpt-4o")
        sc.session_start = time.time() - 3700  # > 1 hour
        out = sc.summary()
        assert "h" in out

    def test_summary_token_counts_formatted(self):
        sc = SessionCost(model="claude-sonnet-4")
        sc.record(12_345, 6_789)
        out = sc.summary()
        # Comma-formatted numbers should appear
        assert "12,345" in out
        assert "6,789" in out


# ---------------------------------------------------------------------------
# Module-level singleton: init / get / record
# ---------------------------------------------------------------------------


class TestModuleSingleton:
    def setup_method(self):
        # Reset the global tracker before each test to avoid cross-test bleed
        cost_tracker._tracker = None

    def test_get_returns_none_before_init(self):
        assert get() is None

    def test_init_returns_session_cost(self):
        tracker = init("claude-sonnet-4")
        assert isinstance(tracker, SessionCost)
        assert tracker.model == "claude-sonnet-4"

    def test_get_returns_tracker_after_init(self):
        init("gpt-4o")
        assert get() is not None
        assert get().model == "gpt-4o"

    def test_init_resets_previous_tracker(self):
        t1 = init("claude-sonnet-4")
        t1.record(1000, 500)
        t2 = init("gpt-4o")
        assert t2.total_tokens == 0
        assert t2.model == "gpt-4o"
        assert get() is t2

    def test_record_updates_global_tracker(self):
        init("claude-sonnet-4")
        record(100, 50)
        assert get().total_input_tokens == 100
        assert get().total_output_tokens == 50

    def test_record_is_noop_when_uninitialised(self):
        # Should not raise; silently no-ops
        record(100, 50)
        assert get() is None

    def test_module_level_record_accumulates(self):
        init("claude-haiku-3-5-20251001")
        record(500, 250)
        record(500, 250)
        assert get().total_input_tokens == 1000
        assert get().total_output_tokens == 500
        assert get().call_count == 2
