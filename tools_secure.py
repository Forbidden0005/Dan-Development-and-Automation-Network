"""Secure core tools: file operations, bash, search with enhanced security."""

import asyncio
import fnmatch
import logging
import os
import re
from difflib import unified_diff
from pathlib import Path
from typing import Optional, AsyncGenerator

try:
    import aiofiles
except ModuleNotFoundError:  # pragma: no cover - optional fast path
    aiofiles = None

import tool_registry as registry
from security_utils import (
    SecurePathValidator,
    SecureCommandExecutor,
    sanitize_user_input,
    validate_file_size,
)

logger = logging.getLogger(__name__)

# Global security instances
_path_validator = SecurePathValidator()
_command_executor = SecureCommandExecutor(use_whitelist=True, max_execution_time=30)

# ── Secure Helpers ───────────────────────────────────────────────────────────


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


# ── Secure File Operations ──────────────────────────────────────────────────


def _validate_text_payload(label: str, value: str, max_length: int) -> str:
    """Validate file payloads without changing the caller's intended text."""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    if len(value) > max_length:
        raise ValueError(f"{label} too large: {len(value)} > {max_length}")
    if "\x00" in value:
        raise ValueError(f"{label} must not contain null bytes")
    return value


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


async def read_file_async(path: str, offset: int = 0, limit: int = 0) -> str:
    """Async version of read_file for better performance."""
    try:
        path = sanitize_user_input(path, max_length=500)
        p = _safe_path(path)

        if not p.exists():
            return f"Error: File not found: {path}"
        if not p.is_file():
            return f"Error: Not a file: {path}"

        validate_file_size(p, max_size_mb=50)

        if aiofiles is not None:
            async with aiofiles.open(p, mode="r", encoding="utf-8", errors="replace") as f:
                content = await f.read()
        else:
            logger.info("aiofiles not available; using thread-backed async file read fallback")
            content = await asyncio.to_thread(
                p.read_text,
                encoding="utf-8",
                errors="replace",
            )

        lines = content.splitlines()

        if offset or limit:
            end = offset + limit if limit else len(lines)
            lines = lines[offset:end]

        output_lines = []
        for i, line in enumerate(lines[:10000]):
            output_lines.append(f"{i+offset+1:4d} | {line}")

        result = "\n".join(output_lines)
        if len(lines) > 10000:
            result += f"\n... (truncated, {len(lines)} total lines)"

        return result

    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        logger.error("Error reading file %s: %s", path, e)
        return f"Error reading {path}: {e}"


def write_file(path: str, content: str, create_dirs: bool = True) -> str:
    """Write content to a file with security validation."""
    try:
        # Sanitize inputs
        path = sanitize_user_input(path, max_length=500)
        content = _validate_text_payload("content", content, max_length=1000000)

        p = _safe_path(path)

        if create_dirs:
            p.parent.mkdir(parents=True, exist_ok=True)

        old_content = ""
        if p.exists():
            validate_file_size(p, max_size_mb=50)
            old_content = p.read_text(encoding="utf-8", errors="replace")

        # Write content
        p.write_text(content, encoding="utf-8")

        # Generate diff for feedback
        diff = _diff_text(old_content, content, p.name)
        if diff:
            return f"✓ Wrote {len(content)} bytes to {path}\n\n{diff}"
        return f"✓ Wrote {len(content)} bytes to {path} (no changes)"

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
        old_text = _validate_text_payload("old_text", old_text, max_length=50000)
        new_text = _validate_text_payload("new_text", new_text, max_length=50000)

        p = _safe_path(path)
        if not p.exists():
            return f"Error: File not found: {path}"

        validate_file_size(p, max_size_mb=50)

        content = p.read_text(encoding="utf-8", errors="replace")
        count = content.count(old_text)
        if count == 0:
            return f"Error: old_text not found in {path}"
        if count > 1:
            return f"Error: old_text matches {count} locations. Be more specific."

        new_content = content.replace(old_text, new_text, 1)
        p.write_text(new_content, encoding="utf-8")

        diff = _diff_text(content, new_content, p.name)
        return f"✓ Edited {path}\n\n{diff}"

    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        logger.error("Error editing file %s: %s", path, e)
        return f"Error editing {path}: {e}"


