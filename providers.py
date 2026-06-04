"""LLM provider abstraction layer with proactive API key rotation."""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── API Key Rotation ─────────────────────────────────────────────────────────

class KeyRotator:
    """Rotates through up to 5 API keys on a fixed time interval.

    Uses each key for HOLD_SECONDS (default 20s) before switching to the
    next key on the following API call. Simple and predictable.
    """

    HOLD_SECONDS = 120  # seconds to stay on one key before rotating (reduced rotation frequency)

    def __init__(self, prefix: str):
        self.prefix = prefix
        self.keys: list[str] = []
        self._index = 0
        self._key_start_time: float = time.time()
        self._calls_per_key: dict[int, int] = {}

        for i in range(1, 6):
            key = os.environ.get(f"{prefix}_{i}", "").strip()
            if key:
                self.keys.append(key)

        if not self.keys:
            single = os.environ.get(prefix, "").strip()
            if single:
                self.keys.append(single)

        if not self.keys:
            raise ValueError(
                f"No API keys found. Set {prefix}_1 through {prefix}_5, "
                f"or set {prefix} as a fallback."
            )

        for i in range(len(self.keys)):
            self._calls_per_key[i] = 0

        logger.info("KeyRotator[%s]: loaded %d key(s)", prefix, len(self.keys))

    def record_usage(self, key_idx: int, tokens: int) -> None:
        """Record that a call was made on a key (kept for interface compat)."""
        self._calls_per_key[key_idx] = self._calls_per_key.get(key_idx, 0) + 1

    def next(self, estimated_tokens: int = 5000) -> tuple[str, int]:
        """Return the current key. Rotate only if 20s have elapsed.

        Returns (api_key, key_index_0based).
        """
        now = time.time()
        elapsed = now - self._key_start_time

        if elapsed >= self.HOLD_SECONDS and len(self.keys) > 1:
            self._index = (self._index + 1) % len(self.keys)
            self._key_start_time = now
            logger.debug("Rotated to key %d after %.1fs", self._index + 1, elapsed)

        return self.keys[self._index], self._index

    @property
    def current_index(self) -> int:
        return self._index + 1

    @property
    def count(self) -> int:
        return len(self.keys)

    def status(self) -> str:
        """Human-readable status of all keys."""
        elapsed = time.time() - self._key_start_time
        remaining = max(0, self.HOLD_SECONDS - elapsed)
        lines = []
        for i in range(len(self.keys)):
            calls = self._calls_per_key.get(i, 0)
            marker = f" ◄ active ({remaining:.0f}s left)" if i == self._index else ""
            lines.append(f"  Key {i+1}: {calls} calls{marker}")
        return "\n".join(lines)


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class Message:
    role: str
    content: str | list[dict]

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class Response:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    key_index: int = 0


# ── Providers ────────────────────────────────────────────────────────────────

