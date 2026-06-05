"""Session persistence — save, load, and list Dan conversation sessions."""

import json
import time
import uuid
from pathlib import Path

from config import USER_DATA_DIR

SESSIONS_DIR = USER_DATA_DIR / "sessions"


def _dir() -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR


def _safe_session_stem(name: str) -> str:
    stem = name.strip()
    if not stem:
        return ""
    if Path(stem).name != stem or any(sep in stem for sep in ("/", "\\")):
        return ""
    if stem.endswith(".json"):
        stem = stem[:-5]
    return "".join(c for c in stem if c.isalnum() or c in "_-.")[:80]


# ── Save ──────────────────────────────────────────────────────────────────────

def save(messages: list[dict], provider: str, model: str,
         name: str = "", session_id: str = "") -> str:
    """Save the current conversation to disk.

    If *name* is given, saves to sessions/<name>.json (overwrites existing).
    Otherwise uses the session_id for the filename.

    Returns a human-readable confirmation string.
    """
    d     = _dir()
    sid   = session_id or str(uuid.uuid4())[:8]
    fname = (name.strip() or sid).replace(" ", "_")

    # Guard against dangerous filenames
    fname = "".join(c for c in fname if c.isalnum() or c in "_-.")[:80]
    if not fname:
        fname = sid

    filepath = d / f"{fname}.json"
    data = {
        "session_id": sid,
        "name":       fname,
        "created":    time.time(),
        "updated":    time.time(),
        "provider":   provider,
        "model":      model,
        "messages":   messages,
    }
    filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"✓ Session saved → {filepath.name} ({len(messages)} messages)"


# ── Auto-save ─────────────────────────────────────────────────────────────────

def auto_save(messages: list[dict], provider: str, model: str,
              session_id: str) -> None:
    """Silently auto-save the session after each turn (best-effort)."""
    if not messages:
        return
    try:
        d        = _dir()
        filepath = d / f"_auto_{session_id}.json"
        data = {
            "session_id": session_id,
            "name":       f"_auto_{session_id}",
            "created":    time.time(),
            "updated":    time.time(),
            "provider":   provider,
            "model":      model,
            "messages":   messages,
        }
        filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── Load ──────────────────────────────────────────────────────────────────────

def load(name: str) -> tuple[list[dict], dict] | None:
    """Load a session by name or session_id.

    Returns *(messages, metadata_dict)* on success, *None* if not found.
    Checks for exact filename match (with and without .json extension).
    """
    d = _dir().resolve()
    stem = _safe_session_stem(name)
    if not stem:
        return None

    candidates = [
        d / f"{stem}.json",
        d / f"_auto_{stem}.json",
    ]
    for fp in candidates:
        try:
            resolved = fp.resolve()
            resolved.relative_to(d)
        except ValueError:
            continue

        if resolved.exists():
            try:
                data = json.loads(resolved.read_text(encoding="utf-8"))
                return data.get("messages", []), data
            except Exception:
                continue
    return None


# ── List ──────────────────────────────────────────────────────────────────────

def list_sessions(include_auto: bool = False) -> list[dict]:
    """Return session metadata sorted by most-recently updated first.

    Auto-save files (prefixed with ``_auto_``) are excluded by default.
    """
    d = _dir()
    sessions: list[dict] = []
    for fp in d.glob("*.json"):
        if not include_auto and fp.stem.startswith("_auto_"):
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            sessions.append({
                "name":          data.get("name", fp.stem),
                "updated":       data.get("updated", 0),
                "message_count": len(data.get("messages", [])),
                "provider":      data.get("provider", "?"),
                "model":         data.get("model", "?"),
                "filename":      fp.name,
            })
        except Exception:
            continue
    return sorted(sessions, key=lambda x: x["updated"], reverse=True)


def format_sessions_table() -> str:
    """Return a formatted table of saved sessions for display."""
    sessions = list_sessions()
    if not sessions:
        return "No saved sessions found.\n  Use /session save [name] to save the current session."

    lines = [f"{'NAME':<30} {'MSGS':>4}  {'UPDATED':<20}  {'PROVIDER/MODEL'}"]
    lines.append("-" * 75)
    for s in sessions:
        ts    = time.strftime("%Y-%m-%d %H:%M", time.localtime(s["updated"]))
        model = f"{s['provider']}/{s['model']}"[:28]
        lines.append(f"{s['name']:<30} {s['message_count']:>4}  {ts:<20}  {model}")
    return "\n".join(lines)
