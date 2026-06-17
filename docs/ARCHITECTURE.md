# Dan Architecture

This document maps the module layout, ownership, and dependency relationships for Dan v2.5.x. Read this before making structural changes, adding new modules, or proposing refactors.

Last updated: 2026-06-09 (steward pass 20) — reflects GUI decoupling pass, tool consolidation, deprecation annotations, and scripts additions from steward passes 5–19.

---

## Entry Points

| File | Role |
|---|---|
| `Dan.py` | CLI REPL — the primary entry point for terminal use. Contains the main loop, argument parsing, `--doctor` diagnostics, and startup flow. |
| `dan_gui_modern.py` | **Supported** desktop shell. Claude-inspired, Dan-branded, theme-aware. Inherits from `ctk.CTk` and `DanControllerMixin` directly — no longer coupled to `dan_gui.py`. |
| `dan_gui.py` | **Deprecated** legacy visual shell. No external callers remain. Caller audit complete (steward pass 14); deprecation header added. Pending deletion — requires explicit user approval (Destructive Action Gate). |

`Dan.py` and `dan_gui_modern.py` are the two user-facing paths. Everything else is a library or support module.

---

## Module Groups

### Agent Layer

| Module | Role |
|---|---|
| `agent.py` | Core agent loop — drives the LLM conversation with tool calls. Both CLI and GUI paths use this. |
| `context_mgr.py` | Token usage tracking and conversation compaction. |
| `cost_tracker.py` | Token and cost accounting across sessions. |
| `session_mgr.py` | Conversation session persistence — save, load, list. |

### Provider Layer

| Module | Role |
|---|---|
| `providers.py` | Provider abstraction and selection. Entry point for `get_provider()`. Includes API key rotation. |
| `provider_types.py` | Shared types: `Message`, `ToolCall`, `ProviderResponse`, etc. |
| `provider_anthropic.py` | Anthropic (Claude) adapter. |
| `provider_openai.py` | OpenAI (GPT) adapter. |
| `provider_ollama.py` | Ollama (local models) adapter. |
| `provider_venice.py` | Venice adapter. |
| `provider_common.py` | Shared provider utilities. |
| `api_config.py` | Persistent provider and key settings (reads from `.env` / environment). |

### Tool Registry

| Module | Role |
|---|---|
| `tool_registry.py` | Tool registration, lookup, and dispatch. Central registry all tools register into. Includes audit log wiring and optional Level 3 confirmation gate. |
| `tools.py` | **Primary** core tool implementation — file, bash, search tools with full security annotations, async read, and output truncation. |
| `tools_secure.py` | **Deprecated** — original secure tool layer. All functionality consolidated into `tools.py` (steward pass 9). No Python file imports it except a historical comment in the test suite. Pending deletion — requires explicit user approval. |
| `security_utils.py` | Path validation, command allowlist (`SAFE_COMMANDS` + `RESTRICTED_COMMAND_REQUIREMENTS`), input sanitization, URL validation, `ToolAuditLog`. See `docs/SECURITY_BOUNDARIES.md`. |

### Tool Families (Packages)

Each package has an `__init__.py` that exports a `register_*_tools()` function. All families are registered through `dan_gui_support.register_all_tools()`.

| Package | Role |
|---|---|
| `actions/` | Reusable automation templates (slash-command actions). |
| `knowledge/` | Persistent memory system across sessions — ingest, search, list. |
| `web/` | Web fetch, search, and scraping tools. |
| `workers/` | Worker pool — parallel sub-agent delegation. |

### Development Tools

| Module | Role |
|---|---|
| `code_tools.py` | Test runner, linter, formatter, symbol analysis. |
| `code_execution.py` | Sandboxed Python code execution. |
| `git_tools.py` | Git integration — status, diff, add, commit, log. |
| `project_tools.py` | Project context tools — file listing, structure, search. |
| `project_context.py` | Project context state — active project, working directory. |
| `project_indexer.py` | Project indexing and scan map helpers. |
| `codebase_index.py` | Symbol index and codebase search for LLM context. |
| `skills.py` | Skills — task templates adapted from external skill repos. |

### Optional Tool Families

These are registered only when their dependencies are available. A missing dependency is silently skipped at startup.

| Module | Dependencies | Role |
|---|---|---|
| `image_tools.py` | `Pillow`, `pytesseract`, `opencv-python`, `easyocr` | Image read, OCR, visual understanding. |
| `ml_tools.py` | `pandas`, `scikit-learn`, `joblib` | Local ML inference and data analysis. |
| `auth_tools.py` | `auth_system.py` | Local auth-state management. |

### Auth System

| Module | Role |
|---|---|
| `auth_system.py` | Local credential store and auth-state management. Not network-backed. |
| `auth_tools.py` | Tool wrappers around `auth_system`. |

### GUI Layer

