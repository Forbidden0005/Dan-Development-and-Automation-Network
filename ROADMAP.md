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

Verified on 2026-06-16:

- `python -m pytest -q` passes (on real Windows; Linux sandbox has a Python 3.10 / `.pytest_cache` mount permission issue preventing sandbox verification)
- `python -m ruff check .` passes (on real Windows; sandbox shows stale FUSE view of `pyproject.toml`)
- CI exists and runs lint plus tests
- Core runtime systems exist for CLI, GUI, providers, tool registry, security validation, project indexing, and repo health checks
- Dan now has a real in-process sub-agent foundation instead of a worker stub: durable sessions, automatic file claims on mutation, conflict blocking, runner-backed parallel execution, and CLI inspection/approval controls
- The supported desktop shell now exposes sub-agent state through a real `Agents` workspace pane, and sub-agent shell approvals now cover destructive delete/rename and package-uninstall commands
- `dan_gui_modern.py` is the supported desktop shell; `dan_gui.py` is deprecated (no callers confirmed, deletion pending user approval)
- the PyInstaller portable GUI packaging path has been executed locally and produces a real Windows build output
- GitHub Actions has Windows packaging jobs for GUI and CLI with smoke tests
- `.github/workflows/release.yml` added: tag-triggered GitHub Release workflow with installer asset upload
- `assets/dan_icon.ico` present and wired: `SetupIconFile` active in `Dan.iss`, `--icon` conditional in `build_windows.py`
- `RELEASE.md` updated: stale "What Is Not Yet Done" section corrected; installer build instructions and automated release workflow section added (reflects steward passes 11–13 work); icon gap removed (steward pass 19)
- `python -m pytest -q` passes with `739 passed` and one known `.pytest_cache` permission warning
- `python -m pytest -q` passes with `743 passed` and one known `.pytest_cache` permission warning
- `python -m pytest -q` passes with `746 passed` and one known `.pytest_cache` permission warning
- `python -m pytest -q` passes with `747 passed` and one known `.pytest_cache` permission warning
- `python -m pytest -q` passes with `750 passed` and one known `.pytest_cache` permission warning
- `python -m pytest -q` passes with `751 passed` and one known `.pytest_cache` permission warning
- `python -m ruff check .` passes
- `python scripts/build_windows.py --target all` completes on real Windows and produces fresh GUI + CLI portable bundles
- `python scripts/verify_windows_build.py --target gui` passes
- `python scripts/verify_windows_build.py --target cli` passes
- `python scripts/smoke_windows_cli.py` passes against the packaged `DanCLI.exe`
- local installer compilation is now verified on this workstation: Inno Setup 6.7.3 is installed under `%LOCALAPPDATA%\Programs\Inno Setup 6\`, `python scripts/build_windows.py --installer-only` succeeds, and `dist/installer/Dan-2.5.1-setup.exe` is produced locally

- the default portable GUI + CLI bundles were rebuilt with explicit dev-only PyInstaller exclusions, and the shipped `_internal` trees no longer contain `IPython`, `black`, `ipykernel`, `jedi`, `mypy`, `parso`, `prompt_toolkit`, `pytest`, or `_pytest`

- `python scripts/build_windows.py --target gui --dry-run` now fails fast when `config.py`, `pyproject.toml`, and `installer/Dan.iss` drift on the release version
- the build and release paths now support optional Authenticode signing for `Dan.exe`, `DanCLI.exe`, and the installer when `signtool` plus certificate material are configured; published binaries remain unsigned until real certificate secrets are provided
- the tag-triggered GitHub release workflow now runs an explicit release-version sync dry-run before any Windows build step, and its comments/instructions now match the three-source version rule instead of the older two-source wording
- `python scripts/build_windows.py --target gui --dry-run --expect-version <version>` now proves whether a caller-supplied release version matches the synchronized repo version, and the tagged release workflow uses that gate before publishing
- `python scripts/release_artifacts.py` now generates `dist/release/SHA256SUMS.txt` and `dist/release/release-manifest.json` for the GUI exe, CLI exe, and installer, and the tagged GitHub release workflow publishes those integrity artifacts alongside the installer
- `python scripts/release_readiness.py` now provides a single local release-readiness verdict with explicit remediation steps, installer-artifact verification, and release-integrity verification; on this workstation it currently reports 9 checks, 8 passing, and exactly 1 blocking item: missing signing certificate material

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
- Fixed chat bubble sizing so reply width stays stable while user, assistant, and streaming message bubbles grow vertically to fit wrapped content without clipping overflow
- Fixed the chat-log regression caused by pre-layout wrapped-line measurement: message bubbles now fall back to logical-line sizing until the textbox has a real width, preventing invisible multi-thousand-pixel bubbles
- Compacted the supported desktop shell across the header, sidebar, right rail, and composer, and removed the dedicated welcome block after the first user message while restoring it on `new_chat()`
- Ran live-window visual QA against the real desktop shell, removed the redundant compact-header subtitle, and verified the tightened shell against an actual rendered Dan window instead of relying on unit tests alone
- Fixed build-only dependency diagnostics so installed `PyInstaller` is recognized correctly by the startup doctor and repo health checks
- Re-ran the supported portable Windows release path locally: GUI + CLI bundles built, both package verifiers passed, and the packaged CLI smoke test passed

### Completed In This Packaging Hardening Pass

- Added default PyInstaller exclusions for obvious dev-only module stacks: `IPython`, `black`, `ipykernel`, `jedi`, `mypy`, `parso`, `prompt_toolkit`, `pytest`, and `_pytest`
- Added packaging tests asserting those exclusions are present in the generated build command
- Rebuilt the portable GUI + CLI bundles on real Windows after the exclusion change
- Re-ran `scripts/verify_windows_build.py` for both targets and `scripts/smoke_windows_cli.py`; all passed after the exclusion change
- Inspected the shipped bundle contents under `dist/windows/Dan/Dan/_internal` and `dist/windows/DanCLI/DanCLI/_internal`; none of the excluded dev-only modules are present in the packaged runtime
- PyInstaller cross-reference reports still mention some excluded names as analyzed references, but the packaged runtime contents are clean; treat bundle contents and packaged smoke tests as the release-relevant evidence

### Completed In This Release Version Gate Pass

- Added a release-version consistency gate to `scripts/build_windows.py`
- The build path now reads and compares `config.py` `APP_VERSION`, `pyproject.toml` `[project].version`, and `installer/Dan.iss` `MyAppVersion` before any portable or installer build starts
- Added tests covering both the matching path and the mismatch failure path
- Verified the gate with `python scripts/build_windows.py --target gui --dry-run`; the build now prints the verified release version and fails fast on version drift instead of allowing a mismatched installer release
- Added an explicit Windows CI step that runs the same dry-run version gate before the first packaging build starts, so release drift fails with a clear signal in GitHub Actions

### Completed In This Optional Signing Support Pass

- Added optional Authenticode signing support to `scripts/build_windows.py` for the packaged GUI exe, CLI exe, and installer
- Added sign-tool discovery plus explicit `--sign`, `--sign-tool`, `--sign-cert`, `--sign-password`, and `--sign-timestamp-url` build options
- Default signing configuration now reads `DAN_SIGN_PFX`, `DAN_SIGN_PFX_PASSWORD`, and optional `DAN_SIGN_TIMESTAMP_URL`
- Dry-run builds now print the masked signing command so the release path can be inspected end-to-end without executing signtool
- Added unit tests covering signing configuration validation and signing-command generation
- Updated `.github/workflows/release.yml` so tagged releases sign artifacts automatically when `DAN_SIGN_PFX_BASE64` and `DAN_SIGN_PFX_PASSWORD` secrets are configured, while preserving unsigned fallback behavior when they are absent

### Completed In This Release Workflow Alignment Pass

- Added an explicit release-version sync dry-run step to `.github/workflows/release.yml` before any Windows release build starts
- Corrected the release workflow comments so they require version synchronization across `config.py`, `pyproject.toml`, and `installer/Dan.iss`, not just the older two-file wording
- Updated `RELEASE.md` to clarify that the three-source version rule is the real release requirement, including the installer metadata file

### Completed In This Tag-Version Enforcement Pass

- Added `--expect-version` to `scripts/build_windows.py` so callers can require the synchronized repo version to match an external release version before any build work starts
- Added unit tests covering both the matching and mismatched expected-version paths
- Verified the matching path with `python scripts/build_windows.py --target gui --dry-run --expect-version 2.5.1`
- Verified the failure path with `python scripts/build_windows.py --target gui --dry-run --expect-version 9.9.9`; it now stops immediately with a version-mismatch error instead of allowing a wrongly tagged release flow to continue
- Updated `.github/workflows/release.yml` so tagged releases verify that the pushed tag version matches the synchronized repo version before publishing artifacts

### Completed In This Release Readiness Verifier Pass

- Added `scripts/release_readiness.py` as a single-command local release gate
- The verifier checks synchronized release version state, packaged GUI presence, packaged CLI presence, packaged CLI smoke health, local Inno Setup availability, local `signtool.exe` availability, and signing-certificate availability
- Added targeted tests for readiness rendering, check collection, and signing-material failure detection
- Verified the script locally with `python scripts/release_readiness.py`; it currently reports 5 passing checks and 2 blocking checks on this workstation
- The current verified blockers are explicit: `ISCC.exe` is not installed locally, and signing certificate material is not configured

### Completed In This Release Documentation And Remediation Pass

- Tightened `scripts/release_readiness.py` so it also checks local `signtool.exe` availability and prints remediation steps for blocking items instead of leaving the operator to infer them
- Expanded `tests/test_release_readiness.py` to cover remediation rendering, the new signing-tool check, and the updated readiness-check ordering
- Rewrote `RELEASE.md` around the actual Windows release path: version sources, pre-release verification, portable builds, installer builds, local ship gate, GitHub release workflow, and exact signing-secret preparation
- Rewrote `INSTALL.md` to match the current Windows-first repo instead of the older mixed install guidance, including the supported GUI shell, packaging path, installer path, and signed-build prerequisites
- Rewrote `README.md` and `ONBOARDING.md` so they point at the same ship gate and release prerequisites instead of drifting from the current release workflow
- Verified with `python -m pytest -q tests\\test_release_readiness.py tests\\test_build_windows.py`, `python -m ruff check scripts\\release_readiness.py tests\\test_release_readiness.py`, and `python scripts\\release_readiness.py`

### Completed In This Local Installer Verification Pass

- Installed Inno Setup 6.7.3 locally via `winget`, which placed `ISCC.exe` under `%LOCALAPPDATA%\\Programs\\Inno Setup 6\\`
- Fixed `scripts/build_windows.py` `find_iscc()` so user-local Inno Setup installs are detected instead of only `Program Files` and `PATH`
- Added a regression test covering `LOCALAPPDATA`-based `ISCC.exe` detection
- Fixed `installer/Dan.iss` `AppId` syntax so the stable GUID is emitted as a literal instead of being parsed as an invalid Inno constant
- Added installer-artifact verification to `scripts/release_readiness.py`, so the local ship gate now requires the expected `Dan-<version>-setup.exe` output instead of only checking compiler availability
- Verified with `python -m pytest -q tests\\test_build_windows.py tests\\test_release_readiness.py`, `python -m ruff check scripts\\build_windows.py scripts\\release_readiness.py tests\\test_build_windows.py tests\\test_release_readiness.py`, `python scripts\\build_windows.py --installer-only`, and `python scripts\\release_readiness.py`
- Current verified local release status is now stronger: installer tool present, installer artifact present, signing tool present, and only signing certificate material remains blocking

### Completed In This Release Integrity Artifact Pass

- Added `scripts/release_artifacts.py` to generate `dist/release/SHA256SUMS.txt` and `dist/release/release-manifest.json` from the built GUI exe, CLI exe, and installer
- Added targeted tests for release artifact collection, hashing, checksum rendering, and manifest writing in `tests/test_release_artifacts.py`
- Tightened `scripts/release_readiness.py` so local ship readiness now also requires the release checksum and manifest artifacts to exist and match the current built outputs
- Updated `.github/workflows/release.yml` so tagged releases generate and upload the checksum file and JSON manifest alongside the installer asset
- Updated `RELEASE.md`, `README.md`, and `ONBOARDING.md` so the checksum/manifest step is part of the documented release truth path
- Verified with `python -m pytest -q tests\\test_build_windows.py tests\\test_release_artifacts.py tests\\test_release_readiness.py`, `python -m ruff check scripts\\build_windows.py scripts\\release_artifacts.py scripts\\release_readiness.py tests\\test_build_windows.py tests\\test_release_artifacts.py tests\\test_release_readiness.py`, `python scripts\\release_artifacts.py`, and `python scripts\\release_readiness.py`
- Current verified local release status is stronger again: GUI bundle present, CLI bundle present, installer present, release integrity artifacts present, signing tool present, and only signing certificate material remains blocking

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

### Completed In This security_utils.py Test Coverage Pass (2026-06-10 steward pass 34)

- Created `tests/test_security_utils.py` with 80 new test methods directly covering `security_utils.py` — the core security classes were previously tested only indirectly through `tools.py` patches in `test_dan.py`
- **`SecurePathValidator.__init__`**: default root falls back to cwd; explicit root is resolved to absolute Path; multiple roots all stored; empty list treated same as None
- **`SecurePathValidator.validate_path`**: path inside root returns resolved Path; root itself accepted; empty string raises ValueError; non-string raises; path outside all roots raises "outside allowed"; `../../` traversal blocked; path in second of two roots accepted; deeply nested subdirectory accepted
- **`SecurePathValidator.is_safe_path`**: True for valid path; False for outside path; False for empty string; return type verified as bool
- **`SecureCommandExecutor.__init__`**: default `use_whitelist=True`; default `max_execution_time=30`; `compiled_patterns` populated; `compiled_requirements` has `powershell` and `pwsh` entries
- **`validate_command` — shell features**: pipe, redirect `>`, semicolon, backtick, ampersand, `<` all blocked with "Shell features" message
- **`validate_command` — input validation**: empty string raises "non-empty string"; non-string raises; whitespace-only handled without crash
- **`validate_command` — dangerous patterns**: `rm -rf /`, `sudo`, `kill -9`, `cmd /c`, `cmd /k`, `powershell -Command`, `powershell -EncodedCommand`, `wmic process call create`, `powershell -ExecutionPolicy Bypass` all blocked with "dangerous" message
- **`validate_command` — whitelist**: `ls`, `python`, `git`, `pytest`, `ruff` all pass; unknown command raises "not in whitelist"; `.exe` extension stripped (`python.exe` → `python`); path prefix stripped (`/usr/bin/python`); `use_whitelist=False` bypasses whitelist for unknown commands; dangerous patterns still enforced when whitelist disabled
- **`validate_command` — RESTRICTED_COMMAND_REQUIREMENTS**: bare `powershell` blocked with "requires a specific invocation"; `powershell -File script.ps1` passes; `powershell.exe -File script.ps1` passes; bare `pwsh` blocked; `pwsh -File myscript.ps1` passes; `pwsh -Command` caught by dangerous-pattern check first
- **`_has_shell_features`**: simple command returns False; unquoted pipe/redirect/semicolon returns True; pipe inside double-quoted string returns False; pipe inside single-quoted string returns False
- **`sanitize_user_input`**: normal string returned; non-string raises "must be a string"; None raises; over-max-length raises "too long"; exactly-at-limit passes; leading/trailing whitespace stripped; null bytes removed; control chars (`\x01`) removed; newlines and tabs preserved; 3+ consecutive newlines collapsed to 2; two newlines preserved; empty string returns empty; custom max_length enforced
- **`validate_file_size`**: non-existent file returns silently; small file within limit passes; file over limit raises "too large"; file exactly at limit passes (not strictly greater); `max_size_mb=0` blocks any nonempty file; default 50 MB limit accepts small file
- All 80 tests pass (verified in /tmp sandbox; see Known Benign Issues for FUSE limitation)
- No production code changes; test additions only

### Completed In This Sub-Agent Parallelism Foundation Pass (2026-06-15)

- Created `docs/superpowers/specs/2026-06-15-subagent-parallelism-design.md`
- Created `docs/superpowers/plans/2026-06-15-subagent-parallelism.md`
- Replaced the `workers/__init__.py` stub worker pool with a manager-backed sub-agent implementation
- Added durable sub-agent sessions with IDs, status, event logs, claimed paths, timestamps, parent linkage, and final result/error state
- Added manager-owned path claims with file/directory overlap conflict detection
- Added runtime sub-agent context plumbing so mutating tools can identify the acting agent
- Added automatic path claiming on first mutation for sub-agents in `tools.py`
- Blocked conflicting writes when another sub-agent already owns the target path
- Added a first destructive-action approval gate for sub-agent `Move` operations
- Added CLI visibility and control surfaces:
  - `/agents` and `/workers` list active sessions
  - `/agent inspect <id>`
  - `/agent approve <id>`
  - `/agent deny <id> [reason]`
  - `/agent cancel <id>`
- Configured real sub-agent runners for both CLI and GUI startup paths
- Added `tests/test_workers.py` covering session lifecycle, claims, approvals, runner-backed execution, and tool lock enforcement
- Restored full green verification after the slice by fixing low-risk compatibility drift in `tools.py` and `provider_ollama.py`

### Completed In This Sub-Agent Visibility And Shell Approval Pass (2026-06-15)

- Added a real `Agents` workspace pane to `dan_gui_modern.py`
- Added manager-backed agent snapshot rendering in the right rail so the desktop shell can show live sub-agent IDs, statuses, claim counts, approvals, and prompts
- Added lightweight auto-refresh for the `Agents` pane while it is selected
- Broadened sub-agent destructive approval routing in `security_utils.py` for shell commands:
  - delete commands: `del`, `rm`, `rmdir`
  - rename/move commands: `move`, `mv`, `ren`
  - package removal commands: `pip uninstall`, `npm uninstall`, `pnpm remove/rm`, `yarn remove/uninstall`
- Added tests covering shell approval blocking and GUI agent snapshot rendering

### Completed In This skills.py Test Coverage Pass (2026-06-10 steward pass 33)

- Created `tests/test_skills.py` with 54 new test methods covering `skills.py` — previously untested
- **`find_duplicates`**: empty directory returns zero-count message; identical files (≥ min_size) detected as duplicates; different-content files not reported; files below min_size skipped; custom min_size respected; `.git` subdirectory skipped; `__pycache__` subdirectory skipped; report shows group count; file path (not dir) returns "Error"; path outside allowed root returns "Security error"
- **`scaffold_project`**: unknown template returns error listing available names; python scaffold creates all expected directories (src/tests/docs/scripts) and files (README.md, requirements.txt, .gitignore, pyproject.toml, tests/test_main.py); README and pyproject.toml contain project name substitution; .gitignore contains venv entry; returns success message; duplicate project name returns "Error … exists"; node scaffold creates package.json (with name) and src/index.js; web scaffold creates public/index.html (with name) and src/main.js; path outside allowed root returns "Security error"
- **`generate_changelog`**: feat/fix/docs/refactor prefixes categorized correctly; scoped prefix (e.g. `fix(auth):`) stripped to body only; unprefixed commits categorized; commit count in footer; empty stdout → "No commits found"; FileNotFoundError → "git not found" error; TimeoutExpired → "timed out" error; non-zero returncode → "Error" with stderr text; `--since`/`--until` arguments passed through; default call includes commit count limit; output starts with `# Changelog`
- **`run_webapp_test`**: loopback, localhost, private-range, `file://`, and `ftp://` URLs all return "Security error"; `allow_local=True` bypasses the security gate (connection error, not security error)
- **`register_skill_tools`**: all four tools (FindDuplicates, Scaffold, Changelog, WebTest) registered; all in `skills` category; handlers are callable; descriptions are non-empty
- `autouse` fixture saves/restores `registry._TOOLS`, `registry._CACHED_SCHEMAS`, and `skills._path_validator` around every test; `tmp_validator` fixture provides a `SecurePathValidator` scoped to `tmp_path`
- All 54 tests pass (verified in /tmp sandbox; FUSE `.pytest_cache` permission issue prevents running directly in repo sandbox — see Known Benign Issues)
- No production code changes; test additions only

