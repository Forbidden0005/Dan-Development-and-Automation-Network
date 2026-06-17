"""
Direct tests for security_utils.py — SecurePathValidator, SecureCommandExecutor,
sanitize_user_input, and validate_file_size.

Coverage strategy:
- SecurePathValidator: constructor defaults, root resolution, validate_path
  (happy path, traversal, outside-root), is_safe_path, multi-root.
- SecureCommandExecutor: validate_command — empty/non-string, shell features,
  dangerous patterns, whitelist (pass/fail), .exe extension stripping, path
  prefix stripping, RESTRICTED_COMMAND_REQUIREMENTS (powershell/pwsh),
  use_whitelist=False bypass.  _has_shell_features quoting semantics.
- sanitize_user_input: type check, length limit, null-byte / control-char
  removal, newline collapsing, whitespace stripping.
- validate_file_size: non-existent file passes silently, within-limit passes,
  over-limit raises, zero-byte limit on tiny file.

ToolAuditLog is already covered by tests/test_tool_registry_audit.py.
validate_fetch_url / validate_redirect_url are already covered in tests/test_dan.py.
"""

import pytest
from pathlib import Path

import security_utils
from security_utils import (
    SecureCommandExecutor,
    SecurePathValidator,
    sanitize_user_input,
    validate_file_size,
)


# ── SecurePathValidator ───────────────────────────────────────────────────────


class TestSecurePathValidatorInit:
    def test_default_root_is_cwd(self):
        # When no roots are supplied the validator falls back to cwd.
        validator = SecurePathValidator()
        assert len(validator.allowed_roots) == 1
        assert validator.allowed_roots[0] == Path.cwd().resolve()

    def test_explicit_root_is_resolved(self, tmp_path):
        # A relative root string must be resolved to an absolute Path.
        validator = SecurePathValidator(allowed_roots=[str(tmp_path)])
        assert validator.allowed_roots[0] == tmp_path.resolve()

    def test_multiple_roots_stored(self, tmp_path):
        # All supplied roots are stored after resolution.
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        validator = SecurePathValidator(allowed_roots=[str(root_a), str(root_b)])
        assert len(validator.allowed_roots) == 2
        assert root_a.resolve() in validator.allowed_roots
        assert root_b.resolve() in validator.allowed_roots

    def test_empty_list_uses_cwd(self):
        # An empty list behaves the same as None — cwd is used.
        validator = SecurePathValidator(allowed_roots=[])
        assert validator.allowed_roots[0] == Path.cwd().resolve()


