"""Coding intelligence tools — test runner, linter, formatter, symbol analysis."""

import ast
import json
import logging
import os
import re
import subprocess
from pathlib import Path

import tool_registry as registry

logger = logging.getLogger(__name__)

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
              ".tox", "dist", "build", ".mypy_cache", ".pytest_cache"}


# ── Subprocess helper ─────────────────────────────────────────────────────────

def _run(cmd: list[str], cwd: str | None = None,
         timeout: int = 120) -> tuple[int, str, str]:
    """Run a subprocess. Returns (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            cmd, cwd=cwd or os.getcwd(),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 1, "", f"Timed out after {timeout}s"
    except FileNotFoundError:
        return 1, "", f"Command not found: {cmd[0]}"
    except Exception as e:
        return 1, "", str(e)


# ── 1. RunTests ───────────────────────────────────────────────────────────────

def run_tests(path: str = ".", framework: str = "", args: str = "",
              timeout: int = 60) -> str:
    """Run the project's test suite and return structured results."""

    root = Path(path).resolve()

    # Auto-detect framework
    if not framework:
        if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists():
            framework = "pytest"
        elif (root / "package.json").exists():
            framework = "jest"
        elif list(root.rglob("test_*.py")) or list(root.rglob("*_test.py")):
            framework = "pytest"
        else:
            framework = "pytest"  # default

    extra = args.split() if args else []

    if framework in ("pytest", "py"):
        cmd = ["python", "-m", "pytest", "--tb=short", "-q"] + extra + [str(path)]
        code, out, err = _run(cmd, timeout=timeout)
        output = out + (("\n" + err) if err.strip() else "")

        # Parse summary line
        summary_match = re.search(
            r"(\d+ passed)?[,\s]*(\d+ failed)?[,\s]*(\d+ error)?[,\s]*(\d+ warning)?",
            output, re.IGNORECASE
        )
        lines = [f"Framework: pytest", f"Exit code: {code}"]

        # Extract failures for quick reference
        failures = re.findall(r"FAILED (.+?)(?:\s*-\s*.+)?$", output, re.MULTILINE)
        if failures:
            lines.append(f"\nFailed tests ({len(failures)}):")
            for f in failures[:20]:
                lines.append(f"  ✗ {f.strip()}")
            if len(failures) > 20:
                lines.append(f"  ... and {len(failures) - 20} more")

        lines.append(f"\n{'─'*50}")
        lines.append(output[-3000:] if len(output) > 3000 else output)
        return "\n".join(lines)

    elif framework in ("unittest",):
        cmd = ["python", "-m", "unittest", "discover", "-s", str(path)] + extra
        code, out, err = _run(cmd, timeout=timeout)
        return f"Framework: unittest\nExit code: {code}\n\n{(out + err)[-3000:]}"

    elif framework in ("jest", "npm test", "npm"):
        cmd = ["npm", "test", "--", "--passWithNoTests"] + extra
        code, out, err = _run(cmd, cwd=str(root), timeout=timeout)
        return f"Framework: jest\nExit code: {code}\n\n{(out + err)[-3000:]}"

    elif framework in ("go", "go test"):
        cmd = ["go", "test", "./..."] + extra
        code, out, err = _run(cmd, cwd=str(root), timeout=timeout)
        return f"Framework: go test\nExit code: {code}\n\n{(out + err)[-3000:]}"

    else:
        return (f"Unknown test framework: {framework}. "
                "Supported: pytest, unittest, jest, go")


# ── 2. LintCheck ─────────────────────────────────────────────────────────────

