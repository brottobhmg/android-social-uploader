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

## Pull requests

- Keep pull requests focused on a single concern.
- Reference any related issue in the description.
- Ensure CI (tests) passes.