### Completed In This tool_registry Test Coverage Pass (2026-06-10 steward pass 32)

- Created `tests/test_tool_registry.py` with 44 new test methods covering the core registration and query API in `tool_registry.py` — the audit log and confirmation gate were already covered by `test_tool_registry_audit.py`; this file covers the remaining surface
- **`Tool` dataclass**: `to_api_schema()` output format (name/description/input_schema keys), correct values for each field, default `safety_level=1`, default `category="core"`
- **`register()` / `register_tool()` alias**: stores tool by name, alias is transparent, correct name/description/category/safety_level stored, default safety_level=1, default category="core", re-registration overwrites previous entry, schema cache (`_CACHED_SCHEMAS`) is cleared to None on every register call, handler callable is the exact stored object
- **`get_tool()`**: returns None for unknown name, returns `Tool` instance for registered name
- **`get_all_tools()`**: returns list, includes registered tool, includes multiple registered tools
- **`get_tool_schemas()`**: returns list of schema dicts, each with name/description/input_schema, result is cached (same object on second call), cache is rebuilt (new object) after a subsequent register
- **`get_schemas_for_categories()`**: filters by single category, empty set returns nothing, multiple categories combined correctly
- **`all_categories()`**: returns set, includes registered category, includes multiple categories
- **`list_by_category()`**: returns dict, groups tools correctly, values are Tool instances
- **`execute_tool()` dispatch**: unknown tool → error string starting with "Error" containing tool name, success → handler return value, handler receives input dict as **kwargs, exception in handler → error string with exception message, success result does not start with "Error"
- Autouse fixture saves/restores module-level `_TOOLS`, `_CACHED_SCHEMAS`, and `_confirmation_gate` between every test for full state isolation; `_tr_` name prefix prevents collision with `test_tool_registry_audit.py` test tools
- All 44 tests pass (verified in /tmp sandbox; FUSE .pytest_cache permission issue prevents running directly in repo sandbox — see Known Benign Issues)
- No production code changes; test additions only

