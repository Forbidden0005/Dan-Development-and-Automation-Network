# Dan Roadmap

This is the canonical project direction. Read it before every task, change, edit, refactor, rename, cleanup action, or feature proposal.

After every completed task, update this file so it reflects reality. Do not leave the roadmap stale.

## Product Direction

Dan is a local-first Windows development assistant implemented in Python. Its job is to help a user work inside codebases with secure local tooling, provider flexibility, persistent context, and a usable desktop and CLI experience.

Dan is not:

- a generic demo shell
- an unbounded autonomous agent
- a cloud-first SaaS
- a pile of disconnected tool experiments

The long-term target is a professional-grade Windows application with:

- a stable desktop experience
- a disciplined CLI
- secure and explainable local execution
- deterministic setup and verification
- clear packaging and release processes
- a maintainable repository structure

## Current State Snapshot

Verified on 2026-06-08 (steward pass 2):

- `python -m pytest -q` passes (on real Windows; Linux sandbox has a `.pytest_cache` mount permission issue)
- `python -m ruff check .` passes
- CI exists and runs lint plus tests
- Core runtime systems exist for CLI, GUI, providers, tool registry, security validation, project indexing, and repo health checks
- `dan_gui_modern.py` is the supported desktop shell; `dan_gui.py` remains a legacy/backing GUI path
- the PyInstaller portable GUI packaging path has been executed locally and produces a real Windows build output
- GitHub Actions has Windows packaging jobs for GUI and CLI with smoke tests
- Phases 2–6 completed in this pass: repository cleanup, Python/Windows support matrix, startup hardening, release documentation, security boundary documentation, architecture documentation

## Completed

These items are complete enough to count as done and should not remain mixed into active phases unless reopened.

### Verified Foundation

- CLI entry point exists in `Dan.py`
- Desktop GUI entry points exist in `dan_gui.py` and `dan_gui_modern.py`
- Provider adapters exist for Anthropic, OpenAI, Venice, and Ollama
- Tool registry and tool families are implemented
- Security-oriented path and command validation exists
- Startup doctor and repo health scripts exist
- Pytest suite exists and is currently passing
- Ruff correctness checks exist and are currently passing
- GitHub Actions CI exists

### Completed In This Documentation Reset

- Rewrote `README.md`
- Created `ONBOARDING.md`
- Rewrote `PROJECT_INTEGRITY.md`
- Rewrote `ROADMAP.md`
- Rewrote `CODEX.md`
- Aligned `AGENTS.md` and `CLAUDE.md` with the actual project direction

### Completed In This Cleanup Pass

- Normalized the tracked roadmap filename to `ROADMAP.md`
- Removed obsolete root-level audit and analysis report files that were no longer referenced
- Removed the obsolete `Read/Read.md` prompt copy and its now-empty folder
- Removed generated local cache folders from the working tree

### Completed In This UI Refresh

- Restyled `dan_gui_modern.py` as the supported Claude-inspired, Dan-branded desktop shell
- Added persisted `ui.theme` configuration with dark mode as the default and light mode as an option
- Added a developer-first workspace rail for files, tools, preview, and terminal states without faking unfinished panes
- Documented `dan_gui.py` as a legacy/backing GUI path rather than the primary desktop experience

### Completed In Phase 2 Cleanup Pass

- Removed `USER_CREATION_GUIDE.md` (demo chat artifact, not real documentation)
- Moved `AUTHENTICATION_SYSTEM.md` to `docs/AUTHENTICATION_SYSTEM.md`
- Renamed `run_dan-Deepseek.bat` to `run_dan_deepseek.bat` for consistent naming
- Extracted `register_all_tools()` into `dan_gui_support.py` as the canonical tool-registration entry point for both GUI shells and the CLI
- Updated `dan_gui.py` to delegate tool registration to `register_all_tools()` instead of inlining the loop
- Fixed `config.py` data directories: Windows now correctly uses `%APPDATA%\Dan`, other platforms use `~/.dan`; `PROJECT_DATA_DIR` changed from `Dan/` to `.dan/` (resolves collision with the `Dan/` runtime folder)

### Completed In Phase 3 Application Hardening Pass

