"""Coding intelligence tools - test runner, linter, formatter, symbol analysis."""

import ast
import importlib.util
import logging
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import tool_registry as registry

logger = logging.getLogger(__name__)

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
              ".tox", "dist", "build", ".mypy_cache", ".pytest_cache"}
_PYTHON_CANDIDATES = ("python", "py")
_DEV_REQUIREMENT_SOURCES = {"requirements-dev.txt"}
_OPTIONAL_REQUIREMENT_SOURCES = {"requirements-ml.txt", "requirements-vision.txt"}
_PROVIDER_RUNTIME_REQUIREMENTS = {
    "anthropic": ["anthropic"],
    "openai": ["openai"],
    "venice": ["openai"],
    "ollama": ["httpx"],
}
_OPTIONAL_RUNTIME_PACKAGES = {"aiofiles", "ddgs"}
_STARTUP_TARGET_IMPORTS = {
    "cli": [],
    "gui": ["customtkinter", "tkinter"],
}
_STARTUP_TARGET_PACKAGES = {
    "cli": [],
    "gui": ["customtkinter"],
}
_PROVIDER_KEY_HINTS = {
    "anthropic": (
        ("ANTHROPIC_API_KEY", "export ANTHROPIC_API_KEY=..."),
        ("ANTHROPIC_API_KEY_1", "export ANTHROPIC_API_KEY_1=..."),
    ),
    "openai": (
        ("OPENAI_API_KEY", "export OPENAI_API_KEY=..."),
    ),
    "venice": (
        ("VENICE_API_KEY", "export VENICE_API_KEY=..."),
    ),
}
_IMPORT_TO_PACKAGE = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
}
_PACKAGE_TO_IMPORTS = {
    "aiofiles": ("aiofiles",),
    "anthropic": ("anthropic",),
    "black": ("black",),
    "customtkinter": ("customtkinter",),
    "ddgs": ("ddgs",),
    "detect-secrets": ("detect_secrets",),
    "easyocr": ("easyocr",),
    "httpx": ("httpx",),
    "joblib": ("joblib",),
    "lightgbm": ("lightgbm",),
    "mypy": ("mypy",),
    "numpy": ("numpy",),
    "opencv-python": ("cv2",),
    "openai": ("openai",),
    "pandas": ("pandas",),
    "Pillow": ("PIL",),
    "pre-commit": ("pre_commit",),
    "pytest": ("pytest",),
    "pytest-cov": ("pytest_cov",),
    "pytesseract": ("pytesseract",),
    "ruff": ("ruff",),
    "scikit-learn": ("sklearn",),
    "tensorflow": ("tensorflow",),
    "torch": ("torch",),
    "xgboost": ("xgboost",),
}


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


def _python_cmd() -> list[str]:
    """Resolve the local Python command without assuming `python` is on PATH."""
    for candidate in _PYTHON_CANDIDATES:
        if shutil.which(candidate):
            return [candidate]
    return ["python"]


def _bounded_timeout(timeout: int, default: int = 120) -> int:
    try:
        value = int(timeout)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, 600))


def _iter_requirement_files(root: Path) -> list[Path]:
    discovered: list[Path] = []
    seen: set[Path] = set()

    def visit(req_path: Path) -> None:
        req_path = req_path.resolve()
        if req_path in seen or not req_path.exists():
            return
        seen.add(req_path)
        discovered.append(req_path)

        for raw_line in req_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(("-r ", "--requirement ")):
                include_target = line.split(maxsplit=1)[1].strip()
                visit(req_path.parent / include_target)

    for req_path in sorted(root.glob("requirements*.txt")):
        visit(req_path)
    visit(root / "requirements/base.txt")

    return discovered


def _parse_requirement_name(line: str) -> str:
    candidate = line.split("#", 1)[0].strip()
    if not candidate or candidate.startswith(("-", "git+", "http://", "https://")):
        return ""
    return re.split(r"[>=<!~;\[]", candidate)[0].strip()