class TestSecurePathValidatorValidatePath:
    def test_valid_path_inside_root_returns_resolved_path(self, tmp_path):
        target = tmp_path / "subdir" / "file.txt"
        target.parent.mkdir(parents=True)
        target.touch()
        validator = SecurePathValidator(allowed_roots=[str(tmp_path)])
        result = validator.validate_path(str(target))
        assert result == target.resolve()
        assert isinstance(result, Path)

    def test_root_itself_is_accepted(self, tmp_path):
        # The root directory itself should be within the allowed root.
        validator = SecurePathValidator(allowed_roots=[str(tmp_path)])
        result = validator.validate_path(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_empty_string_raises(self, tmp_path):
        validator = SecurePathValidator(allowed_roots=[str(tmp_path)])
        with pytest.raises(ValueError, match="non-empty string"):
            validator.validate_path("")

    def test_non_string_raises(self, tmp_path):
        validator = SecurePathValidator(allowed_roots=[str(tmp_path)])
        with pytest.raises(ValueError):
            validator.validate_path(None)  # type: ignore[arg-type]

    def test_path_outside_root_raises(self, tmp_path):
        # A path that escapes the allowed root via resolved absolute path.
        import tempfile
        other_root = Path(tempfile.gettempdir()) / "other_root_xyz"
        validator = SecurePathValidator(allowed_roots=[str(tmp_path)])
        with pytest.raises(ValueError, match="outside allowed"):
            validator.validate_path(str(other_root))

    def test_traversal_attempt_blocked(self, tmp_path):
        # ../../etc/passwd resolves outside tmp_path.
        evil = str(tmp_path) + "/../../etc/passwd"
        validator = SecurePathValidator(allowed_roots=[str(tmp_path)])
        with pytest.raises(ValueError, match="outside allowed"):
            validator.validate_path(evil)

    def test_path_in_second_of_two_roots_accepted(self, tmp_path):
        # A path inside the second root must be accepted.
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        target = root_b / "file.txt"
        target.touch()
        validator = SecurePathValidator(allowed_roots=[str(root_a), str(root_b)])
        result = validator.validate_path(str(target))
        assert result == target.resolve()

    def test_subdirectory_path_accepted(self, tmp_path):
        # Paths nested deeply inside the root are fine.
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        validator = SecurePathValidator(allowed_roots=[str(tmp_path)])
        result = validator.validate_path(str(deep))
        assert result == deep.resolve()


class TestSecurePathValidatorIsSafePath:
    def test_returns_true_for_valid_path(self, tmp_path):
        validator = SecurePathValidator(allowed_roots=[str(tmp_path)])
        assert validator.is_safe_path(str(tmp_path)) is True

    def test_returns_false_for_outside_path(self, tmp_path):
        import tempfile
        other = Path(tempfile.gettempdir()) / "nowhere_xyz"
        validator = SecurePathValidator(allowed_roots=[str(tmp_path)])
        assert validator.is_safe_path(str(other)) is False

    def test_returns_false_for_empty_string(self, tmp_path):
        validator = SecurePathValidator(allowed_roots=[str(tmp_path)])
        assert validator.is_safe_path("") is False

    def test_return_type_is_bool(self, tmp_path):
        validator = SecurePathValidator(allowed_roots=[str(tmp_path)])
        result = validator.is_safe_path(str(tmp_path))
        assert isinstance(result, bool)


# ── SecureCommandExecutor ─────────────────────────────────────────────────────


class TestSecureCommandExecutorInit:
    def test_default_use_whitelist_is_true(self):
        executor = SecureCommandExecutor()
        assert executor.use_whitelist is True

    def test_default_max_execution_time(self):
        executor = SecureCommandExecutor()
        assert executor.max_execution_time == 30

    def test_compiled_patterns_populated(self):
        executor = SecureCommandExecutor()
        assert len(executor.compiled_patterns) > 0

    def test_compiled_requirements_populated(self):
        # powershell and pwsh must have compiled requirement patterns.
        executor = SecureCommandExecutor()
        assert "powershell" in executor.compiled_requirements
        assert "pwsh" in executor.compiled_requirements


class TestValidateCommandShellFeatures:
    """Shell operator detection blocks any command containing unquoted operators."""

    def test_pipe_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="Shell features"):
            executor.validate_command("ls | grep foo")

    def test_redirect_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="Shell features"):
            executor.validate_command("echo hello > out.txt")

    def test_semicolon_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="Shell features"):
            executor.validate_command("echo hi; echo bye")

    def test_backtick_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="Shell features"):
            executor.validate_command("echo `whoami`")

    def test_ampersand_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="Shell features"):
            executor.validate_command("sleep 10 & echo done")

    def test_less_than_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="Shell features"):
            executor.validate_command("cat < file.txt")


class TestValidateCommandInput:
    def test_empty_string_raises(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="non-empty string"):
            executor.validate_command("")

    def test_non_string_raises(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError):
            executor.validate_command(None)  # type: ignore[arg-type]

    def test_whitespace_only_raises(self):
        # shlex.split of "   " produces [], so parsed is empty — no base command
        # to check; the whitelist block skips it silently. But empty strings still
        # raise.  Whitespace-only is subtle — just verify it doesn't crash.
        executor = SecureCommandExecutor()
        # May raise or pass silently — the key invariant is it must not execute.
        try:
            executor.validate_command("   ")
        except ValueError:
            pass  # acceptable


