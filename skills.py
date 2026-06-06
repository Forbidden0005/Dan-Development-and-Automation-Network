"""Skills — tools adapted from awesome-claude-skills repos."""

import hashlib
import logging
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import tool_registry as registry
from security_utils import (
    SecurePathValidator,
    sanitize_user_input,
    validate_fetch_url,
    validate_redirect_url,
)

logger = logging.getLogger(__name__)

_path_validator = SecurePathValidator()


# ── Find Duplicates (from file-organizer skill) ─────────────────────────────


def find_duplicates(path: str = ".", min_size: int = 1024) -> str:
    """Find duplicate files by content hash."""
    try:
        path = sanitize_user_input(path, max_length=500)
        root = _path_validator.validate_path(path)
        if not root.is_dir():
            return f"Error: Not a directory: {path}"
    except ValueError as e:
        return f"Security error: {e}"

    hash_map: dict[str, list[str]] = defaultdict(list)
    files_scanned = 0
    skip = {".git", "__pycache__", "node_modules", ".venv", ".dan"}

    for fp in root.rglob("*"):
        if not fp.is_file() or any(s in fp.parts for s in skip):
            continue
        if fp.stat().st_size < min_size:
            continue
        if fp.stat().st_size > 100 * 1024 * 1024:  # skip >100MB
            continue
        files_scanned += 1
        if files_scanned > 10_000:
            break
        try:
            h = hashlib.md5(fp.read_bytes(), usedforsecurity=False).hexdigest()
            hash_map[h].append(str(fp.relative_to(root)))
        except (PermissionError, OSError):
            continue

    dupes = {h: paths for h, paths in hash_map.items() if len(paths) > 1}
    if not dupes:
        return f"No duplicates found ({files_scanned} files scanned)."

    lines = [
        f"Found {sum(len(p) - 1 for p in dupes.values())} duplicate files in {len(dupes)} groups:"
    ]
    for h, paths in list(dupes.items())[:50]:
        size = Path(root / paths[0]).stat().st_size
        size_str = f"{size:,}b" if size < 1024 else f"{size // 1024:,}KB"
        lines.append(f"\n  [{size_str}] (md5: {h[:8]}...)")
        for p in paths:
            lines.append(f"    {p}")

    if len(dupes) > 50:
        lines.append(f"\n  ... and {len(dupes) - 50} more groups")
    return "\n".join(lines)


# ── Project Scaffold (from file-organizer skill) ────────────────────────────

SCAFFOLDS = {
    "python": {
        "dirs": ["src", "tests", "docs", "scripts"],
        "files": {
            "src/__init__.py": "",
            "tests/__init__.py": "",
            "tests/test_main.py": '"""Smoke tests for the generated package."""\n\nimport importlib\n\n\ndef test_project_package_imports():\n    assert importlib.import_module("src") is not None\n',
            "README.md": "# {name}\n\n## Setup\n\n```bash\npip install -r requirements.txt\n```\n\n## Usage\n\n```bash\npython -m src\n```\n",
            "requirements.txt": "",
            ".gitignore": "__pycache__/\n*.pyc\n.venv/\n.env\ndist/\n*.egg-info/\n",
            "pyproject.toml": '[project]\nname = "{name}"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n',
        },
    },
    "node": {
        "dirs": ["src", "tests", "docs"],
        "files": {
            "src/index.js": "// Entry point\n",
            "tests/.gitkeep": "",
            "README.md": "# {name}\n\n## Setup\n\n```bash\nnpm install\n```\n\n## Usage\n\n```bash\nnpm start\n```\n",
            ".gitignore": "node_modules/\ndist/\n.env\n",
            "package.json": '{{\n  "name": "{name}",\n  "version": "0.1.0",\n  "main": "src/index.js",\n  "scripts": {{\n    "start": "node src/index.js",\n    "test": "jest"\n  }}\n}}\n',
        },
    },
    "web": {
        "dirs": ["src", "src/components", "src/styles", "public", "tests"],
        "files": {
            "public/index.html": '<!DOCTYPE html>\n<html lang="en">\n<head><meta charset="UTF-8"><title>{name}</title></head>\n<body><div id="app"></div><script type="module" src="/src/main.js"></script></body>\n</html>\n',
            "src/main.js": "// Entry point\n",
            "src/styles/main.css": "/* Global styles */\n",
            "README.md": "# {name}\n",
            ".gitignore": "node_modules/\ndist/\n.env\n",
        },
    },
}


