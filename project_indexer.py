"""Project indexing and scan map helpers for Dan."""

from __future__ import annotations

import ast
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", "target", ".cargo",
    ".mypy_cache", ".pytest_cache", ".tox", "coverage", "htmlcov",
    "obj", "bin", ".vs", ".idea", ".vscode", ".eggs",
    "site-packages", ".terraform", ".serverless", ".expo",
    ".gradle", ".m2", "vendor",
}

SKIP_EXTS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".bin",
    ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg", ".bmp", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
    ".woff", ".woff2", ".ttf", ".eot",
}

ENTRY_NAMES = {
    "main.py", "app.py", "server.py", "run.py", "manage.py",
    "index.js", "index.ts", "app.js", "app.ts", "server.js", "server.ts",
    "main.go", "main.rs", "main.cpp", "main.c",
    "Program.cs", "Main.java",
}

LANG_MAP = {
    ".py": "Python", ".pyw": "Python",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".mts": "TypeScript",
    ".jsx": "React", ".tsx": "React/TS",
    ".rs": "Rust", ".go": "Go",
    ".java": "Java", ".kt": "Kotlin",
    ".cs": "C#", ".vb": "VB.NET",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++",
    ".c": "C", ".h": "C/C++", ".hpp": "C++",
    ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
    ".vue": "Vue", ".svelte": "Svelte",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
    ".sh": "Shell", ".bash": "Shell",
    ".bat": "Batch", ".ps1": "PowerShell",
    ".sql": "SQL", ".graphql": "GraphQL",
    ".tf": "Terraform", ".md": "Markdown",
}

MAX_FILE_SIZE = 500_000
MAX_FILES = 200
MAX_CONTEXT = 14_000


@dataclass
class FileInfo:
    rel_path: str
    language: str
    line_count: int
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    is_entry: bool = False

    def one_line(self) -> str:
        parts = []
        if self.classes:
            shown = self.classes[:5]
            extra = f"+{len(self.classes)-5}" if len(self.classes) > 5 else ""
            parts.append("class " + ", ".join(shown) + extra)
        if self.functions:
            shown = self.functions[:6]
            extra = f"+{len(self.functions)-6}" if len(self.functions) > 6 else ""
            parts.append(", ".join(shown) + extra + "()")
        if self.imports:
            parts.append("<- " + ", ".join(self.imports[:4]))
        detail = "  [" + " | ".join(parts) + "]" if parts else ""
        star = " *" if self.is_entry else ""
        return f"{Path(self.rel_path).name}{star}  {self.line_count}L{detail}"


@dataclass
class ProjectMap:
    root: str
    display_name: str
    files: list[FileInfo]
    languages: dict[str, int]
    total_files: int
    skipped: int
    scan_secs: float

    def summary(self) -> str:
        lang_str = ", ".join(
            f"{count} {language}" for language, count in
            sorted(self.languages.items(), key=lambda item: -item[1])[:5]
        )
        return (
            f"Loaded: {self.display_name}  "
            f"({self.total_files} files | {lang_str})  "
            f"[{self.scan_secs:.1f}s]"
        )

    def to_prompt(self) -> str:
        lang_str = " | ".join(
            f"{count} {language}" for language, count in
            sorted(self.languages.items(), key=lambda item: -item[1])[:6]
        )
        lines = [
            "<project_context>",
            f"PROJECT: {self.display_name}",
            f"ROOT:    {self.root}",
            f"STACK:   {lang_str}",
            f"FILES:   {self.total_files} total, {len(self.files)} indexed",
            "",
            "FILE MAP  (* = entry point)",
            "-" * 60,
        ]

        by_dir: dict[str, list[FileInfo]] = {}
        for file_info in self.files:
            directory = str(Path(file_info.rel_path).parent)
            by_dir.setdefault(directory, []).append(file_info)

        for directory in sorted(by_dir):
            if directory != ".":
                lines.append(f"\n  {directory}/")
                indent = "    "
            else:
                lines.append("")
                indent = "  "
            for file_info in sorted(by_dir[directory], key=lambda item: item.rel_path):
                lines.append(f"{indent}{file_info.one_line()}")

        all_classes = [
            (file_info.rel_path, class_name)
            for file_info in self.files
            for class_name in file_info.classes
        ]
        all_functions = [
            (file_info.rel_path, function_name)
            for file_info in self.files
            for function_name in file_info.functions
        ]

        if all_classes:
            lines += ["", "-" * 60, "CLASSES:"]
            for path, class_name in sorted(all_classes, key=lambda item: item[1])[:50]:
                lines.append(f"  {class_name}  ->  {path}")

        if all_functions:
            lines += ["", "FUNCTIONS:"]
            for path, function_name in sorted(all_functions, key=lambda item: item[1])[:80]:
                lines.append(f"  {function_name}()  ->  {path}")

        lines.append("</project_context>")
        result = "\n".join(lines)
        if len(result) > MAX_CONTEXT:
            result = result[:MAX_CONTEXT] + "\n... (map truncated)\n</project_context>"
        return result


