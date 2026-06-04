"""LLM provider abstraction layer with proactive API key rotation."""

from provider_anthropic import AnthropicProvider
from provider_common import KeyRotator
from provider_ollama import OllamaProvider
from provider_openai import OpenAIProvider
from provider_types import Message, Response, ToolCall
from provider_venice import VeniceProvider

__all__ = [
    "AnthropicProvider",
    "KeyRotator",
    "Message",
    "OllamaProvider",
    "OpenAIProvider",
    "Response",
    "ToolCall",
    "VeniceProvider",
    "get_provider",
]


def get_provider(name: str | None = None, model: str | None = None):
    """Factory to get a provider by name."""
    from config import DEFAULT_MODEL, DEFAULT_PROVIDER

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
    if name == "openai":
        return provider_cls(model=model if "gpt" in model else "gpt-4o")
    if name == "venice":
        return provider_cls(model=model if model != DEFAULT_MODEL else "llama-3.3-70b")
    return provider_cls(model=model)
