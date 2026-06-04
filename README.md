# Dan

Dan is a local desktop assistant for development automation. It combines a Python GUI, multiple model providers, a tool registry, persistent knowledge, worker agents, project context loading, and execution helpers for iterative coding workflows.

The current focus is moving the project from prototype shape toward production discipline: clean repository hygiene, repeatable checks, scoped execution boundaries, and clearer dependency ownership.

## Capabilities

- Multi-provider model support: Anthropic, OpenAI, Venice, and Ollama.
- Core tools for reading, writing, editing, searching, and command execution.
- Knowledge storage for user and project memory.
- Worker pool for delegated sub-tasks.
- Project loader and codebase indexing tools.
- Execution loop helpers for running snippets, files, and tests.
- Optional image and ML tool families.

## Install

Create and activate a virtual environment first, then install the core runtime dependencies:

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Optional tool families are intentionally split out:

```bash
python -m pip install -r requirements-vision.txt
python -m pip install -r requirements-ml.txt
```

For development and CI checks:

```bash
python -m pip install -r requirements-dev.txt
```

## Configure

Set the provider key or local provider settings you plan to use:

```bash
export ANTHROPIC_API_KEY="..."
export OPENAI_API_KEY="..."
export VENICE_API_KEY="..."
export DAN_PROVIDER="ollama"
export DAN_MODEL="qwen2.5-coder:7b"
```

Ollama does not require an API key, but the Ollama server must be running.

## Run

Launch the GUI:

```bash
python Dan.py --doctor --target gui
python dan_gui_modern.py
```

Launch the terminal interface:

```bash
python Dan.py --doctor --target cli
python Dan.py
```

Run one prompt and exit:

```bash
python Dan.py --print "summarize this project"
```

## Quality Checks

Run the test suite:

```bash
pytest
```

Run the focused correctness lint rules:

```bash
ruff check .
```

Run coverage locally:

```bash
pytest --cov --cov-report=term-missing
```

Audit local bootstrap health:

```bash
python Dan.py --doctor --target cli
python -c "import code_tools; print(code_tools.startup_doctor('.', target='gui'))"
```

Run the full repository health audit:

```bash
python scripts/repo_health.py
```

## Repository Hygiene

Generated files, local secrets, local app state, test caches, and virtual environments are ignored by default. Keep heavy optional dependencies in their dedicated requirements files so the core install remains fast and predictable.

## Project Structure

```text
Dan.py                Terminal entry point
dan_gui_modern.py     Modern desktop GUI entry point
dan_gui.py            Legacy desktop GUI/controller shell
agent.py              Agent loop and tool orchestration
providers.py          Model provider adapters
tool_registry.py      Shared tool registry
tools.py              Core filesystem, search, and shell tools
code_execution.py     Structured run and test loop tools
code_tools.py         Lint, format, analysis, and dependency helpers
knowledge/            Persistent memory tools
web/                  Web fetch and search tools
workers/              Worker pool
actions/              Reusable prompt/action templates
tests/                Pytest suite
```

## Production Readiness Notes

Dan can execute commands and code by design. Production use should keep this capability bounded by path validation, command validation, timeouts, visible output, and explicit user intent. New tools should extend the existing registry and security utilities rather than creating separate execution paths.
