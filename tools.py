"""Core tools: file operations, bash, search with enhanced security."""

import fnmatch
import logging
import os
import re
import shutil
import subprocess
from difflib import unified_diff
from pathlib import Path

import tool_registry as registry
from security_utils import (
    SecurePathValidator,
    SecureCommandExecutor,
    sanitize_user_input,
    validate_fetch_url,
    validate_file_size,
    validate_redirect_url,
)

logger = logging.getLogger(__name__)

# Global security instances
_path_validator = SecurePathValidator()
_command_executor = SecureCommandExecutor(use_whitelist=True, max_execution_time=30)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _safe_path(path: str) -> Path:
    """Securely resolve and validate a file path."""
    try:
        return _path_validator.validate_path(path)
    except ValueError as e:
        logger.warning("Path validation failed: %s", e)
        raise


def _diff_text(old: str, new: str, filename: str) -> str:
    """Generate a unified diff."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = unified_diff(old_lines, new_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}")
    return "".join(diff)


def _backup(path: Path) -> str | None:
    """Create a .bak backup of a file before destructive operations.

    Returns the backup path string on success, or None if the file didn't
    exist yet (no backup needed).
    """
    if not path.exists():
        return None
    bak = path.with_suffix(path.suffix + ".bak")
    try:
        shutil.copy2(path, bak)
        return str(bak)
    except Exception as e:
        logger.warning("Backup failed for %s: %s", path, e)
        return None


# ── Tool Handlers ────────────────────────────────────────────────────────────


def read_file(path: str, offset: int = 0, limit: int = 0) -> str:
    """Read a file's contents with security validation."""
    try:
        # Sanitize inputs
        path = sanitize_user_input(path, max_length=500)

        p = _safe_path(path)
        if not p.exists():
            return f"Error: File not found: {path}"
        if not p.is_file():
            return f"Error: Not a file: {path}"

        # Validate file size before reading
        validate_file_size(p, max_size_mb=50)

        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            if offset or limit:
                end = offset + limit if limit else len(lines)
                lines = lines[offset:end]

            # Limit output size to prevent memory exhaustion
            output_lines = []
            for i, line in enumerate(lines[:10000]):  # Max 10k lines
                output_lines.append(f"{i+offset+1:4d} | {line}")

            result = "\n".join(output_lines)
            if len(lines) > 10000:
                result += f"\n... (truncated, {len(lines)} total lines)"

            return result

        except Exception as e:
            logger.error("Error reading file %s: %s", path, e)
            return f"Error reading {path}: {e}"

    except ValueError as e:
        return f"Security error: {e}"


def write_file(path: str, content: str, create_dirs: bool = True) -> str:
    """Write content to a file with security validation."""
    try:
        # Sanitize inputs
        path = sanitize_user_input(path, max_length=500)
        content = sanitize_user_input(content, max_length=1000000)  # 1MB limit

        p = _safe_path(path)
        if create_dirs:
            p.parent.mkdir(parents=True, exist_ok=True)

        old_content = p.read_text(errors="replace") if p.exists() else ""

        # Validate content size
        if len(content) > 10 * 1024 * 1024:  # 10MB limit
            return "Error: Content too large (max 10MB)"

        # Backup before overwriting an existing file
        bak = _backup(p)

        p.write_text(content, encoding="utf-8")
        logger.info("File written: %s (%d bytes)", path, len(content))

        diff = _diff_text(old_content, content, p.name)
        bak_note = f"  (backup: {bak})" if bak else ""
        if diff:
            return f"✓ Wrote {len(content)} bytes to {path}{bak_note}\n\n{diff}"
        return f"✓ Wrote {len(content)} bytes to {path} (no changes){bak_note}"

    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        logger.error("Error writing file %s: %s", path, e)
        return f"Error writing {path}: {e}"