def _iter_declared_dependencies(root: Path) -> list[tuple[str, str]]:
    requirements: list[tuple[str, str]] = []

    for req_file in _iter_requirement_files(root):
        for raw_line in req_file.read_text(encoding="utf-8").splitlines():
            pkg = _parse_requirement_name(raw_line)
            if pkg:
                requirements.append((pkg, req_file.relative_to(root).as_posix()))

    pyproject_path = root / "pyproject.toml"
    if pyproject_path.exists():
        try:
            parsed = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            parsed = {}

        project = parsed.get("project", {})
        for dep in project.get("dependencies", []):
            pkg = _parse_requirement_name(dep)
            if pkg:
                requirements.append((pkg, "pyproject.toml"))

        for group_name, deps in (project.get("optional-dependencies", {}) or {}).items():
            for dep in deps:
                pkg = _parse_requirement_name(dep)
                if pkg:
                    requirements.append((pkg, f"pyproject.toml[optional:{group_name}]"))

    return requirements


def _check_declared_dependencies(root: Path) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    requirements = _iter_declared_dependencies(root)
    installed: list[tuple[str, str]] = []
    missing: list[tuple[str, str]] = []
    seen: set[str] = set()

    for pkg, source in requirements:
        key = pkg.lower()
        if key in seen:
            continue
        seen.add(key)

        spec = None
        for import_name in _package_import_candidates(pkg):
            spec = importlib.util.find_spec(import_name)
            if spec is not None:
                break
        if spec is not None:
            installed.append((pkg, source))
        else:
            missing.append((pkg, source))

    return installed, missing


def _declared_dependency_names(root: Path) -> set[str]:
    return {
        pkg.lower()
        for pkg, _ in _iter_declared_dependencies(root)
    }


def _local_module_names(root: Path) -> set[str]:
    names = {path.stem for path in root.glob("*.py")}
    names.update(
        path.name
        for path in root.iterdir()
        if path.is_dir() and (path / "__init__.py").exists()
    )
    return names


def _third_party_imports(root: Path) -> dict[str, list[str]]:
    imports: dict[str, set[str]] = {}
    local_names = _local_module_names(root)
    stdlib_names = set(sys.stdlib_module_names)

    for py_file in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in py_file.parts):
            continue

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue

        rel_path = py_file.relative_to(root).as_posix()
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module.split(".", 1)[0]]

            for module in modules:
                if not module or module in stdlib_names or module in local_names:
                    continue
                package_name = _IMPORT_TO_PACKAGE.get(module, module)
                imports.setdefault(package_name, set()).add(rel_path)

    return {
        package: sorted(paths)
        for package, paths in sorted(imports.items())
    }


def _find_undeclared_dependencies(root: Path) -> dict[str, list[str]]:
    declared = _declared_dependency_names(root)
    imports = _third_party_imports(root)
    return {
        package: paths
        for package, paths in imports.items()
        if package.lower() not in declared
    }


def _package_import_candidates(package: str) -> tuple[str, ...]:
    explicit = _PACKAGE_TO_IMPORTS.get(package)
    if explicit:
        return explicit

    normalized = package.lower()
    explicit = _PACKAGE_TO_IMPORTS.get(normalized)
    if explicit:
        return explicit

    return (package.replace("-", "_").lower(),)


def _iter_python_files(root: Path) -> list[Path]:
    return [
        py_file
        for py_file in root.rglob("*.py")
        if not any(part in _SKIP_DIRS for part in py_file.parts)
    ]


def _detect_active_provider(provider: str = "") -> str:
    if provider.strip():
        return provider.strip().lower()

    try:
        from api_config import load_config

        return str(load_config().get("provider", "")).strip().lower()
    except Exception:
        return ""


