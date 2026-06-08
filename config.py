"""Dan configuration and constants."""

import os
import sys
from pathlib import Path

# Branding
APP_NAME = "Dan"
APP_VERSION = "2.5.1"
APP_TAGLINE = "Development Automation Network"

# ── Data directories ──────────────────────────────────────────────────────────
# User-global state (knowledge, sessions, auth) lives under the OS-appropriate
# per-user roaming-data directory so it survives reinstalls and is not confused
# with the project folder.
#
#   Windows : %APPDATA%\Dan\   (C:\Users\<name>\AppData\Roaming\Dan\)
#   Other   : ~/.dan/
#
# Project-local state (per-repo knowledge, project index, auth cache) lives in
# .dan/ inside the working directory. This name avoids colliding with the
# Dan.py entry-point script and the Dan/ folder that older builds used; .dan/
# is already listed in .gitignore so it is never accidentally committed.
if sys.platform == "win32":
    _appdata = Path(os.environ.get("APPDATA", str(Path.home())))
    USER_DATA_DIR: Path = _appdata / "Dan"
else:
    USER_DATA_DIR = Path.home() / ".dan"

PROJECT_DATA_DIR: Path = Path(".dan")

# Provider config
DEFAULT_PROVIDER = os.environ.get("DAN_PROVIDER", "ollama")
DEFAULT_MODEL = os.environ.get("DAN_MODEL", "qwen2.5-coder:7b")

# Context limits per model family
CONTEXT_LIMITS: dict[str, int] = {
    "claude": 200_000,
    "gpt-4": 128_000,
    "gpt-3.5": 16_000,
    "venice": 128_000,
    "ollama": 32_000,
}

# Compaction
COMPACTION_THRESHOLD = 0.75  # compact when context is 75% full
TOKEN_ESTIMATE_RATIO = 3.5  # chars per token estimate

# Workers
MAX_WORKERS = 3
MAX_WORKER_DEPTH = 3


# Colors
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
