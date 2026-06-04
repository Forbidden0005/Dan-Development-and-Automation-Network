"""Context manager — tracks token usage and compacts conversations."""

import logging
from config import COMPACTION_THRESHOLD, TOKEN_ESTIMATE_RATIO

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length."""
    return int(len(text) / TOKEN_ESTIMATE_RATIO)


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Estimate total tokens across messages."""
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += estimate_tokens(str(block))
        total += 4  # overhead per message
    return total


def needs_compaction(messages: list[dict], context_limit: int) -> bool:
    """Check if conversation needs compaction."""
    used = estimate_messages_tokens(messages)
    threshold = int(context_limit * COMPACTION_THRESHOLD)
    return used > threshold


def compact(messages: list[dict], provider: object) -> list[dict]:
    """Compact conversation by summarizing older messages."""
    if len(messages) <= 4:
        return messages

    # Keep the last 4 exchanges, summarize the rest
    to_summarize = messages[:-4]
    to_keep = messages[-4:]

    # Build summary text
    summary_parts = []
    for m in to_summarize:
        role = m["role"]
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
            )
        if content:
            summary_parts.append(f"[{role}]: {content[:200]}")

    summary_text = "\n".join(summary_parts)

    # Ask the provider to summarize
    try:
        from providers import Message
        summary_prompt = (
            "Summarize this conversation history concisely, preserving key decisions, "
            "file changes, and context needed to continue:\n\n" + summary_text
        )
        resp = provider.chat(
            messages=[Message(role="user", content=summary_prompt)],
            max_tokens=1024,
        )
        summary = resp.text
    except Exception as e:
        logger.warning("Compaction summary failed, using truncation: %s", e)
        summary = summary_text[:2000]

    compacted = [
        {"role": "user", "content": f"[Conversation summary]\n{summary}"},
        {"role": "assistant", "content": "Understood, I have the context. Let's continue."},
    ]
    compacted.extend(to_keep)

    old_tokens = estimate_messages_tokens(messages)
    new_tokens = estimate_messages_tokens(compacted)
    logger.info("Compacted: %d → %d tokens (%.0f%% reduction)",
                old_tokens, new_tokens, (1 - new_tokens/old_tokens) * 100)

    return compacted