def lint_check(path: str = ".", tool: str = "", fix: bool = False) -> str:
    """Run a linter/type-checker and return issues."""

    root = Path(path).resolve()

    # Auto-detect linting tool
    if not tool:
        if (root / "pyproject.toml").exists() or list(root.rglob("*.py")):
            # Prefer ruff > flake8 > pylint for Python
            for candidate in ["ruff", "flake8", "pylint"]:
                code, _, _ = _run([candidate, "--version"])
                if code == 0:
                    tool = candidate
                    break
            if not tool:
                # Try mypy for type checking
                code, _, _ = _run(["mypy", "--version"])
                tool = "mypy" if code == 0 else "none"
        elif (root / "package.json").exists():
            tool = "eslint"
        else:
            tool = "none"

    if tool == "none":
        return ("No linter found. Install one: pip install ruff  OR  pip install flake8")

    if tool == "ruff":
        args = ["ruff", "check"]
        if fix:
            args.append("--fix")
        args.append(str(path))
        code, out, err = _run(args)
        output = out + (("\n" + err) if err.strip() else "")
        if not output.strip():
            return f"ruff: No issues found in {path}"
        issues = len(output.strip().splitlines())
        return f"ruff ({issues} issue(s)):\n\n{output[:4000]}"

    elif tool == "flake8":
        args = ["flake8", "--max-line-length=120", str(path)]
        code, out, err = _run(args)
        output = out + (("\n" + err) if err.strip() else "")
        if not output.strip():
            return f"flake8: No issues found in {path}"
        lines = output.strip().splitlines()
        return f"flake8 ({len(lines)} issue(s)):\n\n{output[:4000]}"

    elif tool == "mypy":
        args = ["mypy", "--ignore-missing-imports", str(path)]
        code, out, err = _run(args)
        output = out + (("\n" + err) if err.strip() else "")
        if "Success:" in output and "no issues" in output:
            return f"mypy: No type errors found in {path}"
        return f"mypy:\n\n{output[:4000]}"

    elif tool == "pylint":
        args = ["pylint", "--output-format=text", str(path)]
        code, out, err = _run(args)
        output = out
        if not output.strip():
            return f"pylint: No issues found in {path}"
        return f"pylint:\n\n{output[:4000]}"

    elif tool == "eslint":
        args = ["npx", "eslint", str(path)]
        if fix:
            args.append("--fix")
        code, out, err = _run(args, cwd=str(root))
        output = out + (("\n" + err) if err.strip() else "")
        return f"eslint:\n\n{output[:4000]}"

    else:
        return f"Unknown linter: {tool}. Options: ruff, flake8, mypy, pylint, eslint"


# ── 3. FormatCode ─────────────────────────────────────────────────────────────

def format_code(path: str = ".", formatter: str = "",
                check_only: bool = False) -> str:
    """Run a code formatter and report what changed."""

    root = Path(path).resolve()

    # Auto-detect
    if not formatter:
        # Check for pyproject.toml / Python files
        if list(root.rglob("*.py")):
            for candidate in ["ruff", "black", "autopep8"]:
                code, _, _ = _run([candidate, "--version"])
                if code == 0:
                    formatter = candidate
                    break
        elif list(root.rglob("*.ts")) or list(root.rglob("*.js")):
            formatter = "prettier"

    if not formatter:
        return ("No formatter found. Install one:\n"
                "  Python: pip install ruff  OR  pip install black\n"
                "  JS/TS:  npm install -g prettier")

    if formatter == "ruff":
        args = ["ruff", "format"]
        if check_only:
            args.append("--check")
        args.append(str(path))
        code, out, err = _run(args)
        output = (out + err).strip()
        if not output:
            return f"ruff format: {path} is already formatted."
        return f"ruff format:\n{output}"

    elif formatter == "black":
        args = ["black"]
        if check_only:
            args.append("--check")
        args.append(str(path))
        code, out, err = _run(args)
        output = (out + err).strip()
        return f"black:\n{output}"

    elif formatter == "autopep8":
        args = ["autopep8", "--in-place", "--aggressive", str(path)]
        if check_only:
            args = ["autopep8", "--diff", str(path)]
        code, out, err = _run(args)
        return f"autopep8:\n{(out or 'No changes needed.').strip()}"

    elif formatter == "prettier":
        args = ["npx", "prettier", "--write", str(path)]
        if check_only:
            args = ["npx", "prettier", "--check", str(path)]
        code, out, err = _run(args, cwd=str(root))
        return f"prettier:\n{(out + err).strip()}"

    else:
        return f"Unknown formatter: {formatter}. Options: ruff, black, autopep8, prettier"


# ── 4. FindUsages ─────────────────────────────────────────────────────────────

