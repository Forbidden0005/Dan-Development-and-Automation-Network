# Dan

Dan is a local-first Python desktop assistant for development automation on Windows. It combines a CLI, a desktop GUI, multiple LLM providers, a tool registry, secure file and command tooling, project indexing, and persistent local state for iterative coding workflows.

This repository is in a transition phase: the runtime works, tests pass, and core systems exist, but the project still needs structural cleanup, packaging discipline, and release hardening before it can be treated as a professional-grade Windows product.

## Current Status

- Runtime health is good: `pytest` passes and `ruff check .` passes.
- Documentation has been reset to match the actual project instead of the unrelated Lucid/WinUI material that had drifted into the repo.
- `dan_gui_modern.py` is the supported desktop shell. It uses a Claude-inspired,
  Dan-branded workspace with dark mode by default and a persisted light-mode option.
- The next focus is productionization: repository cleanup, packaging, release flow, architecture tightening, and Windows-first polish.

## What Dan Includes Today

- CLI entry point in `Dan.py`
- Supported desktop GUI shell in `dan_gui_modern.py`; legacy GUI/backing behavior remains in `dan_gui.py`
- Provider adapters for Anthropic, OpenAI, Venice, and Ollama
- Core tool registry with file, search, shell, git, project, code execution, knowledge, web, worker, and skill tool families
- Security-oriented path and command validation
- Project indexing and repository health checks
- Automated tests and CI

## Quick Start

**Requires:** Python 3.11+ · Windows 10 (build 19041+) or Windows 11

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Optional tool families:

```powershell
python -m pip install -r requirements-vision.txt
python -m pip install -r requirements-ml.txt
```

## Configuration

Create a local `.env` or set environment variables directly:

```text
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
VENICE_API_KEY=
DAN_PROVIDER=ollama
DAN_MODEL=qwen2.5-coder:7b
```

See [.env.example](/C:/Users/tyler/Desktop/Dan/.env.example) for the supported variables.

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
```

## Windows Packaging

Dan now has a repeatable PyInstaller-based portable build path for Windows.

Install packaging dependencies:

```powershell
python -m pip install -r requirements-packaging.txt
```

Build the supported desktop shell:

```powershell
python scripts/build_windows.py --target gui
```

Build the CLI companion:

```powershell
python scripts/build_windows.py --target cli
```

Preview the exact commands without building:

```powershell
python scripts/build_windows.py --target all --dry-run
```

Portable output is written under `dist/windows/`. The current packaging path targets portable `onedir` builds, not an installer or MSIX package yet.
The default core build excludes heavyweight optional ML and vision stacks unless you opt into `--with-ml` or `--with-vision`.
GitHub Actions now includes a Windows packaging job that builds and verifies the supported GUI artifact.
That Windows packaging job also builds the CLI companion and runs a packaged CLI smoke test against the built executable.
Pushing a `v*.*.*` tag triggers `.github/workflows/release.yml`, which builds, verifies, and smoke-tests the portable GUI + CLI bundles, then publishes them as downloadable GitHub Release assets. See [RELEASE.md](/C:/Users/tyler/Desktop/Dan/RELEASE.md).

## Repository Map

- [ONBOARDING.md](/C:/Users/tyler/Desktop/Dan/ONBOARDING.md): setup, reading order, first-run workflow
- [PROJECT_INTEGRITY.md](/C:/Users/tyler/Desktop/Dan/PROJECT_INTEGRITY.md): mandatory decision gate for every task
- [ROADMAP.md](/C:/Users/tyler/Desktop/Dan/ROADMAP.md): canonical direction, backlog, and completed work
- [RELEASE.md](/C:/Users/tyler/Desktop/Dan/RELEASE.md): version scheme, release steps, and build checklist
- [CODEX.md](/C:/Users/tyler/Desktop/Dan/CODEX.md): strict operating instructions for Codex sessions

## Immediate Production Gaps

- Top-level repository layout is still too noisy for long-term maintenance.
- The legacy GUI file still backs shared controller behavior and should be extracted or retired carefully.
- Windows packaging is defined (portable `onedir` builds, automated release publishing on tags); a signed installer `.exe` is not yet wired on this branch.
- Operational docs existed in conflicting versions and required reset.
- Several historical analysis documents should be archived or reorganized instead of living at repo root forever.
- The current packaging flow produces portable builds; installer work is still pending.

## Rule

Before any non-trivial task, read [ROADMAP.md](/C:/Users/tyler/Desktop/Dan/ROADMAP.md) and [PROJECT_INTEGRITY.md](/C:/Users/tyler/Desktop/Dan/PROJECT_INTEGRITY.md). After each completed task, update [ROADMAP.md](/C:/Users/tyler/Desktop/Dan/ROADMAP.md) so the repo state stays truthful.
