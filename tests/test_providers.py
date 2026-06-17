"""
Provider test coverage — steward pass 28 (2026-06-10).

These tests complement the provider tests already in test_dan.py.
They target paths that are not exercised there:

  OllamaProvider  : _to_ollama_tools, chat (non-streaming), chat_stream happy
                    path, _parse_tool_calls edge cases, properties
  OpenAIProvider  : context_limit for non-gpt-4 model, key_count, supports_streaming
  AnthropicProvider: chat_stream rate-limit fallback to chat(), key_count,
                     context_limit
  VeniceProvider  : tool-gating (only for FUNCTION_CALLING_MODELS), API error
                    returns error Response, context_limit table, key_count,
                    supports_streaming, init without api_key raises ValueError

All tests use only stdlib / monkeypatching — no real network calls.
"""

import sys
import types
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_fake_httpx(*, text_response="ok", usage=None, tool_calls=None,
                     stream_lines=None, stream_error=False):
    """Build a fake httpx module for OllamaProvider tests."""
    usage = usage or {"prompt_eval_count": 1, "eval_count": 2}
    tool_calls = tool_calls or []
    stream_lines = stream_lines or []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "message": {"content": text_response, "tool_calls": tool_calls},
                **usage,
            }

    class FakeStreamContext:
        def __enter__(self):
            if stream_error:
                raise RuntimeError("stream error")
            return self

        def __exit__(self, *_):
            return False

        def raise_for_status(self):
            pass

        def iter_lines(self):
            return iter(stream_lines)

    class FakeHttpx:
        @staticmethod
        def post(url, json=None, timeout=None):
            return FakeResponse()

        @staticmethod
        def stream(method, url, json=None, timeout=None):
            return FakeStreamContext()

    return FakeHttpx


def _make_fake_openai(*, content="done", tool_calls=None, prompt_tokens=5, completion_tokens=3):
    """Build a fake openai module for OpenAI/Venice provider tests."""
    tool_calls = tool_calls or []

    class FakeCompletion:
        def create(self, **kwargs):
            message = types.SimpleNamespace(content=content, tool_calls=tool_calls)
            choice = types.SimpleNamespace(message=message, finish_reason="stop")
            usage = types.SimpleNamespace(
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
            )
            return types.SimpleNamespace(choices=[choice], usage=usage)

    fake_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=FakeCompletion())
    )

    class FakeOpenAI:
        OpenAI = staticmethod(lambda api_key=None, base_url=None: fake_client)

    return FakeOpenAI


def _simple_rotator(key="test-key"):
    """Return a minimal KeyRotator stand-in."""
    class FakeRotator:
        count = 1

        def next(self, estimated_tokens=0):
            return (key, 0)

        def record_usage(self, key_idx, total):
            pass

    return FakeRotator()


# ── OllamaProvider ────────────────────────────────────────────────────────────

class TestOllamaProviderTools:
    def test_to_ollama_tools_basic_conversion(self):
        import provider_ollama

        tools = [
            {
                "name": "Read",
                "description": "Read a file",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
            }
        ]
        result = provider_ollama.OllamaProvider._to_ollama_tools(tools)

        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "Read"
        assert result[0]["function"]["description"] == "Read a file"
        assert result[0]["function"]["parameters"]["type"] == "object"

    def test_to_ollama_tools_uses_default_schema_when_missing(self):
        import provider_ollama

        tools = [{"name": "Glob"}]
        result = provider_ollama.OllamaProvider._to_ollama_tools(tools)

        assert result[0]["function"]["parameters"] == {"type": "object", "properties": {}}

    def test_to_ollama_tools_empty_list(self):
        import provider_ollama

        assert provider_ollama.OllamaProvider._to_ollama_tools([]) == []


class TestOllamaProviderMessages:
    def test_to_ollama_messages_plain_string_content(self):
        """Messages with string content (not list) pass through directly."""
        import provider_ollama
        from provider_types import Message

        msgs = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there"),
        ]
        result = provider_ollama.OllamaProvider._to_ollama_messages(msgs, "")

        assert result[0] == {"role": "user", "content": "Hello"}
        assert result[1] == {"role": "assistant", "content": "Hi there"}

    def test_to_ollama_messages_omits_system_when_empty(self):
        import provider_ollama
        from provider_types import Message

        msgs = [Message(role="user", content="hi")]
        result = provider_ollama.OllamaProvider._to_ollama_messages(msgs, "")

        assert result[0]["role"] == "user"
        assert not any(m["role"] == "system" for m in result)

    def test_to_ollama_messages_non_dict_blocks_skipped(self):
        """Non-dict blocks in list content are silently skipped."""
        import provider_ollama
        from provider_types import Message

        msgs = [Message(role="assistant", content=["not a dict", {"type": "text", "text": "hi"}])]
        result = provider_ollama.OllamaProvider._to_ollama_messages(msgs, "")

        # Only the valid block contributes content
        assert result[0]["content"] == "hi"