### Completed In This agent.py Test Coverage Pass (2026-06-10 steward pass 31)

- Fixed duplicate method in `tests/test_context_mgr.py`: `test_compact_does_not_log_on_short_circuit` appeared twice (copy-paste error from pass 30); second exact copy removed; file is now 43 unique test methods (one fewer than the stated 44 — the duplicate was functionally identical, so coverage is unchanged)
- Created `tests/test_agent.py` with 51 new test methods covering the pure helper functions in `agent.py` — previously untested
- **`AgentInterrupted`**: extends BaseException (not Exception), checkpoint stored, empty checkpoint accepted, str is "interrupted", not swallowed by broad `except Exception`
- **`_tool_label`**: WebSearch/WebFetch/Bash/Read/Write/HttpRequest/unknown tool name/missing input key — all label formats verified
- **`select_tool_categories`**: short conversational → empty set (boundary at 5 words), task signal in short message → non-empty, always-on categories present in any task result, web/git/code/knowledge/workers keyword routing, multiple keywords → multiple categories, case-insensitive matching
- **`_extract_text_tool_call`**: plain text → None, empty string → None, JSON array → None, JSON without name key → None, unregistered tool name → None, registered tool → ToolCall with id="rescued_0", "arguments" key alias accepted, "function.name" nesting accepted, malformed JSON → None, leading whitespace stripped before check
- **`_build_assistant_content`**: empty response → [], text only → single text block, exact text preserved with newlines, tool calls only → tool_use blocks with correct keys, text + tools → both blocks, multiple tool calls in order, required keys verified
- **`_last_message_text`**: empty list → "", string content returned directly, uses last message not first, list content joins text blocks, non-text blocks skipped, missing content key → "", None content → "", empty string content → ""
- All 51 tests pass (verified in /tmp sandbox; FUSE staleness of test_context_mgr.py is a known benign issue — Windows file is correct per Read tool)
- No production code changes; test additions and one duplicate removal only

