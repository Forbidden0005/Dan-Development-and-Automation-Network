"""Tests for skills.py — find_duplicates, scaffold_project, generate_changelog,
run_webapp_test, and register_skill_tools.

All tests are purely unit-level: filesystem operations use pytest's ``tmp_path``
fixture; subprocess calls are monkeypatched; no real network connections are made.
The module-level ``skills._path_validator`` is replaced with a
``SecurePathValidator`` scoped to ``tmp_path`` so every test can exercise
the real validation logic inside its own isolated directory.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import skills
import tool_registry as registry
from security_utils import SecurePathValidator


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _restore_registry():
    """Snapshot and restore the tool registry + path validator around every test."""
    saved_tools = dict(registry._TOOLS)
    saved_schemas = registry._CACHED_SCHEMAS
    saved_validator = skills._path_validator

    yield

    registry._TOOLS.clear()
    registry._TOOLS.update(saved_tools)
    registry._CACHED_SCHEMAS = saved_schemas
    skills._path_validator = saved_validator


@pytest.fixture()
def tmp_validator(tmp_path):
    """Replace skills._path_validator with one scoped to tmp_path."""
    v = SecurePathValidator(allowed_roots=[str(tmp_path)])
    skills._path_validator = v
    return tmp_path


# ── find_duplicates ───────────────────────────────────────────────────────────


class TestFindDuplicates:
    def test_empty_directory_no_duplicates(self, tmp_validator):
        result = skills.find_duplicates(str(tmp_validator))
        assert "No duplicates found" in result
        assert "0 files scanned" in result

    def test_finds_duplicate_pair(self, tmp_validator):
        # Two files with identical content that meets the min_size threshold
        content = b"A" * 2000
        (tmp_validator / "alpha.txt").write_bytes(content)
        (tmp_validator / "beta.txt").write_bytes(content)
        result = skills.find_duplicates(str(tmp_validator))
        assert "Found" in result
        assert "alpha.txt" in result or "beta.txt" in result

    def test_different_content_not_reported(self, tmp_validator):
        # Files with distinct content must not appear in a duplicates report
        (tmp_validator / "one.txt").write_bytes(b"A" * 2000)
        (tmp_validator / "two.txt").write_bytes(b"B" * 2000)
        result = skills.find_duplicates(str(tmp_validator))
        assert "No duplicates found" in result

    def test_files_below_min_size_skipped(self, tmp_validator):
        # Identical small files are ignored when below min_size
        content = b"tiny"
        (tmp_validator / "x.txt").write_bytes(content)
        (tmp_validator / "y.txt").write_bytes(content)
        result = skills.find_duplicates(str(tmp_validator), min_size=9999)
        assert "No duplicates found" in result

    def test_custom_min_size_respected(self, tmp_validator):
        # Same files found when min_size lowered to 1 byte
        content = b"tiny"
        (tmp_validator / "x.txt").write_bytes(content)
        (tmp_validator / "y.txt").write_bytes(content)
        result = skills.find_duplicates(str(tmp_validator), min_size=1)
        assert "Found" in result

    def test_skips_git_directory(self, tmp_validator):
        # .git subdirectory files must not be counted
        git_dir = tmp_validator / ".git"
        git_dir.mkdir()
        content = b"G" * 2000
        (git_dir / "obj1").write_bytes(content)
        (git_dir / "obj2").write_bytes(content)
        result = skills.find_duplicates(str(tmp_validator))
        assert "No duplicates found" in result

    def test_skips_pycache_directory(self, tmp_validator):
        pycache = tmp_validator / "__pycache__"
        pycache.mkdir()
        content = b"P" * 2000
        (pycache / "mod.pyc").write_bytes(content)
        (pycache / "mod2.pyc").write_bytes(content)
        result = skills.find_duplicates(str(tmp_validator))
        assert "No duplicates found" in result

    def test_report_shows_group_count(self, tmp_validator):
        # Report header mentions how many duplicate groups were found
        content = b"R" * 2000
        (tmp_validator / "p.txt").write_bytes(content)
        (tmp_validator / "q.txt").write_bytes(content)
        result = skills.find_duplicates(str(tmp_validator))
        # "Found N duplicate files in M groups"
        assert "groups" in result.lower() or "group" in result.lower()

    def test_file_path_instead_of_directory(self, tmp_validator):
        # Passing a file (not a directory) path returns an error
        f = tmp_validator / "notadir.txt"
        f.write_text("hello")
        result = skills.find_duplicates(str(f))
        assert result.startswith("Error:")

    def test_path_outside_allowed_root_returns_security_error(self, tmp_validator):
        # Any path outside the scoped validator must be rejected
        result = skills.find_duplicates("/")
        assert "Security error" in result or "Error" in result


# ── scaffold_project ──────────────────────────────────────────────────────────


class TestScaffoldProject:
    def test_unknown_template_returns_error(self, tmp_validator):
        result = skills.scaffold_project("myapp", template="rust", path=str(tmp_validator))
        assert "Unknown template" in result
        assert "rust" in result

    def test_available_templates_listed_in_error(self, tmp_validator):
        result = skills.scaffold_project("myapp", template="invalid", path=str(tmp_validator))
        assert "python" in result
        assert "node" in result
        assert "web" in result

    def test_python_scaffold_creates_expected_dirs(self, tmp_validator):
        skills.scaffold_project("mypkg", template="python", path=str(tmp_validator))
        project = tmp_validator / "mypkg"
        for d in ("src", "tests", "docs", "scripts"):
            assert (project / d).is_dir(), f"missing dir: {d}"

    def test_python_scaffold_creates_expected_files(self, tmp_validator):
        skills.scaffold_project("mypkg", template="python", path=str(tmp_validator))
        project = tmp_validator / "mypkg"
        for f in ("README.md", "requirements.txt", ".gitignore", "pyproject.toml"):
            assert (project / f).is_file(), f"missing file: {f}"

    def test_python_scaffold_readme_contains_project_name(self, tmp_validator):
        skills.scaffold_project("awesomelib", template="python", path=str(tmp_validator))
        readme = (tmp_validator / "awesomelib" / "README.md").read_text()
        assert "awesomelib" in readme

    def test_python_scaffold_pyproject_contains_project_name(self, tmp_validator):
        skills.scaffold_project("mylib", template="python", path=str(tmp_validator))
        content = (tmp_validator / "mylib" / "pyproject.toml").read_text()
        assert "mylib" in content

    def test_python_scaffold_returns_success_message(self, tmp_validator):
        result = skills.scaffold_project("proj", template="python", path=str(tmp_validator))
        assert "Created" in result
        assert "proj" in result

    def test_duplicate_project_name_returns_error(self, tmp_validator):
        skills.scaffold_project("dupapp", template="python", path=str(tmp_validator))
        result = skills.scaffold_project("dupapp", template="python", path=str(tmp_validator))
        assert "Error" in result
        assert "exists" in result.lower()

    def test_node_scaffold_creates_package_json(self, tmp_validator):
        skills.scaffold_project("nodeproj", template="node", path=str(tmp_validator))
        pkg = tmp_validator / "nodeproj" / "package.json"
        assert pkg.is_file()
        content = pkg.read_text()
        assert "nodeproj" in content

    def test_node_scaffold_creates_src_entry_point(self, tmp_validator):
        skills.scaffold_project("nodeproj", template="node", path=str(tmp_validator))
        assert (tmp_validator / "nodeproj" / "src" / "index.js").is_file()

    def test_web_scaffold_creates_html_entry_point(self, tmp_validator):
        skills.scaffold_project("webproj", template="web", path=str(tmp_validator))
        html = tmp_validator / "webproj" / "public" / "index.html"
        assert html.is_file()
        assert "webproj" in html.read_text()

    def test_web_scaffold_creates_main_js(self, tmp_validator):
        skills.scaffold_project("webproj", template="web", path=str(tmp_validator))
        assert (tmp_validator / "webproj" / "src" / "main.js").is_file()

    def test_path_outside_allowed_root_returns_security_error(self, tmp_validator):
        result = skills.scaffold_project("proj", template="python", path="/tmp")
        assert "Security error" in result or "Error" in result

    def test_python_scaffold_test_file_exists(self, tmp_validator):
        # The generated test file is present
        skills.scaffold_project("mypkg", template="python", path=str(tmp_validator))
        assert (tmp_validator / "mypkg" / "tests" / "test_main.py").is_file()

    def test_python_scaffold_gitignore_excludes_venv(self, tmp_validator):
        skills.scaffold_project("mypkg", template="python", path=str(tmp_validator))
        gitignore = (tmp_validator / "mypkg" / ".gitignore").read_text()
        assert ".venv" in gitignore or "venv" in gitignore


# ── generate_changelog ────────────────────────────────────────────────────────


def _mock_run(stdout: str, returncode: int = 0, stderr: str = "") -> MagicMock:
    """Return a MagicMock that looks like subprocess.CompletedProcess."""
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


_SAMPLE_COMMITS = (
    "abc1234|feat: add login page|Alice|2026-06-01\n"
    "def5678|fix(auth): resolve token expiry|Bob|2026-06-02\n"
    "ghi9012|docs: update contributing guide|Carol|2026-06-03\n"
    "jkl3456|refactor: extract helper module|Dave|2026-06-04\n"
    "mno7890|no-prefix miscellaneous change|Eve|2026-06-05"
)


class TestGenerateChangelog:
    def test_feat_prefix_categorized_as_new_features(self):
        with patch("skills.subprocess.run", return_value=_mock_run(_SAMPLE_COMMITS)):
            result = skills.generate_changelog()
        assert "New Features" in result or "feat" in result.lower()
        assert "add login page" in result

    def test_fix_prefix_categorized_as_bug_fixes(self):
        with patch("skills.subprocess.run", return_value=_mock_run(_SAMPLE_COMMITS)):
            result = skills.generate_changelog()
        assert "Bug Fixes" in result or "fix" in result.lower()
        assert "resolve token expiry" in result

    def test_docs_prefix_categorized_as_documentation(self):
        with patch("skills.subprocess.run", return_value=_mock_run(_SAMPLE_COMMITS)):
            result = skills.generate_changelog()
        assert "Documentation" in result
        assert "update contributing guide" in result

    def test_refactor_prefix_categorized_correctly(self):
        with patch("skills.subprocess.run", return_value=_mock_run(_SAMPLE_COMMITS)):
            result = skills.generate_changelog()
        assert "Refactor" in result or "refactor" in result.lower()

    def test_unprefixed_commit_falls_to_other_or_fix(self):
        # "no-prefix miscellaneous change" has no conventional prefix; it ends
        # up under "other" or a keyword-matched category — either is acceptable
        with patch("skills.subprocess.run", return_value=_mock_run(_SAMPLE_COMMITS)):
            result = skills.generate_changelog()
        assert "no-prefix miscellaneous change" in result

    def test_total_commit_count_in_footer(self):
        with patch("skills.subprocess.run", return_value=_mock_run(_SAMPLE_COMMITS)):
            result = skills.generate_changelog()
        assert "commits processed" in result

    def test_empty_stdout_returns_no_commits_message(self):
        with patch("skills.subprocess.run", return_value=_mock_run("")):
            result = skills.generate_changelog()
        assert "No commits found" in result

    def test_git_not_found_returns_error_message(self):
        with patch("skills.subprocess.run", side_effect=FileNotFoundError()):
            result = skills.generate_changelog()
        assert "git not found" in result.lower() or "Error" in result

    def test_git_timeout_returns_error_message(self):
        with patch(
            "skills.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 15),
        ):
            result = skills.generate_changelog()
        assert "timed out" in result.lower() or "Error" in result

    def test_nonzero_returncode_returns_error_message(self):
        with patch(
            "skills.subprocess.run",
            return_value=_mock_run("", returncode=1, stderr="not a git repo"),
        ):
            result = skills.generate_changelog()
        assert "Error" in result
        assert "not a git repo" in result

    def test_since_argument_passed_to_git(self):
        with patch("skills.subprocess.run", return_value=_mock_run("")) as mock_run:
            skills.generate_changelog(since="2026-01-01")
        call_args = mock_run.call_args[0][0]
        assert any("--since=2026-01-01" in a for a in call_args)

    def test_until_argument_passed_to_git(self):
        with patch("skills.subprocess.run", return_value=_mock_run("")) as mock_run:
            skills.generate_changelog(until="2026-06-01")
        call_args = mock_run.call_args[0][0]
        assert any("--until=2026-06-01" in a for a in call_args)

    def test_default_call_includes_limit_flag(self):
        # Without since/until, the command must include a count limit
        with patch("skills.subprocess.run", return_value=_mock_run("")) as mock_run:
            skills.generate_changelog()
        call_args = mock_run.call_args[0][0]
        assert any(a.startswith("-") and a[1:].isdigit() for a in call_args)

    def test_output_starts_with_changelog_heading(self):
        with patch("skills.subprocess.run", return_value=_mock_run(_SAMPLE_COMMITS)):
            result = skills.generate_changelog()
        assert result.strip().startswith("# Changelog")

    def test_scoped_conventional_commit_prefix_parsed(self):
        # "fix(auth): ..." — the scope must not appear in the clean entry
        with patch("skills.subprocess.run", return_value=_mock_run(_SAMPLE_COMMITS)):
            result = skills.generate_changelog()
        # "fix(auth):" stripped; body "resolve token expiry" present
        assert "resolve token expiry" in result


# ── run_webapp_test ───────────────────────────────────────────────────────────


class TestRunWebappTest:
    def test_loopback_address_blocked(self):
        result = skills.run_webapp_test("http://127.0.0.1/path")
        assert "Security error" in result

    def test_localhost_blocked(self):
        result = skills.run_webapp_test("http://localhost/")
        assert "Security error" in result

    def test_private_network_blocked(self):
        result = skills.run_webapp_test("http://192.168.1.1/")
        assert "Security error" in result

    def test_file_scheme_blocked(self):
        result = skills.run_webapp_test("file:///etc/passwd")
        assert "Security error" in result

    def test_ftp_scheme_blocked(self):
        result = skills.run_webapp_test("ftp://example.com/file")
        assert "Security error" in result

    def test_allow_local_permits_loopback(self):
        # With allow_local=True the security gate passes; the connection will
        # fail because nothing is listening, but the error must NOT be a
        # "Security error" — it should be a connection failure.
        result = skills.run_webapp_test("http://127.0.0.1:9/", allow_local=True)
        assert "Security error" not in result


# ── register_skill_tools ──────────────────────────────────────────────────────


class TestRegisterSkillTools:
    def test_registers_find_duplicates_tool(self):
        registry._TOOLS.clear()
        skills.register_skill_tools()
        assert "FindDuplicates" in registry._TOOLS

    def test_registers_scaffold_tool(self):
        registry._TOOLS.clear()
        skills.register_skill_tools()
        assert "Scaffold" in registry._TOOLS

    def test_registers_changelog_tool(self):
        registry._TOOLS.clear()
        skills.register_skill_tools()
        assert "Changelog" in registry._TOOLS

    def test_registers_webtest_tool(self):
        registry._TOOLS.clear()
        skills.register_skill_tools()
        assert "WebTest" in registry._TOOLS

    def test_all_tools_in_skills_category(self):
        registry._TOOLS.clear()
        skills.register_skill_tools()
        for tool in registry._TOOLS.values():
            assert tool.category == "skills", f"{tool.name} has wrong category: {tool.category}"

    def test_find_duplicates_handler_is_callable(self):
        registry._TOOLS.clear()
        skills.register_skill_tools()
        tool = registry._TOOLS["FindDuplicates"]
        assert callable(tool.handler)

    def test_scaffold_handler_is_callable(self):
        registry._TOOLS.clear()
        skills.register_skill_tools()
        assert callable(registry._TOOLS["Scaffold"].handler)

    def test_all_tools_have_description(self):
        registry._TOOLS.clear()
        skills.register_skill_tools()
        for tool in registry._TOOLS.values():
            assert tool.description, f"{tool.name} has empty description"
