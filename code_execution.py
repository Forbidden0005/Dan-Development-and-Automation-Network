"""
code_execution.py - Structured code execution loop for Dan.

Tools:
  RunCode     - execute a code snippet in any language, return structured result
  RunFile     - run a source file with auto-detected interpreter
  TestLoop    - run tests, show failures clearly, designed for fix cycles
  IterateFix  - run a command, loop until success or max tries reached

The IterateFix pattern (run -> error -> Dan edits -> run -> ...) emerges naturally
when Dan has clear, actionable error output from these tools.
"""

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import tool_registry as registry
from security_utils import SecureCommandExecutor, SecurePathValidator, sanitize_user_input

_MAX_TIMEOUT_SECONDS = 120
_MAX_SNIPPET_CHARS = 200_000
_MAX_STDIN_CHARS = 1_000_000
_MAX_ARGS_CHARS = 2_000

_path_validator = SecurePathValidator()
_command_validator = SecureCommandExecutor(
    use_whitelist=True,
    max_execution_time=_MAX_TIMEOUT_SECONDS,
)
_PYTHON_CANDIDATES = ("python", "py")

# -- Language detection --------------------------------------------------------

# Maps extension -> (interpreter_cmd, file_extension_for_tempfile)
_INTERPRETERS: dict[str, tuple[list[str], str]] = {
    "python":     (["python"],              ".py"),
    "py":         (["python"],              ".py"),
    "javascript": (["node"],                ".js"),
    "js":         (["node"],                ".js"),
    "typescript": (["npx", "ts-node"],      ".ts"),
    "ts":         (["npx", "ts-node"],      ".ts"),
    "go":         (["go", "run"],           ".go"),
    "rust":       (None,                    ".rs"),   # needs compile step
    "bash":       (["bash"],                ".sh"),
    "shell":      (["bash"],                ".sh"),
    "sh":         (["bash"],                ".sh"),
    "powershell": (["powershell", "-File"], ".ps1"),
    "ps1":        (["powershell", "-File"], ".ps1"),
    "ruby":       (["ruby"],                ".rb"),
    "rb":         (["ruby"],                ".rb"),
    "php":        (["php"],                 ".php"),
    "lua":        (["lua"],                 ".lua"),
    "perl":       (["perl"],                ".pl"),
}

_EXT_TO_LANG: dict[str, str] = {
    ".py":   "python",   ".pyw":  "python",
    ".js":   "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts":   "typescript", ".mts": "typescript",
    ".go":   "go",
    ".rs":   "rust",
    ".sh":   "bash",     ".bash": "bash",    ".zsh": "bash",
    ".rb":   "ruby",
    ".php":  "php",
    ".lua":  "lua",
    ".pl":   "perl",
    ".ps1":  "powershell",
}

_TEST_RUNNERS: dict[str, list[str]] = {
    "python": ["python", "-m", "pytest", "--tb=short", "-v"],
    "javascript": ["npm", "test"],
    "typescript": ["npm", "test"],
    "go":         ["go", "test", "./..."],
    "rust":       ["cargo", "test"],
}


def _detect_lang_from_ext(path: Path) -> str:
    return _EXT_TO_LANG.get(path.suffix.lower(), "")


def _detect_lang_from_shebang(content: str) -> str:
    first = content.split("\n")[0].strip()
    if "python" in first: return "python"
    if "node"   in first: return "javascript"
    if "bash"   in first or "sh" in first: return "bash"
    if "ruby"   in first: return "ruby"
    if "php"    in first: return "php"
    return ""


def _bounded_timeout(timeout: int, default: int = 30) -> int:
    """Clamp user-provided timeouts to a production-safe range."""
    try:
        value = int(timeout)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, _MAX_TIMEOUT_SECONDS))


def _validate_text_size(label: str, value: str, max_chars: int) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    if len(value) > max_chars:
        raise ValueError(f"{label} is too large: {len(value)} > {max_chars} chars")


def _safe_path(path: str) -> Path:
    path = sanitize_user_input(path, max_length=500)
    return _path_validator.validate_path(path)


def _split_args(args: str) -> list[str]:
    if args is None:
        return []
    if not isinstance(args, str):
        raise ValueError("args must be a string")
    if not args.strip():
        return []
    args = sanitize_user_input(args, max_length=_MAX_ARGS_CHARS)
    try:
        return shlex.split(args, posix=os.name != "nt")
    except ValueError as e:
        raise ValueError(f"Invalid arguments: {e}") from e


def _command_to_string(cmd: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)