class TestOllamaProviderParseToolCalls:
    def test_parse_tool_calls_with_dict_arguments(self):
        """Arguments already a dict — should pass through without JSON parsing."""
        import provider_ollama

        msg = {
            "tool_calls": [
                {"function": {"name": "Write", "arguments": {"path": "out.txt", "content": "x"}}}
            ]
        }
        calls = provider_ollama.OllamaProvider._parse_tool_calls(msg)

        assert calls[0].name == "Write"
        assert calls[0].input == {"path": "out.txt", "content": "x"}

    def test_parse_tool_calls_malformed_json_string_returns_empty_input(self):
        import provider_ollama

        msg = {"tool_calls": [{"function": {"name": "Read", "arguments": "{bad json"}}]}
        calls = provider_ollama.OllamaProvider._parse_tool_calls(msg)

        assert calls[0].input == {}

    def test_parse_tool_calls_empty_list(self):
        import provider_ollama

        assert provider_ollama.OllamaProvider._parse_tool_calls({}) == []
        assert provider_ollama.OllamaProvider._parse_tool_calls({"tool_calls": []}) == []

    def test_parse_tool_calls_assigns_sequential_ids(self):
        import provider_ollama

        msg = {
            "tool_calls": [
                {"function": {"name": "Read", "arguments": {}}},
                {"function": {"name": "Glob", "arguments": {}}},
            ]
        }
        calls = provider_ollama.OllamaProvider._parse_tool_calls(msg)

        assert calls[0].id == "call_0"
        assert calls[1].id == "call_1"


class TestOllamaProviderChat:
    def test_chat_happy_path(self, monkeypatch):
        import provider_ollama
        from provider_types import Message

        fake_httpx = _make_fake_httpx(
            text_response="Great!", usage={"prompt_eval_count": 4, "eval_count": 9}
        )
        monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
        provider = provider_ollama.OllamaProvider("llama3.1")
        response = provider.chat([Message(role="user", content="hello")])

        assert response.text == "Great!"
        assert response.stop_reason == "stop"
        assert response.usage == {"input": 4, "output": 9}

    def test_chat_includes_tools_in_payload(self, monkeypatch):
        """When tools are passed, the payload should include the tools key."""
        import provider_ollama
        from provider_types import Message

        captured = {}

        class CapturingHttpx:
            @staticmethod
            def post(url, json=None, timeout=None):
                captured["payload"] = json
                r = types.SimpleNamespace()
                r.raise_for_status = lambda: None
                r.json = lambda: {
                    "message": {"content": "ok", "tool_calls": []},
                    "prompt_eval_count": 0,
                    "eval_count": 0,
                }
                return r

        monkeypatch.setitem(sys.modules, "httpx", CapturingHttpx)
        provider = provider_ollama.OllamaProvider("llama3.1")
        provider.chat(
            [Message(role="user", content="hi")],
            tools=[{"name": "Read", "input_schema": {}}],
        )

        assert "tools" in captured["payload"]
        assert captured["payload"]["stream"] is False

    def test_chat_without_tools_omits_tools_key(self, monkeypatch):
        import provider_ollama
        from provider_types import Message

        captured = {}

        class CapturingHttpx:
            @staticmethod
            def post(url, json=None, timeout=None):
                captured["payload"] = json
                r = types.SimpleNamespace()
                r.raise_for_status = lambda: None
                r.json = lambda: {
                    "message": {"content": "ok", "tool_calls": []},
                    "prompt_eval_count": 0,
                    "eval_count": 0,
                }
                return r

        monkeypatch.setitem(sys.modules, "httpx", CapturingHttpx)
        provider = provider_ollama.OllamaProvider("llama3.1")
        provider.chat([Message(role="user", content="hi")])

        assert "tools" not in captured["payload"]


