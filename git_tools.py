"""Git integration tools — first-class git operations for Dan."""

import logging
import os
import re
import subprocess
from pathlib import Path

import tool_registry as registry

logger = logging.getLogger(__name__)


# ── Core helper ───────────────────────────────────────────────────────────────

def _git(args: list[str], cwd: str | None = None,
         timeout: int = 30) -> tuple[int, str, str]:
    """Run a git command. Returns (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd or os.getcwd(),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", f"git {args[0]} timed out after {timeout}s"
    except FileNotFoundError:
        return 1, "", "git not found — is git installed and on PATH?"
    except Exception as e:
        return 1, "", str(e)


def _is_git_repo() -> bool:
    code, _, _ = _git(["rev-parse", "--is-inside-work-tree"])
    return code == 0


# ── Tool handlers ─────────────────────────────────────────────────────────────

def git_status(short: bool = False) -> str:
    """Show the working tree status."""
    if not _is_git_repo():
        return "Error: Not inside a git repository."

    # Branch and tracking info
    code, branch_out, _ = _git(["branch", "--show-current"])
    branch = branch_out.strip() or "(detached HEAD)"

    code, ahead_out, _ = _git([
        "rev-list", "--left-right", "--count", "HEAD...@{upstream}"
    ])
    tracking = ""
    if code == 0 and ahead_out.strip():
        parts = ahead_out.strip().split()
        if len(parts) == 2:
            ahead, behind = parts
            notes = []
            if int(ahead) > 0:  notes.append(f"{ahead} ahead")
            if int(behind) > 0: notes.append(f"{behind} behind")
            if notes:
                tracking = f" ({', '.join(notes)})"

    lines = [f"Branch: {branch}{tracking}"]

    if short:
        code, out, _ = _git(["status", "--short"])
    else:
        code, out, _ = _git(["status", "--short", "--branch"])

    if code != 0:
        return f"git status failed: {out or _}"

    status_lines = out.strip().splitlines()
    if not status_lines or (len(status_lines) == 1 and status_lines[0].startswith("##")):
        lines.append("Working tree clean — nothing to commit.")
        return "\n".join(lines)

    # Categorize
    staged, unstaged, untracked = [], [], []
    for line in status_lines:
        if line.startswith("##"):
            continue
        x, y = line[0], line[1]
        fname = line[3:]
        if x != " " and x != "?":
            staged.append(f"  {x}  {fname}")
        if y not in (" ", "?") and x == " ":
            unstaged.append(f"  {y}  {fname}")
        if x == "?" and y == "?":
            untracked.append(f"  {fname}")

    if staged:
        lines.append(f"\nStaged ({len(staged)}):")
        lines.extend(staged)
    if unstaged:
        lines.append(f"\nModified, not staged ({len(unstaged)}):")
        lines.extend(unstaged)
    if untracked:
        lines.append(f"\nUntracked ({len(untracked)}):")
        lines.extend(untracked[:20])
        if len(untracked) > 20:
            lines.append(f"  ... and {len(untracked) - 20} more")

    return "\n".join(lines)


def git_diff(staged: bool = False, path: str = "", stat: bool = False) -> str:
    """Show changes between working tree and index (or staged changes)."""
    if not _is_git_repo():
        return "Error: Not inside a git repository."

    args = ["diff"]
    if staged:
        args.append("--staged")
    if stat:
        args.append("--stat")
    if path:
        args += ["--", path]

    code, out, err = _git(args)
    if code != 0:
        return f"git diff failed: {err.strip()}"
    if not out.strip():
        label = "staged" if staged else "unstaged"
        return f"No {label} changes."

    # Truncate very large diffs
    lines = out.splitlines()
    if len(lines) > 500:
        out = "\n".join(lines[:500]) + f"\n... (truncated — {len(lines)} total lines)"
    return out


def git_log(count: int = 10, oneline: bool = True, path: str = "") -> str:
    """Show commit history."""
    if not _is_git_repo():
        return "Error: Not inside a git repository."

    count = max(1, min(count, 100))
    args = ["log", f"-{count}"]
    if oneline:
        args += ["--pretty=format:%C(yellow)%h%Creset %C(cyan)%ad%Creset %s %C(dim)(%an)%Creset",
                 "--date=short"]
    else:
        args += ["--pretty=format:%H%n%ad%n%an <%ae>%n%B%n---", "--date=iso"]
    if path:
        args += ["--", path]

    code, out, err = _git(args)
    if code != 0:
        return f"git log failed: {err.strip()}"
    if not out.strip():
        return "No commits found."
    return out


def git_commit(message: str, add_all: bool = False) -> str:
    """Create a git commit.

    If *add_all* is True, stages all tracked modified files first (like git commit -a).
    Does NOT run git add on untracked files — use GitAdd for that.
    """
    if not _is_git_repo():
        return "Error: Not inside a git repository."
    if not message.strip():
        return "Error: Commit message cannot be empty."

    if add_all:
        code, _, err = _git(["add", "-u"])
        if code != 0:
            return f"git add -u failed: {err.strip()}"

    code, out, err = _git(["commit", "-m", message])
    if code != 0:
        output = (out + err).strip()
        if "nothing to commit" in output:
            return "Nothing to commit — working tree is clean."
        return f"git commit failed:\n{output}"
    return out.strip()


def git_add(paths: str = ".") -> str:
    """Stage files for commit. Pass '.' to stage all changes."""
    if not _is_git_repo():
        return "Error: Not inside a git repository."

    path_list = [p.strip() for p in paths.split(",") if p.strip()]
    if not path_list:
        path_list = ["."]

    results = []
    for p in path_list:
        code, _, err = _git(["add", p])
        if code != 0:
            results.append(f"  Failed to add '{p}': {err.strip()}")
        else:
            results.append(f"  Staged: {p}")

    # Show what's now staged
    code2, stat_out, _ = _git(["status", "--short"])
    staged = [l for l in stat_out.splitlines() if l and l[0] not in (" ", "?")]
    results.append(f"\n{len(staged)} file(s) now staged for commit.")
    return "\n".join(results)


def git_branch(name: str = "", checkout: bool = False,
               create: bool = False) -> str:
    """List branches, or create/switch to a branch."""
    if not _is_git_repo():
        return "Error: Not inside a git repository."

    if not name:
        # List all branches
        code, out, err = _git(["branch", "-a", "--format=%(refname:short) %(HEAD)"])
        if code != 0:
            return f"git branch failed: {err.strip()}"
        lines = []
        for line in out.strip().splitlines():
            parts = line.rsplit(" ", 1)
            bname = parts[0].strip()
            active = parts[1].strip() == "*" if len(parts) > 1 else False
            prefix = "→ " if active else "  "
            lines.append(f"{prefix}{bname}")
        return "\n".join(lines) if lines else "No branches found."

    if create:
        code, out, err = _git(["checkout", "-b", name])
    elif checkout:
        code, out, err = _git(["checkout", name])
    else:
        code, out, err = _git(["branch", name])

    output = (out + err).strip()
    if code != 0:
        return f"git branch error: {output}"
    return output or f"✓ Branch '{name}' {'created and checked out' if create else ('checked out' if checkout else 'created')}."


def git_stash(action: str = "list", message: str = "") -> str:
    """Manage git stash: list / push / pop / drop."""
    if not _is_git_repo():
        return "Error: Not inside a git repository."

    action = action.lower()
    if action == "list":
        code, out, err = _git(["stash", "list"])
        return out.strip() or "No stashes." if code == 0 else f"Error: {err}"
    elif action in ("push", "save"):
        args = ["stash", "push"]
        if message:
            args += ["-m", message]
        code, out, err = _git(args)
        return (out + err).strip()
    elif action == "pop":
        code, out, err = _git(["stash", "pop"])
        return (out + err).strip()
    elif action == "drop":
        code, out, err = _git(["stash", "drop"])
        return (out + err).strip()
    else:
        return f"Unknown stash action: {action}. Options: list, push, pop, drop"


# ── Registration ──────────────────────────────────────────────────────────────

def register_git_tools() -> None:
    """Register all git tools."""

    registry.register(
        name="GitStatus",
        description=(
            "Show git working tree status: current branch, staged files, "
            "modified files, and untracked files."
        ),
        parameters={
            "type": "object",
            "properties": {
                "short": {
                    "type": "boolean",
                    "description": "Short format output",
                    "default": False,
                },
            },
        },
        handler=git_status, category="git",
    )

    registry.register(
        name="GitDiff",
        description=(
            "Show changes in the working tree or staged area. "
            "Use staged=true to see what would be committed."
        ),
        parameters={
            "type": "object",
            "properties": {
                "staged": {
                    "type": "boolean",
                    "description": "Show staged (index) diff instead of working tree",
                    "default": False,
                },
                "path": {
                    "type": "string",
                    "description": "Limit diff to a specific file or directory",
                    "default": "",
                },
                "stat": {
                    "type": "boolean",
                    "description": "Show diffstat summary instead of full patch",
                    "default": False,
                },
            },
        },
        handler=git_diff, category="git",
    )

    registry.register(
        name="GitLog",
        description="Show git commit history.",
        parameters={
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of commits to show (1–100)",
                    "default": 10,
                },
                "oneline": {
                    "type": "boolean",
                    "description": "One line per commit",
                    "default": True,
                },
                "path": {
                    "type": "string",
                    "description": "Show only commits that affect this file/dir",
                    "default": "",
                },
            },
        },
        handler=git_log, category="git",
    )

    registry.register(
        name="GitAdd",
        description=(
            "Stage files for commit. Use '.' to stage all changes, "
            "or pass comma-separated file paths."
        ),
        parameters={
            "type": "object",
            "properties": {
                "paths": {
                    "type": "string",
                    "description": "Files to stage (comma-separated, or '.' for all)",
                    "default": ".",
                },
            },
        },
        handler=git_add, category="git",
    )

    registry.register(
        name="GitCommit",
        description="Create a git commit with the given message.",
        parameters={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message",
                },
                "add_all": {
                    "type": "boolean",
                    "description": "Stage all tracked modified files before committing",
                    "default": False,
                },
            },
            "required": ["message"],
        },
        handler=git_commit, category="git",
    )

    registry.register(
        name="GitBranch",
        description=(
            "List branches (no args), create a branch, or switch to one. "
            "Use create=true to create+checkout, checkout=true to switch."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Branch name (empty = list all)",
                    "default": "",
                },
                "create": {
                    "type": "boolean",
                    "description": "Create and checkout this new branch",
                    "default": False,
                },
                "checkout": {
                    "type": "boolean",
                    "description": "Switch to this existing branch",
                    "default": False,
                },
            },
        },
        handler=git_branch, category="git",
    )

    registry.register(
        name="GitStash",
        description="Manage git stash: list, push (save), pop, or drop.",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "push", "pop", "drop"],
                    "description": "Stash operation",
                    "default": "list",
                },
                "message": {
                    "type": "string",
                    "description": "Description for stash push",
                    "default": "",
                },
            },
        },
        handler=git_stash, category="git",
    )