def _partition_missing_dependencies(
    missing: list[tuple[str, str]]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]]:
    """Split missing packages into runtime, development, and optional groups."""
    runtime_missing: list[tuple[str, str]] = []
    dev_missing: list[tuple[str, str]] = []
    optional_missing: list[tuple[str, str]] = []

    for pkg, source in missing:
        if source in _OPTIONAL_REQUIREMENT_SOURCES:
            optional_missing.append((pkg, source))
        elif source in _DEV_REQUIREMENT_SOURCES:
            dev_missing.append((pkg, source))
        else:
            runtime_missing.append((pkg, source))

    return runtime_missing, dev_missing, optional_missing


def _group_missing_by_source(
    missing: list[tuple[str, str]]
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for pkg, source in missing:
        grouped.setdefault(source, []).append(pkg)
    return grouped


def _classify_runtime_missing(
    runtime_missing: list[tuple[str, str]],
    active_provider: str,
    startup_target: str,
) -> tuple[
    list[tuple[str, str]],
    dict[str, list[tuple[str, str]]],
    list[tuple[str, str]],
]:
    startup_required = {
        pkg.lower() for pkg in _PROVIDER_RUNTIME_REQUIREMENTS.get(active_provider, [])
    }
    startup_required.update(
        pkg.lower() for pkg in _STARTUP_TARGET_PACKAGES.get(startup_target, [])
    )

    other_provider_packages = {
        pkg.lower()
        for provider_name, packages in _PROVIDER_RUNTIME_REQUIREMENTS.items()
        if provider_name != active_provider
        for pkg in packages
    }
    gui_only_packages = {
        pkg.lower()
        for pkg in _STARTUP_TARGET_PACKAGES.get("gui", [])
        if startup_target != "gui"
    }

    startup_runtime_missing: list[tuple[str, str]] = []
    feature_scoped_runtime_missing: dict[str, list[tuple[str, str]]] = {}
    general_runtime_missing: list[tuple[str, str]] = []

    for pkg, source in runtime_missing:
        normalized = pkg.lower()
        if normalized in startup_required:
            startup_runtime_missing.append((pkg, source))
        elif normalized in other_provider_packages:
            feature_scoped_runtime_missing.setdefault(
                "Inactive provider SDKs", []
            ).append((pkg, source))
        elif normalized in gui_only_packages:
            feature_scoped_runtime_missing.setdefault(
                "GUI-only packages", []
            ).append((pkg, source))
        elif normalized in _OPTIONAL_RUNTIME_PACKAGES:
            feature_scoped_runtime_missing.setdefault(
                "Optional runtime accelerators", []
            ).append((pkg, source))
        else:
            general_runtime_missing.append((pkg, source))

    return startup_runtime_missing, feature_scoped_runtime_missing, general_runtime_missing


def _has_provider_credentials(active_provider: str) -> bool:
    if active_provider == "anthropic":
        for env_name, _ in _PROVIDER_KEY_HINTS["anthropic"]:
            if os.environ.get(env_name, "").strip():
                return True
        for idx in range(2, 6):
            if os.environ.get(f"ANTHROPIC_API_KEY_{idx}", "").strip():
                return True
        return False

    if active_provider in {"openai", "venice"}:
        env_name = _PROVIDER_KEY_HINTS[active_provider][0][0]
        if os.environ.get(env_name, "").strip():
            return True
        try:
            from api_config import get_secret

            return bool(get_secret(f"{active_provider}.api_key"))
        except Exception:
            return False

    return True


def _provider_key_guidance(active_provider: str) -> str:
    hints = _PROVIDER_KEY_HINTS.get(active_provider)
    if not hints:
        return ""

    preferred_env, example = hints[0]
    if active_provider == "anthropic":
        return (
            f"Provider '{active_provider}' has no API key configured. Set {preferred_env} "
            f"(or numbered variants like ANTHROPIC_API_KEY_1), or load one with "
            f"/config {active_provider}.api_key=..."
        )

    return (
        f"Provider '{active_provider}' has no API key configured. Set {preferred_env} "
        f"or load one with /config {active_provider}.api_key=..."
    )


def _collect_environment_diagnostics(
    root: Path,
    provider: str = "",
    target: str = "cli",
) -> dict[str, object]:
    active_provider = _detect_active_provider(provider)
    startup_target = target.strip().lower() or "cli"
    if startup_target not in _STARTUP_TARGET_IMPORTS:
        startup_target = "cli"

    installed, missing = _check_declared_dependencies(root)
    undeclared = _find_undeclared_dependencies(root)
    runtime_missing, dev_missing, optional_missing = _partition_missing_dependencies(missing)
    startup_runtime_missing, feature_scoped_runtime_missing, general_runtime_missing = (
        _classify_runtime_missing(runtime_missing, active_provider, startup_target)
    )
    runtime_missing_map = {pkg.lower(): (pkg, source) for pkg, source in runtime_missing}
    provider_missing = [
        pkg for pkg in _PROVIDER_RUNTIME_REQUIREMENTS.get(active_provider, [])
        if importlib.util.find_spec(pkg) is None
    ]
    target_missing = [
        module for module in _STARTUP_TARGET_IMPORTS[startup_target]
        if importlib.util.find_spec(module) is None
    ]
    python_cmd = " ".join(_python_cmd())
    has_tests = (
        (root / "tests").exists()
        or (root / "pytest.ini").exists()
        or any(root.rglob("test_*.py"))
        or any(root.rglob("*_test.py"))
    )
    pytest_available = importlib.util.find_spec("pytest") is not None

    blockers: list[str] = []
    advisories: list[str] = []
    notes: list[str] = []

    if sys.version_info < (3, 9):
        blockers.append(
            f"Python {sys.version_info.major}.{sys.version_info.minor} detected; project requires 3.9+."
        )
    else:
        notes.append(
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} detected."
        )

    notes.append(f"Launcher: {python_cmd}")
    notes.append(f"Active provider: {active_provider or 'unknown'}")
    notes.append(f"Startup target: {startup_target}")

    if startup_runtime_missing:
        blockers.append(
            "Startup-critical runtime dependencies are missing: "
            + ", ".join(pkg for pkg, _ in startup_runtime_missing[:8])
            + (" ..." if len(startup_runtime_missing) > 8 else "")
        )

    runtime_advisory_targets = startup_runtime_missing + general_runtime_missing
    if runtime_advisory_targets:
        advisories.append(
            "Runtime dependencies are missing: "
            + ", ".join(pkg for pkg, _ in runtime_advisory_targets[:8])
            + (" ..." if len(runtime_advisory_targets) > 8 else "")
        )

    if startup_target == "gui" and target_missing:
        blockers.append(
            "GUI runtime imports are unavailable: "
            + ", ".join(target_missing)
        )

    provider_only_missing = [
        pkg for pkg in provider_missing
        if pkg.lower() not in {name.lower() for name, _ in startup_runtime_missing}
    ]

    if provider_only_missing:
        blockers.append(
            f"Provider '{active_provider}' is missing required SDK(s): {', '.join(provider_only_missing)}."
        )

    if active_provider in _PROVIDER_KEY_HINTS and not _has_provider_credentials(active_provider):
        blockers.append(_provider_key_guidance(active_provider))

    if undeclared:
        advisories.append(
            "Imported packages are not declared in requirements: "
            + ", ".join(list(undeclared)[:8])
            + (" ..." if len(undeclared) > 8 else "")
        )

    if has_tests and not pytest_available:
        advisories.append(
            "Pytest is not installed, so the test suite cannot run in this environment."
        )

    if active_provider == "ollama":
        notes.append(f"Ollama URL: {os.environ.get('OLLAMA_URL', 'http://localhost:11434')}")
        notes.append("Ollama server health is not probed here; verify it is running before use.")
    if dev_missing:
        notes.append(
            f"Development tools not installed: {len(dev_missing)} "
            "(tests, linting, and formatting will be limited until installed)."
        )
    if optional_missing:
        notes.append(
            f"Optional feature packages not installed: {len(optional_missing)} "
            "(ML and vision tools remain unavailable until installed)."
        )
    if feature_scoped_runtime_missing:
        notes.append(
            "Feature-scoped runtime packages are missing, but they are not required "
            f"for the active {startup_target} startup path."
        )

    return {
        "root": root,
        "provider": active_provider,
        "target": startup_target,
        "installed": installed,
        "missing": missing,
        "runtime_missing": runtime_missing,
        "startup_runtime_missing": startup_runtime_missing,
        "feature_scoped_runtime_missing": feature_scoped_runtime_missing,
        "general_runtime_missing": general_runtime_missing,
        "dev_missing": dev_missing,
        "optional_missing": optional_missing,
        "undeclared": undeclared,
        "provider_missing": provider_missing,
        "provider_only_missing": provider_only_missing,
        "target_missing": target_missing,
        "has_tests": has_tests,
        "pytest_available": pytest_available,
        "blockers": blockers,
        "advisories": advisories,
        "notes": notes,
    }


