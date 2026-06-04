"""
project_context.py — Singleton that holds the currently loaded project map.

agent.py reads this on every turn and injects it into the system prompt so
Dan always knows the project structure without the user having to repeat it.
"""

_context: str = ""   # formatted project map for injection into system prompt
_root: str    = ""   # absolute path to project root
_name: str    = ""   # project display name


def set(root: str, name: str, formatted: str) -> None:
    global _context, _root, _name
    _context = formatted
    _root    = root
    _name    = name


def get() -> str:
    return _context


def root() -> str:
    return _root


def name() -> str:
    return _name


def clear() -> None:
    global _context, _root, _name
    _context = _root = _name = ""


def is_loaded() -> bool:
    return bool(_context)
