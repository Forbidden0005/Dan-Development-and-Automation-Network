"""Tool registry — pluggable tool system for Dan.

Architecture notes
------------------
Tools are registered with a *safety level* (1–3) that reflects how
reversible and contained their side effects are:

  Level 1 — read-only, no side effects (file reads, system info, search)
  Level 2 — standard writes, typically reversible (file edits, git ops)
  Level 3 — elevated execution (shell commands, code execution, workers)

A *confirmation gate* callback can be installed at runtime to intercept
Level 3 tool calls before they execute. The gate receives the tool name,
input dict, and safety level and returns True to allow or False to deny.
If no gate is installed all tools execute without prompting (the default
behaviour for interactive CLI and GUI sessions where the user is present).

An *audit log* records every tool invocation outcome to
``%APPDATA%\\Dan\\tool_audit.log`` (or ``~/.dan/tool_audit.log`` on non-
Windows). Input parameter *values* are never logged — only parameter names
— to keep the log safe to review without leaking sensitive content.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

# Registered tools
_TOOLS: dict[str, "Tool"] = {}
# Schema cache invalidated on every register() call
_CACHED_SCHEMAS: list[dict] | None = None

# Optional confirmation gate for Level 3 tools.
# Signature: (tool_name: str, tool_input: dict, safety_level: int) -> bool
# Return True to allow, False to deny.
_confirmation_gate: Callable[[str, dict, int], bool] | None = None

# Lazy-initialised audit log singleton.
_audit_log: "ToolAuditLog | None" = None  # type: ignore[name-defined]


def _get_audit_log() -> "ToolAuditLog":  # type: ignore[name-defined]
    """Return the process-wide ToolAuditLog, creating it on first call."""
    global _audit_log
    if _audit_log is None:
        try:
            from config import USER_DATA_DIR
            from security_utils import ToolAuditLog

            _audit_log = ToolAuditLog(log_dir=USER_DATA_DIR)
        except Exception:  # noqa: BLE001
            # Fall back to current directory so the log is never silently lost.
            from security_utils import ToolAuditLog

            _audit_log = ToolAuditLog(log_dir=Path.cwd())
    return _audit_log


# ---------------------------------------------------------------------------
# Tool dataclass
# ---------------------------------------------------------------------------


@dataclass
class Tool:
    """A registered tool with metadata, schema, and an execution handler."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for input_schema
    handler: Callable[..., str]
    category: str = "core"
    safety_level: int = 1  # 1=read-only  2=standard  3=elevated/shell

    def to_api_schema(self) -> dict:
        """Return the Anthropic tool schema format expected by the provider layer."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(
    name: str,
    description: str,
    parameters: dict[str, Any],
    handler: Callable[..., str],
    category: str = "core",
    safety_level: int = 1,
) -> None:
    """Register a tool.

    Args:
        name:         Unique tool name used in API calls and audit logs.
        description:  Human-readable description surfaced to the LLM.
        parameters:   JSON Schema object describing accepted inputs.
        handler:      Callable invoked with unpacked tool inputs.
        category:     Logical grouping (e.g. ``"file"``, ``"shell"``).
        safety_level: 1 (read-only), 2 (standard write), or 3 (elevated).
                      Level 3 tools are subject to the confirmation gate.
    """
    global _CACHED_SCHEMAS
    _TOOLS[name] = Tool(
        name=name,
        description=description,
        parameters=parameters,
        handler=handler,
        category=category,
        safety_level=safety_level,
    )
    _CACHED_SCHEMAS = None
    logger.debug("Registered tool: %s (category=%s, level=%d)", name, category, safety_level)


def register_tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    handler: Callable[..., str],
    category: str = "core",
    safety_level: int = 1,
) -> None:
    """Backward-compatible alias for :func:`register`."""
    register(
        name=name,
        description=description,
        parameters=parameters,
        handler=handler,
        category=category,
        safety_level=safety_level,
    )


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def get_tool(name: str) -> Tool | None:
    """Return the named tool, or ``None`` if not registered."""
    return _TOOLS.get(name)


def get_all_tools() -> list[Tool]:
    """Return all registered tools."""
    return list(_TOOLS.values())


def get_tool_schemas() -> list[dict]:
    """Return tool schemas for all registered tools (cached)."""
    global _CACHED_SCHEMAS
    if _CACHED_SCHEMAS is None:
        _CACHED_SCHEMAS = [t.to_api_schema() for t in _TOOLS.values()]
    return _CACHED_SCHEMAS


def get_schemas_for_categories(categories: set[str]) -> list[dict]:
    """Return tool schemas for a specific set of categories only."""
    return [t.to_api_schema() for t in _TOOLS.values() if t.category in categories]


def all_categories() -> set[str]:
    """Return the set of all registered tool categories."""
    return {t.category for t in _TOOLS.values()}


def list_by_category() -> dict[str, list[Tool]]:
    """Return tools grouped by category."""
    cats: dict[str, list[Tool]] = {}
    for t in _TOOLS.values():
        cats.setdefault(t.category, []).append(t)
    return cats


# ---------------------------------------------------------------------------
# Confirmation gate
# ---------------------------------------------------------------------------


def set_confirmation_gate(
    callback: Callable[[str, dict, int], bool] | None,
) -> None:
    """Install (or remove) a confirmation gate for Level 3 tool execution.

    The *callback* is invoked synchronously before any tool whose
    ``safety_level >= 3`` is executed.  It receives:

      - ``tool_name`` (str)    — name of the tool about to run
      - ``tool_input`` (dict)  — the raw input dict
      - ``safety_level`` (int) — always 3 for gate-checked calls

    Return ``True`` to permit execution, ``False`` to deny it.

    Pass ``None`` to remove the gate and allow all tools to execute without
    prompting (the default behaviour for interactive sessions).

    Example — simple CLI prompt gate::

        def cli_gate(tool_name, tool_input, safety_level):
            ans = input(f"Allow {tool_name}? [y/N] ")
            return ans.strip().lower() == "y"

        tool_registry.set_confirmation_gate(cli_gate)
    """
    global _confirmation_gate
    _confirmation_gate = callback
    if callback is None:
        logger.debug("ToolRegistry: confirmation gate removed")
    else:
        logger.debug("ToolRegistry: confirmation gate installed (%s)", callback.__name__)


def get_confirmation_gate() -> Callable[[str, dict, int], bool] | None:
    """Return the currently installed confirmation gate, or ``None``."""
    return _confirmation_gate


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool by name with the given input dict.

    Execution flow:
    1. Look up the tool; return an error string if not found.
    2. For Level 3 tools, invoke the confirmation gate (if installed).
       Deny → return an error string and record outcome "denied".
    3. Execute the handler; catch all exceptions.
    4. Record the outcome to the audit log.

    The audit log receives parameter *names* only — never values — to avoid
    persisting sensitive content such as file paths, command strings, or
    code to disk.

    Args:
        tool_name:  Registered name of the tool to run.
        tool_input: Dict of parameter name → value.

    Returns:
        A string result from the tool handler, or an error message string.
        Callers can distinguish success from failure by checking whether the
        return value starts with ``"Error"`` — this convention is stable.
    """
    tool = _TOOLS.get(tool_name)
    if not tool:
        return f"Error: Unknown tool '{tool_name}'"

    # ── Confirmation gate (Level 3 only) ─────────────────────────────────────
    if tool.safety_level >= 3 and _confirmation_gate is not None:
        try:
            allowed = _confirmation_gate(tool_name, tool_input, tool.safety_level)
        except Exception as gate_exc:  # noqa: BLE001
            logger.warning(
                "Confirmation gate raised an exception for tool %s: %s",
                tool_name,
                gate_exc,
            )
            allowed = False  # deny on gate error — fail safe

        if not allowed:
            _get_audit_log().record(
                tool_name=tool_name,
                input_keys=list(tool_input.keys()),
                safety_level=tool.safety_level,
                outcome="denied",
                duration_ms=0.0,
            )
            return f"Error: execution of '{tool_name}' was denied by the confirmation gate"

    # ── Execute ───────────────────────────────────────────────────────────────
    start = time.monotonic()
    try:
        result = tool.handler(**tool_input)
        duration_ms = (time.monotonic() - start) * 1000
        _get_audit_log().record(
            tool_name=tool_name,
            input_keys=list(tool_input.keys()),
            safety_level=tool.safety_level,
            outcome="success",
            duration_ms=duration_ms,
        )
        return result
    except Exception as exc:
        duration_ms = (time.monotonic() - start) * 1000
        logger.error("Tool %s failed: %s", tool_name, exc)
        _get_audit_log().record(
            tool_name=tool_name,
            input_keys=list(tool_input.keys()),
            safety_level=tool.safety_level,
            outcome="error",
            duration_ms=duration_ms,
            error=str(exc),
        )
        return f"Error executing {tool_name}: {exc}"
