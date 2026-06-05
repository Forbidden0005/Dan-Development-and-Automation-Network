from provider_common import KeyRotator, parse_tool_arguments
from provider_types import Message, Response, ToolCall


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

    def chat(
        self,
        messages: list[Message],
        system: str = "",
        tools: list[dict] | None = None,
        max_tokens: int = 8192,
    ) -> Response:
        est = sum(len(str(m.content)) for m in messages) // 4
        api_key, key_idx = self.rotator.next(estimated_tokens=est)
        client = self._openai.OpenAI(api_key=api_key)

        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(m.to_dict() for m in messages)

        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": msgs,
        }

        if tools:
            oai_tools = []
            for t in tools:
                oai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "parameters": t.get("input_schema", {}),
                        },
                    }
                )
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
                resp.tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        input=parse_tool_arguments(tc.function.arguments),
                    )
                )
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