def scaffold_project(name: str, template: str = "python", path: str = ".") -> str:
    """Create a project scaffold from a template."""
    try:
        name = sanitize_user_input(name, max_length=100)
        path = sanitize_user_input(path, max_length=500)
        root = _path_validator.validate_path(path)
    except ValueError as e:
        return f"Security error: {e}"

    template = template.lower()
    if template not in SCAFFOLDS:
        return f"Unknown template: {template}. Available: {', '.join(SCAFFOLDS.keys())}"

    scaffold = SCAFFOLDS[template]
    project_dir = root / name

    if project_dir.exists():
        return f"Error: Directory already exists: {project_dir}"

    created = []
    project_dir.mkdir(parents=True)
    created.append(f"{name}/")

    for d in scaffold["dirs"]:
        (project_dir / d).mkdir(parents=True, exist_ok=True)
        created.append(f"  {d}/")

    for fp, content in scaffold["files"].items():
        full_path = project_dir / fp
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content.format(name=name))
        created.append(f"  {fp}")

    return f"✓ Created {template} project '{name}':\n" + "\n".join(created)


# ── Changelog Generator (from changelog-generator skill) ────────────────────


def generate_changelog(since: str = "", until: str = "", format: str = "markdown") -> str:
    """Generate a changelog from git history."""
    try:
        # Build git log command
        cmd = ["git", "log", "--pretty=format:%H|%s|%an|%ad", "--date=short"]
        if since:
            cmd.append(f"--since={since}")
        if until:
            cmd.append(f"--until={until}")
        if not since and not until:
            cmd.append("-50")  # default: last 50 commits

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, cwd=os.getcwd())
        if result.returncode != 0:
            return f"Error running git log: {result.stderr.strip()}"

        if not result.stdout.strip():
            return "No commits found in the specified range."

        # Parse and categorize commits
        categories: dict[str, list[str]] = {
            "feat": [],
            "fix": [],
            "docs": [],
            "refactor": [],
            "test": [],
            "chore": [],
            "perf": [],
            "style": [],
            "breaking": [],
            "other": [],
        }

        CATEGORY_MAP = {
            "feat": "feat",
            "feature": "feat",
            "add": "feat",
            "fix": "fix",
            "bug": "fix",
            "patch": "fix",
            "hotfix": "fix",
            "doc": "docs",
            "docs": "docs",
            "readme": "docs",
            "refactor": "refactor",
            "refact": "refactor",
            "test": "test",
            "tests": "test",
            "chore": "chore",
            "build": "chore",
            "ci": "chore",
            "deps": "chore",
            "perf": "perf",
            "performance": "perf",
            "optimize": "perf",
            "style": "style",
            "format": "style",
            "lint": "style",
            "breaking": "breaking",
            "break": "breaking",
        }

        EMOJI_MAP = {
            "feat": "✨",
            "fix": "🐛",
            "docs": "📝",
            "refactor": "♻️",
            "test": "🧪",
            "chore": "🔧",
            "perf": "⚡",
            "style": "🎨",
            "breaking": "💥",
            "other": "📦",
        }

        LABEL_MAP = {
            "feat": "New Features",
            "fix": "Bug Fixes",
            "docs": "Documentation",
            "refactor": "Refactoring",
            "test": "Tests",
            "chore": "Maintenance",
            "perf": "Performance",
            "style": "Styling",
            "breaking": "Breaking Changes",
            "other": "Other",
        }

        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue
            _hash, subject, author, date = parts

            # Categorize by conventional commit prefix
            matched = False
            subject_lower = subject.lower()
            for keyword, cat in CATEGORY_MAP.items():
                if subject_lower.startswith(keyword + ":") or subject_lower.startswith(
                    keyword + "("
                ):
                    # Strip the prefix
                    clean = re.sub(r"^[\w]+(\([^)]*\))?:\s*", "", subject)
                    categories[cat].append(f"{clean} ({author}, {date})")
                    matched = True
                    break

            if not matched:
                # Try keyword detection in the message
                for keyword, cat in CATEGORY_MAP.items():
                    if keyword in subject_lower:
                        categories[cat].append(f"{subject} ({author}, {date})")
                        matched = True
                        break

            if not matched:
                categories["other"].append(f"{subject} ({author}, {date})")

        # Format output
        lines = ["# Changelog\n"]
        for cat, entries in categories.items():
            if not entries:
                continue
            emoji = EMOJI_MAP.get(cat, "📦")
            label = LABEL_MAP.get(cat, cat.title())
            lines.append(f"\n## {emoji} {label}\n")
            for entry in entries:
                lines.append(f"- {entry}")

        total = sum(len(e) for e in categories.values())
        lines.append(f"\n---\n*{total} commits processed*")

        return "\n".join(lines)

    except subprocess.TimeoutExpired:
        return "Error: git log timed out"
    except FileNotFoundError:
        return "Error: git not found. Are you in a git repository?"
    except Exception as e:
        return f"Error generating changelog: {e}"