# ── Secure Command Execution ────────────────────────────────────────────────


def run_bash(command: str, timeout: int = 30) -> str:
    """Execute a bash command with comprehensive security controls."""
    try:
        # Sanitize command input
        command = sanitize_user_input(command, max_length=2000)

        old_timeout = _command_executor.max_execution_time
        _command_executor.max_execution_time = max(1, min(int(timeout), 300))
        try:
            # Execute using secure command executor
            result = _command_executor.execute_command(command, cwd=None)
        finally:
            _command_executor.max_execution_time = old_timeout

        # Limit output size
        if len(result) > 10000:
            result = result[:10000] + "\n... (output truncated)"

        return result

    except ValueError as e:
        logger.warning("Command blocked: %s", e)
        return f"Security error: {e}"
    except Exception as e:
        logger.error("Command execution failed: %s", e)
        return f"Execution error: {e}"


# ── Search and Directory Operations ─────────────────────────────────────────


def glob_files(pattern: str, path: str = ".") -> str:
    """Find files matching a glob pattern with security validation."""
    try:
        pattern = sanitize_user_input(pattern, max_length=200)
        path = sanitize_user_input(path, max_length=500)

        search_path = _safe_path(path)
        if not search_path.is_dir():
            return f"Error: Not a directory: {path}"

        matches = []
        try:
            for file_path in search_path.rglob(pattern):
                # Only show files within the allowed directory
                try:
                    rel_path = file_path.relative_to(search_path)
                    matches.append(str(rel_path))
                except ValueError:
                    # Skip files outside the search directory
                    continue

                # Limit number of results
                if len(matches) >= 1000:
                    matches.append("... (results truncated)")
                    break
        except Exception as e:
            return f"Error during search: {e}"

        if not matches:
            return f"No files matching '{pattern}' in {path}"

        return "\n".join(matches)

    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        logger.error("Glob operation failed: %s", e)
        return f"Error: {e}"


def grep_files(pattern: str, path: str = ".", include: str = "") -> str:
    """Search for a regex pattern in files with security validation."""
    try:
        pattern = sanitize_user_input(pattern, max_length=500)
        path = sanitize_user_input(path, max_length=500)
        include = sanitize_user_input(include, max_length=100)

        search_path = _safe_path(path)
        if not search_path.is_dir():
            return f"Error: Not a directory: {path}"

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

        matches = []
        files_searched = 0

        # Determine file pattern
        file_pattern = include if include else "*"

        try:
            for file_path in search_path.rglob(file_pattern):
                if not file_path.is_file():
                    continue

                files_searched += 1
                if files_searched > 1000:  # Limit files searched
                    matches.append("... (search truncated)")
                    break

                # Skip large files
                if file_path.stat().st_size > 10 * 1024 * 1024:  # 10MB
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    for line_num, line in enumerate(content.splitlines(), 1):
                        if regex.search(line):
                            rel_path = file_path.relative_to(search_path)
                            matches.append(f"{rel_path}:{line_num}: {line.strip()}")

                            # Limit matches per file
                            if len(matches) >= 500:
                                matches.append("... (matches truncated)")
                                return "\n".join(matches)

                except (UnicodeDecodeError, PermissionError):
                    # Skip binary files or files we can't read
                    continue

        except Exception as e:
            return f"Error during search: {e}"

        if not matches:
            return f"No matches for '{pattern}' in {path}"

        return "\n".join(matches)

    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        logger.error("Grep operation failed: %s", e)
        return f"Error: {e}"


