# Meerada — working name (`meerada` CLI, package `handover`)

**Measure what your LLM spend actually buys.**

Every dashboard shows you tokens and latency. Nobody shows you the only number
that matters: **CPAT — cost per accepted task** — what one *verified, completed*
unit of work really costs, including the retries, the reasoning-token burn, and
the attempts that died on the way.

`meerada` (working name — may change) reads your LLM traffic locally, verifies task success with programmatic
signals (test exit codes, schema validation, output contracts), and renders a
ranked model leaderboard for **your** workload — not a synthetic benchmark.

## Quickstart

```bash
pip install -e .
meerada record events.jsonl # ingest a trace source (metadata extracted locally)
meerada report              # ranked HTML leaderboard: CPAT, waste, success rates
```

Zero infrastructure: local SQLite, one self-contained HTML file, no accounts.

## Privacy, by architecture

- Request/response **content never leaves your environment** — traces store only
  metadata, salted SHA-256 fingerprints, and aggregate scores.
- The salt is generated locally per database and is never transmitted.
- The report is a local file. Nothing is published anywhere.

## What the numbers mean

| Metric | Definition |
|---|---|
| **CPAT** | Σ cost of *all* attempts ÷ verified successful tasks |
| **TTAT** | Σ wall time of all attempts ÷ successful tasks |
| Attempts/win | Σ attempts ÷ successful tasks |
| Waste | retries + excess reasoning + uncached context + dead tasks |

Every proportion carries its sample size and a Wilson 95% confidence interval.
Every estimated (non-measured) number is labelled `derived`. Tasks with no
verification signal are **excluded**, never guessed.

## Status

P0 (core pipeline + report) complete. P1 in progress: task clustering,
output-contract extraction, golden sets, and `meerada pack` — the handover pack that
lets you migrate a workload between models with a measured gap report.

See `SPEC.md` for the full design. Development: `make test`, `make lint`.