### Completed In This context_mgr Test Coverage Pass (2026-06-10 steward pass 30)

- Created `tests/test_context_mgr.py` with 44 new test methods covering all functions in `context_mgr.py` — previously only shallow coverage existed in `test_dan.py`
- **`estimate_tokens`**: empty string → 0, single char → 0 (floor division), exact ratio multiple, 35-char known calculation, longer text, whitespace, unicode (code-point length), proportionality
- **`estimate_messages_tokens`**: empty list → 0, single string content with exact arithmetic, +4 overhead per message, missing content key defaults to empty, list content with dict blocks (str(block) costed), non-dict list items skipped without crash, empty list content, multiple message accumulation, mixed string and list content
- **`needs_compaction`**: empty list → False, small context → False, over threshold → True, exact-at-threshold boundary (uses strict `>`), just-over threshold → True, return type is bool, huge context_limit prevents compaction
- **`compact`**: empty/1/2/3/4 messages returned unchanged (identity check); 5+ messages triggers compaction; summary message structure (role=user, `[Conversation summary]` prefix, provider text included — uses `sys.modules` stub for providers.Message); ack message is second; last 4 preserved exactly; result length = 2 + 4; failing provider falls back to truncated text; fallback preserves last 4; fallback caps at 2000 chars; list content text-block extraction; non-text blocks produce empty and are skipped; empty content messages skipped in summary_parts; long content truncated at 200 chars in summary_parts; logging INFO on compaction; no log on short-circuit
- All 44 tests pass (verified in isolated sandbox run; FUSE .pytest_cache permission issue prevents running directly in repo sandbox — see Known Benign Issues)
- No production code changes; test additions only