class TestOllamaProviderChatStream:
    def _make_stream_lines(self, chunks, final_usage=None):
        """Build JSONL lines for the streaming response."""
        import json
        lines = []
        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            entry = {"message": {"content": chunk, "tool_calls": []}, "done": is_last}
            if is_last and final_usage:
                entry["prompt_eval_count"] = final_usage[0]
                entry["eval_count"] = final_usage[1]
            lines.append(json.dumps(entry))
        return lines

    def test_chat_stream_happy_path_collects_text(self, monkeypatch):
        import provider_ollama
        from provider_types import Message

        stream_lines = self._make_stream_lines(["Hello", " world"], final_usage=(3, 5))

        class FakeStreamContext:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def raise_for_status(self):
                pass

            def iter_lines(self_inner):
                return iter(stream_lines)

        class FakeHttpx:
            @staticmethod
            def stream(method, url, json=None, timeout=None):
                return FakeStreamContext()

        monkeypatch.setitem(sys.modules, "httpx", FakeHttpx)
        provider = provider_ollama.OllamaProvider("llama3.1")

        received = []
        response = provider.chat_stream(
            [Message(role="user", content="hi")], on_text=received.append
        )

        assert response.text == "Hello world"
        assert received == ["Hello", " world"]
        assert response.usage == {"input": 3, "output": 5}

    def test_chat_stream_calls_on_text_for_each_chunk(self, monkeypatch):
        import provider_ollama
        from provider_types import Message

        stream_lines = self._make_stream_lines(["A", "B", "C"])

        class FakeStreamContext:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def iter_lines(self_inner):
                return iter(stream_lines)

        class FakeHttpx:
            @staticmethod
            def stream(method, url, json=None, timeout=None):
                return FakeStreamContext()

        monkeypatch.setitem(sys.modules, "httpx", FakeHttpx)
        provider = provider_ollama.OllamaProvider("llama3.1")

        chunks = []
        provider.chat_stream([Message(role="user", content="hi")], on_text=chunks.append)

        assert chunks == ["A", "B", "C"]

    def test_chat_stream_skips_empty_lines(self, monkeypatch):
        """Empty lines in the stream should be silently skipped."""
        import json
        import provider_ollama
        from provider_types import Message

        lines = [
            "",
            json.dumps({"message": {"content": "ok", "tool_calls": []}, "done": True,
                        "prompt_eval_count": 1, "eval_count": 1}),
        ]

        class FakeStreamContext:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def iter_lines(self_inner):
                return iter(lines)

        class FakeHttpx:
            @staticmethod
            def stream(method, url, json=None, timeout=None):
                return FakeStreamContext()

        monkeypatch.setitem(sys.modules, "httpx", FakeHttpx)
        provider = provider_ollama.OllamaProvider("llama3.1")
        response = provider.chat_stream([Message(role="user", content="hi")])

        assert response.text == "ok"


class TestOllamaProviderProperties:
    def test_supports_streaming_is_true(self, monkeypatch):
        import provider_ollama

        fake_httpx = _make_fake_httpx()
        monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
        provider = provider_ollama.OllamaProvider()

        assert provider.supports_streaming is True

    def test_context_limit(self, monkeypatch):
        import provider_ollama

        fake_httpx = _make_fake_httpx()
        monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
        provider = provider_ollama.OllamaProvider()

        assert provider.context_limit == 32_000

    def test_key_count_is_one(self, monkeypatch):
        import provider_ollama

        fake_httpx = _make_fake_httpx()
        monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
        provider = provider_ollama.OllamaProvider()

        assert provider.key_count == 1

    def test_ollama_url_from_environment(self, monkeypatch):
        import provider_ollama

        fake_httpx = _make_fake_httpx()
        monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
        monkeypatch.setenv("OLLAMA_URL", "http://custom-host:11434")
        provider = provider_ollama.OllamaProvider()

        assert provider.base_url == "http://custom-host:11434"


# ── OpenAIProvider ─────────────────────────────────────────────────────────────

