import json
import os
import re

from provider_common import parse_tool_arguments
from provider_types import Message, Response, ToolCall


class VeniceProvider:
    """Venice AI provider — OpenAI-compatible API with uncensored models."""

    VENICE_BASE_URL = "https://api.venice.ai/api/v1"
    FUNCTION_CALLING_MODELS = {
        "zai-org-glm-4.7",
        "mistral-31-24b",
        "llama-3.2-3b",
        "qwen3-4b",
    }

    def __init__(self, model: str = "llama-3.3-70b", api_key: str = "", base_url: str = ""):
        self.model = model
        self.base_url = base_url or self.VENICE_BASE_URL

        if not api_key:
            try:
                from api_config import get_secret

                api_key = get_secret("venice.api_key")
            except Exception:
                pass
        if not api_key:
            api_key = os.environ.get("VENICE_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "No Venice API key found. Set VENICE_API_KEY, "
                "or load it in Settings or /config for the current session."
            )
        self._api_key = api_key

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
        client = self._openai.OpenAI(
            api_key=self._api_key,
            base_url=self.base_url,
        )

        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(m.to_dict() for m in messages)

        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": msgs,
        }

        if tools and self.model in self.FUNCTION_CALLING_MODELS:
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

        if "<think>" in resp.text:
            resp.text = re.sub(r"<think>.*?</think>\s*", "", resp.text, flags=re.DOTALL)

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
