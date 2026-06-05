"""Tests for Dan."""

import asyncio
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Tool Registry Tests ─────────────────────────────────────────────────────

class TestToolRegistry:
    def setup_method(self):
        import tool_registry as reg
        reg._TOOLS.clear()

    def test_register_and_get(self):
        import tool_registry as reg
        reg.register("TestTool", "A test", {"type": "object", "properties": {}}, lambda: "ok")
        assert reg.get_tool("TestTool") is not None
        assert reg.get_tool("NoTool") is None

    def test_execute(self):
        import tool_registry as reg
        reg.register("Echo", "Echo", {"type": "object", "properties": {"msg": {"type": "string"}}},
                      lambda msg="": f"echo: {msg}")
        assert reg.execute_tool("Echo", {"msg": "hello"}) == "echo: hello"

    def test_execute_unknown(self):
        import tool_registry as reg
        result = reg.execute_tool("NonExistent", {})
        assert "Unknown tool" in result

    def test_schemas(self):
        import tool_registry as reg
        reg.register("T1", "Desc", {"type": "object"}, lambda: "")
        schemas = reg.get_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "T1"

    def test_categories(self):
        import tool_registry as reg
        reg.register("A", "", {"type": "object"}, lambda: "", category="core")
        reg.register("B", "", {"type": "object"}, lambda: "", category="web")
        cats = reg.list_by_category()
        assert "core" in cats
        assert "web" in cats


# ── Core Tools Tests ─────────────────────────────────────────────────────────

class TestCoreTools:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        # Patch security validator to allow temp directories for testing
        import tools
        tools._path_validator = tools.SecurePathValidator(allowed_roots=[self.tmpdir, "/"])

    def test_read_file(self):
        from tools import read_file
        fp = Path(self.tmpdir) / "test.txt"
        fp.write_text("line1\nline2\nline3")
        result = read_file(str(fp))
        assert "line1" in result
        assert "line2" in result

    def test_read_file_not_found(self):
        from tools import read_file
        result = read_file("/nonexistent/file.txt")
        assert "Error" in result or "Security error" in result

    def test_read_with_offset(self):
        from tools import read_file
        fp = Path(self.tmpdir) / "test.txt"
        fp.write_text("a\nb\nc\nd\ne")
        result = read_file(str(fp), offset=2, limit=2)
        assert "c" in result
        assert "d" in result

    def test_write_file(self):
        from tools import write_file
        fp = Path(self.tmpdir) / "out.txt"
        result = write_file(str(fp), "hello world")
        assert "✓" in result
        assert fp.read_text() == "hello world"

    def test_write_creates_dirs(self):
        from tools import write_file
        fp = Path(self.tmpdir) / "sub" / "dir" / "file.txt"
        write_file(str(fp), "nested")
        assert fp.read_text() == "nested"

    def test_edit_file(self):
        from tools import edit_file
        fp = Path(self.tmpdir) / "edit.txt"
        fp.write_text("foo bar baz")
        result = edit_file(str(fp), "bar", "qux")
        assert "✓" in result
        assert fp.read_text() == "foo qux baz"

    def test_edit_not_found(self):
        from tools import edit_file
        fp = Path(self.tmpdir) / "edit.txt"
        fp.write_text("hello")
        result = edit_file(str(fp), "xyz", "abc")
        assert "not found" in result

    def test_edit_ambiguous(self):
        from tools import edit_file
        fp = Path(self.tmpdir) / "edit.txt"
        fp.write_text("aaa aaa")
        result = edit_file(str(fp), "aaa", "bbb")
        assert "2 locations" in result

    def test_bash(self):
        from tools import run_bash
        result = run_bash("echo hello")
        assert "hello" in result

    def test_bash_timeout(self):
        from tools import run_bash
        # Override the executor timeout for this test
        import tools
        old_timeout = tools._command_executor.max_execution_time
        tools._command_executor.max_execution_time = 1
        result = run_bash("sleep 5")
        tools._command_executor.max_execution_time = old_timeout
        assert "timed out" in result or "Execution error" in result or "Security error" in result

    def test_bash_blocked(self):
        from tools import run_bash
        result = run_bash("rm -rf /")
        assert "Blocked" in result

    def test_glob(self):
        from tools import glob_files
        (Path(self.tmpdir) / "a.py").touch()
        (Path(self.tmpdir) / "b.py").touch()
        (Path(self.tmpdir) / "c.txt").touch()
        result = glob_files("*.py", self.tmpdir)
        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result

    def test_grep(self):
        from tools import grep_search
        fp = Path(self.tmpdir) / "code.py"
        fp.write_text("def hello():\n    return 42\n")
        result = grep_search("hello", self.tmpdir)
        assert "hello" in result

    def test_list_dir(self):
        from tools import list_directory
        (Path(self.tmpdir) / "file.txt").touch()
        (Path(self.tmpdir) / "sub").mkdir()
        result = list_directory(self.tmpdir)
        assert "file.txt" in result
        assert "sub/" in result


# ── Knowledge Tests ──────────────────────────────────────────────────────────

class TestKnowledge:
    def setup_method(self):
        import shutil
        self.tmpdir = tempfile.mkdtemp()
        # Patch config paths
        import config
        self._orig_user = config.USER_DATA_DIR
        self._orig_project = config.PROJECT_DATA_DIR
        config.USER_DATA_DIR = Path(self.tmpdir) / "user"
        config.PROJECT_DATA_DIR = Path(self.tmpdir) / "project"

    def teardown_method(self):
        import shutil, config
        config.USER_DATA_DIR = self._orig_user
        config.PROJECT_DATA_DIR = self._orig_project
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_and_load(self):
        from knowledge import KnowledgeEntry, save, load
        entry = KnowledgeEntry(name="test", content="hello", scope="user")
        save(entry)
        loaded = load("test", "user")
        assert loaded is not None
        assert loaded.content == "hello"

    def test_delete(self):
        from knowledge import KnowledgeEntry, save, load, delete
        save(KnowledgeEntry(name="del", content="bye", scope="user"))
        delete("del", "user")
        assert load("del", "user") is None

    def test_search(self):
        from knowledge import KnowledgeEntry, save, search
        save(KnowledgeEntry(name="py", content="Python is great", scope="user"))
        save(KnowledgeEntry(name="js", content="JavaScript too", scope="user"))
        results = search("python")
        assert len(results) == 1
        assert results[0].name == "py"

    def test_list_all(self):
        from knowledge import KnowledgeEntry, save, list_all
        save(KnowledgeEntry(name="a", content="aaa", scope="user"))
        save(KnowledgeEntry(name="b", content="bbb", scope="project"))
        entries = list_all()
        assert len(entries) == 2

    def test_context_block(self):
        from knowledge import KnowledgeEntry, save, get_context_block
        save(KnowledgeEntry(name="ctx", content="context data", scope="user"))
        block = get_context_block()
        assert "<knowledge>" in block
        assert "context data" in block


# ── Context Manager Tests ────────────────────────────────────────────────────

class TestContextManager:
    def test_estimate_tokens(self):
        from context_mgr import estimate_tokens
        assert estimate_tokens("hello world") > 0

    def test_needs_compaction_false(self):
        from context_mgr import needs_compaction
        messages = [{"role": "user", "content": "hi"}]
        assert not needs_compaction(messages, 200_000)

    def test_needs_compaction_true(self):
        from context_mgr import needs_compaction
        big = "x" * 600_000  # way over threshold
        messages = [{"role": "user", "content": big}]
        assert needs_compaction(messages, 200_000)


# ── Actions Tests ────────────────────────────────────────────────────────────

class TestActions:
    def test_builtin_actions(self):
        from actions import get_all_actions, get_action
        actions = get_all_actions()
        assert "commit" in actions
        assert "review" in actions

    def test_get_action(self):
        from actions import get_action
        action = get_action("commit")
        assert action is not None
        assert "git" in action.prompt.lower()

    def test_unknown_action(self):
        from actions import get_action
        assert get_action("nonexistent") is None


# ── Workers Tests ────────────────────────────────────────────────────────────

class TestWorkers:
    def test_spawn_no_agent(self):
        from workers import WorkerPool
        pool = WorkerPool()
        task = pool.spawn("test prompt")
        assert task.status == "error"

    def test_spawn_with_agent(self):
        from workers import WorkerPool
        pool = WorkerPool()
        task = pool.spawn("test", wait=True, agent_fn=lambda p: f"done: {p}")
        assert task.status == "done"
        assert "done: test" in task.result

    def test_list_tasks(self):
        from workers import WorkerPool
        pool = WorkerPool()
        pool.spawn("a")
        pool.spawn("b")
        assert len(pool.list_tasks()) == 2

    def test_get_task(self):
        from workers import WorkerPool
        pool = WorkerPool()
        task = pool.spawn("find me")
        found = pool.get_task(task.id)
        assert found is not None
        assert found.prompt == "find me"


# ── Provider Tests ───────────────────────────────────────────────────────────

class TestProviders:
    def test_message_to_dict(self):
        from providers import Message
        m = Message(role="user", content="hello")
        d = m.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "hello"

    def test_response_defaults(self):
        from providers import Response
        r = Response()
        assert r.text == ""
        assert r.tool_calls == []

    def test_get_provider_unknown(self):
        from providers import get_provider
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("fakeprovider")

    def test_get_provider_is_case_insensitive(self):
        from providers import get_provider

        provider = get_provider("OLLAMA", "test-model")

        assert provider is not None
        assert getattr(provider, "model", "") == "test-model"

    def test_provider_facade_exports_provider_classes(self):
        from providers import AnthropicProvider, OllamaProvider, OpenAIProvider, VeniceProvider

        assert AnthropicProvider.__name__ == "AnthropicProvider"
        assert OpenAIProvider.__name__ == "OpenAIProvider"
        assert OllamaProvider.__name__ == "OllamaProvider"
        assert VeniceProvider.__name__ == "VeniceProvider"

    def test_key_rotator_uses_fallback_key(self, monkeypatch):
        from providers import KeyRotator

        monkeypatch.delenv("TEST_PROVIDER_1", raising=False)
        monkeypatch.setenv("TEST_PROVIDER", "demo-key")

        rotator = KeyRotator("TEST_PROVIDER")

        key, index = rotator.next()

        assert key == "demo-key"
        assert index == 0
        assert rotator.count == 1