### Completed In This provider_common Test Coverage Pass (2026-06-10 steward pass 29)

- Created `tests/test_provider_common.py` with 33 new test methods covering `provider_common.py` — previously untested
- **`parse_tool_arguments`**: dict input returned as-is, None/empty-string → {}, valid JSON string → dict, nested dict, empty JSON object, invalid JSON (no raise), JSON array → {}, JSON string scalar → {}, JSON number → {}, JSON null → {}, bytes input, integer input → {}, list input → {}, whitespace-only string → {}
- **`KeyRotator.__init__`**: no keys → ValueError with message, single fallback key via bare prefix, numbered keys loaded in order (KR_1…KR_3), blank numbered key skipped, whitespace-only key stripped and skipped, all five slots loaded
- **`KeyRotator.next`**: single key never rotates, multi-key rotates after HOLD_SECONDS elapsed (time.time manipulation), no rotation before hold interval, rotation wraps back to index 0, return type is (str, int)
- **`KeyRotator` properties and methods**: `current_index` is 1-based, `count` matches loaded keys, `record_usage` increments `_calls_per_key` per index, `status()` contains key entries, marks active key, reflects call counts, returns str
- All 33 tests pass (verified by running in /tmp with pytest -p no:cacheprovider; FUSE .pytest_cache permission issue prevents running directly in repo sandbox — see Known Benign Issues)
- No production code changes; test additions only

### Completed In This Provider Test Coverage Pass (2026-06-10 steward pass 28)

- Created `tests/test_providers.py` with 38 new test methods covering provider paths not exercised in `test_dan.py`
- **OllamaProvider**: `_to_ollama_tools` (basic conversion, missing schema default, empty list), `_to_ollama_messages` with plain string content and non-dict block skipping, `_parse_tool_calls` with dict arguments, malformed JSON string, empty list, sequential ID assignment; `chat` happy path, tools included/omitted in payload; `chat_stream` happy path with `on_text` callback, chunk accumulation, empty-line skipping; `supports_streaming`, `context_limit`, `key_count` properties, `OLLAMA_URL` env var override
- **OpenAIProvider**: `context_limit` for gpt-4 (128k) and non-gpt-4 (16k) models, `supports_streaming` is False, `key_count` delegates to rotator, system message prepended correctly
- **AnthropicProvider**: `context_limit` (200k), `supports_streaming`, `key_count` delegates to rotator, `chat_stream` rate-limit fallback correctly calls `chat()`
- **VeniceProvider**: init raises `ValueError` without any API key, accepts explicit key, reads `VENICE_API_KEY` env var; `chat` text response, `<think>` tag stripping, tools only forwarded for `FUNCTION_CALLING_MODELS` (not for other models), API error returns `stop_reason='error'`, system message prepended; `supports_streaming`, `key_count`, `context_limit` table for all known models plus unknown-model default, `base_url` default and override
- All tests use monkeypatching only — no real network calls; ruff clean; no production code changes

### Completed In This cost_tracker And session_mgr Test Coverage Pass (2026-06-10 steward pass 27)

- Created `tests/test_cost_tracker.py` with 46 new test methods covering `cost_tracker.py` — previously untested
- Tests cover: `_get_rates` (model substring matching, first-match-wins ordering including haiku-3-5 before haiku-3 and gpt-4o-mini before gpt-4o, fallback for unknown models, case insensitivity, empty string), `SessionCost.record` (accumulation across calls, negative input/output token clamping to zero, zero-token call-count increment), `SessionCost.total_tokens` (sum property, zero at start), `SessionCost.estimate_cost` (known-rate calculation, zero for local/free models, small sub-cent usage), `SessionCost.is_free_model` (llama/qwen/mistral/venice free; claude/gpt/unknown not free), `SessionCost.summary` (model name, call count, free-model no-charge label, paid-model dollar sign, duration format in seconds/minutes/hours, comma-formatted token counts), module-level singleton `init`/`get`/`record` (none before init, reset on re-init, record accumulates, noop when uninitialized)
- Created `tests/test_session_mgr.py` with 47 new test methods covering `session_mgr.py` — previously untested
- Tests cover: `_safe_session_stem` (valid alphanumeric, underscore/dash/dot, whitespace stripping, .json extension stripping, empty/whitespace-only → empty, `../` traversal → empty, backslash traversal → empty, absolute path → empty, special chars stripped, 80-char truncation), `save` (file creation, valid JSON, confirmation string, message count in result, provider/model stored, path-separator sanitization in name — confirmed `../../evil` → `....evil.json` stays inside sessions dir, empty name fallback to session_id, space→underscore, overwrite), `auto_save` (creates `_auto_` prefixed file, no-op on empty messages, silent on I/O error), `load` (found by name, not found returns None, .json extension stripped, `../` traversal rejected, empty name returns None, corrupt JSON returns None, metadata fields returned, auto-save reachable by session_id, symlink/traversal containment), `delete` (success, not found → False, empty name → False, traversal rejected, auto-save files not matched by `delete`), `list_sessions` (empty list, auto excluded by default, included with flag, sorted by updated desc, metadata fields present, message count correct, corrupt files skipped silently), `format_sessions_table` (no-sessions message, header row present, session name present)
- Confirmed that `save()` path sanitization strips `/` (the traversal enabler) before joining with `SESSIONS_DIR`, so `../../evil` produces a safe flat filename; path containment verified in test
- No production code changes; test additions only