def _validate_process_command(cmd: list[str]) -> None:
    _command_validator.validate_command(_command_to_string(cmd))


def _resolve_python_command() -> list[str]:
    """Prefer python on PATH, but fall back to the Windows launcher when needed."""
    for candidate in _PYTHON_CANDIDATES:
        if shutil.which(candidate):
            return [candidate]
    return ["python"]


def _resolve_interpreter_command(command: list[str] | None) -> list[str] | None:
    if command is None or not command:
        return command
    if command[0] == "python":
        return _resolve_python_command() + command[1:]
    return command


def _run_proc(cmd: list[str], cwd: str | None = None,
              stdin_text: str = "", timeout: int = 30,
              validate_command: bool = True) -> tuple[int, str, str, float]:
    """Run a subprocess. Returns (returncode, stdout, stderr, elapsed_seconds)."""
    t0 = time.perf_counter()
    try:
        timeout = _bounded_timeout(timeout)
        if validate_command:
            _validate_process_command(cmd)
        r = subprocess.run(
            cmd, cwd=cwd or os.getcwd(),
            input=stdin_text or None,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        return r.returncode, r.stdout, r.stderr, time.perf_counter() - t0
    except ValueError as e:
        return 1, "", f"Blocked command: {e}", time.perf_counter() - t0
    except subprocess.TimeoutExpired:
        return 1, "", f"Timed out after {timeout}s", time.perf_counter() - t0
    except FileNotFoundError:
        return 1, "", f"Interpreter not found: {cmd[0]}", time.perf_counter() - t0
    except Exception as e:
        return 1, "", str(e), time.perf_counter() - t0


def _format_result(code: int, stdout: str, stderr: str,
                   elapsed: float, label: str = "") -> str:
    """Build a clear, actionable result string."""
    icon    = "OK" if code == 0 else "FAIL"
    header  = f"{icon} Exit {code}  [{elapsed:.2f}s]"
    if label:
        header = f"{label}  -  {header}"

    parts = [header]

    if stdout.strip():
        out = stdout.strip()
        if len(out) > 4000:
            out = out[:2000] + f"\n... ({len(out)-2000} chars truncated) ...\n" + out[-500:]
        parts.append(f"\n== STDOUT ==\n{out}")

    if stderr.strip():
        err = stderr.strip()
        if len(err) > 3000:
            err = err[:1500] + f"\n... ({len(err)-1500} chars truncated) ...\n" + err[-500:]
        parts.append(f"\n== STDERR ==\n{err}")

    if code != 0 and not stdout.strip() and not stderr.strip():
        parts.append("\n(No output - process exited non-zero with no messages)")

    return "\n".join(parts)


# -- Tool: RunCode -------------------------------------------------------------

def run_code(code: str, language: str = "python",
             stdin: str = "", timeout: int = 30) -> str:
    """
    Execute a code snippet and return the result.
    Writes to a temp file, runs with the appropriate interpreter, cleans up.
    """
    try:
        _validate_text_size("code", code, _MAX_SNIPPET_CHARS)
        _validate_text_size("stdin", stdin, _MAX_STDIN_CHARS)
        language = sanitize_user_input(language, max_length=40)
        timeout = _bounded_timeout(timeout)
    except ValueError as e:
        return f"Security error: {e}"

    lang = language.lower().strip()
    entry = _INTERPRETERS.get(lang)
    if not entry:
        supported = ", ".join(sorted(_INTERPRETERS))
        return f"Error: unsupported language '{language}'.\nSupported: {supported}"

    interp, ext = entry

    # Rust needs a compile step - wrap in cargo project
    if lang == "rust":
        return _run_rust_snippet(code, timeout)

    # Write to temp file
    with tempfile.NamedTemporaryFile(suffix=ext, mode="w",
                                     encoding="utf-8", delete=False) as f:
        f.write(code)
        tmp_path = f.name

    try:
        interp = _resolve_interpreter_command(interp)
        cmd = interp + [tmp_path]
        code_r, stdout, stderr, elapsed = _run_proc(cmd, stdin_text=stdin,
                                                     timeout=timeout)
        return _format_result(code_r, stdout, stderr, elapsed,
                               label=f"RunCode [{language}]")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _run_rust_snippet(code: str, timeout: int) -> str:
    """Compile and run a Rust snippet via rustc."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "snippet.rs"
        out = Path(tmp) / "snippet"
        src.write_text(code, encoding="utf-8")

        # Compile
        cc, cout, cerr, cel = _run_proc(
            ["rustc", str(src), "-o", str(out)], timeout=timeout)
        if cc != 0:
            return _format_result(cc, cout, cerr, cel, label="RunCode [rust/compile]")

        # Run
        rc, rout, rerr, rel = _run_proc([str(out)], timeout=timeout,
                                         validate_command=False)
        return _format_result(rc, rout, rerr, rel, label="RunCode [rust/run]")


# -- Tool: RunFile -------------------------------------------------------------

def run_file(path: str, args: str = "", stdin: str = "", timeout: int = 30) -> str:
    """
    Run a source file with its auto-detected interpreter.
    Supports Python, JavaScript, TypeScript, Go, Rust, Bash, Ruby, PHP.
    """
    try:
        p = _safe_path(path)
        extra_args = _split_args(args)
        _validate_text_size("stdin", stdin, _MAX_STDIN_CHARS)
        timeout = _bounded_timeout(timeout)
    except ValueError as e:
        return f"Security error: {e}"

    if not p.exists():
        return f"Error: file not found: {path}"
    if not p.is_file():
        return f"Error: not a file: {path}"

    # Detect language
    lang = _detect_lang_from_ext(p)
    if not lang:
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            lang = _detect_lang_from_shebang(content)
        except Exception:
            pass
    if not lang:
        return f"Error: cannot detect language for {p.name}. Use RunCode with explicit language."

    entry = _INTERPRETERS.get(lang)
    if not entry:
        return f"Error: no interpreter configured for {lang}."

    interp, _ = entry
    if lang == "rust":
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading file: {e}"
        return _run_rust_snippet(content, timeout)

    if lang == "go":
        # `go run` needs the file directly
        cmd = ["go", "run", str(p)] + extra_args
    else:
        interp = _resolve_interpreter_command(interp)
        cmd = interp + [str(p)] + extra_args

    code_r, stdout, stderr, elapsed = _run_proc(
        cmd, cwd=str(p.parent), stdin_text=stdin, timeout=timeout)

    return _format_result(code_r, stdout, stderr, elapsed,
                          label=f"RunFile [{p.name}]")


# -- Tool: TestLoop ------------------------------------------------------------

def test_loop(path: str = ".", framework: str = "",
              args: str = "", timeout: int = 120) -> str:
    """
    Run the test suite and return a clear, fix-oriented summary.

    Designed for repeated calls - Dan reads failures, edits code, calls again.
    Shows: which tests failed, why they failed, file:line for each failure.
    """
    try:
        root = _safe_path(path)
        extra = _split_args(args)
        timeout = _bounded_timeout(timeout, default=120)
    except ValueError as e:
        return f"Security error: {e}"

    if not root.exists():
        return f"Error: path not found: {path}"
    if not root.is_dir():
        return f"Error: not a directory: {path}"

    # Auto-detect framework
    if not framework:
        framework = _detect_test_framework(root)

    if framework == "pytest":
        return _run_pytest(root, extra, timeout)
    elif framework in ("jest", "vitest", "npm"):
        return _run_npm_test(root, extra, timeout)
    elif framework == "go":
        return _run_go_test(root, extra, timeout)
    elif framework == "rust":
        return _run_cargo_test(root, extra, timeout)
    else:
        return (f"Could not detect test framework in: {root}\n"
                "Supported: pytest, jest, vitest, go test, cargo test\n"
                "Pass framework='pytest' (or other) explicitly.")


def _detect_test_framework(root: Path) -> str:
    if (root / "Cargo.toml").exists():              return "rust"
    if (root / "go.mod").exists():                  return "go"
    if (root / "package.json").exists():
        try:
            pkg = __import__("json").loads((root/"package.json").read_text())
            scripts = pkg.get("scripts", {})
            if "vitest" in str(scripts): return "vitest"
        except Exception: pass
        return "jest"
    # Python - prefer pytest
    for pat in ("pytest.ini", "pyproject.toml", "setup.cfg"):
        if (root / pat).exists(): return "pytest"
    if list(root.rglob("test_*.py")) or list(root.rglob("*_test.py")):
        return "pytest"
    return "pytest"  # best default


def _run_pytest(root: Path, extra: list, timeout: int) -> str:
    cmd = _resolve_python_command() + ["-m", "pytest", "--tb=short", "-v", "--no-header"] + extra + [str(root)]
    rc, out, err, elapsed = _run_proc(cmd, timeout=timeout)
    combined = out + ("\n" + err if err.strip() else "")

    if rc == 0:
        passed = re.search(r"(\d+) passed", combined)
        n = passed.group(1) if passed else "all"
        return f"OK Tests passed  [{elapsed:.1f}s]  ({n} passing)"

    # Parse failures for clear summary
    lines     = combined.splitlines()
    failures  = _parse_pytest_failures(lines)
    summary   = re.search(r"=+ ([\d\w ,]+) =+\s*$", combined, re.MULTILINE)
    sum_line  = summary.group(1).strip() if summary else "tests failed"

    result = [f"FAIL {sum_line}  [{elapsed:.1f}s]", ""]

    if failures:
        result.append(f"FAILURES ({len(failures)}):")
        result.append("-" * 60)
        for fail in failures:
            result.append(fail)
        result.append("-" * 60)

    # Raw output truncated
    raw = combined.strip()
    if len(raw) > 3000:
        raw = raw[:1500] + "\n...(truncated)...\n" + raw[-800:]
    result.append("\nFULL OUTPUT:")
    result.append(raw)
    return "\n".join(result)


def _parse_pytest_failures(lines: list[str]) -> list[str]:
    """Extract individual test failure blocks from pytest --tb=short output."""
    failures = []
    current  = []
    in_fail  = False

    for line in lines:
        if re.match(r"_{5,} .+ _{5,}", line) or re.match(r"FAILED .+", line):
            if current and in_fail:
                failures.append("\n".join(current))
            current = [line]
            in_fail = True
        elif in_fail:
            if re.match(r"={5,}", line):
                if current:
                    failures.append("\n".join(current))
                current  = []
                in_fail  = False
            else:
                current.append(line)

    if current and in_fail:
        failures.append("\n".join(current))

    return [f[:800] for f in failures[:15]]  # cap at 15 failures, 800 chars each


def _run_npm_test(root: Path, extra: list, timeout: int) -> str:
    cmd = ["npm", "test", "--"] + extra
    rc, out, err, elapsed = _run_proc(cmd, cwd=str(root), timeout=timeout)
    combined = (out + "\n" + err).strip()
    icon = "OK" if rc == 0 else "FAIL"
    if len(combined) > 4000:
        combined = combined[:2000] + "\n...(truncated)...\n" + combined[-1000:]
    return f"{icon} npm test  [exit {rc}  {elapsed:.1f}s]\n\n{combined}"


def _run_go_test(root: Path, extra: list, timeout: int) -> str:
    cmd = ["go", "test", "-v", "./..."] + extra
    rc, out, err, elapsed = _run_proc(cmd, cwd=str(root), timeout=timeout)
    combined = (out + "\n" + err).strip()

    if rc == 0:
        passed = len(re.findall(r"^--- PASS:", combined, re.MULTILINE))
        return f"OK Go tests passed  [{elapsed:.1f}s]  ({passed} passing)"

    failed = re.findall(r"^--- FAIL: (\S+)", combined, re.MULTILINE)
    result = [f"FAIL Go tests failed  [exit {rc}  {elapsed:.1f}s]"]
    if failed:
        result.append(f"\nFailed: {', '.join(failed[:20])}")
    if len(combined) > 3000:
        combined = combined[:1500] + "\n...\n" + combined[-800:]
    result.append(f"\n{combined}")
    return "\n".join(result)


def _run_cargo_test(root: Path, extra: list, timeout: int) -> str:
    cmd = ["cargo", "test"] + extra
    rc, out, err, elapsed = _run_proc(cmd, cwd=str(root), timeout=timeout)
    combined = (out + "\n" + err).strip()

    if rc == 0:
        passed = re.search(r"(\d+) passed", combined)
        n = passed.group(1) if passed else "all"
        return f"OK Cargo tests passed  [{elapsed:.1f}s]  ({n} passing)"

    failed = re.findall(r"^test .+ \.\.\. FAILED", combined, re.MULTILINE)
    result = [f"FAIL Cargo tests failed  [exit {rc}  {elapsed:.1f}s]"]
    if failed:
        result.append(f"\nFailed ({len(failed)}): " + ", ".join(
            re.sub(r"^test | \.\.\. FAILED$", "", f) for f in failed[:15]))
    if len(combined) > 3000:
        combined = combined[:1500] + "\n...\n" + combined[-800:]
    result.append(f"\n{combined}")
    return "\n".join(result)


# -- Tool: IterateFix ----------------------------------------------------------

def iterate_fix(command: str, working_dir: str = ".",
                max_tries: int = 5, timeout: int = 60) -> str:
    """
    Run a shell command repeatedly until it succeeds or max_tries is exhausted.

    On each failure, returns the full error output so Dan can fix and call again.
    Dan should: read the error -> edit the relevant file -> call IterateFix again.

    This is the core of the run->fix->run loop.
    """
    try:
        command = sanitize_user_input(command, max_length=2_000)
        root = _safe_path(working_dir)
        if not root.is_dir():
            return f"Error: working_dir is not a directory: {working_dir}"
        _command_validator.validate_command(command)
        cmd = _split_args(command)
        if not cmd:
            return "Error: command cannot be empty."
        try:
            max_tries_value = int(max_tries)
        except (TypeError, ValueError):
            max_tries_value = 5
        max_tries = max(1, min(max_tries_value, 10))
        timeout = _bounded_timeout(timeout, default=60)
    except ValueError as e:
        return f"Security error: {e}"

    results = []
    for attempt in range(1, max_tries + 1):
        rc, stdout, stderr, elapsed = _run_proc(cmd, cwd=str(root), timeout=timeout)

        if rc == 0:
            out = (stdout + stderr).strip()
            return (f"OK Succeeded on attempt {attempt}/{max_tries}  [{elapsed:.2f}s]\n\n"
                    + (out[:2000] if out else "(no output)"))

        # Failed - return error for Dan to act on
        header = (f"FAIL Attempt {attempt}/{max_tries} failed  [exit {rc}  {elapsed:.2f}s]\n"
                  f"Command: {command}\n")
        out    = (stdout + "\n" + stderr).strip()
        if len(out) > 3000:
            out = out[:1500] + "\n...(truncated)...\n" + out[-800:]

        if attempt < max_tries:
            footer = (f"\n\n-----------------------------------------\n"
                      f"Fix the issue above, then call IterateFix again "
                      f"({max_tries - attempt} attempt(s) remaining).")
        else:
            footer = f"\n\nFAIL Max tries ({max_tries}) reached. Could not auto-fix."

        results.append(header + out + footer)

        # Return after each failure so Dan can fix before next call
        return results[-1]

    return results[-1] if results else "No attempts made."


# -- Registration --------------------------------------------------------------

def register_execution_tools() -> None:

    registry.register(
        name="RunCode",
        description=(
            "Execute a code snippet in any language and return stdout/stderr. "
            "Supports: python, javascript, typescript, go, rust, bash, ruby, php, lua."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code":     {"type": "string",  "description": "Source code to execute"},
                "language": {"type": "string",  "description": "Language name (e.g. 'python', 'javascript')", "default": "python"},
                "stdin":    {"type": "string",  "description": "Optional stdin input", "default": ""},
                "timeout":  {"type": "integer", "description": "Max seconds to run", "default": 30},
            },
            "required": ["code"],
        },
        handler=run_code,
        category="execution",
    )

    registry.register(
        name="RunFile",
        description=(
            "Run a source file with its auto-detected interpreter. "
            "Auto-detects Python, JS, TS, Go, Rust, Bash, Ruby, PHP from extension."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path":    {"type": "string",  "description": "Path to the source file"},
                "args":    {"type": "string",  "description": "Command-line arguments", "default": ""},
                "stdin":   {"type": "string",  "description": "Optional stdin input", "default": ""},
                "timeout": {"type": "integer", "description": "Max seconds to run", "default": 30},
            },
            "required": ["path"],
        },
        handler=run_file,
        category="execution",
    )

    registry.register(
        name="TestLoop",
        description=(
            "Run the project test suite (pytest/jest/go test/cargo test) and return "
            "a fix-oriented summary: which tests failed, why, and where. "
            "Call repeatedly after fixing - designed for the fix loop."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path":      {"type": "string", "description": "Project or test directory", "default": "."},
                "framework": {"type": "string", "description": "Test framework (auto-detected if omitted)", "default": ""},
                "args":      {"type": "string", "description": "Extra args passed to the test runner", "default": ""},
                "timeout":   {"type": "integer","description": "Max seconds to run", "default": 120},
            },
        },
        handler=test_loop,
        category="execution",
    )

    registry.register(
        name="IterateFix",
        description=(
            "Run a shell command. If it fails, return the full error so Dan can fix "
            "the code and call again. Tracks attempts toward max_tries. "
            "Use this for: compile errors, script failures, any run->fix->run cycle."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command":     {"type": "string",  "description": "Shell command to run (e.g. 'python main.py')"},
                "working_dir": {"type": "string",  "description": "Working directory", "default": "."},
                "max_tries":   {"type": "integer", "description": "Max fix attempts", "default": 5},
                "timeout":     {"type": "integer", "description": "Seconds per attempt", "default": 60},
            },
            "required": ["command"],
        },
        handler=iterate_fix,
        category="execution",
    )