def find_usages(symbol: str, path: str = ".", language: str = "") -> str:
    """Find all usages of a symbol (function, class, variable) across a codebase.

    Returns occurrences grouped by type: definition, call, import, assignment.
    """
    if not symbol.strip():
        return "Error: symbol cannot be empty."

    root = Path(path).resolve()
    if not root.exists():
        return f"Error: Path not found: {path}"

    # Build patterns per usage type
    patterns = {
        "definition": [
            rf"^\s*def\s+{re.escape(symbol)}\s*[\(:]",
            rf"^\s*class\s+{re.escape(symbol)}\s*[\(:]",
            rf"^\s*async\s+def\s+{re.escape(symbol)}\s*\(",
        ],
        "import": [
            rf"^\s*from\s+\S+\s+import\s+.*\b{re.escape(symbol)}\b",
            rf"^\s*import\s+.*\b{re.escape(symbol)}\b",
        ],
        "call": [
            rf"\b{re.escape(symbol)}\s*\(",
        ],
        "assignment": [
            rf"^\s*{re.escape(symbol)}\s*=",
        ],
        "attribute": [
            rf"\b{re.escape(symbol)}\b",
        ],
    }

    # File extension filter
    auto_ext = language or ""
    ext_map = {
        "python": "*.py", "py": "*.py",
        "js": "*.js", "javascript": "*.js",
        "ts": "*.ts", "typescript": "*.ts",
        "go": "*.go", "rust": "*.rs", "rb": "*.rb",
    }
    glob_pat = ext_map.get(auto_ext.lower(), "*")

    results: dict[str, list[str]] = {k: [] for k in patterns}
    total = 0

    for fp in sorted(root.rglob(glob_pat)):
        if not fp.is_file():
            continue
        if any(s in fp.parts for s in _SKIP_DIRS):
            continue
        if fp.stat().st_size > 2_000_000:
            continue

        try:
            lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        rel = str(fp.relative_to(root))

        for i, line in enumerate(lines, 1):
            for utype, pats in patterns.items():
                for pat in pats:
                    if re.search(pat, line, re.IGNORECASE):
                        results[utype].append(f"  {rel}:{i}  {line.strip()}")
                        total += 1
                        break

    if total == 0:
        return f"No usages of '{symbol}' found in {path}"

    lines_out = [f"Usages of '{symbol}' ({total} total):"]
    priority = ["definition", "import", "call", "assignment", "attribute"]
    for utype in priority:
        items = results[utype]
        if not items:
            continue
        lines_out.append(f"\n{utype.upper()} ({len(items)}):")
        lines_out.extend(items[:30])
        if len(items) > 30:
            lines_out.append(f"  ... and {len(items) - 30} more")

    return "\n".join(lines_out)


# ── 5. RefactorRename ─────────────────────────────────────────────────────────

def refactor_rename(old_name: str, new_name: str, path: str = ".",
                    dry_run: bool = True, file_pattern: str = "*.py") -> str:
    """Rename a symbol across all matching files in the project.

    Always previews changes by default (dry_run=True).
    Set dry_run=False to apply.
    """
    if not old_name.strip() or not new_name.strip():
        return "Error: old_name and new_name must not be empty."

    root = Path(path).resolve()
    if not root.exists():
        return f"Error: Path not found: {path}"

    # Word-boundary pattern — only replace whole words
    pattern = re.compile(rf"\b{re.escape(old_name)}\b")

    changed_files: list[tuple[Path, str, str]] = []  # (path, old, new)

    for fp in sorted(root.rglob(file_pattern)):
        if not fp.is_file():
            continue
        if any(s in fp.parts for s in _SKIP_DIRS):
            continue
        try:
            original = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        if not pattern.search(original):
            continue

        modified = pattern.sub(new_name, original)
        if modified != original:
            changed_files.append((fp, original, modified))

    if not changed_files:
        return f"No occurrences of '{old_name}' found in {path} ({file_pattern})"

    lines = [
        f"{'DRY RUN — ' if dry_run else ''}Rename '{old_name}' → '{new_name}'",
        f"Files affected: {len(changed_files)}",
    ]

    for fp, original, modified in changed_files[:20]:
        rel = str(fp.relative_to(root))
        count = len(pattern.findall(original))
        lines.append(f"\n  {rel} ({count} occurrence{'s' if count != 1 else ''})")

        # Show a compact diff (first 5 changed lines)
        orig_lines  = original.splitlines()
        mod_lines   = modified.splitlines()
        shown = 0
        for i, (ol, ml) in enumerate(zip(orig_lines, mod_lines), 1):
            if ol != ml:
                lines.append(f"    L{i}: {ol.strip()}")
                lines.append(f"       → {ml.strip()}")
                shown += 1
                if shown >= 5:
                    break

    if len(changed_files) > 20:
        lines.append(f"\n... and {len(changed_files) - 20} more files")

    if dry_run:
        lines.append(f"\nRun with dry_run=false to apply these {len(changed_files)} change(s).")
    else:
        # Apply changes
        applied = 0
        for fp, _, modified in changed_files:
            try:
                fp.write_text(modified, encoding="utf-8")
                applied += 1
            except Exception as e:
                lines.append(f"  Error writing {fp}: {e}")
        lines.append(f"\n✓ Renamed in {applied}/{len(changed_files)} files.")

    return "\n".join(lines)


