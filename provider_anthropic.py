from typing import Any, Callable

from provider_common import KeyRotator
from provider_types import Message, Response, ToolCall

import logging

logger = logging.getLogger(__name__)


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

        est = sum(len(str(m.content)) for m in messages) // 4
        est += len(str(system)) // 4 if system else 0

        api_key, key_idx = self.rotator.next(estimated_tokens=est)
        client = self._anthropic.Anthropic(api_key=api_key)

        try:
            result = client.messages.create(**kwargs)
        except self._anthropic.RateLimitError:
            self.rotator.record_usage(key_idx, 0)
            logger.warning("Key %d rate-limited, switching...", key_idx + 1)
            api_key, key_idx = self.rotator.next(estimated_tokens=est)
            client = self._anthropic.Anthropic(api_key=api_key)
            result = client.messages.create(**kwargs)

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
                    on_text: Callable[[str], None] | None = None) -> Response:
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
        est += len(str(system)) // 4 if system else 0
        api_key, key_idx = self.rotator.next(estimated_tokens=est)
        client = self._anthropic.Anthropic(api_key=api_key)

        resp = Response(key_index=key_idx + 1)

        try:
            with client.messages.stream(**kwargs) as stream:
                for chunk in stream.text_stream:
                    resp.text += chunk
                    if on_text:
                        on_text(chunk)

                final = stream.get_final_message()

            resp.stop_reason = final.stop_reason or ""
            resp.usage = {
                "input": final.usage.input_tokens,
                "output": final.usage.output_tokens,
            }

            for block in final.content:
                if block.type == "tool_use":
                    resp.tool_calls.append(ToolCall(
                        id=block.id, name=block.name, input=block.input
                    ))

        except self._anthropic.RateLimitError:
            logger.warning("Key %d rate-limited during stream, retrying...", key_idx + 1)
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