### Completed In This api_config Test Coverage Pass (2026-06-10 steward pass 26)

- Created `tests/test_api_config.py` with 28 new test methods covering `api_config.py` — previously untested
- Tests cover: `load_config` (defaults fallback, saved-value merge, api_key stripping on read, corrupt-file resilience), `save_config` (api_key stripping before write, no in-place mutation of caller dict), `_deep_merge` (scalar override, nested dict merge, new-key addition, dict-to-scalar replacement, deep nesting), `_mask` (long-value redaction, short-value pass-through, non-key fields, length boundary at 10/11 chars), `get_value` (top-level key, nested dot-path, unknown-key error, secret routing through env with masked output), `set_value` (disk persistence for non-secrets, env-only routing for secrets), `get_secret` / `set_secret` (env-var read/write, whitespace stripping, empty-value clearing, unknown-key error)
- Security behavior verified: api_key values are never written to disk by `save_config`; `set_value` for secret keys does not create a config file; `load_config` strips api_key from the venice section even if it was previously persisted
- No production code changes; test additions only

### Completed In This URL Validation Test Coverage Pass (2026-06-09 steward pass 25)

- Added 8 new test methods to `tests/test_dan.py` covering `validate_fetch_url` and `validate_redirect_url` in `security_utils.py` — both were previously untested
- Tests cover: blocked non-HTTP schemes (`file://`, `ftp://`, `javascript:`), empty/whitespace input, loopback (`127.0.0.1`), private ranges (10.x, 192.168.x, 172.16.x), link-local (`169.254.169.254` cloud metadata endpoint), unspecified (`0.0.0.0`), `localhost`, public HTTPS pass-through with whitespace stripping, `allow_local=True` bypass, SSRF via absolute redirect, valid absolute redirect, and relative path resolution
- No production code changes; test additions only

### Completed In This README Framing Accuracy Pass (2026-06-09 steward pass 24)

- Fixed description of `dan_gui.py` in `README.md` "What Dan Includes Today" section: changed "legacy GUI/backing behavior remains in `dan_gui.py`" to "deprecated legacy shell (no active callers; deletion pending user approval)" — the old wording implied active use; the Remaining Gaps section already correctly described the deprecated status
- No code changes; documentation consistency pass only

### Completed In This README Accuracy Pass (2026-06-09 steward pass 23)

- Fixed stale claim in `README.md` Windows Packaging section: "not an installer or MSIX package yet" — updated to correctly reflect that the Inno Setup installer path is complete; added note about the automated release workflow triggered by version tag push
- No code changes; documentation accuracy pass only

### Completed In This Security Docs Accuracy Pass (2026-06-09 steward pass 22)

- Fixed two stale `tools_secure.py` references in `docs/SECURITY_BOUNDARIES.md` (Path Validation and Command Execution "Used by" lines) — updated to `tools.py`, which is the canonical implementation since steward pass 9
- Removed stale Known Gap from `docs/SECURITY_BOUNDARIES.md` ("command allowlist permits powershell and cmd") — this was fully mitigated in steward passes 15–17 via `DANGEROUS_PATTERNS` + `RESTRICTED_COMMAND_REQUIREMENTS`; the mitigation is already documented in sections 2a and 3 of the same file; the gap entry was a documentation contradiction
- No code changes; documentation accuracy pass only

### Completed In This Onboarding And README Accuracy Pass (2026-06-09 steward pass 21)

- Updated `README.md` "Immediate Production Gaps" section: removed stale items (packaging now complete, controller extraction done, installer done, clutter cleanup done); replaced with accurate current gaps (`dan_gui.py` deletion pending approval, `tools_secure.py` deletion pending approval, unsigned executables, module layout consolidation deferred)
- Updated `ONBOARDING.md` "Current Architectural Shape": corrected `dan_gui.py` description from "backing controller behavior" to deprecated/no-callers; added `dan_gui_controller.py` entry; marked `tools_secure.py` as deprecated with test migration complete; updated `dan_gui_modern.py` inheritance note to reflect `ctk.CTk + DanControllerMixin`
- Updated `ONBOARDING.md` "Immediate Priorities": replaced completed items with actual current priorities (deletions pending approval, signed executables, module layout)
- No code changes; documentation accuracy pass only

### Completed In This Architecture Doc Correction Pass (2026-06-09 steward pass 20)

- Updated `docs/ARCHITECTURE.md` to reflect actual post-decoupling state: entry points table corrected; `DanModernGUI` inheritance updated to `ctk.CTk + DanControllerMixin`; `dan_gui.py` marked deprecated; `dan_gui_controller.py` added to GUI Layer and Module Ownership tables; `tools.py` marked canonical; `tools_secure.py` marked deprecated; `RESTRICTED_COMMAND_REQUIREMENTS` and `ToolAuditLog` noted in `security_utils.py` description; `scripts/scan_secrets.py` added to Scripts table; dependency graph corrected to remove the `dan_gui.py` inheritance chain; Known Coupling Issues updated to reflect resolution of the GUI coupling; document version note added
- No code changes; documentation accuracy pass only

### Completed In This Icon Wiring Pass (2026-06-09 steward pass 19)

- `assets/dan_icon.ico` confirmed present (16×16 + 32×32, 32-bit RGBA, created by user)
- Uncommented `SetupIconFile=..\assets\dan_icon.ico` in `installer/Dan.iss` — installer now uses the Dan icon
- Added `--icon assets/dan_icon.ico` wiring to `scripts/build_windows.py` GUI build command (conditional on file existence, so non-blocking if icon is absent on a fresh clone before the asset is committed)
- Removed stale "No icon asset" entry from `RELEASE.md` "What Is Not Yet Done"; updated installer note to reflect active icon state
- Icon gap removed from backlog (see Release Infrastructure section below)

