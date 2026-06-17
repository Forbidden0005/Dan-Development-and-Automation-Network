"""Unit tests for api_config.py — persistent provider and key settings.

Coverage goals:
- load_config: defaults, merging, api_key stripping (security), corrupt-file resilience
- save_config: api_key stripping before write (security), no in-place mutation of input
- _deep_merge: scalar override, nested dict merge, new-key addition, dict-to-scalar replacement
- _mask: long secret redaction, short-value pass-through, non-key field pass-through, boundary
- get_value / set_value: dot-path navigation, secret routing to env (not disk)
- get_secret / set_secret: env-var read/write, whitespace stripping, empty-value clearing

All tests use monkeypatching to isolate CONFIG_FILE from the real user data directory.
No test writes to or reads from the real %APPDATA%/Dan directory.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── load_config / save_config ─────────────────────────────────────────────────


class TestApiConfigLoadSave:
    """Tests for load_config and save_config."""

    def test_load_config_returns_defaults_when_no_file(self, monkeypatch, tmp_path):
        """Missing config file must fall through to built-in defaults, not raise."""
        import api_config

        monkeypatch.setattr(api_config, "CONFIG_FILE", tmp_path / "nonexistent.json")

        config = api_config.load_config()

        assert config["provider"] == "ollama"
        assert "anthropic" in config
        assert "openai" in config
        assert "venice" in config
        assert "ollama" in config

    def test_load_config_merges_saved_values_with_defaults(self, monkeypatch, tmp_path):
        """Saved values override defaults; unspecified keys still return defaults."""
        import api_config

        config_file = tmp_path / "api_config.json"
        config_file.write_text(json.dumps({"provider": "anthropic"}), encoding="utf-8")
        monkeypatch.setattr(api_config, "CONFIG_FILE", config_file)

        config = api_config.load_config()

        assert config["provider"] == "anthropic"
        # Default sub-sections must survive the merge
        assert "anthropic" in config
        assert "ollama" in config

    def test_load_config_strips_api_key_from_venice_section(self, monkeypatch, tmp_path):
        """api_key must never be read back from disk into the venice config section.

        This is a security requirement: even if a stale file contains a key, the
        load path must drop it so callers cannot accidentally expose it.
        """
        import api_config

        config_file = tmp_path / "api_config.json"
        saved = {"venice": {"model": "llama-3.3-70b", "api_key": "sk-venice-stale"}}
        config_file.write_text(json.dumps(saved), encoding="utf-8")
        monkeypatch.setattr(api_config, "CONFIG_FILE", config_file)

        config = api_config.load_config()

        assert "api_key" not in config.get("venice", {}), (
            "load_config must strip api_key from the venice section on read"
        )

    def test_load_config_handles_corrupt_json_gracefully(self, monkeypatch, tmp_path):
        """Corrupt config file must fall back to defaults without raising."""
        import api_config

        config_file = tmp_path / "api_config.json"
        config_file.write_text("{ not valid json }", encoding="utf-8")
        monkeypatch.setattr(api_config, "CONFIG_FILE", config_file)

        config = api_config.load_config()

        # Defaults must still be present after parse failure
        assert config["provider"] == "ollama"
        assert "anthropic" in config

    def test_save_config_strips_api_key_before_writing(self, monkeypatch, tmp_path):
        """API keys must never be persisted to disk — save_config must strip them.

        This is the primary security control preventing credentials from being
        written to the config file.  All three provider sections are tested.
        """
        import api_config

        config_file = tmp_path / "api_config.json"
        monkeypatch.setattr(api_config, "CONFIG_FILE", config_file)
        config = {
            "provider": "anthropic",
            "anthropic": {"model": "claude-opus-4", "api_key": "sk-ant-secret"},
            "openai": {"model": "gpt-4o", "api_key": "sk-openai-secret"},
            "venice": {"model": "llama-3.3-70b", "api_key": "sk-venice-secret"},
            "ollama": {"model": "qwen2.5-coder:7b"},
        }

        api_config.save_config(config)

        written = json.loads(config_file.read_text(encoding="utf-8"))
        assert "api_key" not in written.get("anthropic", {}), "anthropic api_key leaked to disk"
        assert "api_key" not in written.get("openai", {}), "openai api_key leaked to disk"
        assert "api_key" not in written.get("venice", {}), "venice api_key leaked to disk"
        # Non-secret fields must survive the write
        assert written["provider"] == "anthropic"
        assert written["anthropic"]["model"] == "claude-opus-4"

    def test_save_config_does_not_mutate_input_dict(self, monkeypatch, tmp_path):
        """save_config must work on a deep copy — the caller's dict must not be modified.

        If save_config stripped keys in-place the caller's in-memory config would
        lose its api_key for the rest of the session.
        """
        import api_config

        config_file = tmp_path / "api_config.json"
        monkeypatch.setattr(api_config, "CONFIG_FILE", config_file)
        config = {
            "provider": "openai",
            "openai": {"model": "gpt-4o", "api_key": "sk-openai-secret"},
        }

        api_config.save_config(config)

        assert "api_key" in config["openai"], (
            "save_config must not mutate the caller's dict — api_key was stripped in-place"
        )


# ── _deep_merge ───────────────────────────────────────────────────────────────


class TestDeepMerge:
    """Tests for the _deep_merge helper used during config loading."""

    def test_deep_merge_overrides_scalar_value(self):
        import api_config

        base = {"provider": "ollama", "model": ""}
        api_config._deep_merge(base, {"provider": "anthropic"})

        assert base["provider"] == "anthropic"
        assert base["model"] == ""  # untouched key preserved

    def test_deep_merge_merges_nested_dicts_without_losing_base_keys(self):
        import api_config

        base = {"venice": {"model": "llama-3.3-70b", "base_url": "https://api.venice.ai/api/v1"}}
        api_config._deep_merge(base, {"venice": {"model": "mistral-7b"}})

        assert base["venice"]["model"] == "mistral-7b"
        assert base["venice"]["base_url"] == "https://api.venice.ai/api/v1"

    def test_deep_merge_adds_new_top_level_keys(self):
        import api_config

        base = {"a": 1}
        api_config._deep_merge(base, {"b": 2})

        assert base["b"] == 2
        assert base["a"] == 1

    def test_deep_merge_replaces_dict_with_scalar_when_override_is_not_dict(self):
        import api_config

        base = {"a": {"nested": True}}
        api_config._deep_merge(base, {"a": "flat"})

        assert base["a"] == "flat"

    def test_deep_merge_handles_deeply_nested_structure(self):
        import api_config

        base = {"ui": {"theme": "dark", "font_size": 14}}
        api_config._deep_merge(base, {"ui": {"theme": "light"}})

        assert base["ui"]["theme"] == "light"
        assert base["ui"]["font_size"] == 14


# ── _mask ─────────────────────────────────────────────────────────────────────


class TestMask:
    """Tests for _mask — ensures sensitive values are redacted in display output."""

    def test_mask_redacts_long_api_key_values(self):
        import api_config

        value = "sk-ant-1234567890abcdef"
        result = api_config._mask("api_key", value)

        assert "..." in result
        assert result.startswith(value[:8])
        assert result.endswith(value[-4:])
        # The raw secret must not appear in the middle
        assert value not in result

    def test_mask_passes_through_short_values(self):
        """Values of 10 characters or fewer are not masked (length threshold = 10)."""
        import api_config

        result = api_config._mask("api_key", "short")
        assert result == "short"

    def test_mask_passes_through_non_key_fields(self):
        """Non-sensitive fields (no 'key' in field name) must never be masked."""
        import api_config

        result = api_config._mask("model", "claude-opus-4-8-20251101")
        assert result == "claude-opus-4-8-20251101"

    def test_mask_does_not_mask_at_exactly_ten_characters(self):
        """Boundary: exactly 10 chars must not be masked (condition is len > 10)."""
        import api_config

        result = api_config._mask("api_key", "1234567890")
        assert result == "1234567890"

    def test_mask_applies_at_eleven_characters(self):
        """Boundary: 11 chars must trigger masking."""
        import api_config

        result = api_config._mask("api_key", "12345678901")
        assert "..." in result


# ── get_value / set_value ─────────────────────────────────────────────────────


class TestGetSetValue:
    """Tests for get_value and set_value dot-path routing."""

    def test_get_value_reads_known_top_level_config_key(self, monkeypatch, tmp_path):
        import api_config

        monkeypatch.setattr(api_config, "CONFIG_FILE", tmp_path / "none.json")

        result = api_config.get_value("provider")

        assert result == "ollama"

    def test_get_value_navigates_nested_dot_path(self, monkeypatch, tmp_path):
        import api_config

        monkeypatch.setattr(api_config, "CONFIG_FILE", tmp_path / "none.json")

        result = api_config.get_value("ollama.model")

        assert result == "qwen2.5-coder:7b"

    def test_get_value_returns_unknown_for_missing_key(self, monkeypatch, tmp_path):
        import api_config

        monkeypatch.setattr(api_config, "CONFIG_FILE", tmp_path / "none.json")

        result = api_config.get_value("nonexistent.path.here")

        assert "Unknown key" in result

    def test_get_value_routes_secret_keys_through_env_and_masks_output(
        self, monkeypatch, tmp_path
    ):
        """Secret keys (api_key fields) must be read from env, not config, and masked."""
        import api_config

        monkeypatch.setattr(api_config, "CONFIG_FILE", tmp_path / "none.json")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-secret-value-here")

        result = api_config.get_value("anthropic.api_key")

        # Result must be masked — the raw secret must not appear
        assert "sk-ant-test-secret-value-here" not in result
        assert "..." in result

    def test_set_value_persists_non_secret_config_key_to_disk(self, monkeypatch, tmp_path):
        import api_config

        config_file = tmp_path / "api_config.json"
        monkeypatch.setattr(api_config, "CONFIG_FILE", config_file)

        api_config.set_value("provider", "anthropic")

        written = json.loads(config_file.read_text(encoding="utf-8"))
        assert written["provider"] == "anthropic"

    def test_set_value_routes_secret_key_to_env_not_disk(self, monkeypatch, tmp_path):
        """Setting an api_key must go to the process environment, never to the config file."""
        import api_config

        config_file = tmp_path / "api_config.json"
        monkeypatch.setattr(api_config, "CONFIG_FILE", config_file)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        result = api_config.set_value("anthropic.api_key", "sk-ant-newsecret")

        # Config file must not be created — secrets go to env only
        assert not config_file.exists(), (
            "set_value must not write api_key secrets to the config file on disk"
        )
        # Env var must be set for the current process session
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-newsecret"
        assert "current session" in result


# ── get_secret / set_secret ───────────────────────────────────────────────────


class TestGetSetSecret:
    """Tests for the environment-variable-backed secret accessors."""

    def test_get_secret_reads_from_environment_variable(self, monkeypatch):
        import api_config

        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-value")

        assert api_config.get_secret("openai.api_key") == "sk-openai-test-value"

    def test_get_secret_returns_empty_string_when_env_var_unset(self, monkeypatch):
        import api_config

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        assert api_config.get_secret("openai.api_key") == ""

    def test_get_secret_returns_empty_for_unknown_key(self):
        import api_config

        result = api_config.get_secret("unknown.api_key")

        assert result == ""

    def test_set_secret_sets_environment_variable_for_current_process(self, monkeypatch):
        import api_config

        monkeypatch.delenv("VENICE_API_KEY", raising=False)

        api_config.set_secret("venice.api_key", "sk-venice-test")

        assert os.environ.get("VENICE_API_KEY") == "sk-venice-test"

    def test_set_secret_clears_env_var_when_value_is_empty(self, monkeypatch):
        import api_config

        monkeypatch.setenv("VENICE_API_KEY", "sk-venice-old")

        api_config.set_secret("venice.api_key", "")

        assert os.environ.get("VENICE_API_KEY") is None

    def test_set_secret_strips_whitespace_from_value(self, monkeypatch):
        import api_config

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        api_config.set_secret("anthropic.api_key", "  sk-ant-stripped  ")

        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-stripped"

    def test_set_secret_returns_error_message_for_unknown_key(self):
        import api_config

        result = api_config.set_secret("unknown.api_key", "value")

        assert "Unknown secret key" in result

    def test_set_secret_returns_helpful_message_on_success(self, monkeypatch):
        import api_config

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = api_config.set_secret("openai.api_key", "sk-openai-test-val")

        assert "current session" in result
        assert "OPENAI_API_KEY" in result