# ── 6. AnalyzeCode ────────────────────────────────────────────────────────────

def analyze_code(path: str) -> str:
    """Analyze a Python file or directory using the AST.

    Reports: functions, classes, imports, todos, potential issues.
    """
    p = Path(path).resolve()
    if not p.exists():
        return f"Error: Path not found: {path}"

    files = [p] if p.is_file() else list(p.rglob("*.py"))
    files = [f for f in files if not any(s in f.parts for s in _SKIP_DIRS)]

    if not files:
        return f"No Python files found in {path}"

    totals = {"functions": 0, "classes": 0, "imports": 0, "lines": 0,
              "todos": [], "issues": []}

    for fp in files[:50]:  # cap at 50 files
        try:
            source = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        source_lines = source.splitlines()
        totals["lines"] += len(source_lines)

        # Collect TODOs / FIXMEs / HACKs
        for i, line in enumerate(source_lines, 1):
            stripped = line.strip()
            if re.search(r"\b(TODO|FIXME|HACK|XXX|BUG)\b", stripped, re.IGNORECASE):
                rel = str(fp.relative_to(p.parent if p.is_file() else p))
                totals["todos"].append(f"  {rel}:{i}: {stripped}")

        # AST analysis
        try:
            tree = ast.parse(source, filename=str(fp))
        except SyntaxError as e:
            totals["issues"].append(f"  {fp.name}: SyntaxError at line {e.lineno}: {e.msg}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                totals["functions"] += 1
                # Flag missing docstrings on public functions
                is_public = not node.name.startswith("_")
                has_doc   = (isinstance(node.body[0], ast.Expr) and
                             isinstance(node.body[0].value, ast.Constant) and
                             isinstance(node.body[0].value.value, str)) if node.body else False
                if is_public and not has_doc and len(files) == 1:
                    totals["issues"].append(
                        f"  {fp.name}:{node.lineno}: public function '{node.name}' has no docstring"
                    )
            elif isinstance(node, ast.ClassDef):
                totals["classes"] += 1
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                totals["imports"] += 1
            elif isinstance(node, ast.ExceptHandler):
                # Flag bare except
                if node.type is None:
                    totals["issues"].append(
                        f"  {fp.name}:{node.lineno}: bare 'except:' clause — catch specific exceptions"
                    )

    lines = [
        f"Code Analysis: {path}",
        f"  Files:     {len(files)}",
        f"  Lines:     {totals['lines']:,}",
        f"  Functions: {totals['functions']:,}",
        f"  Classes:   {totals['classes']:,}",
        f"  Imports:   {totals['imports']:,}",
    ]

    if totals["todos"]:
        lines.append(f"\nTODOs / FIXMEs ({len(totals['todos'])}):")
        lines.extend(totals["todos"][:20])
        if len(totals["todos"]) > 20:
            lines.append(f"  ... and {len(totals['todos']) - 20} more")

    if totals["issues"]:
        lines.append(f"\nPotential Issues ({len(totals['issues'])}):")
        lines.extend(totals["issues"][:20])
        if len(totals["issues"]) > 20:
            lines.append(f"  ... and {len(totals['issues']) - 20} more")

    if not totals["todos"] and not totals["issues"]:
        lines.append("\nNo issues found.")

    return "\n".join(lines)


# ── 7. CheckDeps ─────────────────────────────────────────────────────────────

def check_deps(path: str = ".") -> str:
    """Check which project dependencies are installed and which are missing."""

    root = Path(path).resolve()
    requirements: list[tuple[str, str]] = []  # (pkg_name, source)

    # requirements.txt
    for req_file in ["requirements.txt", "requirements-dev.txt", "requirements/base.txt"]:
        rf = root / req_file
        if rf.exists():
            for line in rf.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    pkg = re.split(r"[>=<!;\[]", line)[0].strip()
                    if pkg:
                        requirements.append((pkg, req_file))

    # pyproject.toml (basic parsing)
    pp = root / "pyproject.toml"
    if pp.exists():
        content = pp.read_text()
        # Find [project] dependencies
        for m in re.finditer(r'"([^"@\s]+)(?:@[^"]+)?"', content):
            pkg = re.split(r"[>=<!;\[]", m.group(1))[0].strip()
            if pkg and "." not in pkg:  # skip URLs
                requirements.append((pkg, "pyproject.toml"))

    if not requirements:
        return (f"No requirements file found in {path}. "
                "Looked for: requirements.txt, pyproject.toml")

    # Check each with importlib
    import importlib.util
    installed, missing = [], []

    seen = set()
    for pkg, source in requirements:
        if pkg.lower() in seen:
            continue
        seen.add(pkg.lower())

        # Map pkg name to import name
        import_name = pkg.replace("-", "_").lower()
        spec = importlib.util.find_spec(import_name)
        if spec is not None:
            installed.append((pkg, source))
        else:
            missing.append((pkg, source))

    lines = [
        f"Dependency Check ({root.name})",
        f"  Installed: {len(installed)}",
        f"  Missing:   {len(missing)}",
    ]

    if missing:
        lines.append(f"\nMissing packages:")
        for pkg, src in missing:
            lines.append(f"  ✗  {pkg}  (from {src})")
        lines.append(f"\nInstall with: pip install {' '.join(p for p, _ in missing)}")
    else:
        lines.append("\nAll dependencies are installed.")

    return "\n".join(lines)


# ── Registration ──────────────────────────────────────────────────────────────

def register_code_tools() -> None:
    """Register all coding intelligence tools."""

    registry.register(
        name="RunTests",
        description=(
            "Run the project's test suite and return structured pass/fail results. "
            "Auto-detects pytest, unittest, jest, or go test. "
            "Always run this after making code changes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path":      {"type": "string",  "description": "Project root or test directory", "default": "."},
                "framework": {"type": "string",  "description": "Test framework (pytest/unittest/jest/go). Auto-detected if empty.", "default": ""},
                "args":      {"type": "string",  "description": "Extra arguments to pass (e.g. '-k test_login -v')", "default": ""},
                "timeout":   {"type": "integer", "description": "Timeout in seconds", "default": 60},
            },
        },
        handler=run_tests, category="code",
    )

    registry.register(
        name="LintCheck",
        description=(
            "Run a linter or type checker on the codebase and return all issues. "
            "Auto-detects ruff, flake8, mypy, pylint, eslint."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string",  "description": "Path to check",       "default": "."},
                "tool": {"type": "string",  "description": "Linter to use (auto-detected if empty)", "default": ""},
                "fix":  {"type": "boolean", "description": "Apply auto-fixes where possible", "default": False},
            },
        },
        handler=lint_check, category="code",
    )

    registry.register(
        name="FormatCode",
        description=(
            "Run a code formatter (ruff/black for Python, prettier for JS/TS). "
            "Use check_only=true to preview what would change without applying."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path":       {"type": "string",  "description": "File or directory to format", "default": "."},
                "formatter":  {"type": "string",  "description": "Formatter to use (auto-detected if empty)", "default": ""},
                "check_only": {"type": "boolean", "description": "Preview only — do not write changes", "default": False},
            },
        },
        handler=format_code, category="code",
    )

    registry.register(
        name="FindUsages",
        description=(
            "Find all usages of a symbol (function, class, variable) across the codebase. "
            "Groups results by definition, import, call, and assignment."
        ),
        parameters={
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "Symbol name to find"},
                "path":     {"type": "string", "description": "Root directory to search", "default": "."},
                "language": {"type": "string", "description": "Language filter (py/js/ts/go — empty = all)", "default": ""},
            },
            "required": ["symbol"],
        },
        handler=find_usages, category="code",
    )

    registry.register(
        name="RefactorRename",
        description=(
            "Rename a symbol across all matching files using word-boundary replacement. "
            "Previews changes by default (dry_run=true). Set dry_run=false to apply."
        ),
        parameters={
            "type": "object",
            "properties": {
                "old_name":     {"type": "string",  "description": "Current symbol name"},
                "new_name":     {"type": "string",  "description": "New symbol name"},
                "path":         {"type": "string",  "description": "Root directory", "default": "."},
                "dry_run":      {"type": "boolean", "description": "Preview only (default: true)", "default": True},
                "file_pattern": {"type": "string",  "description": "Glob pattern for files to modify", "default": "*.py"},
            },
            "required": ["old_name", "new_name"],
        },
        handler=refactor_rename, category="code",
    )

    registry.register(
        name="AnalyzeCode",
        description=(
            "Analyze a Python file or directory using AST: count functions/classes/imports, "
            "find TODOs, detect potential issues (bare excepts, missing docstrings)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File or directory to analyze"},
            },
            "required": ["path"],
        },
        handler=analyze_code, category="code",
    )

    registry.register(
        name="CheckDeps",
        description=(
            "Check whether project dependencies (requirements.txt / pyproject.toml) "
            "are installed and report any missing packages."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Project root directory", "default": "."},
            },
        },
        handler=check_deps, category="code",
    )