def startup_blocked(path: str = ".", provider: str = "", target: str = "cli") -> bool:
    """Return True when the local environment cannot satisfy startup prerequisites."""
    root = Path(path).resolve()
    diagnostics = _collect_environment_diagnostics(root, provider=provider, target=target)
    return bool(diagnostics["blockers"])


def startup_doctor(path: str = ".", provider: str = "", target: str = "cli") -> str:
    """Report startup readiness for the CLI or GUI entrypoints."""
    root = Path(path).resolve()
    diagnostics = _collect_environment_diagnostics(root, provider=provider, target=target)

    blockers = diagnostics["blockers"]
    advisories = diagnostics["advisories"]
    runtime_missing = diagnostics["runtime_missing"]
    feature_scoped_runtime_missing = diagnostics["feature_scoped_runtime_missing"]
    dev_missing = diagnostics["dev_missing"]
    undeclared = diagnostics["undeclared"]
    notes = diagnostics["notes"]
    active_provider = diagnostics["provider"]
    python_cmd = " ".join(_python_cmd())
    startup_runtime_missing = diagnostics["startup_runtime_missing"]
    provider_only_missing = diagnostics["provider_only_missing"]

    lines = [
        f"Startup Doctor ({root.name})",
        f"  Target:               {diagnostics['target']}",
        f"  Active provider:      {active_provider or 'unknown'}",
        f"  Runtime missing:      {len(runtime_missing)}",
        f"  Startup blockers:     {len(blockers)}",
        f"  Advisories:           {len(advisories)}",
    ]

    if blockers:
        lines.append("\nBlockers:")
        for issue in blockers:
            lines.append(f"  x {issue}")
    else:
        lines.append("\nBlockers:\n  None detected.")

    if advisories:
        lines.append("\nAdvisories:")
        for issue in advisories:
            lines.append(f"  - {issue}")

    if runtime_missing:
        lines.append("\nMissing runtime packages:")
        for pkg, source in runtime_missing[:20]:
            lines.append(f"  - {pkg}  ({source})")

    if feature_scoped_runtime_missing:
        lines.append("\nFeature-scoped runtime packages:")
        for scope, packages in feature_scoped_runtime_missing.items():
            lines.append(f"  {scope}:")
            for pkg, source in packages[:20]:
                lines.append(f"    - {pkg}  ({source})")

    if dev_missing:
        lines.append("\nMissing development packages:")
        for pkg, source in dev_missing[:20]:
            lines.append(f"  - {pkg}  ({source})")

    if undeclared:
        lines.append("\nUndeclared imported packages:")
        for pkg, sources in list(undeclared.items())[:20]:
            lines.append(f"  - {pkg}  ({', '.join(sources[:3])})")

    lines.append("\nNotes:")
    for note in notes:
        lines.append(f"  - {note}")

    if blockers:
        startup_install_targets = [pkg for pkg, _ in startup_runtime_missing]
        startup_install_targets.extend(provider_only_missing)
        startup_install_targets = list(dict.fromkeys(startup_install_targets))
        lines.append(
            "\nSuggested startup fix:\n"
            f"  {python_cmd} -m pip install {' '.join(startup_install_targets or ['-r requirements-core.txt'])}"
        )
        if dev_missing:
            lines.append(
                f"  Optional dev tooling: {python_cmd} -m pip install -r requirements-dev.txt"
            )

    return "\n".join(lines)


