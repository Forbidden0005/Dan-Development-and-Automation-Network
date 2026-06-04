"""Agent loop — drives the LLM conversation with tool calls."""

import json
import logging
import threading
from typing import Any, Callable


class AgentInterrupted(BaseException):
    """Raised when Escape is pressed mid-run. Carries the checkpoint.

    Extends BaseException (not Exception) so broad `except Exception` blocks
    in providers and tools don't accidentally swallow it.
    """
    def __init__(self, checkpoint: list[dict]):
        self.checkpoint = checkpoint
        super().__init__("interrupted")

# ── Tool progress labels ──────────────────────────────────────────────────────

_TOOL_LABELS: dict[str, Callable] = {
    "WebSearch":   lambda i: f"Searching: \"{i.get('query', '')}\"",
    "WebFetch":    lambda i: f"Fetching: {i.get('url', '')[:70]}",
    "HttpRequest": lambda i: f"{i.get('method','GET')}: {i.get('url','')[:60]}",
    "Read":        lambda i: f"Reading: {i.get('path', '')}",
    "Write":       lambda i: f"Writing: {i.get('path', '')}",
    "Edit":        lambda i: f"Editing: {i.get('path', '')}",
    "Append":      lambda i: f"Appending: {i.get('path', '')}",
    "Bash":        lambda i: f"Running: {i.get('command', '')[:60]}",
    "Glob":        lambda i: f"Scanning: {i.get('pattern', '')}",
    "Grep":        lambda i: f"Searching files: \"{i.get('pattern', '')}\"",
    "ListDir":     lambda i: f"Listing: {i.get('path', '.')}",
    "Remember":    lambda i: f"Saving: {i.get('name', '')}",
    "Recall":      lambda i: f"Recalling: \"{i.get('query', '')}\"",
    "GitStatus":   lambda i: "Git status",
    "GitDiff":     lambda i: "Git diff",
    "GitCommit":   lambda i: "Committing",
    "GitLog":      lambda i: "Git log",
    "GitBranch":   lambda i: "Git branches",
    "RunTests":    lambda i: "Running tests",
    "LintCheck":   lambda i: "Linting",
    "FormatCode":  lambda i: "Formatting",
    "AnalyzeCode": lambda i: f"Analyzing: {i.get('path', '')}",
    "IndexProject": lambda i: f"Indexing project: {i.get('project_root', '.')}",
    "SymbolLookup": lambda i: f"Looking up symbol: {i.get('name', '')}",
    "DependencyGraph": lambda i: f"Building dependency graph: {i.get('file_path', '')}",
    "SemanticSearch": lambda i: f"Searching codebase: \"{i.get('query', '')}\"",
    "EmbedProject": lambda i: f"Embedding project: {i.get('project_root', '.')}",
    "Spawn":       lambda i: f"Spawning worker: {i.get('prompt', '')[:40]}",
}


def _tool_label(name: str, inp: dict) -> str:
    fn = _TOOL_LABELS.get(name)
    return fn(inp) if fn else name

import tool_registry as registry
from context_mgr import needs_compaction, compact
from providers import Message, Response, ToolCall
import cost_tracker

# ── Tool selection ────────────────────────────────────────────────────────────

# Always sent — the everyday file/shell tools every task needs
_ALWAYS_ON: set[str] = {"core", "actions"}

# Keyword → category: first match wins, but multiple can match
_KEYWORD_MAP: list[tuple[str, set[str]]] = [
    ("web",       {"search", "web", "browse", "fetch", "url", "http", "online",
                   "internet", "lookup", "look up", "website", "webpage", "google",
                   "cronus", "ddg", "bing", "find info", "read a page"}),
    ("knowledge", {"remember", "recall", "forget", "knowledge", "memorize",
                   "store this", "save this", "note that"}),
    ("git",       {"git", "commit", "push", "pull", "branch", "merge", "pull request",
                   "repository", "repo", "stash", "checkout", "rebase",
                   "blame", "git log", "git diff"}),
    ("code",      {"test", "pytest", "lint", "flake", "format", "black",
                   "coverage", "syntax error", "import error", "run tests",
                   "check code", "type check", "mypy"}),
    ("execution", {"run", "execute", "runcode", "runfile", "iteratefix", "testloop",
                   "run this", "run it", "run the", "run file", "run code",
                   "fix and run", "iterate", "keep trying"}),
    ("workers",   {"worker", "spawn", "parallel", "background", "delegate",
                   "subtask", "concurrently", "simultaneously"}),
    ("skills",    {"duplicate", "duplicates", "dupes", "find dupes",
                   "organize files"}),
    ("project",   {"load project", "scan project", "project map", "codebase",
                   "show project", "unload project", "loadproject"}),
    ("index",     {"index project", "symbol lookup", "dependency graph", "semantic search",
                   "find usages", "where is", "where is defined", "what imports",
                   "who imports", "codebase index", "embed project"}),
]