class TestAgent:
    def test_select_tool_categories_skips_short_chitchat(self):
        from agent import select_tool_categories

        assert select_tool_categories("hey there") == set()

    def test_select_tool_categories_picks_core_and_web(self):
        from agent import select_tool_categories

        categories = select_tool_categories("please search the web for docs")

        assert "core" in categories
        assert "actions" in categories
        assert "web" in categories

    def test_select_tool_categories_picks_index_for_codebase_queries(self):
        from agent import select_tool_categories

        categories = select_tool_categories("where is helper defined and who imports it")

        assert "core" in categories
        assert "actions" in categories
        assert "index" in categories

    def test_extract_text_tool_call_rescues_valid_json(self, monkeypatch):
        import agent

        monkeypatch.setattr(agent.registry, "get_tool", lambda name: object() if name == "Read" else None)

        tool_call = agent._extract_text_tool_call('{"name":"Read","input":{"path":"file.txt"}}')

        assert tool_call is not None
        assert tool_call.name == "Read"
        assert tool_call.input == {"path": "file.txt"}

    def test_build_assistant_content_includes_text_and_tools(self):
        from agent import _build_assistant_content
        from providers import Response, ToolCall

        response = Response(
            text="Done",
            tool_calls=[ToolCall(id="call-1", name="Read", input={"path": "demo.txt"})],
        )

        content = _build_assistant_content(response)

        assert content[0] == {"type": "text", "text": "Done"}
        assert content[1]["type"] == "tool_use"
        assert content[1]["name"] == "Read"

    def test_last_message_text_reads_structured_blocks(self):
        from agent import _last_message_text

        messages = [{"role": "assistant", "content": [{"type": "text", "text": "Hello"}]}]

        assert _last_message_text(messages) == "Hello"

    def test_run_agent_loop_returns_plain_text_response(self, monkeypatch):
        import agent
        from providers import Response

        class FakeProvider:
            context_limit = 1000
            supports_streaming = False

            def chat(self, **kwargs):
                return Response(text="All set", usage={"input": 1, "output": 2})

        recorded = []
        monkeypatch.setattr(agent, "build_system_prompt", lambda: "system")
        monkeypatch.setattr(agent, "select_tool_categories", lambda user_input: {"core"})
        monkeypatch.setattr(agent.registry, "get_schemas_for_categories", lambda categories: [])
        monkeypatch.setattr(agent, "needs_compaction", lambda messages, limit: False)
        monkeypatch.setattr(agent.cost_tracker, "record", lambda inp, out: recorded.append((inp, out)))

        result, updated = agent.run_agent_loop("hello", [], FakeProvider())

        assert result == "All set"
        assert updated[-1] == {"role": "assistant", "content": "All set"}
        assert recorded == [(1, 2)]

    def test_run_agent_loop_executes_tool_calls(self, monkeypatch):
        import agent
        from providers import Response, ToolCall

        class FakeProvider:
            context_limit = 1000
            supports_streaming = False

            def __init__(self):
                self.calls = 0

            def chat(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return Response(
                        tool_calls=[ToolCall(id="call-1", name="Read", input={"path": "demo.txt"})],
                        usage={"input": 1, "output": 1},
                    )
                return Response(text="Finished", usage={"input": 2, "output": 3})

        progress = []
        monkeypatch.setattr(agent, "build_system_prompt", lambda: "system")
        monkeypatch.setattr(agent, "select_tool_categories", lambda user_input: {"core"})
        monkeypatch.setattr(agent.registry, "get_schemas_for_categories", lambda categories: [{"name": "Read"}])
        monkeypatch.setattr(agent.registry, "execute_tool", lambda name, inp: f"read {inp['path']}")
        monkeypatch.setattr(agent, "needs_compaction", lambda messages, limit: False)
        monkeypatch.setattr(agent.cost_tracker, "record", lambda inp, out: None)

        result, updated = agent.run_agent_loop(
            "read file",
            [],
            FakeProvider(),
            on_progress=lambda event, message, data: progress.append((event, message)),
        )

        assert result == "Finished"
        assert any(event == "tool_start" for event, _ in progress)
        assert any(event == "tool_done" for event, _ in progress)
        assert updated[-1] == {"role": "assistant", "content": "Finished"}
        assert updated[-2]["role"] == "user"
        assert updated[-2]["content"][0]["type"] == "tool_result"

    def test_run_agent_loop_streams_when_supported(self, monkeypatch):
        import agent
        from providers import Response

        class FakeProvider:
            context_limit = 1000
            supports_streaming = True

            def chat_stream(self, **kwargs):
                kwargs["on_text"]("Hi")
                kwargs["on_text"](" there")
                return Response(text="Hi there", usage={"input": 1, "output": 1})

        streamed = []
        progress = []
        monkeypatch.setattr(agent, "build_system_prompt", lambda: "system")
        monkeypatch.setattr(agent, "select_tool_categories", lambda user_input: {"core"})
        monkeypatch.setattr(agent.registry, "get_schemas_for_categories", lambda categories: [])
        monkeypatch.setattr(agent, "needs_compaction", lambda messages, limit: False)
        monkeypatch.setattr(agent.cost_tracker, "record", lambda inp, out: None)

        result, updated = agent.run_agent_loop(
            "hello",
            [],
            FakeProvider(),
            stream_callback=streamed.append,
            on_progress=lambda event, message, data: progress.append(event),
        )

        assert result == "Hi there"
        assert "".join(streamed) == "Hi there"
        assert "streaming" in progress
        assert updated[-1] == {"role": "assistant", "content": "Hi there"}

    def test_run_agent_loop_raises_interrupted_before_turn(self, monkeypatch):
        import agent

        event = threading.Event()
        event.set()
        monkeypatch.setattr(agent, "build_system_prompt", lambda: "system")
        monkeypatch.setattr(agent, "select_tool_categories", lambda user_input: {"core"})
        monkeypatch.setattr(agent.registry, "get_schemas_for_categories", lambda categories: [])

        with pytest.raises(agent.AgentInterrupted) as exc_info:
            agent.run_agent_loop("stop", [], object(), interrupt_event=event)

        assert exc_info.value.checkpoint == [{"role": "user", "content": "stop"}]


class TestDanCli:
    def test_handle_slash_command_clear_empties_messages(self):
        import Dan

        messages = [{"role": "user", "content": "hello"}]

        result = Dan.handle_slash_command("/clear", messages, provider=object())

        assert result == "✓ Conversation cleared."
        assert messages == []

    def test_handle_slash_command_config_set_routes_value(self, monkeypatch):
        import Dan

        monkeypatch.setattr("api_config.set_value", lambda key, value: f"{key}={value}")

        result = Dan.handle_slash_command("/config venice.api_key=test-key", [], provider=object())

        assert result == "venice.api_key=test-key"

    def test_handle_slash_command_provider_switch_persists_choice(self, monkeypatch):
        import Dan

        saved = {}
        monkeypatch.setattr("api_config.load_config", lambda: {})
        monkeypatch.setattr("api_config.save_config", lambda cfg: saved.update(cfg) or "ok")

        result = Dan.handle_slash_command("/provider openai", [], provider=object())

        assert "Provider set to 'openai'" in result
        assert saved["provider"] == "openai"

    def test_handle_slash_command_session_load_replaces_messages(self, monkeypatch):
        import Dan

        messages = [{"role": "user", "content": "old"}]
        monkeypatch.setattr(
            Dan.session_mgr,
            "load",
            lambda name: ([{"role": "assistant", "content": "loaded"}], {"name": "demo", "provider": "ollama", "model": "qwen"}),
        )

        result = Dan.handle_slash_command("/session load demo", messages, provider=object())

        assert "Loaded session 'demo'" in result
        assert messages == [{"role": "assistant", "content": "loaded"}]

    def test_handle_slash_command_unknown_returns_helpful_error(self):
        import Dan

        result = Dan.handle_slash_command("/nope", [], provider=object())

        assert "Unknown command" in result

    def test_stream_writer_suppresses_json_tool_call_leak(self, capsys):
        import Dan

        writer = Dan.StreamWriter()
        writer('{"name":"Read"')
        writer(',"input":{"path":"file.txt"}}')
        printed = writer.finish()
        output = capsys.readouterr().out

        assert not printed
        assert output == ""

    def test_stream_writer_prints_text_once_started(self, capsys):
        import Dan

        writer = Dan.StreamWriter()
        writer("Hello")
        writer(" world")
        printed = writer.finish()
        output = capsys.readouterr().out

        assert printed
        assert "Hello world" in output

    def test_get_session_id_is_stable_once_created(self, monkeypatch):
        import Dan

        monkeypatch.setattr(Dan, "_SESSION_ID", "")

        first = Dan._get_session_id()
        second = Dan._get_session_id()

        assert first
        assert first == second


class TestSessionManager:
    def test_save_sanitizes_filename_and_loads_by_name(self, monkeypatch, tmp_path):
        import session_mgr

        monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
        messages = [{"role": "user", "content": "hello"}]

        result = session_mgr.save(messages, "ollama", "qwen", name="my unsafe:/session", session_id="abc123")
        loaded = session_mgr.load("my_unsafesession")

        assert "my_unsafesession.json" in result
        assert loaded is not None
        assert loaded[0] == messages
        assert loaded[1]["provider"] == "ollama"

    def test_auto_save_skips_empty_messages(self, monkeypatch, tmp_path):
        import session_mgr

        monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")

        session_mgr.auto_save([], "ollama", "qwen", "sid123")

        assert not (tmp_path / "sessions").exists()

    def test_list_sessions_excludes_auto_by_default(self, monkeypatch, tmp_path):
        import session_mgr

        monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
        session_mgr.save([{"role": "user", "content": "saved"}], "ollama", "qwen", name="named", session_id="1")
        session_mgr.auto_save([{"role": "user", "content": "auto"}], "ollama", "qwen", "2")

        sessions = session_mgr.list_sessions()
        all_sessions = session_mgr.list_sessions(include_auto=True)

        assert len(sessions) == 1
        assert sessions[0]["name"] == "named"
        assert any(item["filename"].startswith("_auto_") for item in all_sessions)

    def test_format_sessions_table_handles_empty_and_populated(self, monkeypatch, tmp_path):
        import session_mgr

        monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
        empty = session_mgr.format_sessions_table()
        session_mgr.save([{"role": "user", "content": "saved"}], "ollama", "qwen", name="named", session_id="1")
        table = session_mgr.format_sessions_table()

        assert "No saved sessions found" in empty
        assert "NAME" in table
        assert "named" in table


class TestCostTracker:
    def test_get_rates_matches_known_and_default_models(self):
        import cost_tracker

        assert cost_tracker._get_rates("gpt-4o") == (5.00, 15.00)
        assert cost_tracker._get_rates("unknown-model") == (3.00, 15.00)

    def test_session_cost_record_and_summary(self, monkeypatch):
        import cost_tracker

        monkeypatch.setattr(cost_tracker.time, "time", lambda: 130.0)
        session = cost_tracker.SessionCost(model="gpt-4o", session_start=10.0)
        session.record(1_000, 2_000)
        session.record(-5, 100)
        summary = session.summary()

        assert session.total_input_tokens == 1_000
        assert session.total_output_tokens == 2_100
        assert session.call_count == 2
        assert "Model:        gpt-4o" in summary
        assert "API calls:    2" in summary
        assert "Session time: 2m 0s" in summary

    def test_free_model_summary_labels_local_charge(self):
        import cost_tracker

        session = cost_tracker.SessionCost(model="llama3.1")
        session.record(100, 200)

        assert session.is_free_model()
        assert "(local — no charge)" in session.summary()

    def test_global_tracker_lifecycle(self):
        import cost_tracker

        tracker = cost_tracker.init("claude-sonnet-4")
        cost_tracker.record(10, 20)

        assert cost_tracker.get() is tracker
        assert tracker.total_tokens == 30


class TestWebTools:
    def test_extract_text_truncates_and_skips_script_content(self):
        from web import _extract_text

        html = "<html><body><script>ignore()</script><p>Hello</p><p>World</p></body></html>"
        text = _extract_text(html, max_chars=5)

        assert "ignore" not in text
        assert text.endswith("... (truncated)")

    def test_text_extractor_collects_visible_text(self):
        from web import _TextExtractor

        extractor = _TextExtractor()
        extractor.feed("<div>Alpha</div><style>hide</style><p>Beta</p>")

        assert extractor.get_text() == "Alpha\nBeta"

    def test_web_fetch_json_and_binary_paths(self, monkeypatch):
        import web

        class FakeResponse:
            def __init__(self, content_type, text="", payload=None, content=b"123"):
                self.headers = {"content-type": content_type}
                self.text = text
                self._payload = payload or {}
                self.content = content

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        class FakeClient:
            def __init__(self, response):
                self._response = response

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def get(self, url, headers=None):
                return self._response

        json_response = FakeResponse("application/json", payload={"ok": True})
        binary_response = FakeResponse("application/octet-stream", content=b"123456")

        monkeypatch.setitem(sys.modules, "httpx", type("Httpx", (), {"Client": lambda *args, **kwargs: FakeClient(json_response)}))
        assert '"ok": true' in web.web_fetch("https://example.com")

        monkeypatch.setitem(sys.modules, "httpx", type("Httpx", (), {"Client": lambda *args, **kwargs: FakeClient(binary_response)}))
        assert "Binary content" in web.web_fetch("https://example.com/file")

    def test_register_web_tools_registers_expected_names(self, monkeypatch):
        import web

        registered = []
        monkeypatch.setattr(web.registry, "register", lambda **kwargs: registered.append(kwargs["name"]))

        web.register_web_tools()

        assert registered == ["WebFetch", "WebSearch"]


class TestSecurityUtilsMore:
    def test_sanitize_user_input_removes_controls_and_limits_newlines(self):
        from security_utils import sanitize_user_input

        cleaned = sanitize_user_input("hello\x00\n\n\nworld")

        assert cleaned == "hello\n\nworld"

    def test_validate_file_size_raises_for_large_file(self, tmp_path):
        from security_utils import validate_file_size

        file_path = tmp_path / "large.txt"
        file_path.write_bytes(b"x" * 2048)

        with pytest.raises(ValueError, match="File too large"):
            validate_file_size(file_path, max_size_mb=0)

    def test_secure_command_executor_helpers(self, monkeypatch):
        import security_utils

        executor = security_utils.SecureCommandExecutor()
        monkeypatch.setattr("platform.system", lambda: "Windows")
        monkeypatch.setenv("PATH", "C:\\Tools")
        monkeypatch.setenv("SYSTEMROOT", "C:\\Windows")
        monkeypatch.setenv("USERPROFILE", "C:\\Users\\tyler")

        assert executor._is_simple_command("python script.py")
        assert not executor._is_simple_command("python script.py | more")
        assert executor._split_command("python demo.py") == ["python", "demo.py"]
        assert executor._needs_windows_shell("echo hello")
        assert executor._base_command("C:\\Python\\python.exe script.py") == "python"
        assert executor._get_restricted_env()["PATH"] == "C:\\Tools"

    def test_secure_command_executor_validate_command_blocks_dangerous_pattern(self):
        from security_utils import SecureCommandExecutor

        executor = SecureCommandExecutor()

        with pytest.raises(ValueError, match="Blocked dangerous command pattern"):
            executor.validate_command("rm -rf /")


class TestCoreToolsMore:
    def test_backup_and_diff_helpers(self, tmp_path):
        import tools

        file_path = tmp_path / "demo.txt"
        file_path.write_text("before", encoding="utf-8")

        backup_path = tools._backup(file_path)
        diff = tools._diff_text("before\n", "after\n", "demo.txt")

        assert backup_path is not None
        assert Path(backup_path).exists()
        assert "a/demo.txt" in diff
        assert "b/demo.txt" in diff

    def test_read_file_truncates_large_line_output(self, monkeypatch, tmp_path):
        import tools

        monkeypatch.setattr(tools, "_path_validator", tools.SecurePathValidator(allowed_roots=[str(tmp_path)]))
        file_path = tmp_path / "big.txt"
        file_path.write_text("\n".join(f"line {i}" for i in range(10005)), encoding="utf-8")

        result = tools.read_file(str(file_path))

        assert "truncated" in result

    def test_register_core_tools_registers_expected_names(self, monkeypatch):
        import tools

        registered = []
        monkeypatch.setattr(tools.registry, "register", lambda **kwargs: registered.append(kwargs["name"]))

        tools.register_core_tools()

        assert {"Read", "Write", "Edit", "Bash", "Glob", "Grep", "ListDir"}.issubset(set(registered))


class TestSecureTools:
    def test_secure_glob_and_grep_behaviors(self, monkeypatch, tmp_path):
        import tools_secure

        monkeypatch.setattr(tools_secure, "_path_validator", tools_secure.SecurePathValidator(allowed_roots=[str(tmp_path)]))
        root = tmp_path / "proj"
        root.mkdir()
        (root / "a.py").write_text("print('hello')\nvalue = 1\n", encoding="utf-8")
        (root / "b.txt").write_text("other\n", encoding="utf-8")

        globbed = tools_secure.glob_files("*.py", str(root))
        grepped = tools_secure.grep_files("value", str(root), "*.py")

        assert "a.py" in globbed
        assert "a.py:2" in grepped

    def test_secure_list_directory_and_register(self, monkeypatch, tmp_path):
        import tools_secure

        monkeypatch.setattr(tools_secure, "_path_validator", tools_secure.SecurePathValidator(allowed_roots=[str(tmp_path)]))
        root = tmp_path / "proj"
        (root / "sub").mkdir(parents=True)
        (root / "sub" / "file.txt").write_text("x", encoding="utf-8")

        listing = tools_secure.list_directory(str(root))
        assert "proj/" in listing
        assert "file.txt" in listing

        registered = []
        monkeypatch.setattr(tools_secure.registry, "register_tool", lambda **kwargs: registered.append(kwargs["name"]))
        tools_secure.register_secure_core_tools()

        assert {"Read", "Write", "Edit", "Bash", "Glob", "Grep", "ListDir"}.issubset(set(registered))


class TestProviderModules:
    def test_openai_provider_chat_parses_text_and_tool_calls(self, monkeypatch):
        import provider_openai
        from providers import Message

        class FakeRotator:
            count = 2

            def next(self, estimated_tokens=0):
                return ("key-1", 0)

            def record_usage(self, key_idx, total):
                self.recorded = (key_idx, total)

        class FakeCompletion:
            def create(self, **kwargs):
                tool_call = type(
                    "ToolCallObj",
                    (),
                    {"id": "call-1", "function": type("Fn", (), {"name": "Read", "arguments": '{"path":"demo.txt"}'})()},
                )()
                message = type("Msg", (), {"content": "Done", "tool_calls": [tool_call]})()
                choice = type("Choice", (), {"message": message, "finish_reason": "stop"})()
                usage = type("Usage", (), {"prompt_tokens": 11, "completion_tokens": 7})()
                return type("Result", (), {"choices": [choice], "usage": usage})()

        fake_client = type(
            "Client",
            (),
            {"chat": type("Chat", (), {"completions": FakeCompletion()})()},
        )()
        fake_openai = type("OpenAIStub", (), {"OpenAI": lambda api_key=None: fake_client})

        monkeypatch.setitem(sys.modules, "openai", fake_openai)
        monkeypatch.setattr(provider_openai, "KeyRotator", lambda prefix: FakeRotator())

        provider = provider_openai.OpenAIProvider("gpt-4o")
        response = provider.chat([Message(role="user", content="hello")], system="sys", tools=[{"name": "Read", "input_schema": {}}])

        assert response.text == "Done"
        assert response.tool_calls[0].name == "Read"
        assert response.usage == {"input": 11, "output": 7}
        assert provider.context_limit == 128_000

    def test_anthropic_provider_chat_and_stream_fallback(self, monkeypatch):
        import provider_anthropic
        from providers import Message

        class FakeRotator:
            count = 1

            def __init__(self):
                self.calls = []

            def next(self, estimated_tokens=0):
                self.calls.append(("next", estimated_tokens))
                return ("key-1", 0)

            def record_usage(self, key_idx, total):
                self.calls.append(("record", key_idx, total))

        class RateLimitError(Exception):
            pass

        class Block:
            def __init__(self, block_type, text="", block_id="id-1", name="Read", input_data=None):
                self.type = block_type
                self.text = text
                self.id = block_id
                self.name = name
                self.input = input_data or {"path": "demo.txt"}

        usage = type("Usage", (), {"input_tokens": 5, "output_tokens": 7})()
        final_message = type(
            "Final",
            (),
            {
                "stop_reason": "end_turn",
                "usage": usage,
                "content": [Block("tool_use")],
            },
        )()

        class StreamContext:
            def __enter__(self):
                self.text_stream = iter(["Hi", " there"])
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def get_final_message(self):
                return final_message

        class MessagesAPI:
            def __init__(self):
                self.create_calls = 0

            def create(self, **kwargs):
                self.create_calls += 1
                if self.create_calls == 1:
                    raise RateLimitError()
                return type(
                    "Result",
                    (),
                    {
                        "stop_reason": "tool_use",
                        "usage": usage,
                        "content": [Block("text", text="Answer"), Block("tool_use")],
                    },
                )()

            def stream(self, **kwargs):
                return StreamContext()

        messages_api = MessagesAPI()
        fake_anthropic = type(
            "AnthropicStub",
            (),
            {
                "Anthropic": lambda api_key=None: type("Client", (), {"messages": messages_api})(),
                "RateLimitError": RateLimitError,
            },
        )

        monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)
        monkeypatch.setattr(provider_anthropic, "KeyRotator", lambda prefix: FakeRotator())

        provider = provider_anthropic.AnthropicProvider("claude-sonnet-4-6")
        chat_response = provider.chat([Message(role="user", content="hello")])
        streamed = []
        stream_response = provider.chat_stream([Message(role="user", content="hello")], on_text=streamed.append)

        assert chat_response.text == "Answer"
        assert chat_response.tool_calls[0].name == "Read"
        assert "".join(streamed) == "Hi there"
        assert stream_response.tool_calls[0].name == "Read"
        assert provider.supports_streaming

    def test_ollama_provider_converters_and_fallback(self, monkeypatch):
        import provider_ollama
        from providers import Message

        messages = [
            Message(role="assistant", content=[{"type": "text", "text": "Hi"}, {"type": "tool_use", "name": "Read", "input": {"path": "a.txt"}}]),
            Message(role="user", content=[{"type": "tool_result", "content": "ok"}, {"type": "text", "text": "next"}]),
        ]

        converted = provider_ollama.OllamaProvider._to_ollama_messages(messages, "system")
        parsed = provider_ollama.OllamaProvider._parse_tool_calls({"tool_calls": [{"function": {"name": "Read", "arguments": '{"path":"a.txt"}'}}]})

        assert converted[0]["role"] == "system"
        assert converted[1]["tool_calls"][0]["function"]["name"] == "Read"
        assert converted[2]["role"] == "tool"
        assert parsed[0].input == {"path": "a.txt"}

        class StreamFailureHttpx:
            @staticmethod
            def post(url, json=None, timeout=None):
                return type(
                    "Resp",
                    (),
                    {
                        "raise_for_status": lambda self: None,
                        "json": lambda self: {
                            "message": {"content": "Fallback"},
                            "prompt_eval_count": 2,
                            "eval_count": 3,
                        },
                    },
                )()

            @staticmethod
            def stream(*args, **kwargs):
                raise RuntimeError("boom")

        monkeypatch.setitem(sys.modules, "httpx", StreamFailureHttpx)
        provider = provider_ollama.OllamaProvider("llama3.1")
        response = provider.chat_stream([Message(role="user", content="hello")], on_text=lambda chunk: None)

        assert response.text == "Fallback"
        assert response.usage == {"input": 2, "output": 3}

    def test_venice_provider_secret_lookup_error_and_think_cleanup(self, monkeypatch):
        import provider_venice
        from providers import Message

        monkeypatch.setitem(sys.modules, "openai", type("OpenAIStub", (), {"OpenAI": lambda **kwargs: type("Client", (), {"chat": type("Chat", (), {"completions": type("Comp", (), {"create": lambda self, **kw: type(
            "Result",
            (),
            {
                "choices": [type("Choice", (), {"message": type("Msg", (), {"content": "<think>secret</think>Visible", "tool_calls": None})(), "finish_reason": "stop"})()],
                "usage": type("Usage", (), {"prompt_tokens": 1, "completion_tokens": 2})(),
            },
        )()})()})()})}))

        monkeypatch.setenv("VENICE_API_KEY", "venice-key")
        provider = provider_venice.VeniceProvider("llama-3.3-70b")
        response = provider.chat([Message(role="user", content="hello")])

        assert response.text == "Visible"
        assert provider.context_limit == 128_000

        monkeypatch.delenv("VENICE_API_KEY", raising=False)
        monkeypatch.setattr("api_config.get_secret", lambda key: "")
        with pytest.raises(ValueError, match="No Venice API key found"):
            provider_venice.VeniceProvider("llama-3.3-70b")


