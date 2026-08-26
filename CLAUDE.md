# CLAUDE.md — HANDOVER

## What this project is
A system that measures LLM workloads by **completed verified task** (not by token),
and migrates workloads between models by extracting a "handover pack" from historical traces.

Read `SPEC.md` once at the start of a work session. Do not re-read it every turn.

## Non-negotiable rules
1. **No request/response content ever leaves the tenant boundary.** Only metadata, salted hashes, and aggregate scores.
2. **Programmatic verification before model judgement.** Judge is a last resort and must be labelled.
3. **Every metric carries n and a confidence interval.** An alert without statistical significance is a bug.
4. **Every field is graded** `measured` / `derived` / `declared`.
5. **Everything is async.** Nothing we run may sit in the customer's request path.
6. **Every process that calls a model has a hard daily budget cap** read from config. Exceeding it stops the process.
7. Nothing is published to any network. Reports are local files.

## Stack
Python 3.12 · FastAPI · Pydantic v2 · Postgres 16 · DuckDB · Redis+arq · Typer · Jinja2 · pytest
Deployment: docker-compose on a single VPS. **No Kubernetes. No microservices. No vector DB. No frontend framework.**

## Conventions
- Files stay under 300 lines. Split before exceeding.
- Full type hints. `mypy --strict` on `src/`.
- Pydantic models for every boundary. No raw dicts crossing module lines.
- `ruff` for lint and format. Line length 100.
- Money is `Decimal`, never `float`.
- Timestamps are timezone-aware UTC. Always.
- Schema changes bump `schema_version` and add a migration.

## Testing
- Every module ships with tests. Write the failing test first.
- **Tests never call a live model API.** Use recorded fixtures in `tests/fixtures/`.
- Statistical code (`canary/stats.py`, `canary/drift.py`) needs property-based tests with known distributions.

## Working style
- For any task larger than one function: produce a plan, wait for approval, then write code.
- Work on one module at a time. Do not refactor adjacent modules unprompted.
- When you need a file, name it. Do not scan the repository.
- If SPEC.md is ambiguous, ask. Do not invent a design decision and proceed.

## Commands
```
make dev        # docker-compose up
make test       # pytest
make lint       # ruff + mypy
make report     # generate a local HTML report from fixtures
```
