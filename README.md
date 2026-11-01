# AI Engineering Lab

A learning journey and engineering portfolio. This repository holds small, reproducible experiments that explore the engineering trade-offs of modern AI systems: architecture, cost, latency, reliability and security. Experiments are built one at a time, measured with documented methodologies, and written up with their limitations.

## Principles

- **One experiment at a time.** Understand it, measure it, document it, then move on.
- **Measure, don't assume.** Claims are backed by reproducible benchmark data.
- **No fabricated results.** Results are marked pending until benchmarks have actually been run.
- **Model-agnostic.** Models are selected through configuration, never hardcoded.
- **Security-first.** Secrets stay out of the repo; generated code never runs unrestricted; synthetic data only.
- **Minimal abstractions.** Shared code is introduced only when an experiment needs it.

## Experiments

| # | Experiment | Status |
|---|---|---|
| 01 | [MCP vs Code Mode](experiments/01-mcp-vs-code-mode/) | Design |

## Repository layout

```text
docs/           Architecture overview, standards and decision records (ADRs)
experiments/    One directory per experiment (README, configs, src, tests, results, linkedin)
shared/src/     Shared Python package `ai_lab` (config, utils; llm/benchmarking/evaluation planned)
templates/      Experiment template to copy when starting a new experiment
scripts/        Repository-level helper scripts (currently empty)
tests/          Tests for the shared package
.github/        CI workflows, issue and pull request templates
```

## Getting started

Prerequisite: [uv](https://docs.astral.sh/uv/). uv installs Python 3.12 automatically.

```bash
git clone https://github.com/ferozyk/ai-engineering-lab.git
cd ai-engineering-lab
uv sync
cp .env.example .env   # optional; only needed for live model calls
make check             # lint + typecheck + tests
```

## Common commands

| Command | Description |
|---|---|
| `make install` | Install dependencies with `uv sync` |
| `make lint` | Ruff lint and format checks |
| `make format` | Auto-format and fix lint issues |
| `make typecheck` | Run mypy in strict mode |
| `make test` | Run the default test suite (no live calls) |
| `make test-live` | Run tests that call real providers (needs credentials) |
| `make check` | Lint, typecheck and test |
| `make clean` | Remove caches |

## Configuration

Configuration is read from environment variables, optionally via a local `.env` file (see `.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | unset | Provider credential; only required for live model calls |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Provider API endpoint |
| `LLM_PROVIDER` | `openrouter` | Provider selector |
| `LLM_MODEL` | unset | Model identifier; must be chosen explicitly |
| `LLM_TEMPERATURE` | `0` | Sampling temperature (0 to 2) |
| `APP_ENV` | `development` | `development`, `test` or `production` |
| `LOG_LEVEL` | `INFO` | Standard logging level |

No key is needed to install the project or run the default tests. There is intentionally no default model: availability of hosted and free models changes, so choose one explicitly.

## Standards

- [Experiment standards](docs/standards/experiment-standards.md)
- [Benchmarking standards](docs/standards/benchmarking-standards.md)
- [Visual reporting standards](docs/standards/visual-reporting-standards.md)
- [LinkedIn content standards](docs/standards/linkedin-content-standards.md)
- [Architecture decision records](docs/decisions/)
- [Agent guidelines](AGENT_GUIDELINES.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

MIT. See [LICENSE](LICENSE).