class TestContextAndRegistry:
    def test_context_manager_compact_success_and_fallback(self, monkeypatch):
        import context_mgr

        class Provider:
            def chat(self, messages=None, max_tokens=None):
                return type("Resp", (), {"text": "summary"})()

        messages = [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "two"},
            {"role": "user", "content": "three"},
            {"role": "assistant", "content": "four"},
            {"role": "user", "content": "five"},
        ]

        compacted = context_mgr.compact(messages, Provider())
        assert compacted[0]["content"].startswith("[Conversation summary]")

        class FailingProvider:
            def chat(self, messages=None, max_tokens=None):
                raise RuntimeError("nope")

        fallback = context_mgr.compact(messages, FailingProvider())
        assert "[Conversation summary]" in fallback[0]["content"]

    def test_context_manager_estimation_and_threshold(self, monkeypatch):
        import context_mgr

        messages = [{"role": "user", "content": "abcd"}, {"role": "assistant", "content": [{"type": "text", "text": "hello"}]}]
        total = context_mgr.estimate_messages_tokens(messages)

        assert total > 0
        assert context_mgr.needs_compaction(messages, context_limit=1)

    def test_tool_registry_alias_and_schema_cache(self):
        import tool_registry as reg

        reg._TOOLS.clear()
        reg._CACHED_SCHEMAS = None
        reg.register_tool("AliasTool", "desc", {"type": "object"}, lambda: "ok", category="extra")
        first = reg.get_tool_schemas()
        second = reg.get_tool_schemas()

        assert reg.get_tool("AliasTool") is not None
        assert first is second
        assert reg.all_categories() == {"extra"}