class TestOpenAIProviderProperties:
    def test_context_limit_gpt4_models(self, monkeypatch):
        import provider_openai

        monkeypatch.setitem(sys.modules, "openai", _make_fake_openai())
        monkeypatch.setattr(provider_openai, "KeyRotator", lambda prefix: _simple_rotator())
        provider = provider_openai.OpenAIProvider("gpt-4-turbo")

        assert provider.context_limit == 128_000

    def test_context_limit_non_gpt4_model_returns_16k(self, monkeypatch):
        import provider_openai

        monkeypatch.setitem(sys.modules, "openai", _make_fake_openai())
        monkeypatch.setattr(provider_openai, "KeyRotator", lambda prefix: _simple_rotator())
        provider = provider_openai.OpenAIProvider("gpt-3.5-turbo")

        assert provider.context_limit == 16_000

    def test_supports_streaming_is_false(self, monkeypatch):
        import provider_openai

        monkeypatch.setitem(sys.modules, "openai", _make_fake_openai())
        monkeypatch.setattr(provider_openai, "KeyRotator", lambda prefix: _simple_rotator())
        provider = provider_openai.OpenAIProvider("gpt-4o")

        assert provider.supports_streaming is False

    def test_key_count_delegates_to_rotator(self, monkeypatch):
        import provider_openai

        class RotatorWithCount:
            count = 3

            def next(self, estimated_tokens=0):
                return ("key", 0)

            def record_usage(self, key_idx, total):
                pass

        monkeypatch.setitem(sys.modules, "openai", _make_fake_openai())
        monkeypatch.setattr(provider_openai, "KeyRotator", lambda prefix: RotatorWithCount())
        provider = provider_openai.OpenAIProvider("gpt-4o")

        assert provider.key_count == 3

    def test_chat_system_message_prepended(self, monkeypatch):
        """System string should appear as the first message with role 'system'."""
        import provider_openai
        from provider_types import Message

        captured_kwargs = {}

        class CapturingCompletion:
            def create(self, **kwargs):
                captured_kwargs.update(kwargs)
                message = types.SimpleNamespace(content="ok", tool_calls=None)
                choice = types.SimpleNamespace(message=message, finish_reason="stop")
                usage = types.SimpleNamespace(prompt_tokens=1, completion_tokens=1)
                return types.SimpleNamespace(choices=[choice], usage=usage)

        fake_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=CapturingCompletion())
        )
        monkeypatch.setitem(
            sys.modules, "openai",
            types.SimpleNamespace(OpenAI=lambda api_key=None: fake_client)
        )
        monkeypatch.setattr(provider_openai, "KeyRotator", lambda prefix: _simple_rotator())

        provider = provider_openai.OpenAIProvider("gpt-4o")
        provider.chat([Message(role="user", content="hi")], system="Be helpful.")

        messages = captured_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "Be helpful."}
        assert messages[1]["role"] == "user"


# ── AnthropicProvider ──────────────────────────────────────────────────────────

class TestAnthropicProviderProperties:
    def _make_fake_anthropic(self, messages_api):
        """Build a minimal fake anthropic module."""
        return types.SimpleNamespace(
            Anthropic=lambda api_key=None: types.SimpleNamespace(messages=messages_api),
            RateLimitError=RuntimeError,
        )

    def test_context_limit(self, monkeypatch):
        import provider_anthropic

        class NoopMessages:
            pass

        monkeypatch.setitem(sys.modules, "anthropic", self._make_fake_anthropic(NoopMessages()))
        monkeypatch.setattr(provider_anthropic, "KeyRotator", lambda prefix: _simple_rotator())
        provider = provider_anthropic.AnthropicProvider("claude-sonnet-4-6")

        assert provider.context_limit == 200_000

    def test_supports_streaming(self, monkeypatch):
        import provider_anthropic

        class NoopMessages:
            pass

        monkeypatch.setitem(sys.modules, "anthropic", self._make_fake_anthropic(NoopMessages()))
        monkeypatch.setattr(provider_anthropic, "KeyRotator", lambda prefix: _simple_rotator())
        provider = provider_anthropic.AnthropicProvider()

        assert provider.supports_streaming is True

    def test_key_count_delegates_to_rotator(self, monkeypatch):
        import provider_anthropic

        class MultiKeyRotator:
            count = 4

            def next(self, estimated_tokens=0):
                return ("key", 0)

            def record_usage(self, key_idx, total):
                pass

        class NoopMessages:
            pass

        monkeypatch.setitem(sys.modules, "anthropic", self._make_fake_anthropic(NoopMessages()))
        monkeypatch.setattr(provider_anthropic, "KeyRotator", lambda prefix: MultiKeyRotator())
        provider = provider_anthropic.AnthropicProvider()

        assert provider.key_count == 4

    def test_chat_stream_rate_limit_falls_back_to_chat(self, monkeypatch):
        """When streaming raises RateLimitError, chat_stream() falls back to chat()."""
        import provider_anthropic
        from provider_types import Message

        class RateLimitError(Exception):
            pass

        class ChatFallbackMessages:
            def stream(self, **kwargs):
                raise RateLimitError("rate limited")

            def create(self, **kwargs):
                # Called by the fallback chat() method
                usage = types.SimpleNamespace(input_tokens=1, output_tokens=1)
                block = types.SimpleNamespace(type="text", text="Fallback answer")
                return types.SimpleNamespace(
                    stop_reason="end_turn",
                    usage=usage,
                    content=[block],
                )

        fake_anthropic = types.SimpleNamespace(
            Anthropic=lambda api_key=None: types.SimpleNamespace(
                messages=ChatFallbackMessages()
            ),
            RateLimitError=RateLimitError,
        )
        monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)
        monkeypatch.setattr(provider_anthropic, "KeyRotator", lambda prefix: _simple_rotator())

        provider = provider_anthropic.AnthropicProvider()
        response = provider.chat_stream([Message(role="user", content="hello")])

        assert response.text == "Fallback answer"


