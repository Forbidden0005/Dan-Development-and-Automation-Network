"""Tool registry — pluggable tool system for Dan."""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Global registry
_TOOLS: dict[str, "Tool"] = {}
_CACHED_SCHEMAS: list[dict] | None = None


@dataclass
class Tool:
    """A registered tool."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for input_schema
    handler: Callable[..., str]
    category: str = "core"

    def to_api_schema(self) -> dict:
        """Convert to Anthropic tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


def register(name: str, description: str, parameters: dict[str, Any],
             handler: Callable[..., str], category: str = "core") -> None:
    """Register a tool."""
    global _CACHED_SCHEMAS
    _TOOLS[name] = Tool(
        name=name, description=description,
        parameters=parameters, handler=handler, category=category,
    )
    # Invalidate schema cache when tools are registered
    _CACHED_SCHEMAS = None
    logger.debug("Registered tool: %s (%s)", name, category)


def get_tool(name: str) -> Tool | None:
    return _TOOLS.get(name)


def get_all_tools() -> list[Tool]:
    return list(_TOOLS.values())


def get_tool_schemas() -> list[dict]:
    """Get tool schemas with caching for performance."""
    global _CACHED_SCHEMAS
    if _CACHED_SCHEMAS is None:
        _CACHED_SCHEMAS = [t.to_api_schema() for t in _TOOLS.values()]
    return _CACHED_SCHEMAS


def get_schemas_for_categories(categories: set[str]) -> list[dict]:
    """Get tool schemas for a specific set of categories only."""
    return [t.to_api_schema() for t in _TOOLS.values() if t.category in categories]


def all_categories() -> set[str]:
    """Return the set of all registered tool categories."""
    return {t.category for t in _TOOLS.values()}


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool by name with an input dict."""
    tool = _TOOLS.get(tool_name)
    if not tool:
        return f"Error: Unknown tool '{tool_name}'"
    try:
        return tool.handler(**tool_input)
    except Exception as e:
        logger.error("Tool %s failed: %s", tool_name, e)
        return f"Error executing {tool_name}: {e}"


def list_by_category() -> dict[str, list[Tool]]:
    """Group tools by category."""
    cats: dict[str, list[Tool]] = {}
    for t in _TOOLS.values():
        cats.setdefault(t.category, []).append(t)
    return cats