class TestCodeExecutionBundle:
    def test_code_execution_helpers(self, monkeypatch, tmp_path):
        import code_execution

        monkeypatch.setattr(code_execution, "_path_validator", code_execution.SecurePathValidator(allowed_roots=[str(tmp_path)]))
        monkeypatch.setattr(code_execution.shutil, "which", lambda name: None if name == "python" else "C:/Windows/py.exe")

        assert code_execution._detect_lang_from_ext(Path("demo.py")) == "python"
        assert code_execution._detect_lang_from_shebang("#!/usr/bin/env python\nprint('x')") == "python"
        assert code_execution._bounded_timeout(999) == 120
        assert code_execution._split_args("--flag value") == ["--flag", "value"]
        assert code_execution._command_to_string(["python", "demo.py"])
        assert code_execution._safe_path(str(tmp_path / "ok.txt")) == (tmp_path / "ok.txt").resolve()
        assert code_execution._resolve_python_command() == ["py"]
        assert code_execution._resolve_interpreter_command(["python", "-m", "pytest"]) == ["py", "-m", "pytest"]

    def test_run_code_and_run_file_paths(self, monkeypatch, tmp_path):
        import code_execution

        monkeypatch.setattr(code_execution, "_path_validator", code_execution.SecurePathValidator(allowed_roots=[str(tmp_path)]))
        monkeypatch.setattr(
            code_execution,
            "_run_proc",
            lambda cmd, cwd=None, stdin_text="", timeout=30, validate_command=True: (0, "stdout", "", 0.25),
        )

        result = code_execution.run_code("print('hi')", language="python")
        file_path = tmp_path / "demo.py"
        file_path.write_text("print('hi')", encoding="utf-8")
        file_result = code_execution.run_file(str(file_path), args="--demo")

        assert "RunCode [python]" in result
        assert "OK Exit 0" in result
        assert "RunFile [demo.py]" in file_result

    def test_test_loop_and_iterate_fix_branches(self, monkeypatch, tmp_path):
        import code_execution

        monkeypatch.setattr(code_execution, "_path_validator", code_execution.SecurePathValidator(allowed_roots=[str(tmp_path)]))
        root = tmp_path / "proj"
        root.mkdir()
        (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")

        monkeypatch.setattr(code_execution, "_run_pytest", lambda root, extra, timeout: "pytest-results")
        assert code_execution.test_loop(str(root)) == "pytest-results"

        monkeypatch.setattr(
            code_execution,
            "_run_proc",
            lambda cmd, cwd=None, stdin_text="", timeout=30, validate_command=True: (1, "", "boom", 0.5),
        )
        monkeypatch.setattr(code_execution._command_validator, "validate_command", lambda command: None)
        result = code_execution.iterate_fix("python demo.py", working_dir=str(root), max_tries=2)

        assert "Attempt 1/2 failed" in result
        assert "Fix the issue above" in result

    def test_register_execution_tools_registers_expected_names(self, monkeypatch):
        import code_execution

        registered = []
        monkeypatch.setattr(code_execution.registry, "register", lambda **kwargs: registered.append(kwargs["name"]))

        code_execution.register_execution_tools()

        assert {"RunCode", "RunFile", "TestLoop", "IterateFix"}.issubset(set(registered))


class TestCodeToolsBundle:
    def test_run_tests_lint_and_format_paths(self, monkeypatch, tmp_path):
        import code_tools

        root = tmp_path / "proj"
        root.mkdir()
        (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        monkeypatch.setattr(code_tools.shutil, "which", lambda name: None if name == "python" else "C:/Windows/py.exe")

        def fake_run(cmd, cwd=None, timeout=120):
            if cmd[:3] == ["py", "-m", "pytest"]:
                return 0, "2 passed", ""
            if cmd[:2] == ["ruff", "check"]:
                return 0, "", ""
            if cmd[:2] == ["ruff", "format"]:
                return 0, "", ""
            return 0, "", ""

        monkeypatch.setattr(code_tools, "_run", fake_run)

        tests_result = code_tools.run_tests(str(root))
        lint_result = code_tools.lint_check(str(root), tool="ruff")
        format_result = code_tools.format_code(str(root), formatter="ruff")

        assert "Framework: pytest" in tests_result
        assert "ruff: No issues found" in lint_result
        assert "already formatted" in format_result

    def test_find_usages_refactor_analyze_and_deps(self, tmp_path, monkeypatch):
        import code_tools

        root = tmp_path / "proj"
        root.mkdir()
        py = root / "app.py"
        py.write_text(
            "import os\n\n# TODO: fix\n\ndef demo():\n    pass\n\nx = demo()\n",
            encoding="utf-8",
        )
        (root / "requirements.txt").write_text("-r requirements-core.txt\nrequests>=2\n", encoding="utf-8")
        (root / "requirements-core.txt").write_text("missing_pkg\n", encoding="utf-8")
        (root / "pyproject.toml").write_text(
            "[project]\n"
            "dependencies = [\n"
            "  \"tomli>=2\",\n"
            "]\n"
            "[tool.pytest.ini_options]\n"
            "testpaths = [\"tests\"]\n",
            encoding="utf-8",
        )

        usages = code_tools.find_usages("demo", str(root), "python")
        dry_run = code_tools.refactor_rename("demo", "renamed", str(root), dry_run=True)
        analysis = code_tools.analyze_code(str(root))

        import importlib.util
        original_find_spec = importlib.util.find_spec
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: object() if name == "requests" else None)
        deps = code_tools.check_deps(str(root))
        monkeypatch.setattr(importlib.util, "find_spec", original_find_spec)

        assert "Usages of 'demo'" in usages
        assert "DRY RUN" in dry_run
        assert "Code Analysis" in analysis
        assert "Missing runtime packages" in deps
        assert "missing_pkg" in deps
        assert "tomli" in deps
        assert "testpaths" not in deps
        assert "x  missing_pkg" in deps
        deps.encode("cp1252")

    def test_environment_doctor_reports_bootstrap_issues(self, tmp_path, monkeypatch):
        import code_tools

        root = tmp_path / "proj"
        root.mkdir()
        (root / "tests").mkdir()
        (root / "requirements.txt").write_text("-r requirements-core.txt\n", encoding="utf-8")
        (root / "requirements-core.txt").write_text("httpx\nanthropic\n", encoding="utf-8")

        monkeypatch.setattr(code_tools.shutil, "which", lambda name: "C:/Windows/py.exe" if name == "py" else None)
        monkeypatch.setattr(
            code_tools.importlib.util,
            "find_spec",
            lambda name: object() if name == "httpx" else None,
        )

        doctor = code_tools.environment_doctor(str(root), provider="anthropic")

        assert "Environment Doctor" in doctor
        assert "Pytest is not installed" in doctor
        assert "Runtime dependencies are missing: anthropic" in doctor
        assert "Dev missing:           0" in doctor
        assert "Provider 'anthropic' is missing required SDK(s): anthropic." in doctor
        assert "Missing runtime packages:" in doctor
        assert "anthropic  (requirements-core.txt)" in doctor
        assert "Suggested runtime fix:" in doctor
        assert "py -m pip install anthropic" in doctor
        assert "Install test tooling: py -m pip install pytest pytest-cov" in doctor

    def test_repo_health_combines_doctor_compile_and_optional_checks(self, tmp_path, monkeypatch):
        import code_tools

        (tmp_path / "tests").mkdir()
        (tmp_path / "demo.py").write_text("print('ok')\n", encoding="utf-8")
        monkeypatch.setattr(code_tools, "environment_doctor", lambda path, provider="": "doctor-ok")

        def fake_find_spec(name):
            if name in {"pytest", "ruff"}:
                return object()
            return None

        monkeypatch.setattr(code_tools.importlib.util, "find_spec", fake_find_spec)
        monkeypatch.setattr(code_tools, "run_tests", lambda path, framework="", args="", timeout=60: "tests-ok")
        monkeypatch.setattr(code_tools, "lint_check", lambda path, tool="", fix=False: "lint-ok")

        report = code_tools.repo_health(str(tmp_path), provider="ollama", timeout=45)

        assert "Repo Health" in report
        assert "doctor-ok" in report
        assert "OK compileall passed." in report
        assert "tests-ok" in report
        assert "lint-ok" in report

    def test_check_deps_maps_non_importable_package_names(self, tmp_path, monkeypatch):
        import code_tools

        (tmp_path / "requirements.txt").write_text(
            "pytest-cov\nscikit-learn\nopencv-python\n",
            encoding="utf-8",
        )

        def fake_find_spec(name):
            if name in {"pytest_cov", "sklearn", "cv2"}:
                return object()
            return None

        monkeypatch.setattr(code_tools.importlib.util, "find_spec", fake_find_spec)

        report = code_tools.check_deps(str(tmp_path))

        assert "Missing:   0" in report
        assert "Runtime dependencies are installed." in report
        assert "Undeclared imports: 0" in report
    
    def test_check_deps_uses_resolved_python_launcher_for_install_hint(self, tmp_path, monkeypatch):
        import code_tools

        (tmp_path / "requirements.txt").write_text("httpx\n", encoding="utf-8")
        monkeypatch.setattr(code_tools, "_python_cmd", lambda: ["py"])
        monkeypatch.setattr(code_tools.importlib.util, "find_spec", lambda name: None)

        report = code_tools.check_deps(str(tmp_path))

        assert "Install runtime with: py -m pip install httpx" in report

    def test_check_deps_separates_optional_bundle_guidance(self, tmp_path, monkeypatch):
        import code_tools

        (tmp_path / "requirements.txt").write_text("-r requirements-core.txt\n", encoding="utf-8")
        (tmp_path / "requirements-core.txt").write_text("httpx\n", encoding="utf-8")
        (tmp_path / "requirements-ml.txt").write_text("-r requirements-core.txt\npandas\nnumpy\n", encoding="utf-8")

        monkeypatch.setattr(code_tools, "_python_cmd", lambda: ["py"])
        monkeypatch.setattr(
            code_tools.importlib.util,
            "find_spec",
            lambda name: object() if name == "httpx" else None,
        )

        report = code_tools.check_deps(str(tmp_path))

        assert "Runtime dependencies are installed." in report
        assert "Missing optional feature packages:" in report
        assert "pandas" in report
        assert "numpy" in report
        assert "Optional feature bundles:" in report
        assert "py -m pip install -r requirements-ml.txt" in report

    def test_register_code_tools_registers_expected_names(self, monkeypatch):
        import code_tools

        registered = []
        monkeypatch.setattr(code_tools.registry, "register", lambda **kwargs: registered.append(kwargs["name"]))

        code_tools.register_code_tools()

        assert {"RunTests", "LintCheck", "FormatCode", "FindUsages", "RefactorRename", "AnalyzeCode", "CheckDeps", "EnvironmentDoctor", "StartupDoctor", "RepoHealth"}.issubset(set(registered))


class TestCliBootstrap:
    def test_main_uses_config_defaults_for_provider_and_model(self, monkeypatch):
        import Dan

        captured = {}

        class Args:
            prompt = None
            print_mode = False
            provider = None
            model = None
            verbose = False

        monkeypatch.setattr(Dan.argparse.ArgumentParser, "parse_args", lambda self: Args())
        monkeypatch.setattr(Dan, "repl", lambda provider, model, provider_name: captured.update({
            "provider": provider_name,
            "model": model,
            "provider_model": getattr(provider, "model", ""),
        }))
        monkeypatch.setattr(Dan, "one_shot", lambda prompt, provider: None)
        monkeypatch.setattr(
            Dan,
            "get_provider",
            lambda provider_name, model: type("Provider", (), {"model": model})(),
        )
        monkeypatch.delenv("DAN_PROVIDER", raising=False)
        monkeypatch.delenv("DAN_MODEL", raising=False)

        Dan.main()

        assert captured["provider"] == Dan.DEFAULT_PROVIDER
        assert captured["model"] == Dan.DEFAULT_MODEL
        assert captured["provider_model"] == Dan.DEFAULT_MODEL


class TestGitToolsBundle:
    def test_git_helpers_and_status_branches(self, monkeypatch):
        import git_tools

        monkeypatch.setattr(git_tools, "_is_git_repo", lambda: True)

        def fake_git(args, cwd=None, timeout=30):
            if args[:2] == ["branch", "--show-current"]:
                return 0, "main\n", ""
            if args[:3] == ["rev-list", "--left-right", "--count"]:
                return 0, "2 1\n", ""
            if args[:2] == ["status", "--short"]:
                return 0, " M app.py\n?? new.txt\n", ""
            if args[:2] == ["branch", "-a"]:
                return 0, "main *\nfeature \n", ""
            return 0, "", ""

        monkeypatch.setattr(git_tools, "_git", fake_git)

        status = git_tools.git_status(short=True)
        branches = git_tools.git_branch()

        assert "Branch: main (2 ahead, 1 behind)" in status
        assert "Untracked" in status
        assert "→ main" in branches

    def test_git_diff_log_commit_add_and_stash(self, monkeypatch):
        import git_tools

        monkeypatch.setattr(git_tools, "_is_git_repo", lambda: True)

        def fake_git(args, cwd=None, timeout=30):
            if args[0] == "diff":
                return 0, "line\n" * 3, ""
            if args[0] == "log":
                return 0, "abc123 commit", ""
            if args[:2] == ["add", "."]:
                return 0, "", ""
            if args[:2] == ["status", "--short"]:
                return 0, "M  app.py\n", ""
            if args[0] == "commit":
                return 0, "[main abc] msg", ""
            if args[:2] == ["stash", "list"]:
                return 0, "stash@{0}: WIP", ""
            if args[:2] == ["stash", "push"]:
                return 0, "Saved working directory", ""
            return 0, "", ""

        monkeypatch.setattr(git_tools, "_git", fake_git)

        assert "line" in git_tools.git_diff()
        assert "abc123 commit" in git_tools.git_log()
        assert "1 file(s) now staged" in git_tools.git_add(".")
        assert "[main abc] msg" in git_tools.git_commit("msg")
        assert "stash@{0}" in git_tools.git_stash("list")
        assert "Saved working directory" in git_tools.git_stash("push", "wip")

    def test_register_git_tools_registers_expected_names(self, monkeypatch):
        import git_tools

        registered = []
        monkeypatch.setattr(git_tools.registry, "register", lambda **kwargs: registered.append(kwargs["name"]))

        git_tools.register_git_tools()

        assert {"GitStatus", "GitDiff", "GitLog", "GitAdd", "GitCommit", "GitBranch", "GitStash"}.issubset(set(registered))


class TestWorkersMore:
    def test_spawn_tracks_completed_tasks(self):
        from workers import WorkerPool

        pool = WorkerPool()
        task = pool.spawn("hello", wait=True, agent_fn=lambda prompt: prompt.upper())

        assert task.status == "done"
        assert task.result == "HELLO"
        assert pool.get_task(task.id) is task

    def test_spawn_records_worker_type(self):
        from workers import WorkerPool

        pool = WorkerPool()
        task = pool.spawn("task", worker_type="research")

        assert task.worker_type == "research"
        assert task.status == "error"


class TestProjectIndexer:
    def test_scan_extracts_project_symbols(self, tmp_path):
        from project_indexer import ProjectScanner

        root = tmp_path / "sample"
        root.mkdir()
        (root / "app.py").write_text(
            "import os\n\nclass Demo:\n    pass\n\nasync def run_job():\n    return 1\n",
            encoding="utf-8",
        )
        (root / "helper.js").write_text(
            "export function helper() { return true; }\n",
            encoding="utf-8",
        )

        project_map = ProjectScanner(root).scan()

        assert project_map.display_name == "sample"
        assert project_map.total_files >= 2
        assert any(file_info.is_entry for file_info in project_map.files)
        assert any("Demo" in file_info.classes for file_info in project_map.files)
        assert any("run_job" in file_info.functions for file_info in project_map.files)
        assert "JavaScript" in project_map.languages
        assert "<project_context>" in project_map.to_prompt()

    def test_load_project_rejects_missing_path(self):
        from project_tools import _load_project

        result = _load_project("does-not-exist")

        assert "Error: path not found" in result


class TestDanGuiSupport:
    def test_estimate_tokens_handles_string_and_structured_content(self):
        from dan_gui_support import estimate_tokens

        messages = [
            {"content": "abcd" * 4},
            {"content": [{"type": "text", "text": "hello"}]},
        ]

        assert estimate_tokens(messages) > 0

    def test_infer_provider_from_model(self):
        from dan_gui_support import infer_provider_from_model

        assert infer_provider_from_model("claude-sonnet") == "anthropic"
        assert infer_provider_from_model("gpt-4o") == "openai"
        assert infer_provider_from_model("qwen2.5-coder:14b") == "ollama"

    def test_format_relative_date_buckets(self):
        from dan_gui_support import format_relative_date

        now = 10_000.0
        assert format_relative_date(now - 120, now=now) == "2m ago"
        assert format_relative_date(now - 3_600, now=now) == "Today"
        assert format_relative_date(now - 90_000, now=now) == "Yesterday"

    def test_extract_assistant_text_normalizes_content_blocks(self):
        from dan_gui_support import extract_assistant_text

        content = [
            {"type": "text", "text": "Hello"},
            {"type": "tool_use", "name": "demo"},
            {"type": "text", "text": "World"},
        ]

        assert extract_assistant_text(content) == "Hello\nWorld"
        assert extract_assistant_text(" Plain text ") == "Plain text"

    def test_sanitize_prompt_name_strips_unsafe_characters(self):
        from dan_gui_support import sanitize_prompt_name

        assert sanitize_prompt_name(" My:Prompt?/Name ") == "MyPromptName"

    def test_build_actions_text_formats_registry_entries(self):
        from dan_gui_support import build_actions_text

        action = type("Action", (), {"name": "review", "description": "Review code"})()

        assert build_actions_text({"review": action}) == "/review  —  Review code"

    def test_session_title_from_file_prefers_first_user_message(self, tmp_path):
        from dan_gui_support import session_title_from_file

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        (sessions_dir / "chat.json").write_text(
            json.dumps(
                {
                    "messages": [
                        {"role": "assistant", "content": "hi"},
                        {"role": "user", "content": "First real user message"},
                    ]
                }
            ),
            encoding="utf-8",
        )

        title = session_title_from_file({"filename": "chat.json", "name": "Fallback"}, sessions_dir)

        assert title == "First real user message"


class TestDanGuiComponents:
    def test_components_module_exports_reusable_widgets(self):
        from dan_gui_components import GradientStrip, LiveBubble, ThinkingDots, button, label, popup_base

        assert callable(popup_base)
        assert callable(label)
        assert callable(button)
        assert ThinkingDots.__name__ == "ThinkingDots"
        assert GradientStrip.__name__ == "GradientStrip"
        assert LiveBubble.__name__ == "LiveBubble"


class TestApiConfigSecrets:
    def test_set_value_routes_secret_to_session_env(self, monkeypatch, tmp_path):
        import api_config

        monkeypatch.setattr(api_config, "CONFIG_FILE", tmp_path / "api_config.json")
        monkeypatch.delenv("VENICE_API_KEY", raising=False)

        result = api_config.set_value("venice.api_key", "venice-secret-12345")

        assert "current session only" in result
        assert api_config.get_secret("venice.api_key") == "venice-secret-12345"
        assert not api_config.CONFIG_FILE.exists()

    def test_load_config_strips_persisted_secret_values(self, monkeypatch, tmp_path):
        import api_config

        config_file = tmp_path / "api_config.json"
        config_file.write_text(
            json.dumps({"venice": {"api_key": "legacy-secret", "model": "custom-model"}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(api_config, "CONFIG_FILE", config_file)

        config = api_config.load_config()

        assert config["venice"]["model"] == "custom-model"
        assert "api_key" not in config["venice"]

    def test_show_config_masks_environment_secret(self, monkeypatch, tmp_path):
        import api_config

        monkeypatch.setattr(api_config, "CONFIG_FILE", tmp_path / "api_config.json")
        monkeypatch.setenv("VENICE_API_KEY", "venice-secret-12345")

        shown = api_config.show_config()

        assert "api_key_source: environment" in shown
        assert "venice-s...2345" in shown
        assert "venice-secret-12345" not in shown

    def test_save_config_strips_secret_fields_and_defaults_are_not_mutated(self, monkeypatch, tmp_path):
        import api_config

        config_file = tmp_path / "api_config.json"
        monkeypatch.setattr(api_config, "CONFIG_FILE", config_file)
        config = api_config.load_config()
        config["venice"]["api_key"] = "should-not-save"
        config["venice"]["model"] = "custom-model"

        api_config.save_config(config)
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        fresh = api_config.load_config()

        assert "api_key" not in saved["venice"]
        assert "api_key" not in fresh["venice"]
        assert api_config.DEFAULT_CONFIG["venice"]["model"] == "llama-3.3-70b"

    def test_set_secret_unknown_key_is_rejected(self):
        import api_config

        assert "Unknown secret key" in api_config.set_secret("bad.key", "x")


class TestAuthSystemHardening:
    def test_auth_manager_bootstraps_admin_key_to_file(self, monkeypatch, tmp_path, capsys):
        import auth_system

        monkeypatch.setitem(auth_system.AUTH_CONFIG, "auth_database", tmp_path / "auth_data.json")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "audit_log", tmp_path / "auth_audit.log")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "salt_file", tmp_path / "auth_salt.bin")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "bootstrap_admin_key_file", tmp_path / "bootstrap_admin_key.txt")
        monkeypatch.delenv("DAN_AUTH_SALT", raising=False)

        manager = auth_system.AuthManager()
        output = capsys.readouterr().out
        bootstrap_file = auth_system.AUTH_CONFIG["bootstrap_admin_key_file"]

        assert "Bootstrap file:" in output
        assert "API Key:" not in output
        assert bootstrap_file.exists()
        assert "API Key:" in bootstrap_file.read_text(encoding="utf-8")
        assert "admin" in manager.users

    def test_auth_hash_uses_persistent_generated_salt(self, monkeypatch, tmp_path):
        import auth_system

        monkeypatch.setitem(auth_system.AUTH_CONFIG, "auth_database", tmp_path / "auth_data.json")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "audit_log", tmp_path / "auth_audit.log")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "salt_file", tmp_path / "auth_salt.bin")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "bootstrap_admin_key_file", tmp_path / "bootstrap_admin_key.txt")
        monkeypatch.delenv("DAN_AUTH_SALT", raising=False)

        first = auth_system.AuthManager()
        hashed_one = first._hash_api_key("demo-key")

        second = auth_system.AuthManager()
        hashed_two = second._hash_api_key("demo-key")

        assert auth_system.AUTH_CONFIG["salt_file"].exists()
        assert hashed_one == hashed_two

    def test_failed_auth_attempt_uses_non_secret_fingerprint(self, monkeypatch, tmp_path):
        import auth_system

        monkeypatch.setitem(auth_system.AUTH_CONFIG, "require_auth", True)
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "auth_database", tmp_path / "auth_data.json")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "audit_log", tmp_path / "auth_audit.log")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "salt_file", tmp_path / "auth_salt.bin")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "bootstrap_admin_key_file", tmp_path / "bootstrap_admin_key.txt")

        manager = auth_system.AuthManager()
        submitted_key = "submitted-key-that-should-not-be-logged"

        assert manager.authenticate(submitted_key, ip_address="127.0.0.1") is None

        attempt = manager.auth_attempts[-1]
        audit_log = auth_system.AUTH_CONFIG["audit_log"].read_text(encoding="utf-8")
        assert attempt.api_key_fingerprint
        assert submitted_key not in attempt.api_key_fingerprint
        assert submitted_key[:8] not in audit_log
        assert submitted_key not in audit_log

    def test_authenticate_returns_guest_when_auth_disabled(self, monkeypatch, tmp_path):
        import auth_system

        monkeypatch.setitem(auth_system.AUTH_CONFIG, "require_auth", False)
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "auth_database", tmp_path / "auth_data.json")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "audit_log", tmp_path / "auth_audit.log")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "salt_file", tmp_path / "auth_salt.bin")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "bootstrap_admin_key_file", tmp_path / "bootstrap_admin_key.txt")

        manager = auth_system.AuthManager()
        session = manager.authenticate("anything")

        assert session is not None
        assert session.username == "guest"
        assert "*" in session.permissions

    def test_validate_session_expires_and_refreshes(self, monkeypatch, tmp_path):
        import auth_system

        monkeypatch.setitem(auth_system.AUTH_CONFIG, "require_auth", True)
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "session_timeout", 100)
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "auth_database", tmp_path / "auth_data.json")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "audit_log", tmp_path / "auth_audit.log")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "salt_file", tmp_path / "auth_salt.bin")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "bootstrap_admin_key_file", tmp_path / "bootstrap_admin_key.txt")

        manager = auth_system.AuthManager()
        user = auth_system.User("demo", manager._hash_api_key("k"), ["developer"], created=1.0)
        manager.users = {"demo": user}
        session = auth_system.Session("sid", "demo", created=100.0, expires=150.0, last_activity=100.0, permissions={"tools.read"})
        manager.sessions = {"sid": session}
        monkeypatch.setattr(auth_system.time, "time", lambda: 120.0)

        refreshed = manager.validate_session("sid")

        assert refreshed is not None
        assert refreshed.last_activity == 120.0
        assert refreshed.expires == 220.0

        monkeypatch.setattr(auth_system.time, "time", lambda: 300.0)
        assert manager.validate_session("sid") is None
        assert "sid" not in manager.sessions

    def test_check_permission_and_logout(self, monkeypatch, tmp_path):
        import auth_system

        monkeypatch.setitem(auth_system.AUTH_CONFIG, "auth_database", tmp_path / "auth_data.json")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "audit_log", tmp_path / "auth_audit.log")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "salt_file", tmp_path / "auth_salt.bin")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "bootstrap_admin_key_file", tmp_path / "bootstrap_admin_key.txt")

        manager = auth_system.AuthManager()
        session = auth_system.Session("sid", "demo", 0.0, 999.0, 0.0, {"tools.*", "knowledge.read"})
        manager.sessions = {"sid": session}

        assert manager.check_permission(session, "tools.read")
        assert manager.check_permission(session, "knowledge.read")
        assert not manager.check_permission(session, "web.search")

        manager.logout("sid")
        assert "sid" not in manager.sessions

    def test_record_failed_attempt_applies_lockout(self, monkeypatch, tmp_path):
        import auth_system

        monkeypatch.setitem(auth_system.AUTH_CONFIG, "max_failed_attempts", 2)
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "lockout_duration", 50)
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "auth_database", tmp_path / "auth_data.json")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "audit_log", tmp_path / "auth_audit.log")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "salt_file", tmp_path / "auth_salt.bin")
        monkeypatch.setitem(auth_system.AUTH_CONFIG, "bootstrap_admin_key_file", tmp_path / "bootstrap_admin_key.txt")
        monkeypatch.setattr(auth_system.time, "time", lambda: 100.0)

        manager = auth_system.AuthManager()
        manager.users["demo"] = auth_system.User("demo", "hash", ["guest"], created=0.0)

        manager.record_failed_attempt("demo")
        manager.record_failed_attempt("demo")

        assert manager.users["demo"].failed_attempts == 2
        assert manager.users["demo"].locked_until == 150.0

    def test_require_auth_and_role_decorators(self, monkeypatch):
        import auth_system

        @auth_system.require_auth("tools.read")
        def secured():
            return "ok"

        assert "Authentication required" in secured()

        session = auth_system.Session("sid", "demo", 0.0, 10.0, 0.0, {"tools.read"})
        setattr(secured, "_current_session", session)
        monkeypatch.setattr(auth_system, "get_auth_manager", lambda: type("M", (), {"check_permission": lambda self, sess, perm: True})())
        assert secured() == "ok"

        @auth_system.require_role(["admin"])
        def role_secured():
            return "role-ok"

        setattr(role_secured, "_current_session", session)
        monkeypatch.setattr(
            auth_system,
            "get_auth_manager",
            lambda: type("Manager", (), {"users": {"demo": type("User", (), {"roles": ["admin"]})()}})(),
        )
        assert role_secured() == "role-ok"


