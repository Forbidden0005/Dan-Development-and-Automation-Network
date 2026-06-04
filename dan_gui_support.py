"""Pure helper functions for the Dan GUI."""

from __future__ import annotations

import sys
import time
from datetime import datetime


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