def environment_doctor(path: str = ".", provider: str = "") -> str:
    """Report startup blockers and environment drift for the active provider."""
    root = Path(path).resolve()
    diagnostics = _collect_environment_diagnostics(root, provider=provider, target="cli")
    active_provider = diagnostics["provider"]
    installed = diagnostics["installed"]
    missing = diagnostics["missing"]
    runtime_missing = diagnostics["runtime_missing"]
    startup_runtime_missing = diagnostics["startup_runtime_missing"]
    feature_scoped_runtime_missing = diagnostics["feature_scoped_runtime_missing"]
    general_runtime_missing = diagnostics["general_runtime_missing"]
    dev_missing = diagnostics["dev_missing"]
    optional_missing = diagnostics["optional_missing"]
    undeclared = diagnostics["undeclared"]
    provider_missing = diagnostics["provider_missing"]
    has_tests = diagnostics["has_tests"]
    pytest_available = diagnostics["pytest_available"]
    notes = list(diagnostics["notes"])
    blockers = list(diagnostics["blockers"])
    advisories = list(diagnostics["advisories"])
    python_cmd = " ".join(_python_cmd())

    lines = [
        f"Environment Doctor ({root.name})",
        f"  Declared dependencies: {len(installed) + len(missing)}",
        f"  Installed:             {len(installed)}",
        f"  Missing:               {len(missing)}",
        f"  Runtime missing:       {len(runtime_missing)}",
        f"  Dev missing:           {len(dev_missing)}",
        f"  Optional missing:      {len(optional_missing)}",
        f"  Startup blockers:      {len(blockers)}",
        f"  Advisories:            {len(advisories)}",
    ]

    if blockers:
        lines.append("\nStartup blockers:")
        for issue in blockers:
            lines.append(f"  x {issue}")
    else:
        lines.append("\nStartup blockers:\n  None detected.")

    if advisories:
        lines.append("\nAdvisories:")
        for issue in advisories:
            lines.append(f"  - {issue}")

    if runtime_missing:
        lines.append("\nMissing runtime packages:")
        for pkg, source in runtime_missing[:20]:
            lines.append(f"  - {pkg}  ({source})")

    if feature_scoped_runtime_missing:
        lines.append("\nFeature-scoped runtime packages:")
        for scope, packages in feature_scoped_runtime_missing.items():
            lines.append(f"  {scope}:")
            for pkg, source in packages[:20]:
                lines.append(f"    - {pkg}  ({source})")

    if dev_missing:
        lines.append("\nMissing development packages:")
        for pkg, source in dev_missing[:20]:
            lines.append(f"  - {pkg}  ({source})")

    if undeclared:
        lines.append("\nUndeclared imported packages:")
        for pkg, sources in list(undeclared.items())[:20]:
            lines.append(f"  - {pkg}  ({', '.join(sources[:3])})")

    lines.append("\nNotes:")
    for note in notes:
        lines.append(f"  - {note}")

    if runtime_missing or provider_missing or blockers:
        runtime_install_targets = [pkg for pkg, _ in startup_runtime_missing]
        runtime_install_targets.extend(pkg for pkg, _ in general_runtime_missing)
        provider_install_targets = [
            pkg for pkg in _PROVIDER_RUNTIME_REQUIREMENTS.get(active_provider, [])
            if pkg.lower() not in {name.lower() for name in runtime_install_targets}
        ]
        runtime_install_targets.extend(provider_install_targets)
        deduped_runtime_targets = list(dict.fromkeys(runtime_install_targets))
        if deduped_runtime_targets:
            lines.append(
                "\nSuggested runtime fix:\n"
                f"  {python_cmd} -m pip install {' '.join(deduped_runtime_targets)}"
            )
        if feature_scoped_runtime_missing:
            lines.append("\nInstall feature-scoped packages only when needed:")
            for scope, packages in feature_scoped_runtime_missing.items():
                install_targets = " ".join(pkg for pkg, _ in packages)
                lines.append(f"  - {scope}: {python_cmd} -m pip install {install_targets}")
        if has_tests and not pytest_available:
            lines.append(
                f"  Install test tooling: {python_cmd} -m pip install pytest pytest-cov"
            )
        if dev_missing:
            lines.append(
                f"  Or install the full dev toolchain: {python_cmd} -m pip install -r requirements-dev.txt"
            )
    elif dev_missing:
        lines.append(
            "\nSuggested dev fix:\n"
            f"  {python_cmd} -m pip install -r requirements-dev.txt"
        )

    return "\n".join(lines)