# Words that signal the user wants Dan to actually DO something
_TASK_SIGNALS = {
    "read", "write", "edit", "create", "make", "build", "run", "execute",
    "find", "search", "look", "fetch", "get", "show", "list", "check",
    "fix", "update", "change", "delete", "remove", "move", "copy",
    "install", "test", "analyze", "explain", "generate", "add", "open",
    "save", "remember", "commit", "push", "pull", "diff", "help me",
    "can you", "could you", "please", "how do", "what is", "why is",
}


def select_tool_categories(user_input: str) -> set[str]:
    """Return the set of tool categories relevant to this message.

    Returns empty set for short conversational messages so the model
    doesn't get confused and start hallucinating tool calls.
    """
    text = user_input.lower().strip()

    # Pure conversation — no tools needed
    if len(text.split()) <= 5 and not any(sig in text for sig in _TASK_SIGNALS):
        return set()

    cats = set(_ALWAYS_ON)
    for category, keywords in _KEYWORD_MAP:
        if any(kw in text for kw in keywords):
            cats.add(category)
    return cats


logger = logging.getLogger(__name__)


def _extract_text_tool_call(text: str) -> "ToolCall | None":
    """Detect when the model leaks a tool call as raw JSON text and recover it."""
    import re
    stripped = text.strip()
    # Match a bare JSON object with a "name" key (tool call leaked into text stream)
    if not (stripped.startswith("{") and '"name"' in stripped):
        return None
    try:
        data = json.loads(stripped)
        name = data.get("name") or data.get("function", {}).get("name")
        args = data.get("arguments") or data.get("input") or data.get("parameters") or {}
        if name and registry.get_tool(name):
            logger.debug("Rescued text-embedded tool call: %s", name)
            return ToolCall(id="rescued_0", name=name, input=args if isinstance(args, dict) else {})
    except Exception:
        pass
    return None


def _build_assistant_content(resp: Response) -> list[dict]:
    """Convert a provider response into structured assistant content blocks."""
    assistant_content: list[dict] = []
    if resp.text:
        assistant_content.append({"type": "text", "text": resp.text})
    for tc in resp.tool_calls:
        assistant_content.append({
            "type": "tool_use",
            "id": tc.id,
            "name": tc.name,
            "input": tc.input,
        })
    return assistant_content