### Completed In This Documentation Hygiene Pass (2026-06-09 steward pass 18)

- Updated `RELEASE.md`: replaced stale "What Is Not Yet Done" section with accurate status (installer and release pipeline are done); added "Build The Windows Installer" section documenting `--installer` / `--installer-only` flags and Inno Setup prerequisites; added "Automated Release Workflow" section documenting the tag-triggered `.github/workflows/release.yml` pipeline; "What Is Not Yet Done" now only lists the two genuinely open items (icon asset, signed executables)

### Completed In This Positive-Allowlist Security Pass (2026-06-08 steward pass 17)

- Added `RESTRICTED_COMMAND_REQUIREMENTS` class attribute to `SecureCommandExecutor` in `security_utils.py`: maps `powershell` and `pwsh` to a required `-File` pattern; any invocation lacking `-File` is rejected even though the base command is in `SAFE_COMMANDS`
- Compiled requirements into `self.compiled_requirements` in `__init__`, following the same pattern as `self.compiled_patterns`
- Refactored the `validate_command` whitelist block: removed the early `return` for `.exe`-extension commands; canonical name resolution now feeds both the SAFE_COMMANDS check and the RESTRICTED_COMMAND_REQUIREMENTS check; `powershell.exe` and `pwsh.exe` correctly resolve to `powershell`/`pwsh` for the requirement check
- Added 4 new test methods to `tests/test_dan.py` (14 new test cases): `test_validate_command_blocks_bare_powershell`, `test_validate_command_blocks_powershell_without_file_flag`, `test_validate_command_allows_pwsh_file`, `test_validate_command_allows_powershell_exe_with_file`
- Updated `docs/SECURITY_BOUNDARIES.md`: added Section 2a documenting `RESTRICTED_COMMAND_REQUIREMENTS` with a command/pattern/rationale table; removed the "Known remaining gap" paragraph that was previously accurate but is now resolved

### Completed In This Legacy Audit Pass (2026-06-08 steward pass 14)

- Confirmed `dan_gui.py` has no external callers: no Python file outside the module itself imports `dan_gui` or `DanGUI`; launch scripts (`run_gui.bat`, `run_gui.sh`) invoke `dan_gui_modern.py` directly; Dan.py `--target gui` only triggers the startup doctor, not the legacy shell
- Added deprecation header to `dan_gui.py` documenting the caller audit result, the retirement path, and the Destructive Action Gate requirement for deletion
- Created `assets/` directory with `assets/README.md` documenting `dan_icon.ico` format, size, and ImageMagick conversion command; `assets/dan_icon.ico` subsequently placed by user (steward pass 19); `SetupIconFile` now active

### Completed In This Release Action Modernization Pass (2026-06-08 steward pass 13)

- Updated `.github/workflows/release.yml`: replaced deprecated `actions/create-release@v1` and `actions/upload-release-asset@v1` with `softprops/action-gh-release@v2` — actively maintained; combines release creation and asset upload in a single step; `permissions: contents: write` already at job level so no per-step `GITHUB_TOKEN` env block needed; `fail_on_unmatched_files: true` added for early failure if the installer path resolves to nothing

### Completed In This Release Workflow Pass (2026-06-08 steward pass 12)

- Created `.github/workflows/release.yml`: tag-triggered (`v*.*.*`) GitHub Release workflow; builds GUI bundle, CLI companion, and Inno Setup installer; creates a GitHub Release with auto-generated release notes; uploads `Dan-<version>-setup.exe` as a downloadable release asset; `prerelease` flag auto-set when tag contains `-` (e.g. `v2.6.0-rc1`)

### Completed In This Test Migration Pass (2026-06-08 steward pass 10)

- Migrated `TestSecureTools` and `TestSecureToolsExpanded` in `tests/test_dan.py` from `tools_secure` to `tools`: all `import tools_secure` replaced with `import tools`; `_path_validator` and `_command_executor` patches now target `tools` module; `tools_secure.aiofiles` reference corrected to `tools._aiofiles`; `register_secure_core_tools()` calls replaced with `register_core_tools()`; `test_register_secure_core_tools_assigns_correct_safety_levels` renamed to `test_register_core_tools_assigns_correct_safety_levels`
- No Python source files reference `tools_secure` except a historical docstring comment in `tests/test_tools_secure_runtime.py`
- `tools_secure.py` deletion is now unblocked pending explicit user approval (Destructive Action Gate)

### Completed In This Tool Consolidation Pass (2026-06-08 steward pass 9)

- Added `read_file_async` to `tools.py`: optional `aiofiles` fast path with `asyncio.to_thread` fallback; mirrors production-ready implementation previously only in `tools_secure.py`
- Added `run_bash` output truncation to `tools.py` (10 000-char cap with `"... (output truncated)"` notice — was missing, present in `tools_secure.py`)
- Improved `grep_search` in `tools.py`: file size limit 1 MB → 5 MB, match cap 50 → 200 (was over-restrictive relative to `tools_secure.py`)
- Improved `list_directory` in `tools.py`: tree depth 2 → 3, added KB suffix for files ≥ 1 024 bytes
- Added deprecation header to `tools_secure.py`; documented migration path to `tools.py` and pending test updates

### Completed In This GUI Decoupling Pass (2026-06-08)

- Created `dan_gui_controller.py` with `DanControllerMixin`: extracts all non-visual controller logic shared across GUI shells (`_init_dan`, `_bind_shortcuts`, `_cancel_if_processing`, `_handle_enter`, `load_session`, `_inline_error`, `_clear_chat`, `_scroll_to_bottom`)
- Changed `DanModernGUI` inheritance from `DanModernGUI(DanGUI)` to `DanModernGUI(ctk.CTk, DanControllerMixin)` — eliminates the dependency on the legacy shell at the class level
- Added `show_prompts`, `show_terminal`, and `show_error` directly to `DanModernGUI` (previously inherited from `DanGUI`) — modern shell is now fully self-contained
- `dan_gui.py` no longer required by the modern GUI path; can be retired once direct callers are audited

### Completed In This Security Hardening Pass (2026-06-08 steward pass 7)