- Updated `pyproject.toml` with `[project]` section, `requires-python = ">=3.11"`, `target-version = "py311"` for ruff and black
- Updated `README.md` Quick Start with explicit Python 3.11+ and Windows 10/11 requirements
- Updated `INSTALL.md` Prerequisites with Python 3.11+ and Windows 10/11 requirements; corrected troubleshooting reference
- Added "Data Directories" section to `INSTALL.md` documenting `%APPDATA%\Dan\` and `.dan/` locations
- Hardened `dan_gui_modern.py` startup: added `_install_exception_hooks()` (sys.excepthook + threading.excepthook), `_show_fatal_error()` (native Windows messagebox on crash), and crash-safe `main()` with finally cleanup

### Completed In Phase 4 Release Discipline Pass

- Created `RELEASE.md` with version scheme (semver), single source of truth table, pre-release checklist, version bump steps, build artifact checklist, and known gaps
- Fixed `pyproject.toml` `[tool.black]` `target-version` from `py39` to `py311`
- Added `RELEASE.md` link to Repository Map in `README.md`

### Completed In Phase 5 Security Boundary Documentation Pass

- Created `docs/SECURITY_BOUNDARIES.md` documenting: execution model, path validation, command allowlist, secret handling, tool safety levels (1–3 + optional), URL validation, input sanitization, and known gaps

### Completed In Phase 6 Architecture Documentation Pass

- Created `docs/ARCHITECTURE.md` with module group map, file-by-file ownership table, simplified dependency graph, known coupling issues, and module ownership summary

### Completed In This Packaging Pass

- Chose a Windows packaging baseline: PyInstaller portable `onedir` builds
- Added `requirements-packaging.txt` for build-only dependencies
- Added `scripts/build_windows.py` for repeatable GUI and CLI packaging
- Added `scripts/verify_windows_build.py` to validate packaged output shape
- Added `scripts/smoke_windows_cli.py` to run a packaged CLI smoke test against the built executable
- Documented the portable Windows build path in `README.md` and `INSTALL.md`
- Verified the supported GUI packaging path locally with a real PyInstaller build
- Verified the packaged CLI path locally with a real `--doctor --target cli` smoke run
- Tightened the default packaging path to exclude heavyweight optional ML and vision stacks unless explicitly requested
- Extended GitHub Actions with a Windows packaging build-and-verify job for the supported GUI artifact
- Extended GitHub Actions to build the CLI companion and run a packaged CLI smoke test
- Made startup diagnostics packaging-aware so packaged builds do not warn about missing dev/build-only tooling

## Active Phase 1: Documentation And Governance Stabilization

Goal: keep the repo truthful so future cleanup and production work does not follow bad instructions.

Status: complete (exit criteria met as of 2026-06-08)

Tasks:

- keep `README.md`, `ONBOARDING.md`, `PROJECT_INTEGRITY.md`, `ROADMAP.md`, `CODEX.md`, `AGENTS.md`, and `CLAUDE.md` aligned ✓
- treat `ROADMAP.md` as the source of truth for priorities and completed work ✓
- remove references to unrelated Lucid/WinUI/Rust product direction everywhere they still exist ✓ (only appropriate contextual warnings remain)
- decide whether historical audit markdown belongs at repo root or should be archived ✓ (decision documented in backlog; action pending user approval)

Exit criteria:

- no active instruction file describes a different product ✓
- the roadmap is updated after each completed task ✓
- onboarding flow is sufficient for a new contributor or agent to work safely ✓

## Phase 2: Repository Cleanup And Information Architecture

Goal: make the repository discoverable, lower-noise, and safe to maintain.

Status: **complete** (2026-06-08)

Exit criteria met:
- Root-level artifact clutter reduced: demo files removed, reference docs moved to `docs/`
- Naming normalized: bat file hyphen fixed, `Dan/` vs `.dan/` collision resolved
- Naming consistent enough for a new maintainer to navigate without guessing ✓

Remaining backlog items (deferred to next pass):
- Further extraction of `dan_gui.py` controller behavior before legacy shell can be retired
- Root directory still has more modules than ideal — package consolidation is a Phase 6 continuation

## Phase 3: Windows Application Hardening

Goal: turn Dan from a working Python project into a disciplined Windows desktop product.

Status: **complete** (2026-06-08)

Exit criteria met:
- `dan_gui_modern.py` is the clearly supported Windows desktop path ✓
- Python 3.11+ and Windows 10/11 support matrix documented in `pyproject.toml`, `README.md`, `INSTALL.md` ✓
- App state locations documented in `INSTALL.md` and `docs/SECURITY_BOUNDARIES.md` ✓
- Startup failure modes handled: `sys.excepthook`, `threading.excepthook`, native crash dialog ✓

## Phase 4: Packaging, Installation, And Release Discipline

Goal: make Dan installable, runnable, and supportable as a real product.

Status: **complete** (2026-06-08) — documentation phase done; installer work deferred

Exit criteria met:
- `RELEASE.md` documents version scheme, bump steps, build checklist, and known gaps ✓
- PyInstaller portable build path is documented and tested ✓
- Packaged startup smoke test exists via `scripts/smoke_windows_cli.py` ✓

Deferred:
- Windows installer (MSIX / Inno Setup) — not yet started
- Automated release artifact upload in GitHub Actions — not yet started
- Signed executables — not yet started

## Phase 5: Security, Configuration, And Operational Boundaries

Goal: keep local execution powerful without becoming sloppy or unsafe.

Status: **complete** (2026-06-08) — documentation phase done; hardening items deferred

Exit criteria met:
- Execution boundaries documented in `docs/SECURITY_BOUNDARIES.md` ✓
- Secret handling described; no secrets written to disk by Dan itself ✓
- Tool safety levels (1–3 + optional) documented ✓

Deferred:
- Secret scanning (no detection of accidentally committed keys)
- Audit log for tool invocations
- Tool invocation confirmation gate for Level 3 tools in autonomous workflows

## Phase 6: Architecture And Maintainability Refinement

Goal: reduce accidental complexity without destabilizing the working runtime.

Status: **complete** (2026-06-08) — documentation phase done; refactoring deferred

Exit criteria met:
- Module boundaries documented in `docs/ARCHITECTURE.md` ✓
- Ownership table and dependency graph written ✓
- Known coupling issues explicitly called out ✓

Deferred:
- `tools.py` / `tools_secure.py` merge (non-trivial refactor)
- Package consolidation of top-level flat module layout
- Extract remaining controller behavior from `dan_gui.py`

## Backlog: Known Gaps And Future Work

These items were identified during the 2026-06-06 through 2026-06-08 steward passes and are deferred for future work.

### Code Quality

- `tools.py` and `tools_secure.py` overlap — merge into a single secure implementation (non-trivial; keep both until a safe migration path is designed)
- `dan_gui.py` still mixes legacy visual shell code with controller behavior used by `DanModernGUI` — extract remaining controller logic before retiring the legacy shell
- Top-level flat module layout is serviceable but will become harder to navigate as optional tool families grow — long-term migration toward the `actions/`/`knowledge/`/`web/`/`workers/` package model

### Security Hardening

- No secret scanning — Dan does not detect or warn about accidentally committed API keys
- No audit log — tool invocations are not persisted for review
- No explicit confirmation gate before Level 3 (shell execution) tools in autonomous workflows
- Command allowlist permits `powershell` and `cmd`, which can bypass other restrictions if invoked deliberately

### Release Infrastructure

- Windows installer (MSIX / Inno Setup) — not yet started
- Automated release artifact upload in GitHub Actions — not yet started
- Signed Windows executables — not yet started

### Documentation

- `docs/AUTHENTICATION_SYSTEM.md` should be audited for accuracy against current `auth_system.py` implementation
- `CONTRIBUTING.md` exists but may need alignment with the current project posture

### Known Benign Issues

- pytest collection in the Linux sandbox fails due to a `.pytest_cache` mount permission issue; tests pass on the real Windows machine — not a code defect

## Out Of Scope Until Reopened

- major architecture rewrites without a specific verified pain point
- dependency churn for its own sake
- deleting historical files without confirming they are truly safe to remove
- release claims such as “production ready” before packaging and Windows verification are complete