# -- Structured Execution Security Tests -------------------------------------

class TestCodeExecutionSecurity:
    def test_run_file_blocks_paths_outside_allowed_root(self, tmp_path, monkeypatch):
        import code_execution

        allowed = tmp_path / "allowed"
        outside = tmp_path / "outside"
        allowed.mkdir()
        outside.mkdir()
        script = outside / "script.py"
        script.write_text("print('should not run')", encoding="utf-8")

        monkeypatch.setattr(
            code_execution,
            "_path_validator",
            code_execution.SecurePathValidator(allowed_roots=[str(allowed)]),
        )

        result = code_execution.run_file(str(script))

        assert "Security error" in result
        assert "outside allowed directories" in result

    def test_test_loop_blocks_paths_outside_allowed_root(self, tmp_path, monkeypatch):
        import code_execution

        allowed = tmp_path / "allowed"
        outside = tmp_path / "outside"
        allowed.mkdir()
        outside.mkdir()

        monkeypatch.setattr(
            code_execution,
            "_path_validator",
            code_execution.SecurePathValidator(allowed_roots=[str(allowed)]),
        )

        result = code_execution.test_loop(str(outside), framework="pytest")

        assert "Security error" in result
        assert "outside allowed directories" in result

    def test_iterate_fix_blocks_unsafe_commands(self):
        import code_execution

        result = code_execution.iterate_fix("rm -rf /", max_tries=1)

        assert "Security error" in result
        assert "Blocked" in result


