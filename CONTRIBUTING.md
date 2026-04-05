# Contributing to PipePost

Thanks for your interest in contributing! PipePost welcomes contributions of all kinds — bug fixes, new sources/destinations, documentation improvements, and feature ideas.

## Getting Started

1. **Fork** the repository and clone your fork:

   ```bash
   git clone https://github.com/<your-username>/pipepost.git
   cd pipepost
   ```

2. **Create a virtual environment** and install dev dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # or .venv\Scripts\activate on Windows
   pip install -e ".[dev]"
   ```

3. **Create a branch** for your change:

   ```bash
   git checkout -b my-feature
   ```

## Development Workflow

Run these before submitting a PR:

```bash
# Lint
ruff check pipepost/

# Format
ruff format pipepost/

# Type check
mypy --strict pipepost/

# Test
pytest tests/ -v
```

All checks must pass. The CI pipeline runs the same commands on Python 3.11 and 3.12.

## Pull Request Guidelines

- Keep PRs focused — one feature or fix per PR.
- Write clear commit messages that explain *why*, not just *what*.
- Add or update tests for any new functionality.
- Update documentation (README, docstrings) if behavior changes.
- Make sure all CI checks pass before requesting review.

## Adding a Source or Destination

PipePost uses auto-discovery. To add a new source or destination:

1. Create a new file in `pipepost/sources/` or `pipepost/destinations/`.
2. Subclass `Source` or `Destination` from the respective `base` module.
3. Register it with `register_source()` or `register_destination()`.
4. Add tests in `tests/`.

See the existing implementations for reference.

## Code Style

- Follow the existing code style (enforced by `ruff`).
- Use type annotations everywhere (`mypy --strict` must pass).
- Prefer `pathlib.Path` over `os.path`.
- Use `httpx` for HTTP requests (async).

## Reporting Issues

- Use [GitHub Issues](https://github.com/densul/pipepost/issues).
- Include steps to reproduce, expected behavior, and actual behavior.
- Include your Python version and OS.

## License

By contributing, you agree that your contributions will be licensed under the [AGPL-3.0](LICENSE) license.
