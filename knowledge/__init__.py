"""Knowledge system — persistent memory across sessions."""

import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import tool_registry as registry
import config

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeEntry:
    """A stored knowledge entry."""

    name: str
    content: str
    scope: str  # "user" or "project"
    created: float = 0.0
    tags: list[str] | None = None

    def __post_init__(self):
        if not self.created:
            self.created = time.time()
        if self.tags is None:
            self.tags = []


def _store_path(scope: str, create: bool = False) -> Path:
    base = config.USER_DATA_DIR if scope == "user" else config.PROJECT_DATA_DIR
    p = base / "knowledge"
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


_context_cache: str | None = None


def _invalidate_cache() -> None:
    global _context_cache
    _context_cache = None


def save(entry: KnowledgeEntry) -> str:
    """Save a knowledge entry to disk."""
    store = _store_path(entry.scope, create=True)
    filepath = store / f"{entry.name}.json"
    filepath.write_text(json.dumps(asdict(entry), indent=2))
    _invalidate_cache()
    return f"✓ Saved knowledge: {entry.name} ({entry.scope})"


def load(name: str, scope: str = "user") -> KnowledgeEntry | None:
    """Load a knowledge entry."""
    filepath = _store_path(scope) / f"{name}.json"
    if not filepath.exists():
        return None
    data = json.loads(filepath.read_text())
    return KnowledgeEntry(**data)


def delete(name: str, scope: str = "user") -> str:
    filepath = _store_path(scope) / f"{name}.json"
    if filepath.exists():
        filepath.unlink()
        _invalidate_cache()
        return f"✓ Deleted knowledge: {name}"
    return f"Not found: {name}"


def search(query: str, scope: str | None = None) -> list[KnowledgeEntry]:
    """Search knowledge entries by keyword."""
    results = []
    scopes = [scope] if scope else ["user", "project"]
    query_lower = query.lower()

    for s in scopes:
        store = _store_path(s)
        for fp in store.glob("*.json"):
            try:
                data = json.loads(fp.read_text())
                entry = KnowledgeEntry(**data)
                if (
                    query_lower in entry.name.lower()
                    or query_lower in entry.content.lower()
                    or any(query_lower in t.lower() for t in (entry.tags or []))
                ):
                    results.append(entry)
            except Exception:
                continue
    return results


def list_all(scope: str | None = None) -> list[KnowledgeEntry]:
    """List all knowledge entries."""
    entries = []
    scopes = [scope] if scope else ["user", "project"]
    for s in scopes:
        store = _store_path(s)
        for fp in sorted(store.glob("*.json")):
            try:
                data = json.loads(fp.read_text())
                entries.append(KnowledgeEntry(**data))
            except Exception:
                continue
    return entries


def get_context_block() -> str:
    """Build a context block of knowledge for the system prompt (cached)."""
    global _context_cache
    if _context_cache is not None:
        return _context_cache

    entries = list_all()
    if not entries:
        _context_cache = ""
        return ""
    lines = ["<knowledge>"]
    for e in entries:
        tags = ", ".join(e.tags) if e.tags else ""
        lines.append(f"  [{e.scope}] {e.name}: {e.content}" + (f" (tags: {tags})" if tags else ""))
    lines.append("</knowledge>")
    _context_cache = "\n".join(lines)
    return _context_cache


# ── Tool Handlers ────────────────────────────────────────────────────────────


def _remember(name: str, content: str, scope: str = "project", tags: str = "") -> str:
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    entry = KnowledgeEntry(name=name, content=content, scope=scope, tags=tag_list)
    return save(entry)


def _forget(name: str, scope: str = "project") -> str:
    return delete(name, scope)


def _recall(query: str, scope: str = "") -> str:
    results = search(query, scope or None)
    if not results:
        return f"No knowledge found for: {query}"
    lines = []
    for e in results:
        lines.append(f"[{e.scope}] {e.name}: {e.content}")
    return "\n".join(lines)


def _list_knowledge() -> str:
    entries = list_all()
    if not entries:
        return "No knowledge entries stored."
    lines = []
    for e in entries:
        lines.append(f"[{e.scope}] {e.name}: {e.content[:80]}")
    return "\n".join(lines)


def register_knowledge_tools() -> None:
    """Register knowledge tools."""
    registry.register(
        name="Remember",
        description="Save knowledge for future sessions.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short identifier"},
                "content": {"type": "string", "description": "Knowledge content"},
                "scope": {"type": "string", "enum": ["user", "project"], "default": "project"},
                "tags": {"type": "string", "description": "Comma-separated tags", "default": ""},
            },
            "required": ["name", "content"],
        },
        handler=_remember,
        category="knowledge",
    )

    registry.register(
        name="Forget",
        description="Delete a stored knowledge entry.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Knowledge name to delete"},
                "scope": {"type": "string", "enum": ["user", "project"], "default": "project"},
            },
            "required": ["name"],
        },
        handler=_forget,
        category="knowledge",
    )

    registry.register(
        name="Recall",
        description="Search stored knowledge by keyword.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "scope": {
                    "type": "string",
                    "description": "Scope filter (user/project)",
                    "default": "",
                },
            },
            "required": ["query"],
        },
        handler=_recall,
        category="knowledge",
    )

    registry.register(
        name="ListKnowledge",
        description="List all stored knowledge entries.",
        parameters={"type": "object", "properties": {}},
        handler=_list_knowledge,
        category="knowledge",
    )
