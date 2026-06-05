#!/usr/bin/env python3
"""Dan — Development Automation Network. Main REPL entry point."""

import argparse
import itertools
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path

# Ensure the dan directory is on the path
sys.path.insert(0, str(Path(__file__).parent))

from config import APP_NAME, APP_VERSION, APP_TAGLINE, DEFAULT_PROVIDER, DEFAULT_MODEL, Colors, USER_DATA_DIR
from providers import get_provider
from agent import run_agent_loop, AgentInterrupted
from tools import register_core_tools
from knowledge import register_knowledge_tools
from web import register_web_tools
from workers import register_worker_tools, get_pool
from actions import register_action_tools, get_action, get_all_actions
from skills import register_skill_tools
from code_tools import register_code_tools
from git_tools import register_git_tools
from project_tools import register_project_tools
from code_execution import register_execution_tools
from codebase_index import register_index_tools
from code_tools import startup_blocked, startup_doctor
import project_context
import cost_tracker
import session_mgr

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dan")


# ── Initialization ───────────────────────────────────────────────────────────

# ── Checkpoint ───────────────────────────────────────────────────────────────

_CHECKPOINT_FILE = USER_DATA_DIR / "interrupt_checkpoint.json"


def _save_checkpoint(user_input: str, messages: list[dict]) -> None:
    try:
        _CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        import json as _json
        _CHECKPOINT_FILE.write_text(
            _json.dumps({"user_input": user_input, "messages": messages}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _load_checkpoint() -> tuple[str, list[dict]] | None:
    try:
        if not _CHECKPOINT_FILE.exists():
            return None
        import json as _json
        data = _json.loads(_CHECKPOINT_FILE.read_text(encoding="utf-8"))
        return data["user_input"], data["messages"]
    except Exception:
        return None


def _clear_checkpoint() -> None:
    try:
        if _CHECKPOINT_FILE.exists():
            _CHECKPOINT_FILE.unlink()
    except Exception:
        pass


# ── Keyboard listener ─────────────────────────────────────────────────────────

class EscapeListener:
    """Background thread that watches for Escape and sets interrupt_event."""

    def __init__(self):
        self.interrupt_event = threading.Event()
        self._active         = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def arm(self) -> None:
        """Activate escape detection (call before agent loop)."""
        self.interrupt_event.clear()
        self._active.set()

    def disarm(self) -> None:
        """Deactivate escape detection (call after agent loop)."""
        self._active.clear()

    def _run(self) -> None:
        try:
            import msvcrt
            while True:
                self._active.wait()
                if msvcrt.kbhit():
                    ch = msvcrt.getch()
                    if ch == b"\x1b":  # Escape
                        self.interrupt_event.set()
                time.sleep(0.05)
        except Exception:
            pass  # msvcrt unavailable — interrupts won't work but nothing breaks


class ProgressDisplay:
    """Manages spinner and step-by-step status lines during agent execution."""

    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __call__(self, event: str, message: str, data: dict) -> None:
        if event == "thinking":
            self._start(message)
        elif event == "tool_start":
            self._stop_spinner()
            print(f"  {Colors.DIM}⚡ {message}{Colors.RESET}", flush=True)
            self._start("Working")
        elif event == "tool_done":
            self._stop_spinner()
            if message:
                print(f"  {Colors.DIM}↳ {message}{Colors.RESET}", flush=True)
        elif event in ("streaming", "error"):
            self._stop_spinner()

    def _start(self, label: str) -> None:
        self._stop_spinner()
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, args=(label,), daemon=True)
        self._thread.start()

    def _stop_spinner(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.3)
            self._thread = None
        print(f"\r{' ' * 50}\r", end="", flush=True)

    def _spin(self, label: str) -> None:
        for frame in itertools.cycle(self._FRAMES):
            if self._stop.is_set():
                break
            print(f"\r  {Colors.DIM}{frame} {label}...{Colors.RESET}", end="", flush=True)
            time.sleep(0.08)

    def stop(self) -> None:
        self._stop_spinner()


def init_tools() -> int:
    """Register all tools. Returns count."""
    register_core_tools()
    register_knowledge_tools()
    register_web_tools()
    register_worker_tools()
    register_action_tools()
    register_skill_tools()
    register_code_tools()
    register_git_tools()
    register_project_tools()
    register_execution_tools()
    register_index_tools()

    try:
        import image_tools  # auto-registers on import
    except ImportError as e:
        logger.warning("Image tools not available: %s", e)
    except Exception as e:
        logger.error("Failed to load image tools: %s", e)

    try:
        import ml_tools  # auto-registers on import
    except ImportError as e:
        logger.warning("ML tools not available: %s", e)
    except Exception as e:
        logger.error("Failed to load ML tools: %s", e)

    from tool_registry import get_all_tools
    return len(get_all_tools())


# ── Slash Commands ───────────────────────────────────────────────────────────

def handle_slash_command(cmd: str, messages: list[dict], provider: object) -> str | None:
    """Handle slash commands. Returns response text or None to continue."""
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command in ("/quit", "/exit", "/q"):
        print(f"\n{Colors.DIM}Goodbye!{Colors.RESET}")
        get_pool().shutdown()
        sys.exit(0)

    elif command == "/help":
        return _help_text()

    elif command == "/clear":
        messages.clear()
        return "✓ Conversation cleared."

    elif command == "/tools":
        from tool_registry import list_by_category
        cats = list_by_category()
        lines = []
        for cat, tools in sorted(cats.items()):
            lines.append(f"\n  {Colors.BOLD}{cat.upper()}{Colors.RESET}")
            for t in tools:
                lines.append(f"    {t.name:16s} {t.description[:60]}")
        return "\n".join(lines)

    elif command == "/actions":
        actions = get_all_actions()
        if not actions:
            return "No actions available."
        lines = []
        for a in actions.values():
            lines.append(f"  /{a.name:12s} {a.description}")
        return "\n".join(lines)

    elif command == "/config":
        from api_config import show_config, set_value, get_value
        if not arg:
            return show_config()
        if "=" in arg:
            # /config set key=value  OR  /config key=value
            setting = arg.replace("set ", "", 1).strip()
            key, _, value = setting.partition("=")
            return set_value(key.strip(), value.strip())
        else:
            return get_value(arg.strip())

    elif command == "/provider":
        from api_config import load_config, save_config
        if not arg:
            current_provider = (
                getattr(provider, "provider_name", "")
                or provider.__class__.__name__.replace("Provider", "").lower()
            )
            return f"Current provider: {current_provider}. Use /provider <name> to switch.\n  Available: anthropic, openai, venice, ollama"
        new_provider = arg.strip().lower()
        if new_provider not in ("anthropic", "openai", "venice", "ollama"):
            return f"Unknown provider: {new_provider}. Options: anthropic, openai, venice, ollama"
        cfg = load_config()
        cfg["provider"] = new_provider
        save_config(cfg)
        return f"Provider set to '{new_provider}'. Restart Dan to use the new provider."

    elif command == "/models":
        return """Available models by provider:

  [anthropic]
    claude-sonnet-4-20250514   (default, 200k context)
    claude-opus-4-20250514     (most capable)
    claude-haiku-3-20240307    (fastest)

  [openai]
    gpt-4o                     (default, 128k context)
    gpt-4o-mini                (faster, cheaper)
    gpt-4-turbo                (legacy)

  [venice]
    llama-3.3-70b              (default, 128k, general purpose)
    mistral-31-24b             (131k, vision + function calling)
    qwen3-4b                   (40k, fast + function calling)
    zai-org-glm-4.7            (128k, function calling)
    llama-3.2-3b               (131k, fast + function calling)
    venice-uncensored          (32k, uncensored)

  [ollama]
    llama3.1                   (default, local)
    Any model installed via 'ollama pull'
"""

    elif command == "/knowledge" or command == "/memory":
        from knowledge import list_all, search
        if arg:
            results = search(arg)
            if not results:
                return f"No knowledge matching: {arg}"
            return "\n".join(f"  [{e.scope}] {e.name}: {e.content[:80]}" for e in results)
        entries = list_all()
        if not entries:
            return "No knowledge stored."
        return "\n".join(f"  [{e.scope}] {e.name}: {e.content[:80]}" for e in entries)

    elif command == "/workers" or command == "/agents":
        tasks = get_pool().list_tasks()
        if not tasks:
            return "No workers."
        lines = []
        for t in tasks:
            lines.append(f"  {t.id}  {t.status:8s}  {t.prompt[:60]}")
        return "\n".join(lines)

    elif command == "/project":
        sub = arg.strip().lower()
        if not arg or sub == "show":
            # Show current project or instructions
            if project_context.is_loaded():
                return project_context.get()
            return ("No project loaded.\n"
                    "  /project .            — load current directory\n"
                    "  /project <path>       — load a specific directory\n"
                    "  /project clear        — unload current project")
        elif sub == "clear":
            name = project_context.name()
            project_context.clear()
            return f"✓ Unloaded project: {name}" if name else "No project was loaded."
        else:
            # arg is a path
            from project_tools import _load_project
            return _load_project(arg.strip())

    elif command == "/compact":
        from context_mgr import compact, estimate_messages_tokens
        before = estimate_messages_tokens(messages)
        new_messages = compact(messages, provider)
        messages.clear()
        messages.extend(new_messages)
        after = estimate_messages_tokens(messages)
        return f"✓ Compacted: {before} → {after} tokens"

    elif command == "/verbose":
        level = logging.DEBUG if logger.level != logging.DEBUG else logging.WARNING
        logging.getLogger().setLevel(level)
        logger.setLevel(level)
        return f"Logging: {'DEBUG' if level == logging.DEBUG else 'WARNING'}"

    elif command == "/keys":
        if hasattr(provider, 'rotator'):
            return f"API Key Usage (last 60s):\n{provider.rotator.status()}"
        return "Key rotation not available for this provider."

    elif command == "/tokens":
        from context_mgr import estimate_messages_tokens
        tokens = estimate_messages_tokens(messages)
        limit  = getattr(provider, 'context_limit', 200_000)
        pct    = tokens / limit * 100
        return f"Context: ~{tokens:,} / {limit:,} tokens ({pct:.1f}%)"

    elif command == "/cost":
        tracker = cost_tracker.get()
        if tracker is None:
            return "No cost data yet — start chatting first."
        return f"Session cost estimate:\n{tracker.summary()}"

    elif command == "/session":
        sub = arg.split(maxsplit=1)
        sub_cmd = sub[0].lower() if sub else "list"
        sub_arg = sub[1] if len(sub) > 1 else ""

        if sub_cmd == "list":
            return session_mgr.format_sessions_table()

        elif sub_cmd == "save":
            pname    = getattr(provider, 'model', 'unknown')
            prov_str = getattr(provider, '__class__', type(provider)).__name__.replace("Provider", "").lower()
            return session_mgr.save(messages, prov_str, pname, name=sub_arg,
                                    session_id=_get_session_id())

        elif sub_cmd == "load":
            if not sub_arg:
                return "Usage: /session load <name>"
            result = session_mgr.load(sub_arg)
            if result is None:
                return f"Session not found: {sub_arg}"
            loaded_msgs, meta = result
            messages.clear()
            messages.extend(loaded_msgs)
            return (f"✓ Loaded session '{meta.get('name', sub_arg)}' "
                    f"({len(loaded_msgs)} messages, "
                    f"{meta.get('provider', '?')}/{meta.get('model', '?')})")

        elif sub_cmd == "delete":
            if not sub_arg:
                return "Usage: /session delete <name>"
            from config import USER_DATA_DIR
            fp = USER_DATA_DIR / "sessions" / f"{sub_arg}.json"
            if fp.exists():
                fp.unlink()
                return f"✓ Deleted session: {sub_arg}"
            return f"Session not found: {sub_arg}"

        else:
            return ("Session commands:\n"
                    "  /session list           — show saved sessions\n"
                    "  /session save [name]    — save current session\n"
                    "  /session load <name>    — restore a saved session\n"
                    "  /session delete <name>  — delete a saved session")

    else:
        # Check if it's an action
        action_name = command.lstrip("/")
        action = get_action(action_name)
        if action:
            # Execute as agent prompt
            return None  # Let it fall through as a prompt
        return f"Unknown command: {command}. Type /help for commands."


def _help_text() -> str:
    return f"""{Colors.BOLD}{APP_NAME} Commands{Colors.RESET}

  /help                  Show this help
  /quit                  Exit Dan
  /clear                 Clear conversation history
  /tools                 List all available tools
  /actions               List automation actions
  /knowledge [query]     Show stored knowledge (or search by query)
  /workers               Show worker tasks
  /config [key=val]      Show or set API config
  /provider [name]       Show or switch provider
  /models                List available models per provider
  /resume                Resume a task paused with Escape
  /project [path]        Load a project directory into context
  /project clear         Unload current project
  /compact               Force conversation compaction
  /tokens                Show context token usage
  /cost                  Show session token count and estimated cost
  /keys                  Show API key rotation status
  /session list          Show saved sessions
  /session save [name]   Save current conversation
  /session load <name>   Restore a saved conversation
  /session delete <name> Delete a saved session
  /verbose               Toggle debug logging

  /<action>              Run an automation action
"""


# ── Session ID ───────────────────────────────────────────────────────────────

_SESSION_ID: str = ""


def _get_session_id() -> str:
    """Return (or lazily create) the session ID for this REPL run."""
    global _SESSION_ID
    if not _SESSION_ID:
        _SESSION_ID = str(uuid.uuid4())[:8]
    return _SESSION_ID


# ── Banner ───────────────────────────────────────────────────────────────────

def print_banner(tool_count: int, provider_name: str, model: str,
                 key_count: int, streaming: bool = False):
    title  = f"  {APP_NAME} v{APP_VERSION} -- {APP_TAGLINE}  "
    border = "+" + "=" * len(title) + "+"
    stream_label = "yes" if streaming else "no (provider unsupported)"
    print(f"""
{Colors.BOLD}{Colors.CYAN}{border}
|{title}|
{border}{Colors.RESET}

  {Colors.DIM}Provider:{Colors.RESET}  {provider_name} ({model})
  {Colors.DIM}API Keys:{Colors.RESET}  {key_count} loaded (rotating every 120s)
  {Colors.DIM}Streaming:{Colors.RESET} {stream_label}
  {Colors.DIM}Tools:{Colors.RESET}     {tool_count} registered
  {Colors.DIM}Type:{Colors.RESET}      /help for commands, /quit to exit
""")


class StreamWriter:
    """Buffers streamed chunks, suppresses JSON tool-call leaks, prints clean text."""

    def __init__(self):
        self._buf = ""
        self._started = False
        self._suppressed = False

    def __call__(self, chunk: str) -> None:
        self._buf += chunk
        stripped = self._buf.lstrip()
        if stripped.startswith("{"):
            self._suppressed = True
            return
        self._suppressed = False
        if not self._started:
            print(Colors.CYAN, end="", flush=True)
            self._started = True
        print(chunk, end="", flush=True)

    def reset(self) -> None:
        self._buf = ""
        self._started = False
        self._suppressed = False

    def finish(self) -> bool:
        """Print RESET and newline. Returns True if anything was printed."""
        if self._started:
            print(Colors.RESET)
        return self._started


# ── REPL ─────────────────────────────────────────────────────────────────────

def repl(provider: object, model: str, provider_name: str):
    """Main Read-Eval-Print Loop."""
    tool_count  = init_tools()
    key_count   = getattr(provider, 'key_count', 1)
    supports_stream = getattr(provider, 'supports_streaming', False)

    # Initialise per-session cost tracker and session ID
    cost_tracker.init(model)
    sid = _get_session_id()

    print_banner(tool_count, provider_name, model, key_count,
                 streaming=supports_stream)

    messages: list[dict] = []

    stream_cb = StreamWriter() if supports_stream else None
    progress  = ProgressDisplay()
    esc       = EscapeListener()

    while True:
        try:
            user_input = input(f"{Colors.GREEN}dan ▸{Colors.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{Colors.DIM}Goodbye!{Colors.RESET}")
            break

        if not user_input:
            continue

        # Handle slash commands
        if user_input.startswith("/"):
            # /resume is handled here because it needs to mutate messages
            # and fall through to run_agent_loop with the restored input
            if user_input.strip().lower() == "/resume":
                cp = _load_checkpoint()
                if not cp:
                    print(f"\n{Colors.YELLOW}No paused task found.{Colors.RESET}\n")
                    continue
                resume_input, resume_msgs = cp
                messages.clear()
                messages.extend(resume_msgs)
                if messages and messages[-1]["role"] == "user":
                    last = messages[-1].get("content", resume_input)
                    user_input = last if isinstance(last, str) else resume_input
                    messages.pop()
                else:
                    user_input = resume_input
                _clear_checkpoint()
                print(f"\n{Colors.DIM}↩  Resuming: {user_input[:80]}{Colors.RESET}\n")
                # Fall through to run_agent_loop below
            else:
                action_name = user_input.split()[0].lstrip("/")
                action = get_action(action_name)
                if action:
                    user_input = action.prompt
                else:
                    result = handle_slash_command(user_input, messages, provider)
                    if result is not None:
                        print(f"\n{result}\n")
                    continue

        # Run agent loop
        print()
        if stream_cb:
            stream_cb.reset()
        esc.arm()
        try:
            response, messages = run_agent_loop(
                user_input, messages, provider,
                stream_callback=stream_cb,
                on_progress=progress,
                interrupt_event=esc.interrupt_event,
            )
            _clear_checkpoint()
            if stream_cb:
                if not stream_cb.finish():
                    if response:
                        print(f"{Colors.CYAN}{response}{Colors.RESET}")
                print()
            else:
                print(f"\n{Colors.CYAN}{response}{Colors.RESET}\n")

        except AgentInterrupted as exc:
            progress.stop()
            _save_checkpoint(user_input, exc.checkpoint)
            print(f"\n{Colors.YELLOW}⏸  Paused — type /resume to continue.{Colors.RESET}\n")

        except KeyboardInterrupt:
            progress.stop()
            print(f"\n{Colors.YELLOW}Cancelled.{Colors.RESET}\n")
            if messages and messages[-1]["role"] == "user":
                messages.pop()
            continue

        finally:
            esc.disarm()

        # Auto-save after every response (silent, off main thread)
        threading.Thread(
            target=session_mgr.auto_save,
            args=(messages[:], provider_name, model, sid),
            daemon=True,
        ).start()


# ── One-shot Mode ────────────────────────────────────────────────────────────

def one_shot(prompt: str, provider: object):
    """Run a single prompt and exit."""
    init_tools()
    messages: list[dict] = []
    response, _ = run_agent_loop(prompt, messages, provider)
    print(response)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="dan",
        description=f"{APP_NAME} — {APP_TAGLINE}",
    )
    parser.add_argument("prompt", nargs="?", default=None, help="One-shot prompt")
    parser.add_argument("--print", "-p", dest="print_mode", action="store_true",
                        help="Print mode (one-shot, no REPL)")
    parser.add_argument("--provider", default=None, help="LLM provider (anthropic/openai/ollama)")
    parser.add_argument("--model", default=None, help="Model name")
    parser.add_argument("--doctor", action="store_true",
                        help="Run startup diagnostics for the selected target and exit")
    parser.add_argument("--target", default="cli", choices=("cli", "gui"),
                        help="Startup target to validate with --doctor")
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")

    args = parser.parse_args()

    if getattr(args, "verbose", False):
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    # Determine provider
    provider_name = getattr(args, "provider", None) or os.environ.get("DAN_PROVIDER", DEFAULT_PROVIDER)
    model = getattr(args, "model", None) or os.environ.get("DAN_MODEL", DEFAULT_MODEL)

    doctor_mode = getattr(args, "doctor", False)
    startup_target = getattr(args, "target", "cli")

    if doctor_mode:
        report = startup_doctor(".", provider=provider_name, target=startup_target)
        print(report)
        sys.exit(1 if startup_blocked(".", provider=provider_name, target=startup_target) else 0)

    try:
        provider = get_provider(provider_name, model)
    except (ValueError, ImportError) as e:
        print(f"{Colors.RED}Error: {e}{Colors.RESET}")
        print()
        print(startup_doctor(".", provider=provider_name, target="cli"))
        sys.exit(1)

    actual_model = getattr(provider, 'model', model)

    prompt = getattr(args, "prompt", None)
    print_mode = getattr(args, "print_mode", False)

    if prompt and print_mode:
        one_shot(prompt, provider)
    elif prompt:
        one_shot(prompt, provider)
    else:
        repl(provider, actual_model, provider_name)


if __name__ == "__main__":
    main()