class AnthropicProvider:
    """Anthropic Claude API provider with proactive key rotation."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model
        self.rotator = KeyRotator("ANTHROPIC_API_KEY")
        try:
            import anthropic
            self._anthropic = anthropic
        except ImportError:
            raise ImportError("pip install anthropic")

    def chat(self, messages: list[Message], system: str = "",
             tools: list[dict] | None = None, max_tokens: int = 8192) -> Response:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [m.to_dict() for m in messages],
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        # Estimate input size for smart key selection
        est = sum(len(str(m.content)) for m in messages) // 4
        est += len(str(system)) // 4 if system else 0

        # Pick best key proactively
        api_key, key_idx = self.rotator.next(estimated_tokens=est)
        client = self._anthropic.Anthropic(api_key=api_key)
        # Removed debug print for performance

        try:
            result = client.messages.create(**kwargs)
        except self._anthropic.RateLimitError:
            # Shouldn't happen often — mark key full, switch, retry
            self.rotator.record_usage(key_idx, self.rotator.RATE_LIMIT_PER_KEY)
            logger.warning(f"Key {key_idx + 1} rate-limited, switching...")
            api_key, key_idx = self.rotator.next(estimated_tokens=est)
            client = self._anthropic.Anthropic(api_key=api_key)
            # Removed debug print for performance
            result = client.messages.create(**kwargs)

        # Record actual usage
        total_tokens = result.usage.input_tokens + result.usage.output_tokens
        self.rotator.record_usage(key_idx, total_tokens)

        resp = Response(
            stop_reason=result.stop_reason or "",
            usage={"input": result.usage.input_tokens, "output": result.usage.output_tokens},
            key_index=key_idx + 1,
        )
        for block in result.content:
            if block.type == "text":
                resp.text += block.text
            elif block.type == "tool_use":
                resp.tool_calls.append(ToolCall(
                    id=block.id, name=block.name, input=block.input
                ))
        return resp

    def chat_stream(self, messages: list[Message], system: str = "",
                    tools: list[dict] | None = None, max_tokens: int = 8192,
                    on_text: Callable[[str], None] | None = None) -> "Response":
        """Streaming chat — calls *on_text* with each text chunk as it arrives.

        Tool-call content is accumulated silently; the returned Response is
        identical in structure to the non-streaming ``chat()`` result.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [m.to_dict() for m in messages],
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        est = sum(len(str(m.content)) for m in messages) // 4
        api_key, key_idx = self.rotator.next(estimated_tokens=est)
        client = self._anthropic.Anthropic(api_key=api_key)

        resp = Response(key_index=key_idx + 1)

        try:
            with client.messages.stream(**kwargs) as stream:
                # Stream text chunks to caller
                for chunk in stream.text_stream:
                    resp.text += chunk
                    if on_text:
                        on_text(chunk)

                # Collect the completed message (includes tool_use blocks)
                final = stream.get_final_message()

            resp.stop_reason = final.stop_reason or ""
            resp.usage = {
                "input":  final.usage.input_tokens,
                "output": final.usage.output_tokens,
            }

            for block in final.content:
                if block.type == "tool_use":
                    resp.tool_calls.append(ToolCall(
                        id=block.id, name=block.name, input=block.input
                    ))

        except self._anthropic.RateLimitError:
            logger.warning("Key %d rate-limited during stream, retrying...", key_idx + 1)
            # Fall back to non-streaming on rate limit
            return self.chat(messages, system, tools, max_tokens)

        total_tokens = resp.usage.get("input", 0) + resp.usage.get("output", 0)
        self.rotator.record_usage(key_idx, total_tokens)
        return resp

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def context_limit(self) -> int:
        return 200_000

    @property
    def key_count(self) -> int:
        return self.rotator.count


class OpenAIProvider:
    """OpenAI API provider with key rotation."""

    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.rotator = KeyRotator("OPENAI_API_KEY")
        try:
            import openai
            self._openai = openai
        except ImportError:
            raise ImportError("pip install openai")

    def chat(self, messages: list[Message], system: str = "",
             tools: list[dict] | None = None, max_tokens: int = 8192) -> Response:
        est = sum(len(str(m.content)) for m in messages) // 4
        api_key, key_idx = self.rotator.next(estimated_tokens=est)
        client = self._openai.OpenAI(api_key=api_key)
        print(f"  🔑 Key {key_idx + 1}/{self.rotator.count}")

        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(m.to_dict() for m in messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": msgs,
        }

        if tools:
            oai_tools = []
            for t in tools:
                oai_tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {}),
                    }
                })
            kwargs["tools"] = oai_tools

        result = client.chat.completions.create(**kwargs)
        choice = result.choices[0]

        total = (result.usage.prompt_tokens + result.usage.completion_tokens) if result.usage else 0
        self.rotator.record_usage(key_idx, total)

        resp = Response(
            text=choice.message.content or "",
            stop_reason=choice.finish_reason or "",
            usage={
                "input": result.usage.prompt_tokens if result.usage else 0,
                "output": result.usage.completion_tokens if result.usage else 0,
            },
            key_index=key_idx + 1,
        )

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                resp.tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    input=json.loads(tc.function.arguments),
                ))
        return resp

    @property
    def supports_streaming(self) -> bool:
        return False

    @property
    def context_limit(self) -> int:
        if "gpt-4" in self.model:
            return 128_000
        return 16_000

    @property
    def key_count(self) -> int:
        return self.rotator.count