# ── Web App Test Runner (from webapp-testing skill) ──────────────────────────


def run_webapp_test(url: str, script: str = "", checks: str = "", allow_local: bool = False) -> str:
    """Test a web application URL for basic health and optional Playwright checks."""
    try:
        url = validate_fetch_url(url, allow_local=allow_local)
    except ValueError as e:
        return f"Security error: {e}"

    try:
        import httpx
    except ImportError:
        return "Error: pip install httpx"

    results = []

    # Basic health check
    try:
        with httpx.Client(timeout=10) as client:
            current_url = url
            for redirect_count in range(6):
                r = client.get(current_url, follow_redirects=False)
                if 300 <= r.status_code < 400 and r.headers.get("location"):
                    if redirect_count >= 5:
                        return f"Error testing {url}: too many redirects"
                    current_url = validate_redirect_url(
                        current_url,
                        r.headers["location"],
                        allow_local=allow_local,
                    )
                    continue
                break

            results.append(f"GET {url}: {r.status_code} ({len(r.content):,} bytes)")
            results.append(f"Content-Type: {r.headers.get('content-type', 'unknown')}")

            # Basic checks
            if r.status_code >= 400:
                results.append(f"⚠️  HTTP error: {r.status_code}")
            else:
                results.append("✓ Server responding")

            if "text/html" in r.headers.get("content-type", ""):
                html = r.text
                if "<title>" in html.lower():
                    import re as _re

                    title = _re.search(
                        r"<title[^>]*>(.*?)</title>", html, _re.IGNORECASE | _re.DOTALL
                    )
                    if title:
                        results.append(f"✓ Title: {title.group(1).strip()}")
                if "error" in html.lower()[:2000] or "exception" in html.lower()[:2000]:
                    results.append("⚠️  Page may contain error messages")
                else:
                    results.append("✓ No obvious errors in HTML")

    except ValueError as e:
        results.append(f"Security error: {e}")
    except Exception as e:
        results.append(f"❌ Connection failed: {e}")

    return "\n".join(results)


# ── Registration ─────────────────────────────────────────────────────────────


def register_skill_tools() -> None:
    """Register skill-derived tools."""

    registry.register(
        name="FindDuplicates",
        description="Find duplicate files by content hash in a directory.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to scan", "default": "."},
                "min_size": {
                    "type": "integer",
                    "description": "Min file size in bytes",
                    "default": 1024,
                },
            },
        },
        handler=find_duplicates,
        category="skills",
    )

    registry.register(
        name="Scaffold",
        description="Create a new project from a template (python/node/web).",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Project name"},
                "template": {
                    "type": "string",
                    "enum": ["python", "node", "web"],
                    "default": "python",
                },
                "path": {"type": "string", "description": "Parent directory", "default": "."},
            },
            "required": ["name"],
        },
        handler=scaffold_project,
        category="skills",
    )

    registry.register(
        name="Changelog",
        description="Generate a changelog from git commit history.",
        parameters={
            "type": "object",
            "properties": {
                "since": {
                    "type": "string",
                    "description": "Start date/tag (e.g. '2024-01-01' or 'v1.0')",
                    "default": "",
                },
                "until": {"type": "string", "description": "End date/tag", "default": ""},
                "format": {"type": "string", "enum": ["markdown", "plain"], "default": "markdown"},
            },
        },
        handler=generate_changelog,
        category="skills",
    )

    registry.register(
        name="WebTest",
        description="Test a web application URL for health, status, and basic HTML checks.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to test"},
                "allow_local": {
                    "type": "boolean",
                    "description": "Allow loopback/private-network URLs",
                    "default": False,
                },
            },
            "required": ["url"],
        },
        handler=run_webapp_test,
        category="skills",
    )
