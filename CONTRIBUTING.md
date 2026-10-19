# Contributing

Thanks for your interest in contributing to **Auto Test Android**! This project
is a vision-based Android UI automation framework. Below are the guidelines to
keep the codebase clean and consistent.

## Getting started

1. Fork the repository and clone it locally.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and add your API keys.
4. Create a feature branch: `git checkout -b feature/my-change`.

## Code style

- Follow [PEP 8](https://peps.python.org/pep-0008/).
- Use type hints on all public functions and methods.
- Write docstrings for public modules, classes and functions.
- Keep functions small and focused; prefer composition over monoliths.
- Use the `logging` module (via `config.logger`) instead of `print`.

## Adding a new platform

1. Create `platforms/<name>.py` with a class extending `BaseUploader`.
2. Implement `upload(video_path, metadata)` using the helpers in `ui_automator`.
3. Register the class in `platforms/__init__.py`.
4. Add a unit test under `tests/`.

## Testing

Run the test suite before submitting a pull request:

```bash
pytest
```

Make sure all tests pass and add new tests for any new functionality.

## Commit messages

Use clear, conventional commit messages:

- `feat: ...` for new features
- `fix: ...` for bug fixes
- `refactor: ...` for code restructuring
- `docs: ...` for documentation changes
- `test: ...` for test changes
- `chore: ...` for maintenance tasks

## Security

- **Never** commit API keys or secrets.
- Keep all secrets in `.env` (gitignored).
- Do not hardcode private endpoints or infrastructure URLs.

### Secret scanner

The repository ships a dependency-free scanner that refuses commits containing
what looks like a credential. Enable the pre-commit hook once per clone:

```bash
git config core.hooksPath .githooks
```

The hook then scans the staged files on every commit. You can also run it by
hand at any time:

```bash
python scripts/check_secrets.py           # staged files
python scripts/check_secrets.py --all     # every tracked file
python scripts/check_secrets.py --history # every blob in every commit
```

A finding aborts the commit and prints the file, the line and the kind of
secret. Matched values are redacted, so a finding never leaks the credential
into a terminal scrollback or a CI log. If a finding is a false positive, make
the value look like a placeholder (for example `your_key_here`) or extend the
rules in `scripts/check_secrets.py`.

## Pull requests

- Keep pull requests focused on a single concern.
- Reference any related issue in the description.
- Ensure CI (tests) passes.