def _extract_python(text: str) -> tuple[list, list, list]:
    classes = []
    functions = []
    imports = []
    try:
        tree = ast.parse(text)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module.split(".")[0])
    except SyntaxError:
        pass
    return classes, functions, list(dict.fromkeys(imports))[:10]


def _extract_js_ts(text: str) -> tuple[list, list, list]:
    classes = re.findall(r"(?:^|\s)class\s+(\w+)", text)
    functions = re.findall(
        r"(?:^|export\s+)(?:async\s+)?function\s+(\w+)|"
        r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(",
        text,
        re.MULTILINE,
    )
    functions = [item[0] or item[1] for item in functions if item[0] or item[1]]
    imports = re.findall(r"(?:import|require)\s*\(?['\"]([^'\"]+)['\"]", text)
    imports = [item.lstrip("./").split("/")[0] for item in imports if not item.startswith(".")]
    return classes, functions[:20], list(dict.fromkeys(imports))[:10]


def _extract_rust(text: str) -> tuple[list, list, list]:
    classes = re.findall(r"(?:pub\s+)?struct\s+(\w+)|(?:pub\s+)?enum\s+(\w+)", text)
    classes = [item[0] or item[1] for item in classes]
    functions = re.findall(r"(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", text)
    imports = re.findall(r"use\s+([\w:]+)", text)
    imports = [item.split("::")[0] for item in imports]
    return classes, functions[:20], list(dict.fromkeys(imports))[:10]


def _extract_go(text: str) -> tuple[list, list, list]:
    classes = re.findall(r"type\s+(\w+)\s+struct", text)
    functions = re.findall(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)", text, re.MULTILINE)
    imports = re.findall(r'"([\w./]+)"', text)
    imports = [item.split("/")[-1] for item in imports]
    return classes, functions[:20], list(dict.fromkeys(imports))[:10]


def _extract_generic(text: str, ext: str) -> tuple[list, list, list]:
    classes = re.findall(r"class\s+(\w+)", text)
    functions = re.findall(r"(?:def|func|function|fn|sub|void|int|string)\s+(\w+)\s*\(", text)
    return classes[:15], functions[:20], []


def _extract_symbols(text: str, ext: str) -> tuple[list, list, list]:
    if ext in (".py", ".pyw"):
        return _extract_python(text)
    if ext in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".mts"):
        return _extract_js_ts(text)
    if ext == ".rs":
        return _extract_rust(text)
    if ext == ".go":
        return _extract_go(text)
    return _extract_generic(text, ext)


def _should_skip_file(file_path: Path) -> bool:
    lowered_name = file_path.name.lower()
    if file_path.name.startswith("."):
        return True
    if file_path.suffix.lower() in SKIP_EXTS:
        return True
    return lowered_name.endswith(".min.js") or lowered_name.endswith(".min.css")


def _iter_files(root: Path):
    for current_root, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [
            dirname for dirname in dirnames
            if dirname not in SKIP_DIRS and not dirname.startswith(".")
        ]
        current_dir = Path(current_root)
        for filename in sorted(filenames):
            file_path = current_dir / filename
            if _should_skip_file(file_path):
                continue
            yield file_path


class ProjectScanner:
    def __init__(self, root: Path):
        self.root = root

    def scan(self) -> ProjectMap:
        started = time.time()
        files = []
        languages: dict[str, int] = {}
        total = 0
        skipped = 0

        for file_path in _iter_files(self.root):
            total += 1
            ext = file_path.suffix.lower()
            language = LANG_MAP.get(ext, "")
            if language:
                languages[language] = languages.get(language, 0) + 1

            if not language or len(files) >= MAX_FILES:
                skipped += 1
                continue

            try:
                size = file_path.stat().st_size
                if size > MAX_FILE_SIZE:
                    skipped += 1
                    continue
                text = file_path.read_text(encoding="utf-8", errors="replace")
                line_count = text.count("\n") + 1
                classes, functions, imports = _extract_symbols(text, ext)
                relative_path = str(file_path.relative_to(self.root))
                files.append(
                    FileInfo(
                        rel_path=relative_path,
                        language=language,
                        line_count=line_count,
                        classes=classes,
                        functions=functions,
                        imports=imports,
                        is_entry=file_path.name in ENTRY_NAMES,
                    )
                )
            except Exception:
                skipped += 1

        return ProjectMap(
            root=str(self.root),
            display_name=self.root.name,
            files=files,
            languages=languages,
            total_files=total,
            skipped=skipped,
            scan_secs=time.time() - started,
        )