def repo_health(path: str = ".", provider: str = "", timeout: int = 120) -> str:
    """Run the repo's standard health checks with graceful skips for missing tooling."""
    root = Path(path).resolve()
    if not root.exists():
        return f"Error: Path not found: {path}"
    if not root.is_dir():
        return f"Error: Not a directory: {path}"

    timeout = _bounded_timeout(timeout, default=120)
    has_tests = (
        (root / "tests").exists()
        or (root / "pytest.ini").exists()
        or any(root.rglob("test_*.py"))
        or any(root.rglob("*_test.py"))
    )

    compile_errors: list[str] = []
    python_files = _iter_python_files(root)
    for py_file in python_files:
        try:
            py_compile.compile(str(py_file), doraise=True)
        except py_compile.PyCompileError as exc:
            compile_errors.append(str(exc))
        except Exception as exc:
            compile_errors.append(f"{py_file}: {exc}")

    compile_summary = f"OK compileall passed. Checked {len(python_files)} file(s)."
    if compile_errors:
        compile_summary = "FAIL compileall found syntax errors.\n" + "\n".join(compile_errors[:10])

    pytest_available = importlib.util.find_spec("pytest") is not None
    ruff_available = importlib.util.find_spec("ruff") is not None

    if has_tests and pytest_available:
        tests_summary = run_tests(str(root), framework="pytest", timeout=timeout)
    elif has_tests:
        tests_summary = (
            "SKIP pytest is not installed. "
            f"Install with: {' '.join(_python_cmd())} -m pip install -r requirements-dev.txt"
        )
    else:
        tests_summary = "SKIP no test suite detected."

    if ruff_available:
        lint_summary = lint_check(str(root), tool="ruff")
    else:
        lint_summary = (
            "SKIP ruff is not installed. "
            f"Install with: {' '.join(_python_cmd())} -m pip install -r requirements-dev.txt"
        )

    return "\n\n".join(
        [
            f"Repo Health ({root.name})",
            environment_doctor(str(root), provider=provider),
            "Compile Check:\n" + compile_summary,
            "Test Check:\n" + tests_summary,
            "Lint Check:\n" + lint_summary,
        ]
    )


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
        cmd = _python_cmd() + ["-m", "pytest", "--tb=short", "-q"] + extra + [str(path)]
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
                lines.append(f"  x {f.strip()}")
            if len(failures) > 20:
                lines.append(f"  ... and {len(failures) - 20} more")

        lines.append(f"\n{'-'*50}")
        lines.append(output[-3000:] if len(output) > 3000 else output)
        return "\n".join(lines)

    elif framework in ("unittest",):
        cmd = _python_cmd() + ["-m", "unittest", "discover", "-s", str(path)] + extra
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

    # Word-boundary pattern - only replace whole words
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
        f"{'DRY RUN - ' if dry_run else ''}Rename '{old_name}' -> '{new_name}'",
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
                lines.append(f"       -> {ml.strip()}")
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
        lines.append(f"\nOK Renamed in {applied}/{len(changed_files)} files.")

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
                        f"  {fp.name}:{node.lineno}: bare 'except:' clause - catch specific exceptions"
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
    requirements = _iter_declared_dependencies(root)

    if not requirements:
        return (f"No requirements file found in {path}. "
                "Looked for: requirements.txt, requirements-dev.txt, requirements-core.txt, pyproject.toml")
    installed, missing = _check_declared_dependencies(root)
    undeclared = _find_undeclared_dependencies(root)
    runtime_missing, dev_missing, optional_missing = _partition_missing_dependencies(missing)
    optional_missing_by_source = _group_missing_by_source(optional_missing)
    python_cmd = " ".join(_python_cmd())

    lines = [
        f"Dependency Check ({root.name})",
        f"  Installed: {len(installed)}",
        f"  Missing:   {len(missing)}",
        f"  Runtime missing: {len(runtime_missing)}",
        f"  Dev missing:     {len(dev_missing)}",
        f"  Optional missing:{len(optional_missing)}",
        f"  Undeclared imports: {len(undeclared)}",
    ]

    if runtime_missing:
        lines.append("\nMissing runtime packages:")
        for pkg, src in runtime_missing:
            lines.append(f"  x  {pkg}  (from {src})")
        lines.append(
            f"\nInstall runtime with: {python_cmd} -m pip install {' '.join(p for p, _ in runtime_missing)}"
        )
    else:
        lines.append("\nRuntime dependencies are installed.")

    if dev_missing:
        lines.append("\nMissing development packages:")
        for pkg, src in dev_missing:
            lines.append(f"  x  {pkg}  (from {src})")
        lines.append(
            f"\nInstall dev tooling with: {python_cmd} -m pip install -r requirements-dev.txt"
        )

    if optional_missing:
        lines.append("\nMissing optional feature packages:")
        for pkg, src in optional_missing:
            lines.append(f"  x  {pkg}  (from {src})")
        lines.append("\nOptional feature bundles:")
        for source in optional_missing_by_source:
            lines.append(
                f"  - {source}: {python_cmd} -m pip install -r {source}"
            )
    else:
        if not runtime_missing and not dev_missing:
            lines.append("\nAll declared dependencies are installed.")

    if undeclared:
        lines.append("\nImported but undeclared packages:")
        for pkg, sources in undeclared.items():
            lines.append(f"  x  {pkg}  (used by {', '.join(sources[:3])})")

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
                "check_only": {"type": "boolean", "description": "Preview only - do not write changes", "default": False},
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
                "language": {"type": "string", "description": "Language filter (py/js/ts/go - empty = all)", "default": ""},
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

    registry.register(
        name="EnvironmentDoctor",
        description=(
            "Audit local startup health for this project: Python version, active provider SDK, "
            "pytest availability, and missing declared dependencies."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Project root directory", "default": "."},
                "provider": {
                    "type": "string",
                    "description": "Provider to validate (anthropic/openai/venice/ollama). "
                                   "Defaults to the configured provider if omitted.",
                    "default": "",
                },
            },
        },
        handler=environment_doctor, category="code",
    )

    registry.register(
        name="StartupDoctor",
        description=(
            "Check whether the local CLI or GUI entrypoint can start cleanly. "
            "Focuses on runtime blockers such as missing SDKs, GUI packages, and provider credentials."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Project root directory", "default": "."},
                "provider": {
                    "type": "string",
                    "description": "Provider to validate (anthropic/openai/venice/ollama). "
                                   "Defaults to the configured provider if omitted.",
                    "default": "",
                },
                "target": {
                    "type": "string",
                    "description": "Startup target to validate (cli/gui).",
                    "default": "cli",
                },
            },
        },
        handler=startup_doctor, category="code",
    )

    registry.register(
        name="RepoHealth",
        description=(
            "Run the standard repo health audit: environment doctor, compileall, pytest when "
            "available, and ruff when available."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Project root directory", "default": "."},
                "provider": {
                    "type": "string",
                    "description": "Provider to validate (anthropic/openai/venice/ollama). "
                                   "Defaults to the configured provider if omitted.",
                    "default": "",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Per-check timeout in seconds for pytest and lint steps.",
                    "default": 120,
                },
            },
        },
        handler=repo_health, category="code",
    )