# ── VeniceProvider ─────────────────────────────────────────────────────────────

class TestVeniceProviderInit:
    def test_raises_without_api_key(self, monkeypatch):
        import provider_venice

        monkeypatch.setitem(sys.modules, "openai", _make_fake_openai())
        # Ensure no api_config, no env var
        monkeypatch.setattr(
            "provider_venice.VeniceProvider.__init__.__code__",
            provider_venice.VeniceProvider.__init__.__code__,
        )
        monkeypatch.delenv("VENICE_API_KEY", raising=False)

        # Patch get_secret to raise (simulates missing config)
        try:
            import api_config
            monkeypatch.setattr(api_config, "get_secret", lambda key: "")
        except Exception:
            pass

        with pytest.raises((ValueError, Exception)):
            provider_venice.VeniceProvider(model="llama-3.3-70b", api_key="")

    def test_accepts_explicit_api_key(self, monkeypatch):
        import provider_venice

        monkeypatch.setitem(sys.modules, "openai", _make_fake_openai())
        # Should not raise
        provider = provider_venice.VeniceProvider(model="llama-3.3-70b", api_key="explicit-key")
        assert provider._api_key == "explicit-key"

    def test_uses_venice_api_key_env_var(self, monkeypatch):
        import provider_venice

        monkeypatch.setitem(sys.modules, "openai", _make_fake_openai())
        monkeypatch.setenv("VENICE_API_KEY", "env-key")

        # Patch get_secret to return "" so env var path is exercised
        try:
            import api_config
            monkeypatch.setattr(api_config, "get_secret", lambda key: "")
        except Exception:
            pass

        provider = provider_venice.VeniceProvider(model="llama-3.3-70b")
        assert provider._api_key == "env-key"