- Fixed `register_core_tools()` in `tools.py`: all 12 core tools now carry explicit `safety_level` annotations (Level 1: Read/Glob/Grep/ListDir/Diff; Level 2: Write/Edit/Append/Copy/Move/HttpRequest; Level 3: Bash)
- Added `test_register_core_tools_assigns_correct_safety_levels` to `tests/test_dan.py` — verifies gate will fire for Bash and that write-side tools carry level 2

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
- ~~Secret scanning~~ ✓ completed (2026-06-08 steward pass 5)
- ~~Audit log for tool invocations~~ ✓ completed (2026-06-08 steward pass 6)
- ~~Tool invocation confirmation gate for Level 3 tools in autonomous workflows~~ ✓ completed (2026-06-08 steward pass 6)

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
- ~~Extract remaining controller behavior from `dan_gui.py`~~ ✓ completed (2026-06-08)

## Backlog: Known Gaps And Future Work

These items were identified during the 2026-06-06 through 2026-06-08 steward passes and are deferred for future work.

### Code Quality

- ~~`tools.py` and `tools_secure.py` overlap — merge into a single secure implementation~~ ✓ test migration complete (2026-06-08 steward pass 10): `TestSecureTools` and `TestSecureToolsExpanded` in `test_dan.py` now import and patch `tools` directly; `test_tools_secure_runtime.py` was already migrated; no Python file references `tools_secure` except a historical comment. Remaining step: **delete `tools_secure.py`** (requires explicit user approval — Destructive Action Gate)
- ~~`tools_secure.py` `register_secure_core_tools()` uses a flat parameters dict (missing `"type": "object"` + `"properties"` wrapper) — schema would be malformed if sent to the API; also missing `safety_level` annotations~~ ✓ fixed (2026-06-08 steward pass 8): parameters now use proper JSON Schema format; safety_level annotations added (Read/Glob/Grep/ListDir=1, Write/Edit=2, Bash=3); parallel test `test_register_secure_core_tools_assigns_correct_safety_levels` added to `tests/test_dan.py`
- `dan_gui.py` legacy shell is now decoupled from `DanModernGUI` — `DanControllerMixin` in `dan_gui_controller.py` holds all shared non-visual controller logic; `DanModernGUI` inherits from `ctk.CTk + DanControllerMixin` directly; caller audit complete ✓ (2026-06-08 steward pass 14): no external callers found; deprecation header added; **deletion requires explicit user approval (Destructive Action Gate)**
- Top-level flat module layout is serviceable but will become harder to navigate as optional tool families grow — long-term migration toward the `actions/`/`knowledge/`/`web/`/`workers/` package model

### Security Hardening

- ~~Command allowlist permits `powershell` and `cmd`, which can bypass other restrictions if invoked deliberately~~ ✓ fully mitigated (2026-06-08 steward passes 15–17): `DANGEROUS_PATTERNS` blocks the known-dangerous flag combinations (`/c`, `/k`, `-Command`, `-EncodedCommand`, `-ExecutionPolicy Bypass/Unrestricted`, `wmic process call create`) and all `pwsh` equivalents; `RESTRICTED_COMMAND_REQUIREMENTS` (added steward pass 17) applies a positive-allowlist constraint to `powershell`/`pwsh` — any invocation that does not include `-File` is rejected, closing the undocumented-flag gap without breaking `code_execution.py`; `cmd` dangerous invocation forms remain covered by `DANGEROUS_PATTERNS`. 4 new test methods (14 cases) added in pass 17. `docs/SECURITY_BOUNDARIES.md` updated with `RESTRICTED_COMMAND_REQUIREMENTS` table.
- Confirmation gate is opt-in and off by default — autonomous workflows must install it explicitly at session start
- Sub-agent destructive approval routing now covers mutating tool `Move` plus destructive shell commands and package removals, but arbitrary `RunCode` / `IterateFix` intent is still not parsed deeply enough to auto-block every destructive filesystem mutation

### Release Infrastructure

- ~~Windows installer — not yet started~~ ✓ Inno Setup path complete (2026-06-08 steward pass 11): `installer/Dan.iss` created and path bug fixed; `scripts/build_windows.py` supports `--installer` / `--installer-only` flags; `INSTALL.md` documents the full build workflow; CI `windows-packaging` job installs Inno Setup via choco, builds the installer, and uploads artifact
- ~~Icon asset not yet created~~ ✓ complete (2026-06-09 steward pass 19): `assets/dan_icon.ico` placed by user (16×16 + 32×32, 32-bit RGBA); `SetupIconFile` uncommented in `Dan.iss`; `--icon` wired into `build_windows.py` GUI build
- ~~Automated release artifact upload in GitHub Actions~~ ✓ completed (2026-06-08 steward pass 12 + 13): `.github/workflows/release.yml` added; triggers on `v*.*.*` tag push; builds GUI + CLI + Inno Setup installer; creates GitHub Release and uploads `Dan-<version>-setup.exe` via `softprops/action-gh-release@v2` (modernized from deprecated `actions/create-release@v1` + `actions/upload-release-asset@v1`); pre-release flag auto-set when tag contains `-` (e.g. `-rc1`)
- Signed Windows executables — not yet started

### Documentation

- `docs/AUTHENTICATION_SYSTEM.md` audited and corrected against `auth_system.py` ✓ (2026-06-08 steward pass 4) — fixed: require_auth default, bootstrap key delivery, salt behavior, data file locations, role permission details, removed inapplicable network-service advice
- `CONTRIBUTING.md` aligned with current project posture ✓ (2026-06-08 steward pass 3)

### Known Benign Issues

- pytest collection in the Linux sandbox fails due to a `.pytest_cache` mount permission issue; tests pass on the real Windows machine — not a code defect
- `.git/index.lock` persists across sandbox sessions (FUSE mount permission prevents `rm` from the sandbox); the git index also has pre-existing staged deletions of untracked files (`tools_secure.py`, `tool_registry.py`, `tools.py`, several test files) that must NOT be committed — requires manual cleanup on Windows: `rm .git/index.lock && git restore --staged .` followed by `git add` of only intended changes

## Out Of Scope Until Reopened

- major architecture rewrites without a specific verified pain point
- dependency churn for its own sake
- deleting historical files without confirming they are truly safe to remove
- release claims such as “production ready” before packaging and Windows verification are complete
