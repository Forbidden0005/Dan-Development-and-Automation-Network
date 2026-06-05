"""Actions system — reusable automation templates."""

import logging
from dataclasses import dataclass
from pathlib import Path

import tool_registry as registry
import config

logger = logging.getLogger(__name__)


@dataclass
class Action:
    """A reusable action template."""

    name: str
    description: str
    prompt: str
    source: str = "builtin"  # builtin, user, project


# ── Built-in Actions ─────────────────────────────────────────────────────────

BUILTIN_ACTIONS: dict[str, Action] = {
    "commit": Action(
        name="commit",
        description="Generate a git commit with a descriptive message",
        prompt="Look at the current git diff (staged and unstaged). Write a clear, "
        "conventional commit message. Stage all changes and commit.",
    ),
    "review": Action(
        name="review",
        description="Review the current code changes",
        prompt="Look at the current git diff. Review the changes for bugs, style issues, "
        "security concerns, and suggest improvements. Be specific and actionable.",
    ),
    "test": Action(
        name="test",
        description="Run tests and analyze results",
        prompt="Find and run the project's test suite. Analyze any failures and suggest fixes.",
    ),
    "explain": Action(
        name="explain",
        description="Explain the current project structure",
        prompt="Analyze the project structure, key files, dependencies, and architecture. "
        "Provide a clear overview of how the codebase is organized.",
    ),
    "changelog": Action(
        name="changelog",
        description="Generate a user-friendly changelog from git commits",
        prompt="Use the Changelog tool to get the raw commit history, then rewrite it as "
        "polished, user-friendly release notes. Group changes into: New Features, "
        "Improvements, Bug Fixes, and Breaking Changes. Translate technical commit "
        "messages into language a customer would understand. Save the result to CHANGELOG.md.",
    ),
    "organize": Action(
        name="organize",
        description="Analyze and suggest file organization improvements",
        prompt="Analyze the current directory structure using ListDir and Glob. Identify: "
        "1) Files that seem misplaced, 2) Missing standard files (README, .gitignore, etc), "
        "3) Inconsistent naming, 4) Empty or redundant directories. Use FindDuplicates to check "
        "for duplicate files. Suggest a better organization and offer to make the changes.",
    ),
    "scaffold": Action(
        name="scaffold",
        description="Create a new project from a template",
        prompt="Ask the user what kind of project they want to create (Python, Node, or Web), "
        "the project name, and any specific requirements. Use the Scaffold tool to create "
        "the project structure, then customize the generated files based on their requirements.",
    ),
    "research": Action(
        name="research",
        description="Research a topic using web search and summarize findings",
        prompt="Ask the user what topic to research. Use WebSearch to find relevant sources, "
        "then use WebFetch to read the top results in detail. Synthesize the information "
        "into a well-structured summary with key findings, sources, and actionable insights. "
        "Save the research to a markdown file.",
    ),
    "webtest": Action(
        name="webtest",
        description="Test a web application for basic health and issues",
        prompt="Ask the user for the URL to test. Use the WebTest tool to check the server "
        "health, then use WebFetch to analyze the page content. Report on: server status, "
        "page load, obvious errors, missing meta tags, and basic accessibility issues.",
    ),
    "deps": Action(
        name="deps",
        description="Audit project dependencies for issues",
        prompt="Identify the project type (Python/Node/etc) by checking for requirements.txt, "
        "package.json, pyproject.toml, etc. List all dependencies, check for outdated "
        "packages, known security issues, and unused imports. Suggest improvements.",
    ),
}


def _load_custom_actions() -> dict[str, Action]:
    """Load custom actions from .dan/actions/ directories."""
    actions: dict[str, Action] = {}
    for scope, base in [("user", config.USER_DATA_DIR), ("project", config.PROJECT_DATA_DIR)]:
        action_dir = base / "actions"
        if not action_dir.exists():
            continue
        for fp in action_dir.glob("*.md"):
            name = fp.stem
            content = fp.read_text()
            # First line is description, rest is prompt
            lines = content.strip().splitlines()
            desc = lines[0].lstrip("# ").strip() if lines else name
            prompt = "\n".join(lines[1:]).strip() if len(lines) > 1 else desc
            actions[name] = Action(name=name, description=desc, prompt=prompt, source=scope)
    return actions


def get_all_actions() -> dict[str, Action]:
    """Get all actions (builtin + custom)."""
    actions = dict(BUILTIN_ACTIONS)
    actions.update(_load_custom_actions())
    return actions


def get_action(name: str) -> Action | None:
    return get_all_actions().get(name)


# ── Tool Handlers ────────────────────────────────────────────────────────────


def _execute_action(name: str) -> str:
    action = get_action(name)
    if not action:
        available = ", ".join(get_all_actions().keys())
        return f"Unknown action: {name}. Available: {available}"
    # Return the prompt — the agent loop will execute it
    return f"[ACTION:{action.name}] {action.prompt}"


def _list_actions() -> str:
    actions = get_all_actions()
    if not actions:
        return "No actions available."
    lines = []
    for a in actions.values():
        lines.append(f"  /{a.name:12s} {a.description} ({a.source})")
    return "\n".join(lines)


def register_action_tools() -> None:
    """Register action tools."""
    registry.register(
        name="Execute",
        description="Execute a named action (automation template).",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Action name (e.g. 'commit', 'review')"},
            },
            "required": ["name"],
        },
        handler=_execute_action,
        category="actions",
    )

    registry.register(
        name="ListActions",
        description="List all available actions.",
        parameters={"type": "object", "properties": {}},
        handler=_list_actions,
        category="actions",
    )
