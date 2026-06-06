# Dan

Dan is a local-first Python desktop assistant for development automation on Windows. It combines a CLI, a desktop GUI, multiple LLM providers, a tool registry, secure file and command tooling, project indexing, and persistent local state for iterative coding workflows.

This repository is in a transition phase: the runtime works, tests pass, and core systems exist, but the project still needs structural cleanup, packaging discipline, and release hardening before it can be treated as a professional-grade Windows product.

## Current Status

- Runtime health is good: `pytest` passes and `ruff check .` passes.
- Documentation has been reset to match the actual project instead of the unrelated Lucid/WinUI material that had drifted into the repo.
- The next focus is productionization: repository cleanup, packaging, release flow, architecture tightening, and Windows-first polish.

## What Dan Includes Today

- CLI entry point in `Dan.py`
- Desktop GUI entry points in `dan_gui.py` and `dan_gui_modern.py`
- Provider adapters for Anthropic, OpenAI, Venice, and Ollama
- Core tool registry with file, search, shell, git, project, code execution, knowledge, web, worker, and skill tool families
- Security-oriented path and command validation
- Project indexing and repository health checks
- Automated tests and CI

## Quick Start

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

## Repository Map

- [ONBOARDING.md](/C:/Users/tyler/Desktop/Dan/ONBOARDING.md): setup, reading order, first-run workflow
- [PROJECT_INTEGRITY.md](/C:/Users/tyler/Desktop/Dan/PROJECT_INTEGRITY.md): mandatory decision gate for every task
- [ROADMAP.md](/C:/Users/tyler/Desktop/Dan/ROADMAP.md): canonical direction, backlog, and completed work
- [CODEX.md](/C:/Users/tyler/Desktop/Dan/CODEX.md): strict operating instructions for Codex sessions

## Immediate Production Gaps

- Top-level repository layout is still too noisy for long-term maintenance.
- The desktop app has multiple GUI paths without a formally chosen primary shell.
- Windows packaging and installer strategy are not yet defined.
- Operational docs existed in conflicting versions and required reset.
- Several historical analysis documents should be archived or reorganized instead of living at repo root forever.

## Rule

Before any non-trivial task, read [ROADMAP.md](/C:/Users/tyler/Desktop/Dan/ROADMAP.md) and [PROJECT_INTEGRITY.md](/C:/Users/tyler/Desktop/Dan/PROJECT_INTEGRITY.md). After each completed task, update [ROADMAP.md](/C:/Users/tyler/Desktop/Dan/ROADMAP.md) so the repo state stays truthful.