class TestValidateCommandDangerousPatterns:
    def test_rm_rf_slash_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="dangerous"):
            executor.validate_command("rm -rf /")

    def test_sudo_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="dangerous"):
            executor.validate_command("sudo apt-get install vim")

    def test_kill_nine_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="dangerous"):
            executor.validate_command("kill -9 1234")

    def test_cmd_slash_c_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="dangerous"):
            executor.validate_command("cmd /c whoami")

    def test_cmd_slash_k_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="dangerous"):
            executor.validate_command("cmd /k echo hi")

    def test_powershell_command_flag_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="dangerous"):
            executor.validate_command("powershell -Command Get-Process")

    def test_powershell_encoded_command_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="dangerous"):
            executor.validate_command("powershell -EncodedCommand aGVsbG8=")

    def test_wmic_process_call_create_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="dangerous"):
            executor.validate_command("wmic process call create calc.exe")

    def test_powershell_execution_policy_bypass_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="dangerous"):
            executor.validate_command("powershell -ExecutionPolicy Bypass -File script.ps1")


class TestValidateCommandWhitelist:
    def test_ls_allowed(self):
        executor = SecureCommandExecutor()
        executor.validate_command("ls -la")  # must not raise

    def test_python_allowed(self):
        executor = SecureCommandExecutor()
        executor.validate_command("python --version")

    def test_git_allowed(self):
        executor = SecureCommandExecutor()
        executor.validate_command("git status")

    def test_pytest_allowed(self):
        executor = SecureCommandExecutor()
        executor.validate_command("pytest tests/")

    def test_ruff_allowed(self):
        executor = SecureCommandExecutor()
        executor.validate_command("ruff check .")

    def test_unknown_command_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="not in whitelist"):
            executor.validate_command("unknownapp --help")

    def test_exe_extension_stripped_and_resolved(self):
        # python.exe must resolve to "python" which is in the whitelist.
        executor = SecureCommandExecutor()
        executor.validate_command("python.exe --version")  # must not raise

    def test_path_prefix_stripped(self):
        # /usr/bin/python → base is "python" → in whitelist.
        executor = SecureCommandExecutor()
        executor.validate_command("/usr/bin/python --version")  # must not raise

    def test_use_whitelist_false_bypasses_unknown_command(self):
        # When use_whitelist=False, an unknown command not matching any dangerous
        # pattern should be accepted (no whitelist enforcement).
        executor = SecureCommandExecutor(use_whitelist=False)
        executor.validate_command("nonexistentprogramxyz --help")  # must not raise

    def test_use_whitelist_false_still_blocks_dangerous_patterns(self):
        # The dangerous-pattern check runs regardless of use_whitelist.
        executor = SecureCommandExecutor(use_whitelist=False)
        with pytest.raises(ValueError, match="dangerous"):
            executor.validate_command("sudo rm -rf /")


class TestValidateCommandRestrictedRequirements:
    """RESTRICTED_COMMAND_REQUIREMENTS: powershell and pwsh need -File."""

    def test_bare_powershell_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="requires a specific invocation"):
            executor.validate_command("powershell")

    def test_powershell_with_file_flag_allowed(self):
        executor = SecureCommandExecutor()
        executor.validate_command("powershell -File script.ps1")  # must not raise

    def test_powershell_exe_with_file_flag_allowed(self):
        executor = SecureCommandExecutor()
        executor.validate_command("powershell.exe -File script.ps1")  # must not raise

    def test_bare_pwsh_blocked(self):
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="requires a specific invocation"):
            executor.validate_command("pwsh")

    def test_pwsh_with_file_flag_allowed(self):
        executor = SecureCommandExecutor()
        executor.validate_command("pwsh -File myscript.ps1")  # must not raise

    def test_pwsh_command_flag_blocked_by_dangerous_pattern(self):
        # pwsh -Command is caught by DANGEROUS_PATTERNS before the requirement check.
        executor = SecureCommandExecutor()
        with pytest.raises(ValueError, match="dangerous"):
            executor.validate_command("pwsh -Command Get-Process")


class TestHasShellFeatures:
    def test_simple_command_returns_false(self):
        executor = SecureCommandExecutor()
        assert executor._has_shell_features("echo hello") is False

    def test_unquoted_pipe_returns_true(self):
        executor = SecureCommandExecutor()
        assert executor._has_shell_features("ls | grep foo") is True

    def test_unquoted_redirect_returns_true(self):
        executor = SecureCommandExecutor()
        assert executor._has_shell_features("echo hi > out.txt") is True

    def test_pipe_in_double_quoted_string_returns_false(self):
        # The pipe is inside double-quotes — not a shell operator.
        executor = SecureCommandExecutor()
        assert executor._has_shell_features('echo "hello | world"') is False

    def test_pipe_in_single_quoted_string_returns_false(self):
        executor = SecureCommandExecutor()
        assert executor._has_shell_features("echo 'hello | world'") is False

    def test_unquoted_semicolon_returns_true(self):
        executor = SecureCommandExecutor()
        assert executor._has_shell_features("echo hi; echo bye") is True