class OllamaProvider:
    """Local Ollama provider with streaming and tool call support."""

    def __init__(self, model: str = "llama3.1"):
        self.model = model
        self.base_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.timeout  = int(os.environ.get("OLLAMA_TIMEOUT", "300"))
        self.num_ctx  = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
        try:
            import httpx
            self._httpx = httpx
        except ImportError:
            raise ImportError("pip install httpx")

    # ── Format converters ─────────────────────────────────────────────────────

    @staticmethod
    def _to_ollama_tools(tools: list[dict]) -> list[dict]:
        """Convert Anthropic-style tool schemas to Ollama/OpenAI format."""
        result = []
        for t in tools:
            result.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            })
        return result

    @staticmethod
    def _to_ollama_messages(messages: list[Message], system: str) -> list[dict]:
        """Convert Anthropic-style messages to Ollama/OpenAI format."""
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})

        for m in messages:
            content = m.content
            if isinstance(content, str):
                msgs.append({"role": m.role, "content": content})
                continue

            # List content — Anthropic uses blocks; convert each type
            if m.role == "assistant":
                text = ""
                tool_calls = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        text += block.get("text", "")
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": block.get("input", {}),
                            }
                        })
                entry: dict = {"role": "assistant", "content": text}
                if tool_calls:
                    entry["tool_calls"] = tool_calls
                msgs.append(entry)

            elif m.role == "user":
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_result":
                        msgs.append({
                            "role": "tool",
                            "content": str(block.get("content", "")),
                        })
                    elif block.get("type") == "text":
                        msgs.append({"role": "user", "content": block.get("text", "")})

        return msgs

    @staticmethod
    def _parse_tool_calls(message: dict) -> list[ToolCall]:
        """Extract tool calls from an Ollama response message."""
        calls = []
        for i, tc in enumerate(message.get("tool_calls", [])):
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            calls.append(ToolCall(id=f"call_{i}", name=fn.get("name", ""), input=args))
        return calls

    # ── API calls ─────────────────────────────────────────────────────────────

    def chat(self, messages: list[Message], system: str = "",
             tools: list[dict] | None = None, max_tokens: int = 8192) -> Response:
        msgs = self._to_ollama_messages(messages, system)
        payload: dict = {
            "model": self.model, "messages": msgs, "stream": False,
            "options": {"num_ctx": self.num_ctx},
        }
        if tools:
            payload["tools"] = self._to_ollama_tools(tools)

        r = self._httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        message = data.get("message", {})

        resp = Response(
            text=message.get("content", "") or "",
            stop_reason="stop",
            usage={
                "input": data.get("prompt_eval_count", 0),
                "output": data.get("eval_count", 0),
            },
        )
        resp.tool_calls = self._parse_tool_calls(message)
        return resp

    def chat_stream(self, messages: list[Message], system: str = "",
                    tools: list[dict] | None = None, max_tokens: int = 8192,
                    on_text: Callable[[str], None] | None = None) -> Response:
        """Streaming chat — streams text tokens live, collects tool calls at end."""
        msgs = self._to_ollama_messages(messages, system)
        payload: dict = {
            "model": self.model, "messages": msgs, "stream": True,
            "options": {"num_ctx": self.num_ctx},
        }
        if tools:
            payload["tools"] = self._to_ollama_tools(tools)

        resp = Response()
        try:
            with self._httpx.stream(
                "POST", f"{self.base_url}/api/chat",
                json=payload, timeout=self.timeout,
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue

                    message = data.get("message", {})
                    chunk = message.get("content") or ""
                    if chunk:
                        resp.text += chunk
                        if on_text:
                            on_text(chunk)

                    # Tool calls arrive in the final chunk
                    tool_calls = self._parse_tool_calls(message)
                    if tool_calls:
                        resp.tool_calls = tool_calls

                    if data.get("done"):
                        resp.stop_reason = "stop"
                        resp.usage = {
                            "input": data.get("prompt_eval_count", 0),
                            "output": data.get("eval_count", 0),
                        }
                        break
        except Exception as e:
            logger.warning("Stream failed (%s), falling back to non-streaming", e)
            return self.chat(messages, system, tools, max_tokens)

        return resp

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def context_limit(self) -> int:
        return 32_000

    @property
    def key_count(self) -> int:
        return 1


class VeniceProvider:
    """Venice AI provider — OpenAI-compatible API with uncensored models."""

    VENICE_BASE_URL = "https://api.venice.ai/api/v1"

    # Models known to support function calling
    FUNCTION_CALLING_MODELS = {
        "zai-org-glm-4.7", "mistral-31-24b", "llama-3.2-3b", "qwen3-4b",
    }

    def __init__(self, model: str = "llama-3.3-70b", api_key: str = "",
                 base_url: str = ""):
        self.model = model
        self.base_url = base_url or self.VENICE_BASE_URL

        # Try api_config, then env, then passed key
        if not api_key:
            try:
                from api_config import load_config
                cfg = load_config()
                api_key = cfg.get("venice", {}).get("api_key", "")
            except Exception:
                pass
        if not api_key:
            api_key = os.environ.get("VENICE_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "No Venice API key found. Set VENICE_API_KEY env var, "
                "or run /config set venice.api_key=YOUR_KEY"
            )
        self._api_key = api_key

        try:
            import openai
            self._openai = openai
        except ImportError:
            raise ImportError("pip install openai")

    def chat(self, messages: list[Message], system: str = "",
             tools: list[dict] | None = None, max_tokens: int = 8192) -> Response:
        client = self._openai.OpenAI(
            api_key=self._api_key,
            base_url=self.base_url,
        )
        print(f"  Venice ({self.model})")

        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(m.to_dict() for m in messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": msgs,
        }

        # Only pass tools if model supports function calling
        if tools and self.model in self.FUNCTION_CALLING_MODELS:
            oai_tools = []
            for t in tools:
                oai_tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {}),
                    }
                })
            kwargs["tools"] = oai_tools

        # Venice rejects null values — strip None fields
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        try:
            result = client.chat.completions.create(**kwargs)
        except Exception as e:
            return Response(text=f"Venice API error: {e}", stop_reason="error")

        choice = result.choices[0]
        usage_input = result.usage.prompt_tokens if result.usage else 0
        usage_output = result.usage.completion_tokens if result.usage else 0

        resp = Response(
            text=choice.message.content or "",
            stop_reason=choice.finish_reason or "",
            usage={"input": usage_input, "output": usage_output},
        )

        # Strip <think> tags from reasoning models
        if "<think>" in resp.text:
            import re
            resp.text = re.sub(r'<think>.*?</think>\s*', '', resp.text, flags=re.DOTALL)

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                resp.tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    input=json.loads(tc.function.arguments),
                ))
        return resp

    @property
    def supports_streaming(self) -> bool:
        return False

    @property
    def context_limit(self) -> int:
        limits = {
            "llama-3.3-70b": 128_000,
            "llama-3.2-3b": 131_072,
            "mistral-31-24b": 131_072,
            "qwen3-4b": 40_000,
            "zai-org-glm-4.7": 128_000,
            "venice-uncensored": 32_000,
        }
        return limits.get(self.model, 128_000)

    @property
    def key_count(self) -> int:
        return 1


def get_provider(name: str | None = None, model: str | None = None):
    """Factory to get a provider by name."""
    from config import DEFAULT_PROVIDER, DEFAULT_MODEL

    # Check api_config for saved provider preference
    try:
        from api_config import load_config
        cfg = load_config()
        if not name and cfg.get("provider"):
            name = cfg["provider"]
        if not model and name and name in cfg:
            saved_model = cfg[name].get("model", "")
            if saved_model:
                model = saved_model
    except Exception:
        pass

    name = (name or DEFAULT_PROVIDER)
    if isinstance(name, str):
        name = name.strip().lower()
    model = model or DEFAULT_MODEL

    providers = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "venice": VeniceProvider,
        "ollama": OllamaProvider,
    }
    if name not in providers:
        raise ValueError(f"Unknown provider: {name}. Options: {list(providers.keys())}")

    provider_cls = providers[name]
    if name == "anthropic":
        return provider_cls(model=model if "claude" in model else "claude-sonnet-4-6")
    elif name == "openai":
        return provider_cls(model=model if "gpt" in model else "gpt-4o")
    elif name == "venice":
        return provider_cls(model=model if model != DEFAULT_MODEL else "llama-3.3-70b")
    else:
        return provider_cls(model=model)
