#!/usr/bin/env python3
"""
scripts/scan_secrets.py

Scans Git-tracked files for common secret patterns: API keys, tokens, and
high-entropy credential assignments. Intended for CI integration and local
pre-commit checks.

Usage:
    python scripts/scan_secrets.py

Exit codes:
    0 — no secret patterns found in tracked files
    1 — one or more potential secrets detected (findings printed to stdout)
    2 — scan could not complete (git unavailable, not a git repo, etc.)

False positives can be suppressed by adding a trailing comment to the line:
    my_key = "example-value"  # noqa: scan-secrets

The scanner only reads Git-tracked files. Untracked, ignored, and staged-but-
not-yet-committed files are not scanned. If you accidentally commit a real
secret, rotate it immediately — deletion from history requires a rewrite.

This scanner is a best-effort first-pass tool, not a cryptographic guarantee.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Secret patterns
# Each entry is (display_name, compiled_regex).
# Patterns are ordered from most-specific (low false-positive rate) to most-
# generic. The generic assignment pattern is last.
# ---------------------------------------------------------------------------
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Anthropic API keys (sk-ant-apiNN-...)
    (
        "Anthropic API key",
        re.compile(r"sk-ant-(?:api\d+-)?[A-Za-z0-9\-_]{20,}"),
    ),
    # OpenAI API keys (sk-proj-... or sk-...) — require 30+ chars to reduce noise
    (
        "OpenAI API key",
        re.compile(r"sk-(?:proj-)?[A-Za-z0-9]{30,}"),
    ),
    # Venice.ai API keys
    (
        "Venice API key",
        re.compile(r"vn-[A-Za-z0-9\-_]{20,}"),
    ),
    # AWS Access Key IDs (always start with AKIA and are exactly 20 chars)
    (
        "AWS Access Key ID",
        re.compile(r"AKIA[0-9A-Z]{16}"),
    ),
    # Generic API key / secret assignments in code
    # Matches: api_key = "...", apiKey: "...", secret_key = '...', etc.
    # Only triggers when the assigned value is ≥ 20 non-whitespace chars,
    # which is long enough to be a real credential but not a short example.
    (
        "Generic credential assignment",
        re.compile(
            r'(?:api[_\-]?key|apikey|secret[_\-]?key|access[_\-]?token|'
            r'private[_\-]?key|auth[_\-]?token|bearer[_\-]?token)'
            r'\s*[=:]\s*["\']([A-Za-z0-9+/\-_@.]{20,})["\']',
            re.IGNORECASE,
        ),
    ),
]

# ---------------------------------------------------------------------------
# Files and extensions to skip
# ---------------------------------------------------------------------------

# Binary and generated file extensions — not scannable as text
_SKIP_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".svg",
    ".pyc", ".pyo", ".pyd",
    ".exe", ".dll", ".so", ".dylib", ".lib", ".obj",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".whl", ".egg",
    ".lock",
    ".db", ".sqlite", ".sqlite3",
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".bin", ".dat",
})

# Specific filenames to skip even if the extension would be scanned.
# .env.example intentionally contains placeholder empty assignments.
_SKIP_FILENAMES: frozenset[str] = frozenset({
    ".env.example",
    "scan_secrets.py",  # This script itself contains pattern strings
})

# Inline suppression marker — append to a line to silence a match
_SUPPRESS_MARKER = "noqa: scan-secrets"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _get_tracked_files(repo_root: Path) -> list[Path]:
    """
    Return all files currently tracked by git in the repository.

    Raises RuntimeError if git is not available or the call fails.
    """
    result = subprocess.run(
        ["git", "ls-files", "--full-name"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"'git ls-files' failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )

    paths = []
    for line in result.stdout.splitlines():
        rel = line.strip()
        if rel:
            paths.append(repo_root / rel)
    return paths


def _scan_file(path: Path) -> list[tuple[int, str, str]]:
    """
    Scan a single file for secret patterns.

    Returns a list of (line_number, pattern_name, redacted_snippet) tuples.
    The snippet is truncated and partially redacted so that actual secret
    values are not echoed back in scan output.
    """
    if path.suffix.lower() in _SKIP_EXTENSIONS:
        return []
    if path.name in _SKIP_FILENAMES:
        return []

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        # Unreadable file — skip silently
        return []

    findings: list[tuple[int, str, str]] = []
    for line_num, raw_line in enumerate(content.splitlines(), start=1):
        # Respect inline suppression marker
        if _SUPPRESS_MARKER in raw_line:
            continue

        for pattern_name, pattern in SECRET_PATTERNS:
            match = pattern.search(raw_line)
            if match:
                # Build a snippet that shows context without echoing the full value.
                # Redact the matched portion itself to avoid logging real secrets.
                start, end = match.span()
                matched_len = end - start
                redacted_line = (
                    raw_line[:start].strip()
                    + "[REDACTED:"
                    + str(matched_len)
                    + "chars]"
                    + raw_line[end:].strip()
                )
                snippet = redacted_line[:120] + ("…" if len(redacted_line) > 120 else "")
                findings.append((line_num, pattern_name, snippet))
                # Report only the first match per line per file to avoid noise
                break

    return findings


def _scan_repository(repo_root: Path) -> tuple[list[tuple[Path, int, str, str]], list[str]]:
    """
    Scan all tracked files in the repository.

    Returns:
        findings: list of (file_path, line_num, pattern_name, snippet)
        warnings: list of warning messages for files that could not be scanned
    """
    tracked = _get_tracked_files(repo_root)

    findings: list[tuple[Path, int, str, str]] = []
    warnings: list[str] = []

    for file_path in tracked:
        try:
            file_findings = _scan_file(file_path)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"WARNING: could not scan {file_path}: {exc}")
            continue

        for line_num, pattern_name, snippet in file_findings:
            findings.append((file_path, line_num, pattern_name, snippet))

    return findings, warnings


def main() -> int:
    """Entry point. Returns exit code (0, 1, or 2)."""
    repo_root = Path(__file__).resolve().parent.parent

    try:
        findings, warnings = _scan_repository(repo_root)
    except RuntimeError as exc:
        print(f"scan_secrets ERROR: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print(
            "scan_secrets ERROR: 'git' command not found. "
            "Ensure git is installed and on PATH.",
            file=sys.stderr,
        )
        return 2

    # Print any scan warnings to stderr
    for warning in warnings:
        print(warning, file=sys.stderr)

    if not findings:
        print("scan_secrets: no secret patterns found in tracked files.")
        return 0

    # Report findings without echoing real secrets
    print(
        f"scan_secrets: POTENTIAL SECRETS FOUND — {len(findings)} match(es)\n"
    )
    for file_path, line_num, pattern_name, snippet in findings:
        try:
            rel = file_path.relative_to(repo_root)
        except ValueError:
            rel = file_path
        print(f"  {rel}:{line_num}  [{pattern_name}]")
        print(f"    {snippet}")

    print()
    print(
        "Review each match. If it is a false positive, add the following comment\n"
        "to the end of the line to suppress future reports:\n"
        f"    # {_SUPPRESS_MARKER}"
    )
    print()
    print(
        "If it is a real secret, rotate it immediately. Remove it from git history\n"
        "with 'git filter-repo' or contact your security team."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
