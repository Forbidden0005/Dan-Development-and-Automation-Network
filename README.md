# Dan

Dan is a local-first Python development assistant for Windows. It combines a CLI, a desktop GUI, provider adapters, secure local tooling, project indexing, and persistent local state for iterative coding workflows.

The supported desktop shell is `dan_gui_modern.py`. `dan_gui.py` remains in the repo only as a deprecated legacy shell pending explicit deletion approval.

## Current Status

- Core runtime, tests, and linting are in good shape.
- The Windows portable packaging path is real and repeatable.
- The tagged GitHub release workflow exists and builds the installer path.
- Local ship readiness is still blocked on workstation-level release tooling and signing material.

## What Dan Includes

- CLI entry point in `Dan.py`
- Supported desktop shell in `dan_gui_modern.py`
- Provider adapters for Anthropic, OpenAI, Venice, and Ollama
- Secure local file and command tooling
- Project indexing and repo health checks
- Persistent local state under `%APPDATA%\Dan\` and project-local `.dan\`
- Automated tests and CI

## Quick Start

Requires Python 3.11+ on Windows 10/11.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Optional extras:

```powershell
python -m pip install -r requirements-vision.txt
python -m pip install -r requirements-ml.txt
```

## Configuration

Set provider configuration in a local `.env` or in your shell:

```text
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
VENICE_API_KEY=
DAN_PROVIDER=ollama
DAN_MODEL=qwen2.5-coder:7b
```

See [.env.example](.env.example).

## Run

CLI:

```powershell
python Dan.py --doctor --target cli
python Dan.py
```

GUI:

```powershell
python Dan.py --doctor --target gui
python dan_gui_modern.py
```

## Verification

```powershell
python -m pytest -q
python -m ruff check .
python scripts/repo_health.py
python scripts/release_readiness.py
```

Do not claim the repo is healthy unless you actually ran the checks you cite.

## Windows Packaging

Install packaging dependencies:

```powershell
python -m pip install -r requirements-packaging.txt
```

Build the portable bundles:

```powershell
python scripts/build_windows.py --target all
```

Preview the exact packaging commands:

```powershell
python scripts/build_windows.py --target all --dry-run
```

Verify packaged outputs:

```powershell
python scripts/verify_windows_build.py --target gui
python scripts/verify_windows_build.py --target cli
python scripts/smoke_windows_cli.py
```

Portable output lives under `dist/windows/`.

The release path supports:

- version-sync enforcement across `config.py`, `pyproject.toml`, and `installer/Dan.iss`
- optional Authenticode signing
- installer compilation via Inno Setup
- a tagged GitHub release workflow

`python scripts/release_readiness.py` is the local ship gate. It reports:

- version sync
- packaged GUI presence
- packaged CLI presence
- packaged CLI smoke health
- local Inno Setup availability
- release checksum and manifest artifact readiness
- local `signtool.exe` availability
- local signing-certificate readiness

## Repository Map

- [ONBOARDING.md](ONBOARDING.md): shortest safe way into the repo
- [PROJECT_INTEGRITY.md](PROJECT_INTEGRITY.md): mandatory execution gate
- [ROADMAP.md](ROADMAP.md): canonical direction and completed work
- [INSTALL.md](INSTALL.md): local install and packaging setup
- [RELEASE.md](RELEASE.md): release process and ship gate
- [CODEX.md](CODEX.md): Codex operating rules for this repo

## Remaining Gaps

- `dan_gui.py` is deprecated and still pending explicit deletion approval.
- `tools_secure.py` is deprecated and still pending explicit deletion approval.
- The top-level module layout still needs longer-term consolidation.
- Signed Windows builds are not ready until real signing certificate material is configured.

## Rule

Before any non-trivial task, read [ROADMAP.md](ROADMAP.md) and [PROJECT_INTEGRITY.md](PROJECT_INTEGRITY.md). After each completed task, update [ROADMAP.md](ROADMAP.md).
