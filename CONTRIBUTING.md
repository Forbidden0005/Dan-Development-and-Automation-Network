# Contributing to Dan

Thank you for your interest in contributing to Dan! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/dan.git`
3. Create a new branch: `git checkout -b feature/your-feature-name`
4. Install dependencies: `pip install -r requirements.txt`
5. Set up your API key: `export ANTHROPIC_API_KEY="<anthropic-api-key>"`

## Development Workflow

1. Make your changes
2. Run tests: `python -m pytest tests/`
3. Update documentation if needed
4. Commit your changes with clear, descriptive messages
5. Push to your fork
6. Open a Pull Request

## Code Style

- Follow PEP 8 style guidelines
- Use type hints where appropriate
- Write docstrings for new functions and classes
- Keep functions focused and single-purpose

## Testing

- Add tests for new features
- Ensure all tests pass before submitting PR
- Run the test suite: `python -m pytest tests/`

## Pull Request Guidelines

- Clearly describe the changes and motivation
- Reference any related issues
- Update README.md if adding new features
- Keep PRs focused on a single feature/fix

## Adding New Tools

To add a new tool to Dan:

1. Define the tool in `tools.py` or create a new module
2. Register it in `tool_registry.py`
3. Add documentation to the README
4. Include tests for the new tool

## Adding New Actions

To add a new automation action:

1. Create a markdown file in `actions/` directory
2. Follow the format: Description + Prompt
3. Test the action with `/action-name`
4. Document it in the README

## Questions?

Open an issue for questions, bug reports, or feature requests.