def _last_message_text(messages: list[dict]) -> str:
    """Extract human-readable text from the last message in the transcript."""
    if not messages:
        return ""

    last = messages[-1]
    content = last.get("content", "")
    if isinstance(content, list):
        return " ".join(
            block.get("text", "") for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    if isinstance(content, str):
        return content
    return ""

SYSTEM_PROMPT = """\
You are Dan, a powerful AI development assistant. You help developers by reading, writing, \
and editing code, running commands, searching the web, and managing knowledge.

Core tools always available: Read, Write, Edit, Append, Move, Copy, Diff, Bash, Glob, Grep, ListDir, HttpRequest.
Additional tools loaded on demand: WebFetch, WebSearch (web), Remember/Recall/Forget (knowledge), \
Git operations (git), test/lint/format runners (code), Spawn/CheckWorker (workers), \
LoadProject/ShowProject/UnloadProject (project — scan a codebase and inject full structure into context).

Index tools available when relevant: IndexProject, SymbolLookup, FindUsages, DependencyGraph, SemanticSearch, EmbedProject.

Guidelines:
- Be direct and concise
- Show diffs when editing files
- Explain what you're doing and why
- Ask for clarification when a task is ambiguous
- Use the right tool for the job
- Prefer Edit over Write when modifying existing files (preserves structure)
"""


def build_system_prompt() -> str:
    """Build the full system prompt with project map + knowledge context."""
    from knowledge import get_context_block
    import project_context

    base = SYSTEM_PROMPT

    # Inject active project map (file structure, symbols) if one is loaded
    proj = project_context.get()
    if proj:
        base += f"\n\n{proj}"

    knowledge = get_context_block()
    if knowledge:
        base += f"\n\n{knowledge}"

    return base


def run_agent_loop(
    user_input: str,
    messages: list[dict],
    provider: Any,
    max_turns: int = 50,
    stream_callback: Callable[[str], None] | None = None,
    on_progress: Callable[[str, str, dict], None] | None = None,
    interrupt_event: threading.Event | None = None,
) -> tuple[str, list[dict]]:
    """
    Run the agent loop: send user input, handle tool calls, return final text.

    Args:
        stream_callback: If provided and the provider supports streaming,
                         called with each text chunk on the final (text-only)
                         response.  The caller should suppress re-printing the
                         returned text when this is set.

    Returns:
        (assistant_text, updated_messages)
    """
    system       = build_system_prompt()
    categories   = select_tool_categories(user_input)
    tool_schemas = registry.get_schemas_for_categories(categories)
    logger.debug("Tool categories: %s (%d tools)", categories, len(tool_schemas))
    messages.append({"role": "user", "content": user_input})

    checkpoint: list[dict] = list(messages)  # snapshot before first turn

    for turn in range(max_turns):
        # ── Interrupt check ───────────────────────────────────────────────────
        if interrupt_event and interrupt_event.is_set():
            raise AgentInterrupted(checkpoint)

        # ── Compaction check ──────────────────────────────────────────────────
        if needs_compaction(messages, provider.context_limit):
            logger.info("Compacting conversation...")
            messages = compact(messages, provider)

        checkpoint = list(messages)  # safe restore point before this turn
        msg_objs = [Message(**m) for m in messages]

        # ── LLM call — streaming on final turn when supported ─────────────────
        if on_progress:
            on_progress("thinking", "Thinking", {})

        try:
            use_stream = (
                stream_callback is not None
                and getattr(provider, "supports_streaming", False)
            )

            if use_stream:
                # Stop spinner on first streamed token; bail out on interrupt
                _notified = [False]
                def _stream_with_progress(chunk: str) -> None:
                    if interrupt_event and interrupt_event.is_set():
                        raise AgentInterrupted(checkpoint)
                    if not _notified[0]:
                        _notified[0] = True
                        if on_progress:
                            on_progress("streaming", "", {})
                    stream_callback(chunk)

                resp: Response = provider.chat_stream(
                    messages=msg_objs,
                    system=system,
                    tools=tool_schemas if tool_schemas else None,
                    on_text=_stream_with_progress,
                )
            else:
                resp: Response = provider.chat(
                    messages=msg_objs,
                    system=system,
                    tools=tool_schemas if tool_schemas else None,
                )
        except Exception as e:
            if on_progress:
                on_progress("error", "", {})
            error_msg = f"API error: {e}"
            logger.error(error_msg)
            return error_msg, messages

        # ── Record token usage ────────────────────────────────────────────────
        if resp.usage:
            cost_tracker.record(
                resp.usage.get("input", 0),
                resp.usage.get("output", 0),
            )

        # ── Rescue text-embedded tool calls (model leaked JSON into stream) ──────
        if resp.text and not resp.tool_calls:
            leaked = _extract_text_tool_call(resp.text)
            if leaked:
                resp.tool_calls = [leaked]
                resp.text = ""

        # ── Text only — done ─────────────────────────────────────────────────
        if resp.text and not resp.tool_calls:
            messages.append({"role": "assistant", "content": resp.text})
            return resp.text, messages

        # ── Build assistant message (text + tool_use blocks) ──────────────────
        assistant_content = _build_assistant_content(resp)
        messages.append({"role": "assistant", "content": assistant_content})

        # ── Execute tools ─────────────────────────────────────────────────────
        tool_results: list[dict] = []
        for tc in resp.tool_calls:
            if interrupt_event and interrupt_event.is_set():
                raise AgentInterrupted(checkpoint)
            label = _tool_label(tc.name, tc.input)
            if on_progress:
                on_progress("tool_start", label, {"name": tc.name, "input": tc.input})
            logger.info("Tool: %s(%s)", tc.name, json.dumps(tc.input, default=str)[:100])
            result = registry.execute_tool(tc.name, tc.input)
            preview = result[:120].replace("\n", " ") + ("…" if len(result) > 120 else "")
            if on_progress:
                on_progress("tool_done", preview, {"name": tc.name, "result": result})
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tc.id,
                "content":     result,
            })

        messages.append({"role": "user", "content": tool_results})

        if resp.stop_reason == "end_turn" and resp.text:
            return resp.text, messages

    # ── Turn limit reached ────────────────────────────────────────────────────
    last_text = _last_message_text(messages)

    notice = (
        f"⚠️  Reached the tool-call limit ({max_turns} turns). "
        "The task may need to be broken into smaller steps."
    )
    return (f"{last_text}\n\n{notice}" if last_text else notice), messages
