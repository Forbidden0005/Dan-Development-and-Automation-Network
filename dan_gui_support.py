"""Pure helper functions and controller utilities for the Dan GUI.

This module has two sections:
  1. Pure helper functions — no GUI imports, no side effects, fully testable.
  2. register_all_tools() — the canonical tool-registration entry point for
     both GUI shells and the CLI.  Keeping this here means neither DanGUI nor
     DanModernGUI needs to inline the registration loop, and the CLI can call
     it without importing any tkinter code.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path
import json

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_TEMPLATE = (
    "You are an expert in [TOPIC].\n\n"
    "Your role is to:\n- [Task 1]\n- [Task 2]\n\n"
    "Guidelines:\n- Be specific and practical\n"
    "- Provide examples when helpful\n"
    "- Ask for clarification when needed\n"
)


def timestamp_label(now: datetime | None = None) -> str:
    """Return the current time as a short label for chat bubbles."""
    current = now or datetime.now()
    if sys.platform != "win32":
        return current.strftime("%-I:%M %p")
    return current.strftime("%I:%M %p").lstrip("0")


def estimate_tokens(messages: list[dict]) -> int:
    """Estimate token usage from message content."""
    total = 0
    for message in messages:
        content = message.get("content", "")
        total += len(content) // 4 if isinstance(content, str) else len(str(content)) // 4
    return total


def infer_provider_from_model(model: str) -> str:
    """Infer the provider name from the selected model label."""
    if "claude" in model:
        return "anthropic"
    if "gpt" in model:
        return "openai"
    return "ollama"


def format_relative_date(timestamp: float, now: float | None = None) -> str:
    """Format a saved-session timestamp for the sidebar."""
    current_time = now if now is not None else time.time()
    diff = current_time - timestamp
    if diff < 3600:
        return f"{max(1, int(diff / 60))}m ago"
    if diff < 86400:
        return "Today"
    if diff < 172800:
        return "Yesterday"
    if diff < 604800:
        return f"{int(diff / 86400)}d ago"
    return time.strftime("%b %d", time.localtime(timestamp))


def extract_assistant_text(content) -> str:
    """Normalize assistant content blocks into plain text for rendering."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    return "\n".join(
        block.get("text", "").strip()
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


def build_actions_text(actions: dict) -> str:
    """Format action registry entries for the actions popup."""
    return "\n".join(f"/{action.name}  —  {action.description}" for action in actions.values())


def sanitize_prompt_name(name: str) -> str:
    """Return a filesystem-safe prompt name."""
    return "".join(char for char in name if char.isalnum() or char in " _-").strip()


def session_title_from_file(session: dict, sessions_dir: Path) -> str:
    """Read the first user message from a saved session for sidebar display."""
    try:
        file_path = sessions_dir / session["filename"]
        data = json.loads(file_path.read_text(encoding="utf-8"))
        for message in data.get("messages", []):
            if message.get("role") != "user":
                continue
            content = message.get("content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()[:44]
    except Exception:
        pass
    return session.get("name", "Chat")[:44]


# ── Tool registration ─────────────────────────────────────────────────────────

def register_all_tools() -> None:
    """Register every available tool family with the global tool registry.

    This is the single canonical entry point for tool registration.  Both GUI
    shells (DanGUI / DanModernGUI) and the CLI (Dan.py) call this instead of
    inlining their own registration loops.

    Core tool families are always registered.  Optional families (auth, image,
    ml) are registered only when their dependencies are importable; failures are
    silently logged so a missing optional package never blocks startup.
    """
    from tools import register_core_tools
    from knowledge import register_knowledge_tools
    from web import register_web_tools
    from workers import register_worker_tools
    from actions import register_action_tools
    from skills import register_skill_tools

    register_core_tools()
    register_knowledge_tools()
    register_web_tools()
    register_worker_tools()
    register_action_tools()
    register_skill_tools()

    # Optional tool families — import failures are expected when the
    # relevant extra requirements are not installed.
    _OPTIONAL_TOOL_MODULES = ("auth_tools", "image_tools", "ml_tools")
    for mod_name in _OPTIONAL_TOOL_MODULES:
        try:
            mod = __import__(mod_name)
            reg_fn_name = f"register_{mod_name.replace('_tools', '')}_tools"
            reg_fn = getattr(mod, reg_fn_name, None)
            if reg_fn is not None:
                reg_fn()
        except Exception:
            logger.debug("Optional tool module %r not available — skipping.", mod_name)