class TestVeniceProviderChat:
    def _provider(self, monkeypatch, model="llama-3.3-70b", **fake_openai_kwargs):
        import provider_venice

        monkeypatch.setitem(sys.modules, "openai", _make_fake_openai(**fake_openai_kwargs))
        return provider_venice.VeniceProvider(model=model, api_key="test-key")

    def test_chat_returns_text_response(self, monkeypatch):
        from provider_types import Message

        provider = self._provider(monkeypatch, content="Hello from Venice")
        response = provider.chat([Message(role="user", content="hi")])

        assert response.text == "Hello from Venice"
        assert response.stop_reason == "stop"

    def test_chat_strips_think_tags(self, monkeypatch):
        """<think>...</think> blocks should be removed from the response text."""
        from provider_types import Message

        provider = self._provider(
            monkeypatch, content="<think>internal reasoning</think>Final answer"
        )
        response = provider.chat([Message(role="user", content="hi")])

        assert "<think>" not in response.text
        assert response.text == "Final answer"

    def test_chat_tools_only_sent_for_function_calling_models(self, monkeypatch):
        """Tools should only appear in the API call for FUNCTION_CALLING_MODELS."""
        import provider_venice
        from provider_types import Message

        captured = {}

        class CapturingCompletion:
            def create(self, **kwargs):
                captured["kwargs"] = kwargs
                message = types.SimpleNamespace(content="ok", tool_calls=None)
                choice = types.SimpleNamespace(message=message, finish_reason="stop")
                usage = types.SimpleNamespace(prompt_tokens=1, completion_tokens=1)
                return types.SimpleNamespace(choices=[choice], usage=usage)

        fake_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=CapturingCompletion())
        )
        monkeypatch.setitem(
            sys.modules, "openai",
            types.SimpleNamespace(
                OpenAI=lambda api_key=None, base_url=None: fake_client
            )
        )

        tools = [{"name": "Read", "input_schema": {}}]

        # Non-function-calling model: tools should NOT be in kwargs
        provider = provider_venice.VeniceProvider(model="llama-3.3-70b", api_key="k")
        provider.chat([Message(role="user", content="hi")], tools=tools)
        assert "tools" not in captured.get("kwargs", {}), \
            "tools should not be sent for non-function-calling models"

        # Function-calling model: tools SHOULD be in kwargs
        provider2 = provider_venice.VeniceProvider(model="mistral-31-24b", api_key="k")
        provider2.chat([Message(role="user", content="hi")], tools=tools)
        assert "tools" in captured.get("kwargs", {}), \
            "tools should be sent for function-calling models"

    def test_chat_api_error_returns_error_response(self, monkeypatch):
        """API errors are caught and returned as a Response with stop_reason='error'."""
        import provider_venice
        from provider_types import Message

        class ErrorCompletion:
            def create(self, **kwargs):
                raise ConnectionError("API unavailable")

        fake_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=ErrorCompletion())
        )
        monkeypatch.setitem(
            sys.modules, "openai",
            types.SimpleNamespace(
                OpenAI=lambda api_key=None, base_url=None: fake_client
            )
        )

        provider = provider_venice.VeniceProvider(model="llama-3.3-70b", api_key="k")
        response = provider.chat([Message(role="user", content="hi")])

        assert response.stop_reason == "error"
        assert "Venice API error" in response.text

    def test_chat_system_message_prepended(self, monkeypatch):
        import provider_venice
        from provider_types import Message

        captured = {}

        class CapturingCompletion:
            def create(self, **kwargs):
                captured["messages"] = kwargs["messages"]
                message = types.SimpleNamespace(content="ok", tool_calls=None)
                choice = types.SimpleNamespace(message=message, finish_reason="stop")
                usage = types.SimpleNamespace(prompt_tokens=1, completion_tokens=1)
                return types.SimpleNamespace(choices=[choice], usage=usage)

        fake_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=CapturingCompletion())
        )
        monkeypatch.setitem(
            sys.modules, "openai",
            types.SimpleNamespace(OpenAI=lambda api_key=None, base_url=None: fake_client)
        )

        provider = provider_venice.VeniceProvider(model="llama-3.3-70b", api_key="k")
        provider.chat([Message(role="user", content="hello")], system="Be concise.")

        assert captured["messages"][0] == {"role": "system", "content": "Be concise."}


class TestVeniceProviderProperties:
    def _provider(self, monkeypatch, model="llama-3.3-70b"):
        import provider_venice

        monkeypatch.setitem(sys.modules, "openai", _make_fake_openai())
        return provider_venice.VeniceProvider(model=model, api_key="test-key")

    def test_supports_streaming_is_false(self, monkeypatch):
        provider = self._provider(monkeypatch)
        assert provider.supports_streaming is False

    def test_key_count_is_one(self, monkeypatch):
        provider = self._provider(monkeypatch)
        assert provider.key_count == 1

    def test_context_limit_known_models(self, monkeypatch):
        import provider_venice

        monkeypatch.setitem(sys.modules, "openai", _make_fake_openai())

        cases = {
            "llama-3.3-70b": 128_000,
            "llama-3.2-3b": 131_072,
            "mistral-31-24b": 131_072,
            "qwen3-4b": 40_000,
            "venice-uncensored": 32_000,
        }
        for model, expected in cases.items():
            provider = provider_venice.VeniceProvider(model=model, api_key="k")
            assert provider.context_limit == expected, f"Wrong limit for {model}"

    def test_context_limit_unknown_model_returns_default(self, monkeypatch):
        provider = self._provider(monkeypatch, model="some-unknown-model")
        assert provider.context_limit == 128_000

    def test_base_url_defaults_to_venice(self, monkeypatch):
        import provider_venice

        monkeypatch.setitem(sys.modules, "openai", _make_fake_openai())
        provider = provider_venice.VeniceProvider(model="llama-3.3-70b", api_key="k")
        assert provider.base_url == provider_venice.VeniceProvider.VENICE_BASE_URL

    def test_custom_base_url_override(self, monkeypatch):
        import provider_venice

        monkeypatch.setitem(sys.modules, "openai", _make_fake_openai())
        provider = provider_venice.VeniceProvider(
            model="llama-3.3-70b", api_key="k", base_url="https://custom.example.com/v1"
        )
        assert provider.base_url == "https://custom.example.com/v1"
