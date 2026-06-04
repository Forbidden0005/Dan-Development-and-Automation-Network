"""Tests for Dan."""

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