def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Replace old_text with new_text in a file with security validation."""
    try:
        # Sanitize inputs
        path = sanitize_user_input(path, max_length=500)
        old_text = sanitize_user_input(old_text, max_length=100000)
        new_text = sanitize_user_input(new_text, max_length=100000)

        p = _safe_path(path)
        if not p.exists():
            return f"Error: File not found: {path}"

        # Validate file size before reading
        validate_file_size(p, max_size_mb=50)

        content = p.read_text(encoding="utf-8", errors="replace")
        count = content.count(old_text)
        if count == 0:
            return f"Error: old_text not found in {path}"
        if count > 1:
            return f"Error: old_text matches {count} locations. Be more specific."

        new_content = content.replace(old_text, new_text, 1)

        # Validate new content size
        if len(new_content) > 10 * 1024 * 1024:  # 10MB limit
            return "Error: Resulting content too large (max 10MB)"

        # Backup before editing
        bak = _backup(p)

        p.write_text(new_content, encoding="utf-8")
        logger.info("File edited: %s", path)

        diff = _diff_text(content, new_content, p.name)
        bak_note = f"  (backup: {bak})" if bak else ""
        return f"✓ Edited {path}{bak_note}\n\n{diff}"

    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        logger.error("Error editing file %s: %s", path, e)
        return f"Error editing {path}: {e}"


def run_bash(command: str, timeout: int = 30) -> str:
    """Execute a bash command with enhanced security."""
    try:
        # Sanitize input
        command = sanitize_user_input(command, max_length=1000)

        old_timeout = _command_executor.max_execution_time
        _command_executor.max_execution_time = max(1, min(int(timeout), 300))
        try:
            result = _command_executor.execute_command(command, cwd=os.getcwd())
        finally:
            _command_executor.max_execution_time = old_timeout
        logger.info("Command executed successfully: %s", command[:50])
        return result

    except ValueError as e:
        logger.warning("Command blocked: %s - %s", command[:50], e)
        return f"Security error: {e}"
    except Exception as e:
        logger.error("Command execution error: %s", e)
        return f"Execution error: {e}"


def glob_files(pattern: str, path: str = ".") -> str:
    """Find files matching a glob pattern with security validation."""
    try:
        # Sanitize inputs
        pattern = sanitize_user_input(pattern, max_length=200)
        path = sanitize_user_input(path, max_length=500)

        root = _safe_path(path)
        if not root.exists():
            return f"Error: Path not found: {path}"

        matches = sorted(root.rglob(pattern))
        # Skip hidden dirs and common junk
        skip = {".git", "__pycache__", "node_modules", ".venv", ".dan"}
        filtered = [m for m in matches[:1000] if not any(s in m.parts for s in skip)]

        if not filtered:
            return f"No files matching '{pattern}' in {path}"

        # Limit results
        result_lines = [str(m.relative_to(root)) for m in filtered[:500]]
        if len(filtered) > 500:
            result_lines.append(f"... (showing first 500 of {len(filtered)} matches)")

        return "\n".join(result_lines)

    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        logger.error("Glob search error: %s", e)
        return f"Search error: {e}"


def grep_search(pattern: str, path: str = ".", include: str = "") -> str:
    """Search for a regex pattern in files."""
    try:
        pattern = sanitize_user_input(pattern, max_length=500)
        path = sanitize_user_input(path, max_length=500)
        include = sanitize_user_input(include, max_length=100)

        root = _safe_path(path)
        if not root.exists():
            return f"Error: Path not found: {path}"

        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Error: Invalid regex: {e}"
    except ValueError as e:
        return f"Security error: {e}"

    results: list[str] = []
    skip = {".git", "__pycache__", "node_modules", ".venv"}
    globs = root.rglob(include) if include else root.rglob("*")

    for fp in globs:
        if not fp.is_file() or any(s in fp.parts for s in skip):
            continue
        if fp.stat().st_size > 1_000_000:  # skip files > 1MB
            continue
        try:
            for i, line in enumerate(fp.read_text(errors="replace").splitlines(), 1):
                if regex.search(line):
                    rel = fp.relative_to(root)
                    results.append(f"{rel}:{i}: {line.strip()}")
                    if len(results) >= 50:
                        results.append("... (truncated at 50 matches)")
                        return "\n".join(results)
        except Exception:
            continue

    return "\n".join(results) if results else f"No matches for '{pattern}' in {path}"


def list_directory(path: str = ".") -> str:
    """List directory contents with tree view."""
    try:
        path = sanitize_user_input(path, max_length=500)
        root = _safe_path(path)
    except ValueError as e:
        return f"Security error: {e}"

    if not root.exists():
        return f"Error: Path not found: {path}"
    if not root.is_dir():
        return f"Error: Not a directory: {path}"

    skip = {".git", "__pycache__", "node_modules", ".venv"}
    lines: list[str] = [f"{root.name}/"]

    def _tree(dir_path: Path, prefix: str, depth: int) -> None:
        if depth > 2:
            return
        entries = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        entries = [e for e in entries if e.name not in skip and not e.name.startswith(".")]
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                ext = "    " if is_last else "│   "
                _tree(entry, prefix + ext, depth + 1)
            else:
                size = entry.stat().st_size
                lines.append(f"{prefix}{connector}{entry.name} ({size:,}b)")

    _tree(root, "", 0)
    return "\n".join(lines)


# ── New Tool Handlers ────────────────────────────────────────────────────────


def append_file(path: str, content: str) -> str:
    """Append content to a file, creating it if necessary."""
    try:
        path = sanitize_user_input(path, max_length=500)
        # Do NOT strip content — preserve intentional newlines.
        if len(content) > 1_000_000:
            return "Error: Content too large to append (max 1MB per call)"
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(content)
        logger.info("Appended %d bytes to %s", len(content), path)
        return f"✓ Appended {len(content)} bytes to {path}"
    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        return f"Error appending to {path}: {e}"


def diff_files(path_a: str, path_b: str) -> str:
    """Return a unified diff between two files."""
    try:
        a = _safe_path(sanitize_user_input(path_a, max_length=500))
        b = _safe_path(sanitize_user_input(path_b, max_length=500))
        if not a.exists():
            return f"Error: File not found: {path_a}"
        if not b.exists():
            return f"Error: File not found: {path_b}"
        validate_file_size(a, max_size_mb=10)
        validate_file_size(b, max_size_mb=10)
        text_a = a.read_text(encoding="utf-8", errors="replace")
        text_b = b.read_text(encoding="utf-8", errors="replace")
        diff = _diff_text(text_a, text_b, f"{a.name} → {b.name}")
        if not diff:
            return f"Files are identical: {path_a} ↔ {path_b}"
        return diff
    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        return f"Error diffing files: {e}"


def move_path(src: str, dest: str) -> str:
    """Move or rename a file or directory."""
    try:
        s = _safe_path(sanitize_user_input(src, max_length=500))
        d = _safe_path(sanitize_user_input(dest, max_length=500))
        if not s.exists():
            return f"Error: Source not found: {src}"
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
        logger.info("Moved %s → %s", src, dest)
        return f"✓ Moved {src} → {dest}"
    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        return f"Error moving {src}: {e}"


def copy_file(src: str, dest: str) -> str:
    """Copy a file to a new location."""
    try:
        s = _safe_path(sanitize_user_input(src, max_length=500))
        d = _safe_path(sanitize_user_input(dest, max_length=500))
        if not s.exists():
            return f"Error: Source not found: {src}"
        if not s.is_file():
            return f"Error: Source is not a file: {src}"
        validate_file_size(s, max_size_mb=50)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(s), str(d))
        logger.info("Copied %s → %s", src, dest)
        return f"✓ Copied {src} → {dest}"
    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        return f"Error copying {src}: {e}"


def http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str = "",
    timeout: int = 30,
    json_mode: bool = False,
    allow_local: bool = False,
) -> str:
    """Make an HTTP request and return the response."""
    try:
        method = method.upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
            return f"Security error: unsupported HTTP method: {method}"

        url = validate_fetch_url(url, allow_local=allow_local)
    except ValueError as e:
        return f"Security error: {e}"

    try:
        import httpx
    except ImportError:
        return "Error: pip install httpx"

    try:
        headers = headers or {}
        if "User-Agent" not in headers:
            headers["User-Agent"] = "Dan/2.5 (Development Automation Network)"

        kwargs: dict = dict(headers=headers, timeout=timeout, follow_redirects=False)
        if body:
            kwargs["content"] = body.encode()

        with httpx.Client(max_redirects=5) as client:
            current_url = url
            for redirect_count in range(6):
                r = client.request(method, url=current_url, **kwargs)
                if 300 <= r.status_code < 400 and r.headers.get("location"):
                    if redirect_count >= 5:
                        return f"Error making {method} request to {url}: too many redirects"
                    current_url = validate_redirect_url(
                        current_url,
                        r.headers["location"],
                        allow_local=allow_local,
                    )
                    if r.status_code == 303 or (
                        r.status_code in {301, 302} and method not in {"GET", "HEAD"}
                    ):
                        method = "GET"
                        kwargs.pop("content", None)
                    continue
                break

        ct = r.headers.get("content-type", "")
        lines = [
            f"HTTP {r.status_code} {r.reason_phrase}",
            f"Content-Type: {ct}",
            f"Content-Length: {len(r.content)} bytes",
            "",
        ]

        if json_mode or "json" in ct:
            try:
                import json as _json

                lines.append(_json.dumps(r.json(), indent=2)[:10_000])
            except Exception:
                lines.append(r.text[:10_000])
        elif "text" in ct or "html" in ct or "xml" in ct:
            lines.append(r.text[:10_000])
        else:
            lines.append(f"(binary content — {len(r.content)} bytes)")

        return "\n".join(lines)

    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        return f"Error making {method} request to {url}: {e}"


# ── Registration ─────────────────────────────────────────────────────────────


def register_core_tools() -> None:
    """Register all core tools."""

    registry.register(
        name="Read",
        description="Read a file's contents.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
                "offset": {
                    "type": "integer",
                    "description": "Starting line (0-indexed)",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max lines to read (0=all)",
                    "default": 0,
                },
            },
            "required": ["path"],
        },
        handler=read_file,
    )

    registry.register(
        name="Write",
        description="Write content to a file. Shows diff of changes.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
        handler=write_file,
    )

    registry.register(
        name="Edit",
        description="Replace exact text in a file. old_text must match exactly once.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to edit"},
                "old_text": {
                    "type": "string",
                    "description": "Exact text to find (must match once)",
                },
                "new_text": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_text", "new_text"],
        },
        handler=edit_file,
    )

    registry.register(
        name="Bash",
        description="Execute a shell command.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["command"],
        },
        handler=run_bash,
    )

    registry.register(
        name="Glob",
        description="Find files matching a glob pattern.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g. '*.py')"},
                "path": {"type": "string", "description": "Root directory", "default": "."},
            },
            "required": ["pattern"],
        },
        handler=glob_files,
    )

    registry.register(
        name="Grep",
        description="Search for a regex pattern in files.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Root directory", "default": "."},
                "include": {
                    "type": "string",
                    "description": "File glob filter (e.g. '*.py')",
                    "default": "",
                },
            },
            "required": ["pattern"],
        },
        handler=grep_search,
    )

    registry.register(
        name="ListDir",
        description="List directory contents as a tree.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path", "default": "."},
            },
        },
        handler=list_directory,
    )

    # ── New tools ─────────────────────────────────────────────────────────────

    registry.register(
        name="Append",
        description="Append content to a file. Creates the file if it does not exist.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "Content to append"},
            },
            "required": ["path", "content"],
        },
        handler=append_file,
    )

    registry.register(
        name="Diff",
        description="Show a unified diff between two files.",
        parameters={
            "type": "object",
            "properties": {
                "path_a": {"type": "string", "description": "First file path"},
                "path_b": {"type": "string", "description": "Second file path"},
            },
            "required": ["path_a", "path_b"],
        },
        handler=diff_files,
    )

    registry.register(
        name="Move",
        description="Move or rename a file or directory.",
        parameters={
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Source path"},
                "dest": {"type": "string", "description": "Destination path"},
            },
            "required": ["src", "dest"],
        },
        handler=move_path,
    )

    registry.register(
        name="Copy",
        description="Copy a file to a new location.",
        parameters={
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Source file path"},
                "dest": {"type": "string", "description": "Destination path"},
            },
            "required": ["src", "dest"],
        },
        handler=copy_file,
    )

    registry.register(
        name="HttpRequest",
        description=(
            "Make an HTTP request (GET, POST, etc.) and return the response. "
            "Useful for API calls, testing endpoints, and fetching structured data."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Request URL"},
                "method": {"type": "string", "description": "HTTP method", "default": "GET"},
                "headers": {"type": "object", "description": "Request headers dict", "default": {}},
                "body": {
                    "type": "string",
                    "description": "Request body (for POST/PUT)",
                    "default": "",
                },
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
                "json_mode": {
                    "type": "boolean",
                    "description": "Parse response as JSON and pretty-print",
                    "default": False,
                },
                "allow_local": {
                    "type": "boolean",
                    "description": "Allow loopback/private-network URLs",
                    "default": False,
                },
            },
            "required": ["url"],
        },
        handler=http_request,
    )
