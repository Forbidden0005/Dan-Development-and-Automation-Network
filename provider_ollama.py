import json
import logging
import os
from typing import Callable

from provider_types import Message, Response, ToolCall

logger = logging.getLogger(__name__)


class OllamaProvider:
    """Local Ollama provider with streaming and tool call support."""

    def __init__(self, model: str = "llama3.1"):
        self.model = model
        self.base_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.timeout = int(os.environ.get("OLLAMA_TIMEOUT", "300"))
        self.num_ctx = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
        try:
            import httpx

            self._httpx = httpx
        except ImportError:
            raise ImportError("pip install httpx")

    @staticmethod
    def _to_ollama_tools(tools: list[dict]) -> list[dict]:
        result = []
        for t in tools:
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                    },
                }
            )
        return result

    @staticmethod
    def _to_ollama_messages(messages: list[Message], system: str) -> list[dict]:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})

        for m in messages:
            content = m.content
            if isinstance(content, str):
                msgs.append({"role": m.role, "content": content})
                continue

            if m.role == "assistant":
                text = ""
                tool_calls = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        text += block.get("text", "")
                    elif block.get("type") == "tool_use":
                        tool_calls.append(
                            {
                                "function": {
                                    "name": block.get("name", ""),
                                    "arguments": block.get("input", {}),
                                }
                            }
                        )
                entry: dict = {"role": "assistant", "content": text}
                if tool_calls:
                    entry["tool_calls"] = tool_calls
                msgs.append(entry)

            elif m.role == "user":
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_result":
                        msgs.append(
                            {
                                "role": "tool",
                                "content": str(block.get("content", "")),
                            }
                        )
                    elif block.get("type") == "text":
                        msgs.append({"role": "user", "content": block.get("text", "")})

        return msgs

    @staticmethod
    def _parse_tool_calls(message: dict) -> list[ToolCall]:
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

    def chat(
        self,
        messages: list[Message],
        system: str = "",
        tools: list[dict] | None = None,
        max_tokens: int = 8192,
    ) -> Response:
        msgs = self._to_ollama_messages(messages, system)
        payload: dict = {
            "model": self.model,
            "messages": msgs,
            "stream": False,
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

    def chat_stream(
        self,
        messages: list[Message],
        system: str = "",
        tools: list[dict] | None = None,
        max_tokens: int = 8192,
        on_text: Callable[[str], None] | None = None,
    ) -> Response:
        msgs = self._to_ollama_messages(messages, system)
        payload: dict = {
            "model": self.model,
            "messages": msgs,
            "stream": True,
            "options": {"num_ctx": self.num_ctx},
        }
        if tools:
            payload["tools"] = self._to_ollama_tools(tools)

        resp = Response()
        try:
            with self._httpx.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
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