class TestSecurityUtils:
    def test_secure_path_validator_reports_safe_paths(self, tmp_path):
        from security_utils import SecurePathValidator

        allowed = tmp_path / "allowed"
        outside = tmp_path / "outside"
        allowed.mkdir()
        outside.mkdir()

        validator = SecurePathValidator(allowed_roots=[str(allowed)])

        assert validator.is_safe_path(str(allowed / "file.txt"))
        assert not validator.is_safe_path(str(outside / "file.txt"))


class TestAuthToolsBundle:
    def test_login_user_authenticates_without_existing_session(self, monkeypatch):
        import auth_tools

        auth_manager = type(
            "AuthManager",
            (),
            {
                "users": {"demo": type("User", (), {"roles": ["developer"]})()},
                "authenticate": lambda self, api_key: type("Session", (), {"username": "demo"})() if api_key == "good-key" else None,
            },
        )()
        monkeypatch.setattr(auth_tools, "get_auth_manager", lambda: auth_manager)

        success = auth_tools.login_user("good-key")
        failure = auth_tools.login_user("bad-key")

        assert "Successfully authenticated as demo" in success
        assert "Invalid API key" in failure

    def test_login_user_handles_guest_session_without_persisted_user(self, monkeypatch):
        import auth_tools

        guest_session = type("Session", (), {"username": "guest", "permissions": {"*"}})()
        auth_manager = type(
            "AuthManager",
            (),
            {
                "users": {},
                "authenticate": lambda self, api_key: guest_session,
            },
        )()
        monkeypatch.setattr(auth_tools, "get_auth_manager", lambda: auth_manager)

        result = auth_tools.login_user("ignored-in-dev-mode")

        assert "Successfully authenticated as guest" in result
        assert "session permissions: ['*']" in result

    def test_auth_tool_wrappers_cover_logout_status_create_and_permissions(self, monkeypatch):
        import auth_tools

        session = type("Session", (), {"session_id": "sid", "username": "admin", "expires": 123.0, "permissions": {"knowledge.write", "tools.read"}})()
        user = type("User", (), {"roles": ["admin"], "is_active": True, "locked_until": 0.0, "last_login": 99.0})()
        auth_manager = type(
            "AuthManager",
            (),
            {
                "users": {"admin": user},
                "logout": lambda self, sid: None,
                "get_auth_status": lambda self: {"total_users": 1, "active_sessions": 1},
                "create_user": lambda self, username, roles, creator_username: "generated-key",
                "check_permission": lambda self, sess, perm: perm in {"tools.read", "knowledge.write"},
            },
        )()

        monkeypatch.setattr(auth_tools, "get_auth_manager", lambda: auth_manager)
        monkeypatch.setattr(auth_tools, "get_current_session", lambda: session)
        monkeypatch.setattr(auth_tools.time, "time", lambda: 0.0)
        auth_tools.logout_user._current_session = session
        auth_tools.get_auth_status._current_session = session
        auth_tools.create_user._current_session = session
        auth_tools.list_users._current_session = session
        auth_tools.test_permission._current_session = session

        logout_result = auth_tools.logout_user()
        status_result = auth_tools.get_auth_status()
        create_result = auth_tools.create_user("new-user", "guest,developer")
        listed = auth_tools.list_users()
        permissions = auth_tools.test_permission()

        assert "Successfully logged out user: admin" in logout_result
        assert "Authentication Status" in status_result
        assert "User 'new-user' created successfully!" in create_result
        assert "admin: roles=['admin']" in listed
        assert "knowledge.write" in permissions

    def test_create_user_rejects_invalid_role_and_registers_tools(self, monkeypatch):
        import auth_tools

        session = type("Session", (), {"username": "admin"})()
        auth_manager = type("AuthManager", (), {"users": {"admin": type("User", (), {"roles": ["admin"]})()}})()
        monkeypatch.setattr(auth_tools, "get_auth_manager", lambda: auth_manager)
        monkeypatch.setattr(auth_tools, "get_current_session", lambda: session)
        auth_tools.create_user._current_session = session

        invalid = auth_tools.create_user("new-user", "guest,invalid")

        registered = []
        monkeypatch.setattr(auth_tools.registry, "register", lambda **kwargs: registered.append(kwargs["name"]))
        auth_tools.register_auth_tools()

        assert "Invalid roles" in invalid
        assert {"LoginUser", "LogoutUser", "AuthStatus", "CreateUser", "ListUsers", "TestPermissions"}.issubset(set(registered))


