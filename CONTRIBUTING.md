# Contributing

## Development setup

```bash
uv sync --all-packages
cp .env.example .env   # optional
make check
```

Python 3.12 is installed by uv automatically. Experiments are uv workspace members; always install with `--all-packages` (or `make install`), because a plain `uv sync` installs only the root package and removes the members.

## Workflow

1. Create a branch from `master`.
2. Make small, focused commits.
3. Run `make check` before opening a pull request.
4. Open a pull request and complete the checklist in the template.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `chore: initialize repository tooling`
- `docs: add experiment standards`
- `feat: add shared configuration module`
- `test: add initial project tests`
- `ci: add lint workflow`
- `fix: handle empty environment values`
- `refactor: simplify settings loading`

## Quality gates

`make check` runs Ruff (lint and format check), mypy in strict mode and pytest. It must pass.

## Adding a new experiment

1. Copy `templates/experiment-template/` to `experiments/NN-short-name/`.
2. Fill in the README sections; keep results marked as pending until benchmarks have been run.
3. Follow the lifecycle in [experiment standards](docs/standards/experiment-standards.md).
4. Record significant technical choices as an [ADR](docs/decisions/README.md).

## Never commit

- `.env` files, API keys or credentials
- Virtual environments
- Model weights
- Temporary logs

## Pull requests

The pull request template contains the checklist reviewers will use.
