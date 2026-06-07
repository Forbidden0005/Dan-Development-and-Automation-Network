# Onboarding

This file is the shortest safe path into the repo.

## Read In This Order

1. [PROJECT_INTEGRITY.md](/C:/Users/tyler/Desktop/Dan/PROJECT_INTEGRITY.md)
2. [ROADMAP.md](/C:/Users/tyler/Desktop/Dan/ROADMAP.md)
3. [README.md](/C:/Users/tyler/Desktop/Dan/README.md)
4. [CODEX.md](/C:/Users/tyler/Desktop/Dan/CODEX.md)

Do not start implementation before reading the roadmap. The roadmap is the canonical source for direction, priorities, active cleanup items, and completed work.

## What This Project Is

Dan is a local-first Python development assistant for Windows. It is not a web SaaS, not a cloud-only agent, and not a generic prototype sandbox. The target outcome is a dependable desktop application with clear boundaries, secure local execution, predictable setup, and a maintainable release path.

## What You Should Assume

- Existing behavior matters. Avoid broad rewrites.
- The repo contains historical documentation drift. Trust the current roadmap, not old assumptions.
- The codebase is functional now, but not yet packaged and disciplined like a finished Windows product.
- Safety and explicitness matter more than cleverness.

## First-Time Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Optional:

```powershell
python -m pip install -r requirements-vision.txt
python -m pip install -r requirements-ml.txt
```

## First Verification Pass

```powershell
python -m pytest -q
python -m ruff check .
python scripts/repo_health.py
python Dan.py --doctor --target cli
```

Do not claim the app is healthy unless you ran the checks you are citing.

## Current Architectural Shape

- `Dan.py`: CLI entry point and main registration flow
- `dan_gui_modern.py`: supported Claude-inspired desktop GUI shell
- `dan_gui.py`: legacy GUI shell and current backing controller behavior for the modern shell
- `providers.py` and `provider_*.py`: model provider layer
- `tools.py`, `tools_secure.py`, `security_utils.py`: core tool and safety layer
- `code_tools.py`, `code_execution.py`, `project_tools.py`, `git_tools.py`: development workflow tooling
- `knowledge/`, `web/`, `workers/`, `actions/`: tool families and support modules
- `tests/`: pytest coverage for runtime behavior and repo hygiene

## Non-Negotiable Working Rules

- Read the roadmap before every task.
- Use the roadmap to decide whether work is active, deferred, or out of scope.
- Update the roadmap after every completed task.
- If a cleanup action is destructive or hard to reverse, stop and get explicit approval.
- If docs and code disagree, fix the docs or record the mismatch instead of hand-waving it away.

## Immediate Priorities

- Keep the docs truthful.
- Reduce root-level clutter without deleting uncertain history.
- Establish the official Windows packaging and distribution path.
- Harden the supported desktop UX path and extract legacy GUI/controller coupling carefully.
- Tighten configuration, state storage, diagnostics, and release verification.