class TestProjectContextBundle:
    def test_project_context_state_round_trip(self):
        import project_context

        project_context.clear()
        project_context.set("C:/demo", "Demo", "<project_context>demo</project_context>")

        assert project_context.is_loaded()
        assert project_context.root() == "C:/demo"
        assert project_context.name() == "Demo"
        assert project_context.get() == "<project_context>demo</project_context>"

        project_context.clear()
        assert not project_context.is_loaded()

    def test_project_tools_load_show_and_unload(self, tmp_path):
        import project_context
        import project_tools

        project_context.clear()
        root = tmp_path / "sample"
        root.mkdir()
        (root / "app.py").write_text("def demo():\n    return 1\n", encoding="utf-8")

        loaded = project_tools._load_project(str(root))
        shown = project_tools._show_project()
        unloaded = project_tools._unload_project()

        assert "Project context is now injected into every message." in loaded
        assert "<project_context>" in shown
        assert "Unloaded project: sample" in unloaded
        assert "No project loaded." in project_tools._show_project()

    def test_register_project_tools_registers_expected_names(self, monkeypatch):
        import project_tools

        registered = []
        monkeypatch.setattr(project_tools.registry, "register", lambda **kwargs: registered.append(kwargs["name"]))

        project_tools.register_project_tools()

        assert {"LoadProject", "ShowProject", "UnloadProject"}.issubset(set(registered))


class TestSkillsBundle:
    def test_find_duplicates_and_scaffold_project(self, tmp_path, monkeypatch):
        import skills

        monkeypatch.setattr(skills, "_path_validator", skills.SecurePathValidator(allowed_roots=[str(tmp_path)]))
        dupes = tmp_path / "dupes"
        dupes.mkdir()
        payload = "duplicate-content" * 100
        (dupes / "a.txt").write_text(payload, encoding="utf-8")
        (dupes / "b.txt").write_text(payload, encoding="utf-8")

        result = skills.find_duplicates(str(dupes), min_size=10)
        scaffold = skills.scaffold_project("demo_app", template="python", path=str(tmp_path))
        invalid = skills.scaffold_project("demo_app", template="unknown", path=str(tmp_path))

        assert "duplicate files" in result
        assert "a.txt" in result and "b.txt" in result
        assert "Created python project 'demo_app'" in scaffold
        assert (tmp_path / "demo_app" / "pyproject.toml").exists()
        assert "Unknown template" in invalid

    def test_generate_changelog_and_webapp_test(self, monkeypatch):
        import skills

        class Completed:
            returncode = 0
            stdout = "a1|feat: add dashboard|Tyler|2026-06-04\nb2|fix: tighten parser|Tyler|2026-06-04"
            stderr = ""

        monkeypatch.setattr(skills.subprocess, "run", lambda *args, **kwargs: Completed())
        changelog = skills.generate_changelog()

        class Response:
            status_code = 200
            content = b"<html><title>Demo</title><body>ok</body></html>"
            headers = {"content-type": "text/html"}
            text = "<html><title>Demo</title><body>ok</body></html>"

        class Client:
            def __init__(self, **kwargs):
                pass
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def get(self, url):
                return Response()

        fake_httpx = type("Httpx", (), {"Client": Client})
        monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
        web_result = skills.run_webapp_test("https://example.com")

        assert "New Features" in changelog
        assert "Bug Fixes" in changelog
        assert "Server responding" in web_result
        assert "Title: Demo" in web_result

    def test_generate_changelog_errors_and_registers_tools(self, monkeypatch):
        import skills

        def timed_out(*args, **kwargs):
            raise skills.subprocess.TimeoutExpired(cmd="git", timeout=15)

        monkeypatch.setattr(skills.subprocess, "run", timed_out)
        assert "timed out" in skills.generate_changelog()

        registered = []
        monkeypatch.setattr(skills.registry, "register", lambda **kwargs: registered.append(kwargs["name"]))
        skills.register_skill_tools()

        assert {"FindDuplicates", "Scaffold", "Changelog", "WebTest"}.issubset(set(registered))


