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

Verified on 2026-06-08 (steward pass 5):

- `python -m pytest -q` passes (on real Windows; Linux sandbox has a `.pytest_cache` mount permission issue)
- `python -m ruff check .` passes
- CI exists and runs lint plus tests
- Core runtime systems exist for CLI, GUI, providers, tool registry, security validation, project indexing, and repo health checks
- `dan_gui_modern.py` is the supported desktop shell; `dan_gui.py` remains a legacy/backing GUI path
- the PyInstaller portable GUI packaging path has been executed locally and produces a real Windows build output
- GitHub Actions has Windows packaging jobs for GUI and CLI with smoke tests
- Phases 2–6 completed in this pass: repository cleanup, Python/Windows support matrix, startup hardening, release documentation, security boundary documentation, architecture documentation
- 2026-06-11: repaired CI — unpinned ruff (0.15.x) began flagging F821 on quoted `ToolAuditLog` annotations in `tool_registry.py` (fixed via `TYPE_CHECKING` import), and the windows-packaging job ran pytest without installing it (now installs `requirements-dev.txt`); full suite (232 tests) and packaging tests verified locally on ruff 0.15.16

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

### Completed In This Security Hardening Pass (2026-06-08 steward passes 5–6)

- Added `ToolAuditLog` class to `security_utils.py`: thread-safe, fail-safe, append-only JSONL audit log; records tool name, input parameter *keys* (not values), safety level, outcome, and duration per invocation
- Added `safety_level: int` field to `Tool` dataclass in `tool_registry.py` (1=read-only, 2=standard, 3=elevated); `register()` and `register_tool()` accept the new parameter
- Added confirmation gate to `tool_registry.execute_tool`: `set_confirmation_gate(fn)` installs a consent callback invoked before any Level 3 tool; denials record `"denied"` to the audit log; gate is off by default (backward compatible)
- Wired `ToolAuditLog` singleton into `execute_tool`: every success, error, and denial is recorded; audit log path is `USER_DATA_DIR / "tool_audit.log"`
- Added `tests/test_tool_registry_audit.py` with 15 tests covering audit log writes, JSONL validity, truncation, I/O failure silence, gate allow/deny/exception, and integration through `execute_tool`
- Updated `docs/SECURITY_BOUNDARIES.md`: added Tool Audit Log section, added confirmation gate documentation to Level 3 section, revised Known Gaps

### Completed In This Security Hardening Pass (2026-06-08 steward pass 5)

- Added `scripts/scan_secrets.py`: git-aware secret scanner for Anthropic, OpenAI, Venice, AWS, and generic credential assignment patterns; exit code 0/1/2; inline `# noqa: scan-secrets` suppression; runs without external dependencies
- Added `test_scan_secrets_script_exists_and_is_importable` and `test_scan_secrets_finds_no_real_secrets_in_tracked_files` to `tests/test_repo_hygiene.py`
- Updated `docs/SECURITY_BOUNDARIES.md`: removed "no secret scanning" from Known Gaps; documented the scanner and its test in Secret Handling section

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

## Phase 7 — Release Distribution (in progress)

Goal: pushing a version tag produces a GitHub release with downloadable Windows artifacts (the portable GUI and CLI builds that `scripts/build_windows.py` produces today) without manual steps. A single signed installer `.exe` remains the long-term target, but it is gated on the deferred installer and code-signing work listed below and is NOT an exit criterion for this phase.

Deferred-pending-approval items remain explicitly listed; this phase only executes the additive, low-risk pieces.

- [ ] 7.1 Add `.github/workflows/release.yml` that builds and uploads the portable Windows artifacts to the GitHub release on version tags (extends to the installer `.exe` only after the deferred installer work is approved and merged)
- [ ] 7.2 Add size-based rotation + retention policy to `ToolAuditLog` (`security_utils.py`)
- [ ] 7.3 Add session + auto-save retention pruning in `session_mgr.py`
- [ ] 7.4 Persist crash/interrupt checkpoint across process restart and auto-offer resume on next launch
- [ ] 7.5 Enforce `MAX_WORKER_DEPTH` in `workers/__init__.py` before sub-agent spawn

Deferred — require user approval per `PROJECT_INTEGRITY.md`:
- Removal of `tools_secure.py` (566 LOC duplicate of `tools.py`)
- Retirement of `dan_gui.py` legacy shell
- Windows icon asset creation
- Code-signing infrastructure (Azure KeyVault / self-hosted signing agent)

