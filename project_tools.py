"""Project context tools for Dan."""

from pathlib import Path

import project_context
import tool_registry as registry
from project_indexer import ProjectScanner


def _load_project(path: str = ".") -> str:
    """Scan a project directory and set it as the active project context."""
    root = Path(path).resolve()
    if not root.exists():
        return f"Error: path not found: {path}"
    if not root.is_dir():
        return f"Error: not a directory: {path}"

    scanner = ProjectScanner(root)
    proj_map = scanner.scan()
    formatted = proj_map.to_prompt()

    project_context.set(str(root), proj_map.display_name, formatted)
    return proj_map.summary() + "\n\nProject context is now injected into every message."


def _show_project() -> str:
    """Show the currently loaded project map."""
    if not project_context.is_loaded():
        return "No project loaded.\n" "Use LoadProject to scan a directory, or ask Dan to load one."
    return project_context.get()


def _unload_project() -> str:
    """Clear the active project context."""
    if not project_context.is_loaded():
        return "No project was loaded."
    name = project_context.name()
    project_context.clear()
    return f"✓ Unloaded project: {name}"


def register_project_tools() -> None:
    """Register project context tools."""
    registry.register(
        name="LoadProject",
        description=(
            "Scan a project directory and inject its structure (files, classes, "
            "functions, imports) into context so Dan understands the whole codebase."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the project root directory (default: current dir)",
                    "default": ".",
                },
            },
        },
        handler=_load_project,
        category="project",
    )

    registry.register(
        name="ShowProject",
        description="Show the currently loaded project map (file structure, classes, functions).",
        parameters={"type": "object", "properties": {}},
        handler=_show_project,
        category="project",
    )

    registry.register(
        name="UnloadProject",
        description="Clear the active project context.",
        parameters={"type": "object", "properties": {}},
        handler=_unload_project,
        category="project",
    )