| Module | Role |
|---|---|
| `dan_gui.py` | **Deprecated** legacy visual shell (`DanGUI`). No longer a base class of `DanModernGUI`. No external callers. Awaiting deletion approval. |
| `dan_gui_controller.py` | `DanControllerMixin` — extracted non-visual controller logic (provider init, shortcuts, session load, shared helpers). Both GUI shells inherit from this. |
| `dan_gui_modern.py` | `DanModernGUI(ctk.CTk, DanControllerMixin)` — the **supported** desktop shell. Inherits window behaviour from CTk and controller from `DanControllerMixin`. Self-contained. |
| `dan_gui_support.py` | Pure helpers + `register_all_tools()`. No GUI imports; testable in isolation. |
| `dan_gui_theme.py` | Theme token definitions (dark/light). |
| `dan_gui_components.py` | Reusable UI helpers and chat widgets. |
| `gui_compat.py` | CustomTkinter availability check and graceful fallback stubs. |

### Configuration And Verification

| Module | Role |
|---|---|
| `config.py` | Constants: `APP_NAME`, `APP_VERSION`, `USER_DATA_DIR`, `PROJECT_DATA_DIR`, provider defaults, limits. |
| `system_verification.py` | Manual system verification helpers — checks runtime environment. |

### Scripts

| Script | Role |
|---|---|
| `scripts/build_windows.py` | PyInstaller portable build for GUI and CLI. Supports `--installer` / `--installer-only` for Inno Setup. Wires icon if `assets/dan_icon.ico` is present. |
| `scripts/verify_windows_build.py` | Verifies packaged output shape after build. |
| `scripts/smoke_windows_cli.py` | Packaged CLI smoke test — boots the built executable. |
| `scripts/repo_health.py` | Repository health audit — compileall, pytest, ruff. |
| `scripts/scan_secrets.py` | Git-aware secret scanner — Anthropic, OpenAI, Venice, AWS, generic credential patterns. Exit code 0/1/2. |
| `scripts/with_server.py` | MCP server integration helper. |

---

## Dependency Graph (Simplified)

```
Dan.py / dan_gui_modern.py
  └─ agent.py
       └─ tool_registry.py ← tools.py / code_tools.py / git_tools.py / ...
            └─ security_utils.py (path/command validation, ToolAuditLog)
  └─ providers.py
       └─ provider_anthropic.py / provider_openai.py / provider_ollama.py / provider_venice.py
            └─ provider_types.py
  └─ context_mgr.py / cost_tracker.py / session_mgr.py
  └─ config.py (no imports from Dan itself)

dan_gui_modern.py (DanModernGUI)
  └─ ctk.CTk (window)
  └─ dan_gui_controller.py (DanControllerMixin — controller logic)
       └─ dan_gui_support.py → register_all_tools()
            └─ actions / knowledge / web / workers / skills
  └─ dan_gui_theme.py
  └─ dan_gui_components.py
  └─ gui_compat.py

dan_gui.py (DanGUI — DEPRECATED, no longer in the live dependency chain)
```

---

## Known Coupling Issues

- **`dan_gui.py` coupling is resolved.** `DanControllerMixin` (in `dan_gui_controller.py`) holds all shared non-visual controller logic. `DanModernGUI` now inherits from `ctk.CTk + DanControllerMixin` directly. `dan_gui.py` is fully decoupled from the live dependency chain and is pending deletion (user approval required). No active coupling remains.

- **Flat top-level module layout.** All Python modules live at the repository root. This is serviceable for a project of this size but will become harder to navigate as optional tool families grow. The packages (`actions/`, `knowledge/`, `web/`, `workers/`) are the natural model — future modules should follow that shape rather than adding more top-level `.py` files.

- **`tools_secure.py` is deprecated.** All functionality was consolidated into `tools.py` (steward pass 9). `tools_secure.py` is no longer imported by any active module. Pending deletion — requires explicit user approval.

---

## Module Ownership Summary

| Area | Canonical Files | Status |
|---|---|---|
| CLI entry | `Dan.py` | Active |
| GUI entry (supported) | `dan_gui_modern.py` | Active |
| GUI entry (legacy) | `dan_gui.py` | **Deprecated** — decoupled; no callers; pending deletion (user approval required) |
| GUI controller | `dan_gui_controller.py` | Active — `DanControllerMixin` used by `DanModernGUI` |
| GUI support | `dan_gui_support.py`, `dan_gui_theme.py`, `dan_gui_components.py`, `gui_compat.py` | Active |
| Agent loop | `agent.py` | Active |
| Providers | `providers.py`, `provider_*.py`, `provider_types.py`, `api_config.py` | Active |
| Tool registry | `tool_registry.py` | Active |
| Core tools | `tools.py` (canonical), `tools_secure.py` (deprecated, pending deletion) | Active |
| Security | `security_utils.py` | Active |
| Development tools | `code_tools.py`, `code_execution.py`, `git_tools.py`, `project_tools.py`, `project_indexer.py`, `codebase_index.py` | Active |
| Tool packages | `actions/`, `knowledge/`, `web/`, `workers/`, `skills.py` | Active |
| Optional tools | `image_tools.py`, `ml_tools.py`, `auth_tools.py`, `auth_system.py` | Optional |
| Session / context | `session_mgr.py`, `context_mgr.py`, `cost_tracker.py` | Active |
| Configuration | `config.py`, `system_verification.py` | Active |
| Build/release | `scripts/`, `pyproject.toml`, `requirements*.txt` | Active |
| Docs | `README.md`, `INSTALL.md`, `ONBOARDING.md`, `RELEASE.md`, `ROADMAP.md`, `PROJECT_INTEGRITY.md`, `docs/` | Active |