## Phase 8 — Code Hygiene + Security Test Depth

Goal: the security primitives have dedicated unit tests; lint/format is enforced locally; error surfaces are consistent.

- [ ] 8.1 Add `.pre-commit-config.yaml` (ruff, black, end-of-file-fixer, trailing-whitespace)
- [ ] 8.2 Introduce `errors.py` with a `DanError` hierarchy and adopt it in `tool_registry.py` and `security_utils.py` gate paths
- [ ] 8.3 Unit tests for `SecurePathValidator` (traversal, symlink, root-bounds, Windows drive cases)
- [ ] 8.4 Unit tests for `sanitize_user_input` edge cases (null bytes, control chars, max-length rejection)
- [ ] 8.5 Unit tests for `validate_fetch_url` SSRF protections (private CIDRs, link-local, IPv6, redirect chains)

## Phase 9 — CLI Polish + Reproducibility

Goal: the CLI is friendlier to first-time users; installs are reproducible byte-for-byte.

- [ ] 9.1 PowerShell tab-completion module (`scripts/completions/dan.psm1`)
- [ ] 9.2 Cleaner CLI error surfacing in `Dan.py` `main()` — friendly summary by default, full traceback only under `--verbose`
- [ ] 9.3 Generate and commit `uv.lock`; document `uv pip install --frozen` path in `INSTALL.md`

## Phase 10 — Observability + Operator Tools

Goal: an operator can answer "what did Dan run last week and what did it cost?" without grepping JSONL by hand.

- [ ] 10.1 `scripts/audit_query.py` + `/audit` slash command — query the audit log by tool name, time window, outcome
- [ ] 10.2 Persistent cost log (append-only JSONL) written by `cost_tracker.py`, with a `/cost` summary view

## Phase 11 — Documentation Site

Goal: `docs/` is served as a navigable site rather than a folder of markdown.

- [ ] 11.1 mkdocs scaffolding (`mkdocs.yml`, nav for existing docs, GitHub Pages workflow)

## Phase 12 — Backlog (not scheduled)

Captured for visibility; promoted into a phase only when prerequisites are met:
- First-run wizard (provider chooser, key entry, test-call)
- Accessibility audit of `dan_gui_modern.py`
- Mypy adoption (start with `security_utils.py`, `tool_registry.py`, `providers.py`)
- Coverage ratchet (baseline + `fail_under` in CI)
- Plugin / extension authoring guide
- Sample-projects quickstart in `docs/`
- Auto-update mechanism for installed Dan

## Backlog: Known Gaps And Future Work

These items were identified during the 2026-06-06 through 2026-06-08 steward passes and are deferred for future work.

### Code Quality

- `tools.py` and `tools_secure.py` overlap — merge into a single secure implementation (non-trivial; keep both until a safe migration path is designed)
- `dan_gui.py` still mixes legacy visual shell code with controller behavior used by `DanModernGUI` — extract remaining controller logic before retiring the legacy shell
- Top-level flat module layout is serviceable but will become harder to navigate as optional tool families grow — long-term migration toward the `actions/`/`knowledge/`/`web/`/`workers/` package model

### Security Hardening

- Command allowlist permits `powershell` and `cmd`, which can bypass other restrictions if invoked deliberately
- Confirmation gate is opt-in and off by default — autonomous workflows must install it explicitly at session start

### Release Infrastructure

- Windows installer (MSIX / Inno Setup) — not yet started
- Automated release artifact upload in GitHub Actions — not yet started
- Signed Windows executables — not yet started

### Documentation

- `docs/AUTHENTICATION_SYSTEM.md` audited and corrected against `auth_system.py` ✓ (2026-06-08 steward pass 4) — fixed: require_auth default, bootstrap key delivery, salt behavior, data file locations, role permission details, removed inapplicable network-service advice
- `CONTRIBUTING.md` aligned with current project posture ✓ (2026-06-08 steward pass 3)

### Known Benign Issues

- pytest collection in the Linux sandbox fails due to a `.pytest_cache` mount permission issue; tests pass on the real Windows machine — not a code defect

## Out Of Scope Until Reopened

- major architecture rewrites without a specific verified pain point
- dependency churn for its own sake
- deleting historical files without confirming they are truly safe to remove
- release claims such as “production ready” before packaging and Windows verification are complete
