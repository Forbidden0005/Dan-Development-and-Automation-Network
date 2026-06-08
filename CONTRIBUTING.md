# Contributing to Dan

Thank you for your interest in contributing to Dan! This document provides guidelines for contributing to the project.

Before making any non-trivial change, read `ROADMAP.md` and `PROJECT_INTEGRITY.md`. The roadmap is the canonical direction document. New work should align with an active phase or the backlog — not introduce new direction.

For a complete onboarding walkthrough, see `ONBOARDING.md`.

## Requirements

- Python 3.11 or later
- Windows 10 or Windows 11 (Dan is a Windows-first application)

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/dan.git`
3. Create a new branch: `git checkout -b feature/your-feature-name`
4. Install core and dev dependencies:
   ```powershell
   pip install -r requirements-core.txt
   pip install -r requirements-dev.txt
   ```
5. Set up your API key (Windows):
   ```powershell
   $env:ANTHROPIC_API_KEY = "<your-api-key>"
   ```

## Development Workflow

1. Make your changes
2. Run tests: `python -m pytest tests/`
3. Update documentation if needed
4. Commit your changes with clear, descriptive messages
5. Push to your fork
6. Open a Pull Request

## Code Style

- Use `ruff` for linting: `python -m ruff check .`
- Use `black` for formatting: `python -m black .`
- Follow PEP 8 style guidelines
- Use type hints where appropriate
- Write docstrings for new functions and classes
- Keep functions focused and single-purpose

## Testing

- Add tests for new features
- Ensure all tests pass before submitting PR
- Run the test suite: `python -m pytest tests/`
- Run lint: `python -m ruff check .`
- Run repo health check: `python scripts/repo_health.py`

## Pull Request Guidelines

- Clearly describe the changes and motivation
- Reference any related issues
- Update README.md if adding new features
- Keep PRs focused on a single feature/fix

## Adding New Tools

To add a new tool to Dan:

1. Create your tool in the appropriate module (see `docs/ARCHITECTURE.md` for ownership boundaries):
   - General tools → `tools.py` or a new module under `actions/`, `knowledge/`, `web/`, or `workers/`
   - Security-sensitive tools → `tools_secure.py`
2. Register the tool in `tool_registry.py`
3. Add the tool to `register_all_tools()` in `dan_gui_support.py` — this is the canonical registration entry point for both the GUI and CLI
4. Add documentation to the README
5. Include tests for the new tool in `tests/`

## Adding New Actions

To add a new automation action:

1. Create a markdown file in `actions/` directory
2. Follow the format: Description + Prompt
3. Test the action with `/action-name`
4. Document it in the README

## Questions?

Open an issue for questions, bug reports, or feature requests.
