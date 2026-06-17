"""Tests for agent.py.

Covers: AgentInterrupted, _tool_label, select_tool_categories,
        _extract_text_tool_call, _build_assistant_content, _last_message_text.

Design notes:
- No production code changes; test additions only.
- All pure unit tests — no real provider calls, no real tool-registry calls.
- run_agent_loop and build_system_prompt are excluded: they require full
  provider + knowledge infrastructure and belong in integration tests.
- Tests complement the shallow coverage already present in test_dan.py by
  covering edge cases, boundary conditions, and every branch of the
  pure helper functions defined in agent.py.
"""

import pytest

import agent
from providers import Response, ToolCall


# ─────────────────────────────────────────────────────────────────────────────
# AgentInterrupted
# ─────────────────────────────────────────────────────────────────────────────


class TestAgentInterrupted:
    def test_is_base_exception_not_exception(self):
        """Extends BaseException so 'except Exception' blocks cannot swallow it."""
        assert issubclass(agent.AgentInterrupted, BaseException)
        assert not issubclass(agent.AgentInterrupted, Exception)

    def test_checkpoint_stored_on_instance(self):
        """The checkpoint list passed at raise time is accessible on the instance."""
        checkpoint = [{"role": "user", "content": "hello"}]
        exc = agent.AgentInterrupted(checkpoint)
        assert exc.checkpoint is checkpoint

    def test_empty_checkpoint_accepted(self):
        exc = agent.AgentInterrupted([])
        assert exc.checkpoint == []

    def test_str_representation_contains_interrupted(self):
        exc = agent.AgentInterrupted([])
        assert "interrupted" in str(exc)

    def test_not_caught_by_broad_exception_handler(self):
        """A bare 'except Exception' must NOT suppress AgentInterrupted."""
        swallowed = False
        try:
            raise agent.AgentInterrupted([])
        except Exception:
            swallowed = True
        except BaseException:
            pass  # correctly propagated to BaseException level
        assert not swallowed


# ─────────────────────────────────────────────────────────────────────────────
# _tool_label
# ─────────────────────────────────────────────────────────────────────────────


class TestToolLabel:
    def test_websearch_includes_query_text(self):
        label = agent._tool_label("WebSearch", {"query": "python logging"})
        assert "python logging" in label

    def test_webfetch_includes_url(self):
        label = agent._tool_label("WebFetch", {"url": "https://example.com/page"})
        assert "example.com" in label

    def test_webfetch_truncates_long_url_to_70_chars(self):
        url = "https://example.com/" + "x" * 100
        label = agent._tool_label("WebFetch", {"url": url})
        # Lambda slices url[:70]; full URL would make the label much longer.
        assert label.count("x") <= 70

    def test_bash_includes_command(self):
        label = agent._tool_label("Bash", {"command": "pytest -q"})
        assert "pytest -q" in label

    def test_read_includes_path(self):
        label = agent._tool_label("Read", {"path": "src/main.py"})
        assert "src/main.py" in label

    def test_write_includes_path(self):
        label = agent._tool_label("Write", {"path": "output.txt"})
        assert "output.txt" in label

    def test_httprequest_shows_method_and_url(self):
        label = agent._tool_label("HttpRequest", {"method": "POST", "url": "https://api.example.com/v1"})
        assert "POST" in label
        assert "api.example.com" in label

    def test_unknown_tool_returns_name_verbatim(self):
        """Unrecognised tool names fall through to the default (name itself)."""
        label = agent._tool_label("MyCustomTool", {"arg": "value"})
        assert label == "MyCustomTool"

    def test_known_tool_missing_expected_key_uses_empty_default(self):
        """If the expected input key is absent the lambda defaults to ''."""
        label = agent._tool_label("WebSearch", {})
        # Lambda: lambda i: f'Searching: "{i.get("query", "")}"'
        assert label == 'Searching: ""'


# ─────────────────────────────────────────────────────────────────────────────
# select_tool_categories
# ─────────────────────────────────────────────────────────────────────────────


