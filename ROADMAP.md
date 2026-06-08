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

Verified on 2026-06-08:

- `python -m pytest -q` passes
- `python -m ruff check .` passes
- CI exists and runs lint plus tests
- Core runtime systems exist for CLI, GUI, providers, tool registry, security validation, project indexing, and repo health checks
- `dan_gui_modern.py` is the supported desktop shell; `dan_gui.py` remains a legacy/backing GUI path
- the PyInstaller portable GUI packaging path has been executed locally and produces a real Windows build output
- GitHub Actions now has a Windows packaging job that builds and verifies the supported GUI artifact
- GitHub Actions now builds the CLI companion and runs a packaged CLI smoke test
- packaged GUI and CLI artifacts both verify successfully from the current worktree
- The repo still has root-level clutter, packaging gaps, and unfinished Windows release discipline

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

## Active Phase 2: Repository Cleanup And Information Architecture

Goal: make the repository discoverable, lower-noise, and safe to maintain.

Status: in progress (Phase 1 complete as of 2026-06-08; Phase 2 now active)

Tasks:

- reduce root-level markdown clutter by archiving historical one-off reports into a dedicated location
- normalize naming conventions across top-level files and folders
- resolve the `Dan` name collision between product name, runtime state folder, and top-level script
- continue extracting shared GUI controller behavior so the legacy visual shell can be retired safely

Exit criteria:

- root directory contains only active code, active docs, and necessary project files
- ambiguous or duplicated files are either retired, archived, or explicitly owned
- naming is consistent enough that a new maintainer can navigate the repo without guessing

## Active Phase 3: Windows Application Hardening

Goal: turn Dan from a working Python project into a disciplined Windows desktop product.

Status: planned

Tasks:

- harden `dan_gui_modern.py` as the official desktop shell and reduce its dependency on legacy GUI internals
- define the supported Python version and Windows support matrix
- define application data directories, log locations, and cache locations for Windows
- add robust startup diagnostics for GUI and packaged builds
- standardize error reporting, crash-safe behavior, and user-visible recovery messages
- review keyboard handling, console assumptions, and Windows-specific UX edges

Exit criteria:

- there is one clearly supported Windows desktop path
- app state locations are intentional and documented
- startup and failure modes are predictable

## Active Phase 4: Packaging, Installation, And Release Discipline

Goal: make Dan installable, runnable, and supportable as a real product.

Status: planned

Tasks:

- verify the new PyInstaller portable build path against real packaged output
- define installer or portable distribution strategy
- version releases intentionally and document release steps
- add packaged GUI launch or interaction smoke tests where practical

Exit criteria:

- a clean Windows machine can install or run Dan using documented steps
- the release path is repeatable and testable
- packaged startup is explicitly verified

## Active Phase 5: Security, Configuration, And Operational Boundaries

Goal: keep local execution powerful without becoming sloppy or unsafe.

Status: planned

Tasks:

- review command allowlists and shell execution boundaries
- tighten secret-handling expectations, scanning, and local auth-state hygiene
- centralize config loading rules and defaults
- document which tools are safe by default, optional, or restricted
- review how local auth artifacts are generated and stored
- add more explicit verification around sensitive operations and failure modes

Exit criteria:

- execution boundaries are documented and enforced consistently
- secret handling is explicit
- config and auth behavior are predictable

## Active Phase 6: Architecture And Maintainability Refinement

Goal: reduce accidental complexity without destabilizing the working runtime.

Status: planned

Tasks:

- map ownership of top-level modules and identify candidates for package consolidation
- reduce oversized or overlapping modules only when the split is low-risk and justified
- document the role of optional tool families such as vision and ML
- improve dependency ownership between runtime, dev, and optional requirements files
- expand tests when refactors touch security, execution, provider, or GUI-critical paths

Exit criteria:

- module boundaries are clearer
- optional features are separated cleanly from the core runtime
- future refactors have a documented target shape

## Backlog: Concrete Findings To Address

These are known cleanup or productionization items discovered during the 2026-06-06 audit and subsequent steward passes.

- `AGENTS.md` and `CLAUDE.md` had unrelated Lucid/WinUI content and needed replacement
- `ROADMAP.md` was written as a generic audit prompt instead of a real roadmap
- `CODEX.md` was overly broad and partially duplicated the old prompt material
- `USER_CREATION_GUIDE.md` at repo root is a demo chat artifact (not real documentation): contains AI-generated sample user data and promotional phrasing ("USERS SUCCESSFULLY CREATED!"); recommend removal with user approval before Phase 2 cleanup starts
- `AUTHENTICATION_SYSTEM.md` at repo root documents the auth system that exists in code (`auth_system.py`, `auth_tools.py`); should be reviewed for accuracy and either retained as active reference or moved to a `docs/` folder in Phase 2
- pytest collection fails in the mounted sandbox environment due to a `.pytest_cache` permission issue (read-only mount); tests pass on the real Windows machine where the repo lives — not a code defect
- `dan_gui.py` still mixes legacy visual shell code with controller behavior used by the supported modern shell
- packaging and installer strategy are absent
- top-level flat module layout is still serviceable, but not yet clean enough for long-term product maintenance
- local runtime artifacts under `Dan/` exist on disk and need a clearer policy in docs and packaging

## Out Of Scope Until Reopened

- major architecture rewrites without a specific verified pain point
- dependency churn for its own sake
- deleting historical files without confirming they are truly safe to remove
- release claims such as “production ready” before packaging and Windows verification are complete
