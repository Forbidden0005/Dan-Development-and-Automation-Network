"""API configuration — persistent provider and key settings."""

import json
import logging
import os
from pathlib import Path

from config import USER_DATA_DIR

logger = logging.getLogger(__name__)

CONFIG_FILE = USER_DATA_DIR / "api_config.json"
SECRET_KEY_ENV_MAP = {
    "anthropic.api_key": "ANTHROPIC_API_KEY",
    "openai.api_key": "OPENAI_API_KEY",
    "venice.api_key": "VENICE_API_KEY",
}

DEFAULT_CONFIG = {
    "provider": "ollama",
    "model": "",
    "venice": {
        "model": "llama-3.3-70b",
        "base_url": "https://api.venice.ai/api/v1",
    },
    "anthropic": {
        "model": "claude-sonnet-4-6",
    },
    "openai": {
        "model": "gpt-4o",
    },
    "ollama": {
        "model": "qwen2.5-coder:7b",
        "base_url": "http://localhost:11434",
    },
}


def load_config() -> dict:
    """Load config from disk, merging with defaults."""
    config = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text())
            if isinstance(saved.get("venice"), dict):
                saved["venice"].pop("api_key", None)
            _deep_merge(config, saved)
        except Exception as e:
            logger.warning("Failed to load config: %s", e)
    return config


def save_config(config: dict) -> str:
    """Save config to disk."""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return f"Config saved to {CONFIG_FILE}"
    except Exception as e:
        return f"Error saving config: {e}"


def get_secret(key: str) -> str:
    """Return a secret value from environment-backed storage."""
    env_key = SECRET_KEY_ENV_MAP.get(key)
    if not env_key:
        return ""
    return os.environ.get(env_key, "").strip()


def set_secret(key: str, value: str) -> str:
    """Set or clear a secret for the current process session only."""
    env_key = SECRET_KEY_ENV_MAP.get(key)
    if not env_key:
        return f"Unknown secret key: {key}"

    value = value.strip()
    if value:
        os.environ[env_key] = value
        return f"Loaded {key} for the current session only. Persist it via env var {env_key}."

    os.environ.pop(env_key, None)
    return f"Cleared {key} from the current session."


def get_value(key: str) -> str:
    """Get a config value by dot-path (e.g. 'venice.model')."""
    if key in SECRET_KEY_ENV_MAP:
        return _mask(key, get_secret(key))
    config = load_config()
    parts = key.split(".")
    val = config
    for p in parts:
        if isinstance(val, dict) and p in val:
            val = val[p]
        else:
            return f"Unknown key: {key}"
    return str(val)


def set_value(key: str, value: str) -> str:
    """Set a config value by dot-path (e.g. 'venice.api_key=xxx')."""
    if key in SECRET_KEY_ENV_MAP:
        return set_secret(key, value)

    config = load_config()
    parts = key.split(".")
    target = config
    for p in parts[:-1]:
        if p not in target or not isinstance(target[p], dict):
            target[p] = {}
        target = target[p]
    target[parts[-1]] = value
    save_config(config)
    return f"Set {key} = {_mask(key, value)}"


def show_config() -> str:
    """Show current config (masking sensitive values)."""
    config = load_config()
    lines = ["API Configuration:"]
    lines.append(f"  Config file: {CONFIG_FILE}")
    lines.append(f"  Active provider: {config.get('provider', '?')}")
    lines.append("")

    for provider in ["anthropic", "openai", "venice", "ollama"]:
        section = config.get(provider, {})
        if not isinstance(section, dict):
            continue
        lines.append(f"  [{provider}]")
        for k, v in section.items():
            if k == "api_key":
                continue
            lines.append(f"    {k}: {_mask(k, str(v))}")
        secret_key = f"{provider}.api_key"
        if secret_key in SECRET_KEY_ENV_MAP:
            secret_value = get_secret(secret_key)
            source = "environment" if secret_value else "not set"
            lines.append(f"    api_key: {_mask('api_key', secret_value) if secret_value else '(not set)'}")
            lines.append(f"    api_key_source: {source}")
        lines.append("")

    return "\n".join(lines)


def _mask(key: str, value: str) -> str:
    """Mask sensitive values for display."""
    if "key" in key.lower() and len(value) > 10:
        return value[:8] + "..." + value[-4:]
    return value


def _deep_merge(base: dict, override: dict) -> None:
    """Merge override into base recursively."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
