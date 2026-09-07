[English](CONTRIBUTING.md) | [简体中文](CONTRIBUTING.zh-CN.md)

# Contributing

Thank you for improving Desktop Focus Companion. Search existing issues before starting work. For substantial features or data-format changes, open an issue first and describe the user need and compatibility plan.

## Development workflow

1. Fork the repository and create a short-lived branch from the latest `main`.
2. Create a Python 3.12 virtual environment and install `requirements-dev.txt`.
3. Keep the change focused. Never commit databases, settings, logs, build output, or screenshots containing real user data.
4. Add tests for behavior changes; UI changes should cover both languages and relevant themes.
5. Run `quality.ps1` and require Ruff, mypy, and the full pytest suite to pass.
6. Open a pull request describing the problem, approach, verification, and visible changes. Include before/after images for UI work.

Concise Conventional Commit messages such as `fix: preserve timeline hit targets` are encouraged. By submitting a pull request, you agree that your contribution is licensed under the project's MIT License.

## Project invariants

- Database migrations must be forward-only, failure-safe, and must never “repair” a problem by deleting the user's database.
- Keep `app.__version__`, installer metadata, and release tags aligned.
- Preserve the local-first, account-free, telemetry-free product boundary unless a public design discussion agrees otherwise.
- Do not commit images, fonts, icons, or other copyrighted resources without permission.