class TestSelectToolCategories:
    def test_short_conversational_no_signals_returns_empty(self):
        """≤5 words with no task-signal word → empty set (no tools needed)."""
        result = agent.select_tool_categories("hello there")
        assert result == set()

    def test_exactly_five_words_no_signals_returns_empty(self):
        """Boundary: exactly 5 words, no signal → still empty."""
        result = agent.select_tool_categories("one two three four five")
        assert result == set()

    def test_six_or_more_words_includes_always_on_categories(self):
        """Six or more words always includes 'core' and 'actions'."""
        result = agent.select_tool_categories("one two three four five six")
        assert "core" in result
        assert "actions" in result

    def test_short_message_with_task_signal_is_not_empty(self):
        """≤5 words but includes a task-signal word → not empty."""
        result = agent.select_tool_categories("please run it")
        assert len(result) > 0

    def test_web_keyword_adds_web_category(self):
        result = agent.select_tool_categories("please fetch this URL for me now")
        assert "web" in result

    def test_git_keyword_adds_git_category(self):
        result = agent.select_tool_categories("show me the git log for this repo")
        assert "git" in result

    def test_code_keyword_adds_code_category(self):
        result = agent.select_tool_categories("run pytest and check coverage now")
        assert "code" in result

    def test_knowledge_keyword_adds_knowledge_category(self):
        result = agent.select_tool_categories("please remember this note for later use")
        assert "knowledge" in result

    def test_workers_keyword_adds_workers_category(self):
        result = agent.select_tool_categories("spawn a worker to process this in parallel")
        assert "workers" in result

    def test_multiple_keywords_returns_multiple_categories(self):
        result = agent.select_tool_categories("search the web and commit results to git")
        assert "web" in result
        assert "git" in result

    def test_always_on_categories_in_any_task_result(self):
        """When categories are returned, core and actions are always present."""
        result = agent.select_tool_categories("fetch this URL right now for me please")
        assert "core" in result
        assert "actions" in result

    def test_case_insensitive_keyword_matching(self):
        """Keywords are matched after lowercasing the input."""
        result = agent.select_tool_categories("FETCH this URL from the web please now")
        assert "web" in result


# ─────────────────────────────────────────────────────────────────────────────
# _extract_text_tool_call
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractTextToolCall:
    def test_plain_text_returns_none(self):
        assert agent._extract_text_tool_call("hello world") is None

    def test_empty_string_returns_none(self):
        assert agent._extract_text_tool_call("") is None

    def test_json_array_not_object_returns_none(self):
        assert agent._extract_text_tool_call("[1, 2, 3]") is None

    def test_json_without_name_key_returns_none(self, monkeypatch):
        monkeypatch.setattr(agent.registry, "get_tool", lambda name: None)
        result = agent._extract_text_tool_call('{"action": "read", "path": "foo.py"}')
        assert result is None

    def test_json_with_unregistered_name_returns_none(self, monkeypatch):
        monkeypatch.setattr(agent.registry, "get_tool", lambda name: None)
        result = agent._extract_text_tool_call('{"name": "UnknownTool", "input": {}}')
        assert result is None

    def test_registered_tool_name_returns_toolcall(self, monkeypatch):
        fake_tool = object()
        monkeypatch.setattr(agent.registry, "get_tool", lambda name: fake_tool if name == "Read" else None)
        result = agent._extract_text_tool_call('{"name": "Read", "input": {"path": "foo.py"}}')
        assert result is not None
        assert result.name == "Read"
        assert result.input == {"path": "foo.py"}
        assert result.id == "rescued_0"

    def test_arguments_key_also_accepted_as_input(self, monkeypatch):
        """'arguments' key is an accepted alias for the input dict."""
        fake_tool = object()
        monkeypatch.setattr(agent.registry, "get_tool", lambda name: fake_tool if name == "Read" else None)
        result = agent._extract_text_tool_call('{"name": "Read", "arguments": {"path": "bar.py"}}')
        assert result is not None
        assert result.input == {"path": "bar.py"}

    def test_function_nested_name_format_accepted(self, monkeypatch):
        """'function.name' OpenAI-style nesting is also recognised."""
        fake_tool = object()
        monkeypatch.setattr(agent.registry, "get_tool", lambda name: fake_tool if name == "Read" else None)
        payload = '{"function": {"name": "Read"}, "arguments": {"path": "x.py"}}'
        result = agent._extract_text_tool_call(payload)
        assert result is not None
        assert result.name == "Read"

    def test_malformed_json_returns_none(self, monkeypatch):
        monkeypatch.setattr(agent.registry, "get_tool", lambda name: None)
        result = agent._extract_text_tool_call('{"name": "Read", "input":')
        assert result is None

    def test_leading_whitespace_is_stripped_before_check(self, monkeypatch):
        """strip() is applied; a leading space should not block recognition."""
        fake_tool = object()
        monkeypatch.setattr(agent.registry, "get_tool", lambda name: fake_tool if name == "Read" else None)
        result = agent._extract_text_tool_call('  {"name": "Read", "input": {"path": "z.py"}}  ')
        assert result is not None
        assert result.name == "Read"