def list_directory(path: str = ".") -> str:
    """List directory contents as a tree with security validation."""
    try:
        path = sanitize_user_input(path, max_length=500)

        dir_path = _safe_path(path)
        if not dir_path.exists():
            return f"Error: Path not found: {path}"

        if not dir_path.is_dir():
            return f"Error: Not a directory: {path}"

        def _build_tree(
            directory: Path, prefix: str = "", max_depth: int = 3, current_depth: int = 0
        ) -> list:
            if current_depth >= max_depth:
                return ["... (max depth reached)"]

            items = []
            try:
                entries = sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
                for i, entry in enumerate(entries):
                    if len(items) >= 100:  # Limit entries per directory
                        items.append("... (entries truncated)")
                        break

                    is_last = i == len(entries) - 1
                    current_prefix = "└── " if is_last else "├── "

                    if entry.is_dir():
                        items.append(f"{prefix}{current_prefix}{entry.name}/")
                        if current_depth < max_depth - 1:
                            next_prefix = prefix + ("    " if is_last else "│   ")
                            items.extend(
                                _build_tree(entry, next_prefix, max_depth, current_depth + 1)
                            )
                    else:
                        size = entry.stat().st_size
                        size_str = f" ({size:,}b)" if size < 1024 else f" ({size//1024:,}KB)"
                        items.append(f"{prefix}{current_prefix}{entry.name}{size_str}")

            except PermissionError:
                items.append(f"{prefix}... (permission denied)")
            except Exception as e:
                items.append(f"{prefix}... (error: {e})")

            return items

        tree_lines = [f"{dir_path.name}/"]
        tree_lines.extend(_build_tree(dir_path))

        return "\n".join(tree_lines)

    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        logger.error("Directory listing failed: %s", e)
        return f"Error: {e}"


# ── Tool Registration ───────────────────────────────────────────────────────


def register_secure_core_tools():
    """Register the secure versions of core tools."""

    registry.register_tool(
        name="Read",
        description="Read a file's contents.",
        handler=read_file,
        category="files",
        parameters={
            "path": {"type": "string", "description": "File path to read"},
            "offset": {"type": "integer", "default": 0, "description": "Starting line (0-indexed)"},
            "limit": {"type": "integer", "default": 0, "description": "Max lines to read (0=all)"},
        },
    )

    registry.register_tool(
        name="Write",
        description="Write content to a file. Shows diff of changes.",
        handler=write_file,
        category="files",
        parameters={
            "path": {"type": "string", "description": "File path to write"},
            "content": {"type": "string", "description": "Content to write"},
        },
    )

    registry.register_tool(
        name="Edit",
        description="Replace exact text in a file. old_text must match exactly once.",
        handler=edit_file,
        category="files",
        parameters={
            "path": {"type": "string", "description": "File path to edit"},
            "old_text": {"type": "string", "description": "Exact text to find (must match once)"},
            "new_text": {"type": "string", "description": "Replacement text"},
        },
    )

    registry.register_tool(
        name="Bash",
        description="Execute a shell command with security controls.",
        handler=run_bash,
        category="system",
        parameters={
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {"type": "integer", "default": 30, "description": "Timeout in seconds"},
        },
    )

    registry.register_tool(
        name="Glob",
        description="Find files matching a glob pattern.",
        handler=glob_files,
        category="search",
        parameters={
            "pattern": {"type": "string", "description": "Glob pattern (e.g. '*.py')"},
            "path": {"type": "string", "default": ".", "description": "Root directory"},
        },
    )

    registry.register_tool(
        name="Grep",
        description="Search for a regex pattern in files.",
        handler=grep_files,
        category="search",
        parameters={
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "path": {"type": "string", "default": ".", "description": "Root directory"},
            "include": {
                "type": "string",
                "default": "",
                "description": "File glob filter (e.g. '*.py')",
            },
        },
    )

    registry.register_tool(
        name="ListDir",
        description="List directory contents as a tree.",
        handler=list_directory,
        category="files",
        parameters={
            "path": {"type": "string", "default": ".", "description": "Directory path"},
        },
    )