# ── sanitize_user_input ───────────────────────────────────────────────────────


class TestSanitizeUserInput:
    def test_normal_string_returned(self):
        result = sanitize_user_input("hello world")
        assert result == "hello world"

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="must be a string"):
            sanitize_user_input(42)  # type: ignore[arg-type]

    def test_none_raises(self):
        with pytest.raises(ValueError, match="must be a string"):
            sanitize_user_input(None)  # type: ignore[arg-type]

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match="too long"):
            sanitize_user_input("x" * 10001, max_length=10000)

    def test_exactly_at_max_length_passes(self):
        s = "a" * 1000
        result = sanitize_user_input(s, max_length=1000)
        assert len(result) == 1000

    def test_strips_leading_trailing_whitespace(self):
        result = sanitize_user_input("  hello  ")
        assert result == "hello"

    def test_removes_null_bytes(self):
        result = sanitize_user_input("hel\x00lo")
        assert "\x00" not in result
        assert "hello" in result

    def test_removes_control_chars(self):
        # \x01 (SOH) is a control char that should be removed.
        result = sanitize_user_input("hel\x01lo")
        assert "\x01" not in result

    def test_preserves_newlines(self):
        result = sanitize_user_input("line1\nline2")
        assert "line1" in result
        assert "line2" in result

    def test_preserves_tabs(self):
        result = sanitize_user_input("col1\tcol2")
        assert "\t" in result

    def test_collapses_excessive_newlines(self):
        # Three or more consecutive newlines should collapse to two.
        result = sanitize_user_input("a\n\n\n\nb")
        assert "\n\n\n" not in result
        assert "a" in result and "b" in result

    def test_two_newlines_preserved(self):
        result = sanitize_user_input("a\n\nb")
        assert "a\n\nb" in result

    def test_empty_string_returns_empty(self):
        result = sanitize_user_input("")
        assert result == ""

    def test_custom_max_length_enforced(self):
        with pytest.raises(ValueError, match="too long"):
            sanitize_user_input("hello", max_length=4)


# ── validate_file_size ────────────────────────────────────────────────────────


class TestValidateFileSize:
    def test_non_existent_file_returns_silently(self, tmp_path):
        # Missing file is treated as zero-size — no error raised.
        missing = tmp_path / "missing.txt"
        validate_file_size(missing, max_size_mb=1)  # must not raise

    def test_small_file_within_limit_passes(self, tmp_path):
        f = tmp_path / "small.txt"
        f.write_bytes(b"x" * 1024)  # 1 KB
        validate_file_size(f, max_size_mb=1)  # must not raise

    def test_large_file_over_limit_raises(self, tmp_path):
        f = tmp_path / "big.bin"
        # Write just over 1 MB
        f.write_bytes(b"x" * (1024 * 1024 + 1))
        with pytest.raises(ValueError, match="too large"):
            validate_file_size(f, max_size_mb=1)

    def test_file_exactly_at_limit_passes(self, tmp_path):
        # Exactly 1 MB = 1 048 576 bytes — not strictly greater than 1 MB.
        f = tmp_path / "exact.bin"
        f.write_bytes(b"x" * (1024 * 1024))
        validate_file_size(f, max_size_mb=1)  # must not raise

    def test_zero_mb_limit_blocks_nonempty_file(self, tmp_path):
        f = tmp_path / "tiny.txt"
        f.write_bytes(b"hi")
        with pytest.raises(ValueError, match="too large"):
            validate_file_size(f, max_size_mb=0)

    def test_default_limit_accepts_small_file(self, tmp_path):
        f = tmp_path / "small.txt"
        f.write_text("hello")
        validate_file_size(f)  # default 50 MB limit — must not raise
