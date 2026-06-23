# Contributing to MaestroAgent

Thanks for your interest in contributing! MaestroAgent is open-source (MIT) and welcomes contributions of all kinds: bug reports, feature requests, code, docs, templates, and plugins.

## Code of conduct

Be kind. Be concrete. Be patient. Disagreement is fine; disrespect is not.

## Quick start for contributors

```bash
# Fork + clone the repo
git clone https://github.com/YOUR-USERNAME/maestroagent.git
cd maestroagent

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd ../frontend
pnpm install

# Run in dev mode (two terminals)
# T1: maestro serve
# T2: pnpm dev
```

See [`docs/BROWSER_SETUP.md`](docs/BROWSER_SETUP.md) for full setup details.

## Project structure

Read [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md) first. The key boundary:

- **`maestro_core`** is pure Python with zero UI deps. Don't import FastAPI, React, or any provider SDK here.
- **`maestro_api`** is the only HTTP boundary. Routes are thin; business logic lives in core.
- **`frontend/`** talks to the backend only via the typed `api` client in `src/lib/api.ts`.

## How to contribute

### Bug reports

Open an issue with:
1. MaestroAgent version (`maestro --version` or check the status bar).
2. Browser + OS (for PWA issues) or Python version (for backend issues).
3. Steps to reproduce.
4. Expected vs actual behavior.
5. Relevant logs (from the Terminal panel or `docker compose logs`).

### Feature requests

Open an issue with the `feature` label. Describe the use case, not just the solution. The maintainers will discuss whether it fits the v0.1 / v0.2 / v1.0 scope.

### Pull requests

1. **Branch from `main`**: `git checkout -b feat/my-feature`.
2. **Keep PRs small**: one feature or fix per PR. Large PRs take longer to review.
3. **Write tests**: add or update tests in `backend/tests/` for backend changes. Frontend tests are coming in v0.2.
4. **Run checks locally**:
   ```bash
   cd backend && pytest && ruff check . && black --check .
   cd ../frontend && pnpm lint && pnpm typecheck
   ```
5. **Update docs**: if your change affects user-facing behavior, update `docs/` and `README.md`.
6. **Write a clear PR description**: what changed, why, and how to test it.

### Templates and plugins

Templates (in `backend/examples/templates/`) and plugins (in `backend/plugins/`) are the easiest way to contribute:

- A template is a single Python file exposing `build_graph(goal: str, **extras) -> Graph`.
- A plugin is a single Python file exposing `PLUGIN_ENTRIES = [PluginEntry(...)]` or a `register(registry)` function.

Drop a file in the right directory and it auto-loads. No build step.

## Coding standards

### Python (backend)

- **Type hints everywhere.** The codebase targets Python 3.11+.
- **Pydantic v2** for all data models.
- **Async-first.** All I/O is `async def`. Use `anyio.to_thread.run_sync` for sync SDKs.
- **Docstrings** on every public module, class, and function. Google style.
- **Line length 100.** Run `black` + `ruff` before committing.

### TypeScript (frontend)

- **Strict mode.** `tsconfig.json` has `strict: true`.
- **No `any`** without a comment explaining why.
- **Functional components + hooks.** No class components.
- **Zustand for global state.** Don't reach for Redux.
- **Tailwind for styling.** No CSS-in-JS.

### Rust (optional Tauri wrapper, v0.3)

- Only used for the optional desktop wrapper. The browser PWA is the primary surface.
- Follow the existing style in `desktop/src-tauri/src/`.

## Architecture principles

When proposing changes, keep these in mind:

1. **Local-first.** Everything should work with no cloud dependency. Cloud is opt-in.
2. **Browser-first.** New features must work in the PWA. Native-only features are out of scope.
3. **Loops are first-class.** Don't hide iteration inside nodes. Use `LoopHandler`.
4. **Verifiable autonomy.** Every loop's exit must be checkable by an independent verifier.
5. **Observability.** Every transition emits an event. The UI is a consumer, not a special case.
6. **No UI in core.** `maestro_core` stays pure Python.

## Release process (for maintainers)

1. Update `VERSION` in `backend/maestro_core/__init__.py` and `frontend/package.json`.
2. Update `docs/CHANGELOG.md` (coming in v0.2).
3. Tag: `git tag v0.X.Y && git push --tags`.
4. GitHub Actions (coming in v0.2) builds the Docker image and publishes it.

## Getting help

- **Issues:** [github.com/your-org/maestroagent/issues](https://github.com/your-org/maestroagent/issues)
- **Discussions:** [github.com/your-org/maestroagent/discussions](https://github.com/your-org/maestroagent/discussions)

## License

By contributing, you agree that your contributions are licensed under the MIT license.