class TestCodebaseIndexBundle:
    def test_extractors_and_cosine_helpers(self):
        import codebase_index

        py_symbols, py_deps = codebase_index._extract_python(
            "import os\nfrom .helper import run\n\nclass Demo:\n    def work(self, item: int = 1):\n        \"\"\"doc line\"\"\"\n        return item\n\nasync def ping(name):\n    return name\n"
        )
        js_symbols, js_deps = codebase_index._extract_symbols(
            "import x from './lib'\nexport class Widget extends Base {}\nexport function boot(arg) {}\nconst run = (value) => value\n",
            ".js",
        )

        assert any(symbol.name == "Demo" and symbol.kind == "class" for symbol in py_symbols)
        assert any(symbol.name == "work" and symbol.kind == "method" for symbol in py_symbols)
        assert any(dep.is_local for dep in py_deps)
        assert any(symbol.name == "Widget" for symbol in js_symbols)
        assert any(dep.is_local for dep in js_deps)
        assert codebase_index._cosine([1.0, 0.0], [1.0, 0.0]) > 0.99
        assert codebase_index._cosine([1.0], [1.0, 0.0]) == 0.0

    def test_index_lookup_dependency_and_semantic_search(self, tmp_path, monkeypatch):
        import codebase_index

        monkeypatch.setattr(codebase_index, "INDEX_DIR", tmp_path / "index")
        codebase_index.INDEX_DIR.mkdir(parents=True, exist_ok=True)
        root = tmp_path / "proj"
        root.mkdir()
        (root / "app.py").write_text(
            "from .helper import helper\n\nclass Demo:\n    def work(self):\n        return helper()\n",
            encoding="utf-8",
        )
        (root / "helper.py").write_text(
            "def helper():\n    \"\"\"help docs\"\"\"\n    return 'ok'\n",
            encoding="utf-8",
        )

        indexed = codebase_index._index_project(str(root))
        lookup = codebase_index.symbol_lookup("helper", str(root))
        graph = codebase_index.dependency_graph("app.py", str(root))
        search = codebase_index.semantic_search("helper docs", str(root), use_embeddings=False)
        usages = codebase_index.find_usages("helper", str(root))

        assert "Project index for: proj" in indexed
        assert "[function] helper.py:1" in lookup
        assert "Dependency graph: app.py" in graph
        assert "Internal:" in graph
        assert "Semantic search: 'helper docs'" in search
        assert "Usages of 'helper'" in usages

    def test_vector_search_embed_project_and_register_tools(self, tmp_path, monkeypatch):
        import codebase_index

        monkeypatch.setattr(codebase_index, "INDEX_DIR", tmp_path / "index")
        codebase_index.INDEX_DIR.mkdir(parents=True, exist_ok=True)
        db = codebase_index._open_db(str(tmp_path / "proj"))
        with db:
            db.execute(
                "INSERT INTO files (path, rel_path, language, line_count, file_hash, indexed_at) VALUES (?,?,?,?,?,?)",
                ("abs.py", "app.py", "Python", 10, "hash", 1.0),
            )
            db.execute(
                "INSERT INTO symbols (id, file_id, name, kind, line, signature, docstring, parent_class) VALUES (?,?,?,?,?,?,?,?)",
                (1, 1, "helper", "function", 3, "def helper()", "help docs", ""),
            )
            db.execute(
                "INSERT INTO embeddings (symbol_id, embed_text, vector_json) VALUES (?,?,?)",
                (1, "helper def helper()", json.dumps([1.0, 0.0])),
            )
        monkeypatch.setattr(codebase_index, "_get_embedding", lambda text: [1.0, 0.0] if "help" in text else [])

        vector_results = codebase_index._vector_search(db, "help", 5)
        db.close()

        root = tmp_path / "repo"
        root.mkdir()
        (root / "mod.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
        codebase_index._index_project(str(root))
        monkeypatch.setattr(codebase_index, "_get_embedding", lambda text: [0.5, 0.5])
        embed_result = codebase_index.embed_project(str(root))

        registered = []
        monkeypatch.setattr(codebase_index.registry, "register", lambda **kwargs: registered.append(kwargs["name"]))
        codebase_index.register_index_tools()

        assert vector_results and vector_results[0][1] == "helper"
        assert "Embedding complete:" in embed_result
        assert {"IndexProject", "SymbolLookup", "FindUsages", "DependencyGraph", "SemanticSearch", "EmbedProject"}.issubset(set(registered))


class TestCodeToolsDependencyAudit:
    def test_check_deps_reports_undeclared_imports(self, tmp_path):
        import code_tools

        (tmp_path / "requirements-core.txt").write_text("Pillow>=10.0.0\n", encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("-r requirements-core.txt\n", encoding="utf-8")
        (tmp_path / "image_feature.py").write_text(
            "from PIL import Image\nimport openai\n",
            encoding="utf-8",
        )

        report = code_tools.check_deps(str(tmp_path))
        doctor = code_tools.environment_doctor(str(tmp_path), provider="openai")

        assert "Undeclared imports: 1" in report
        assert "openai" in report
        assert "Pillow" not in report.split("Imported but undeclared packages:")[-1]
        assert "Imported packages are not declared in requirements: openai" in doctor


class TestSecureToolsExpanded:
    def test_secure_read_write_edit_and_async_paths(self, monkeypatch, tmp_path):
        import tools_secure

        monkeypatch.setattr(tools_secure, "_path_validator", tools_secure.SecurePathValidator(allowed_roots=[str(tmp_path)]))
        file_path = tmp_path / "demo.txt"

        write_result = tools_secure.write_file(str(file_path), "alpha\nbeta")
        read_result = tools_secure.read_file(str(file_path), offset=1, limit=1)
        edit_result = tools_secure.edit_file(str(file_path), "beta", "gamma")

        class AsyncOpen:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc, tb):
                return False
            async def read(self):
                return "one\ntwo\nthree"

        monkeypatch.setattr(tools_secure.aiofiles, "open", lambda *args, **kwargs: AsyncOpen())
        async_result = asyncio.run(tools_secure.read_file_async(str(file_path), offset=1, limit=1))

        assert "Wrote" in write_result
        assert "2 | beta" in read_result
        assert "Edited" in edit_result
        assert "2 | two" in async_result

    def test_secure_search_listing_and_bash_edge_cases(self, monkeypatch, tmp_path):
        import tools_secure

        monkeypatch.setattr(tools_secure, "_path_validator", tools_secure.SecurePathValidator(allowed_roots=[str(tmp_path)]))
        root = tmp_path / "proj"
        root.mkdir()
        (root / "nested").mkdir()
        (root / "nested" / "a.py").write_text("value = 1\n", encoding="utf-8")
        (root / "b.txt").write_text("hello\n", encoding="utf-8")

        no_glob = tools_secure.glob_files("*.md", str(root))
        bad_regex = tools_secure.grep_files("[", str(root))
        listing = tools_secure.list_directory(str(root))

        captured = {}
        def fake_execute(command, cwd=None):
            captured["timeout"] = tools_secure._command_executor.max_execution_time
            return "x" * 10050

        monkeypatch.setattr(tools_secure._command_executor, "execute_command", fake_execute)
        bash_result = tools_secure.run_bash("echo hello", timeout=7)

        monkeypatch.setattr(tools_secure._command_executor, "execute_command", lambda command, cwd=None: (_ for _ in ()).throw(ValueError("blocked")))
        blocked = tools_secure.run_bash("echo nope")

        assert "No files matching" in no_glob
        assert "Invalid regex pattern" in bad_regex
        assert "nested/" in listing
        assert captured["timeout"] == 7
        assert "blocked" in blocked
        assert "truncated" in bash_result


class TestWebBundleExpanded:
    def test_extract_text_skips_noise_and_truncates(self):
        import web

        html = "<html><header>skip</header><body><h1>Title</h1><script>bad()</script><p>Hello world</p></body></html>"
        result = web._extract_text(html, max_chars=10)

        assert "skip" not in result
        assert "Title" in result
        assert "truncated" in result

    def test_web_search_no_results_and_error(self, monkeypatch):
        import web

        class EmptyDDGS:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def text(self, query, max_results=5):
                return iter(())

        monkeypatch.setitem(sys.modules, "ddgs", type("DDGSMod", (), {"DDGS": EmptyDDGS}))
        empty = web.web_search("nothing")

        class FailingDDGS:
            def __enter__(self):
                raise RuntimeError("boom")
            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setitem(sys.modules, "ddgs", type("DDGSMod", (), {"DDGS": FailingDDGS}))
        failed = web.web_search("broken")

        assert "No results found" in empty
        assert "Error searching for 'broken'" in failed


class TestDanGuiComponentsExpanded:
    def test_popup_label_and_button_helpers(self, monkeypatch):
        import dan_gui_components as gui

        calls = {}

        class FakeTopLevel:
            def __init__(self, parent):
                calls["parent"] = parent
            def title(self, value):
                calls["title"] = value
            def geometry(self, value):
                calls["geometry"] = value
            def configure(self, **kwargs):
                calls["configure"] = kwargs
            def transient(self, parent):
                calls["transient"] = parent
            def grab_set(self):
                calls["grab"] = True
            def after(self, delay, callback):
                calls["after"] = delay

        class FakeFont:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class FakeLabel:
            def __init__(self, parent, **kwargs):
                self.parent = parent
                self.kwargs = kwargs

        class FakeButton:
            def __init__(self, parent, text, command, **kwargs):
                self.parent = parent
                self.text = text
                self.command = command
                self.kwargs = kwargs

        monkeypatch.setattr(gui.ctk, "CTkToplevel", FakeTopLevel)
        monkeypatch.setattr(gui.ctk, "CTkFont", FakeFont)
        monkeypatch.setattr(gui.ctk, "CTkLabel", FakeLabel)
        monkeypatch.setattr(gui.ctk, "CTkButton", FakeButton)

        popup = gui.popup_base("parent", "Demo", 400, 300, "#111")
        lbl = gui.label("parent", "Hello", "#fff", size=15, weight="bold")
        btn = gui.button("parent", "Run", lambda: None, "#111", "#222", width=120)

        assert isinstance(popup, FakeTopLevel)
        assert calls["geometry"] == "400x300"
        assert lbl.kwargs["text"] == "Hello"
        assert btn.kwargs["width"] == 120

    def test_gradient_strip_draw_and_thinking_dots_tick(self):
        from dan_gui_components import GradientStrip, ThinkingDots

        strip = GradientStrip.__new__(GradientStrip)
        strip._color_one = "#000000"
        strip._color_two = "#ffffff"
        strip._height = 2
        lines = []
        strip.winfo_width = lambda: 3
        strip.delete = lambda tag: lines.append(("delete", tag))
        strip.winfo_rgb = lambda color: (0, 0, 0) if color == "#000000" else (65535, 65535, 65535)
        strip.create_line = lambda *args, **kwargs: lines.append(("line", args, kwargs))
        strip._draw()

        dots = ThinkingDots.__new__(ThinkingDots)
        dots._active = True
        dots._step = 0
        configured = []
        dots._dots = [type("Dot", (), {"configure": lambda self, **kwargs: configured.append(kwargs["text_color"])})() for _ in range(3)]
        dots.after = lambda delay, callback: configured.append(delay)
        dots._tick()
        dots.stop()

        assert any(item[0] == "line" for item in lines)
        assert configured[:3] == ["#9060f5", "#4a1a9e", "#2a0a6e"]
        assert dots._active is False

    def test_live_bubble_methods_without_real_tk(self):
        from dan_gui_components import LiveBubble

        inserted = []

        class FakeWidget:
            def tag_configure(self, *args, **kwargs):
                return None
            def insert(self, _end, text, tag):
                inserted.append((text, tag))

        class FakeTextbox:
            def __init__(self):
                self._textbox = FakeWidget()
                self.height = None
            def configure(self, **kwargs):
                if "height" in kwargs:
                    self.height = kwargs["height"]
            def see(self, _value):
                return None
            def grid(self, **kwargs):
                return None
            def index(self, _value):
                return "3.0"
            def get(self, start, end):
                return "tool output"

        class FakeDots:
            def stop(self):
                inserted.append(("stop", "dots"))
            def grid_remove(self):
                inserted.append(("hide", "dots"))

        lifted = []

        class FakeTopLevel:
            def clipboard_clear(self):
                lifted.append("clear")
            def clipboard_append(self, value):
                lifted.append(value)

        class FakeBubble:
            def __init__(self):
                self.bound = []
            def winfo_toplevel(self):
                return FakeTopLevel()
            def bind(self, event, callback):
                self.bound.append(event)

        bubble = LiveBubble.__new__(LiveBubble)
        bubble._card_hover = "#222"
        bubble._muted_text_color = "#999"
        bubble._dots = FakeDots()
        bubble.textbox = FakeTextbox()
        bubble._textbox_widget = bubble.textbox._textbox
        bubble._streaming = False
        bubble._has_content = False
        bubble._full_text = ""
        bubble.bubble = FakeBubble()
        bubble._fit = lambda: None

        buttons = []
        import dan_gui_components as gui

        class FakeButton:
            def __init__(self, parent, **kwargs):
                self.command = kwargs["command"]
                buttons.append(self)
            def place(self, **kwargs):
                return None
            def lower(self):
                return None
            def lift(self):
                return None

        original_button = gui.ctk.CTkButton
        original_font = gui.ctk.CTkFont
        gui.ctk.CTkButton = FakeButton
        gui.ctk.CTkFont = lambda **kwargs: None
        try:
            bubble.add_tool_line("tool line")
            bubble.append_text("hello")
            bubble.finish()
            buttons[0].command()
        finally:
            gui.ctk.CTkButton = original_button
            gui.ctk.CTkFont = original_font

        assert ("tool line\n", "tool") in inserted
        assert ("hello", "normal") in inserted
        assert "tool output" in lifted or "hello" in lifted


class TestDanGuiModern:
    def test_modern_gui_module_exports_shell(self):
        import dan_gui
        import dan_gui_modern

        assert issubclass(dan_gui_modern.DanModernGUI, dan_gui.DanGUI)
        assert callable(dan_gui_modern.main)


class TestGuiCompat:
    def test_gui_dependency_message_is_actionable(self, monkeypatch):
        import gui_compat

        monkeypatch.setattr(gui_compat, "CUSTOMTKINTER_AVAILABLE", False)
        monkeypatch.setattr(
            gui_compat,
            "CUSTOMTKINTER_IMPORT_ERROR",
            ModuleNotFoundError("No module named 'customtkinter'"),
        )

        message = gui_compat.gui_dependency_message()

        assert "Dan GUI cannot start" in message
        assert "requirements-core.txt" in message

    def test_ensure_gui_runtime_raises_clear_error(self, monkeypatch):
        import gui_compat

        monkeypatch.setattr(gui_compat, "CUSTOMTKINTER_AVAILABLE", False)
        monkeypatch.setattr(
            gui_compat,
            "CUSTOMTKINTER_IMPORT_ERROR",
            ModuleNotFoundError("No module named 'customtkinter'"),
        )

        with pytest.raises(RuntimeError, match="Dan GUI cannot start"):
            gui_compat.ensure_gui_runtime()


class TestDanBootstrap:
    def test_init_tools_registers_index_bundle(self, monkeypatch):
        import Dan

        calls = []
        monkeypatch.setattr(Dan, "register_core_tools", lambda: calls.append("core"))
        monkeypatch.setattr(Dan, "register_knowledge_tools", lambda: calls.append("knowledge"))
        monkeypatch.setattr(Dan, "register_web_tools", lambda: calls.append("web"))
        monkeypatch.setattr(Dan, "register_worker_tools", lambda: calls.append("workers"))
        monkeypatch.setattr(Dan, "register_action_tools", lambda: calls.append("actions"))
        monkeypatch.setattr(Dan, "register_skill_tools", lambda: calls.append("skills"))
        monkeypatch.setattr(Dan, "register_code_tools", lambda: calls.append("code"))
        monkeypatch.setattr(Dan, "register_git_tools", lambda: calls.append("git"))
        monkeypatch.setattr(Dan, "register_project_tools", lambda: calls.append("project"))
        monkeypatch.setattr(Dan, "register_execution_tools", lambda: calls.append("execution"))
        monkeypatch.setattr(Dan, "register_index_tools", lambda: calls.append("index"))
        monkeypatch.setitem(sys.modules, "image_tools", type("ImageTools", (), {})())
        monkeypatch.setitem(sys.modules, "ml_tools", type("MlTools", (), {})())

        import tool_registry as registry
        monkeypatch.setattr(registry, "get_all_tools", lambda: [])

        Dan.init_tools()

        assert "index" in calls


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
