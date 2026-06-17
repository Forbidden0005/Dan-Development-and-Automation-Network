# Onboarding

This is the shortest safe path into the repo.

## Read In This Order

1. [PROJECT_INTEGRITY.md](/C:/Users/tyler/Desktop/Dan/PROJECT_INTEGRITY.md)
2. [ROADMAP.md](/C:/Users/tyler/Desktop/Dan/ROADMAP.md)
3. [README.md](/C:/Users/tyler/Desktop/Dan/README.md)
4. [INSTALL.md](/C:/Users/tyler/Desktop/Dan/INSTALL.md)
5. [RELEASE.md](/C:/Users/tyler/Desktop/Dan/RELEASE.md)
6. [CODEX.md](/C:/Users/tyler/Desktop/Dan/CODEX.md)

Do not start implementation before reading the roadmap. `ROADMAP.md` is the canonical direction document.

## Project Shape

Dan is a local-first Windows development assistant implemented in Python.

It is:

- a desktop GUI plus CLI
- local-tooling focused
- Windows-first
- packaging-aware

It is not:

- a cloud-first SaaS
- an unbounded autonomous agent
- a generic prototype sandbox

## First-Time Setup

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

## First Verification Pass

```powershell
python -m pytest -q
python -m ruff check .
python scripts/repo_health.py
python Dan.py --doctor --target cli
python Dan.py --doctor --target gui
python scripts/build_windows.py --target gui --dry-run
python scripts/release_artifacts.py
python scripts/release_readiness.py
```

Do not cite health or readiness without running the checks you reference.

## Current Architecture

- `Dan.py`: CLI entry point
- `dan_gui_modern.py`: supported desktop shell
- `dan_gui_controller.py`: shared GUI controller behavior
- `dan_gui.py`: deprecated legacy GUI shell, pending deletion approval
- `providers.py` and `provider_*.py`: provider layer
- `tools.py`, `security_utils.py`: canonical core tooling and safety layer
- `tools_secure.py`: deprecated compatibility layer, pending deletion approval
- `code_tools.py`, `code_execution.py`, `project_tools.py`, `git_tools.py`: dev workflow tooling
- `knowledge/`, `web/`, `workers/`, `actions/`: tool families and support modules
- `tests/`: pytest coverage

## Non-Negotiable Rules

- Read `ROADMAP.md` before every task.
- Use `ROADMAP.md` to determine whether work is active, deferred, or out of scope.
- Update `ROADMAP.md` after every completed task.
- Stop for explicit approval before destructive cleanup.
- If docs and code disagree, fix the drift or record it plainly.

## Immediate Priorities

- Keep the docs and roadmap truthful.
- Remove deprecated files only after explicit approval.
- Clear the remaining workstation-level release blocker: real signing certificate material.
- Continue tightening the repo toward a production-grade Windows release path.