# ─────────────────────────────────────────────────────────────────────────────
# _build_assistant_content
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildAssistantContent:
    def test_empty_text_and_no_tool_calls_returns_empty_list(self):
        resp = Response(text="", tool_calls=[])
        result = agent._build_assistant_content(resp)
        assert result == []

    def test_text_only_returns_single_text_block(self):
        resp = Response(text="Hello there")
        result = agent._build_assistant_content(resp)
        assert len(result) == 1
        assert result[0] == {"type": "text", "text": "Hello there"}

    def test_text_block_preserves_exact_text_including_newlines(self):
        text = "Line one\nLine two\nLine three"
        resp = Response(text=text)
        result = agent._build_assistant_content(resp)
        assert result[0]["text"] == text

    def test_tool_calls_only_returns_tool_use_blocks(self):
        tc = ToolCall(id="tc_1", name="Read", input={"path": "foo.py"})
        resp = Response(text="", tool_calls=[tc])
        result = agent._build_assistant_content(resp)
        assert len(result) == 1
        block = result[0]
        assert block["type"] == "tool_use"
        assert block["id"] == "tc_1"
        assert block["name"] == "Read"
        assert block["input"] == {"path": "foo.py"}

    def test_text_and_tool_calls_both_appear(self):
        tc = ToolCall(id="tc_2", name="Write", input={"path": "out.txt", "content": "hi"})
        resp = Response(text="Writing file now", tool_calls=[tc])
        result = agent._build_assistant_content(resp)
        assert len(result) == 2
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "tool_use"

    def test_multiple_tool_calls_all_present_in_order(self):
        tc1 = ToolCall(id="tc_a", name="Read", input={"path": "a.py"})
        tc2 = ToolCall(id="tc_b", name="Read", input={"path": "b.py"})
        tc3 = ToolCall(id="tc_c", name="Bash", input={"command": "ls"})
        resp = Response(text="", tool_calls=[tc1, tc2, tc3])
        result = agent._build_assistant_content(resp)
        assert len(result) == 3
        assert [b["id"] for b in result] == ["tc_a", "tc_b", "tc_c"]

    def test_tool_use_block_includes_all_required_keys(self):
        tc = ToolCall(id="tc_x", name="Grep", input={"pattern": "TODO", "path": "."})
        resp = Response(text="", tool_calls=[tc])
        block = agent._build_assistant_content(resp)[0]
        assert set(block.keys()) == {"type", "id", "name", "input"}


# ─────────────────────────────────────────────────────────────────────────────
# _last_message_text
# ─────────────────────────────────────────────────────────────────────────────


class TestLastMessageText:
    def test_empty_list_returns_empty_string(self):
        assert agent._last_message_text([]) == ""

    def test_single_message_string_content_returned(self):
        msgs = [{"role": "user", "content": "hello"}]
        assert agent._last_message_text(msgs) == "hello"

    def test_uses_last_message_not_first(self):
        msgs = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
        ]
        assert agent._last_message_text(msgs) == "second"

    def test_list_content_joins_text_blocks_with_space(self):
        content = [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "world"},
        ]
        msgs = [{"role": "assistant", "content": content}]
        result = agent._last_message_text(msgs)
        assert "hello" in result
        assert "world" in result

    def test_list_content_skips_non_text_type_blocks(self):
        """tool_use blocks inside list content are ignored."""
        content = [
            {"type": "tool_use", "name": "Read", "id": "tc_1"},
            {"type": "text", "text": "done"},
        ]
        msgs = [{"role": "assistant", "content": content}]
        result = agent._last_message_text(msgs)
        assert result.strip() == "done"

    def test_missing_content_key_returns_empty_string(self):
        msgs = [{"role": "user"}]
        assert agent._last_message_text(msgs) == ""

    def test_none_content_value_returns_empty_string(self):
        """content=None is neither str nor list → falls through to return ''."""
        msgs = [{"role": "user", "content": None}]
        result = agent._last_message_text(msgs)
        assert result == ""

    def test_empty_string_content_returns_empty_string(self):
        msgs = [{"role": "user", "content": ""}]
        assert agent._last_message_text(msgs) == ""
