# TASKS.md — סדר בנייה עם פרומפטים מוכנים ל-Claude Code

**כללי עבודה:** משימה אחת לכל סשן. `/clear` בין משימות. אחרי כל משימה — `make test && make lint` ירוקים לפני שממשיכים.
**חלוקת מודלים:** משימות מסומנות `[PLAN]` — מודל חזק. משימות `[BUILD]` — מודל זול מספיק.

---

## P0 — הליבה (שבועות 1–2)

### T1 · פיגומים `[BUILD]`
> Set up the repo skeleton per SPEC.md §12. Create pyproject.toml with the stack from CLAUDE.md, a Makefile with dev/test/lint/report targets, docker-compose.yml with Postgres 16 and Redis, ruff and mypy strict config, and an empty package tree under src/handover/. No business logic. Show me the file tree when done.

### T2 · סכמות `[PLAN]`
> Implement the Pydantic v2 models in src/handover/schema/ for Trace and Task exactly as specified in SPEC.md §3.1 and §3.2. Every field, every nested object. Money as Decimal, timestamps as timezone-aware UTC. Include schema_version. Write tests that validate a full example trace, reject a trace containing any content field, and round-trip through JSON. Do not add fields that are not in the spec.

### T3 · נרמול ואדפטרים `[BUILD]`
> Implement src/handover/collect/: a Normalizer that converts provider payloads into Trace, plus two adapters — litellm_adapter.py (a LiteLLM success/failure callback) and jsonl_adapter.py (reads a JSONL file). The normalizer computes salted SHA-256 fingerprints for system prompt template (variables stripped), input, and output schema. Salt comes from tenant config and never leaves. Assert in tests that no content string survives normalization.

### T4 · מרכיב משימות `[PLAN]`
> Implement src/handover/assemble/task_assembler.py per SPEC.md §3.2. Use explicit task_id when present; otherwise apply the heuristic (same session, same system_prompt_fingerprint, gap under 120s, input overlap over 0.8). A task succeeds if any attempt verified as pass. Tasks with no verification signal get grade "unknown" and must be excluded from metrics. Write tests covering: single success, retry-then-success, all-failed, and unknown.

### T5 · מנוע אימות `[PLAN]`
> Implement src/handover/verify/ with the Verifier protocol from SPEC.md §5.3 and four implementations: ExitCodeVerifier, JsonSchemaVerifier, RegexContractVerifier, SilentAcceptanceVerifier. Each declares its evidence grade. A registry picks applicable verifiers per task and returns the strongest verdict available. Tests must cover the precedence rules from §5.1.

### T6 · מדדים `[PLAN]`
> Implement src/handover/metrics/core.py and waste.py with the exact formulas from SPEC.md §4.1 and §4.2. CPAT, TTAT, attempts_per_win, and the four waste components. Every returned metric must carry n and a Wilson confidence interval where it is a proportion. Waste components must carry their evidence grade. Property-based tests: CPAT is never lower than mean cost per attempt; zero successes returns None, not infinity.

### T7 · דוח מקומי `[BUILD]`
> Implement src/handover/report/ using Jinja2 to render a single self-contained HTML file: headline CPAT per model, waste breakdown, unknown-rate, and a per-cluster table (empty until P1). No external CSS or JS. No network calls. Output goes to a local path from config. Add `make report` running it against tests/fixtures.

### קבלת P0
> Generate 10,000 synthetic traces spanning 3 models and realistic retry patterns, ingest them end to end, and produce the HTML report. Report unknown-rate. Fail the acceptance if unknown-rate exceeds 30%.

---

## P1 — הפאנל וחבילת המסירה (שבועות 3–4)

### T8 · CLI `[BUILD]`
> Implement src/handover/cli/main.py with Typer: `hv record` (wrap or tail a trace source), `hv report`, `hv pack`. Everything runs locally against SQLite by default so a developer can use it with zero infrastructure. Postgres via config.

### T9 · אשכול `[PLAN]`
> Implement src/handover/cluster/ per SPEC.md §7.2 step 1. Feature vector from system_prompt_fingerprint, output_shape, and tool-sequence signature. HDBSCAN. Target 8–15 clusters; auto-merge if over 20. labeler.py generates a human-readable label from 5 representative cases using a model call — this is the only place in this module allowed to call a model, and it must respect the budget cap.

### T10 · חוזה ומדיניות כלים `[PLAN]`
> Implement pack/contract.py and pack/tool_policy.py per SPEC.md §7.2 steps 2–4. Infer JSON schema union with field frequencies, length distribution, tool transition graph, and ordering constraints with confidence levels. Extract edge cases: successful tasks that deviated from the contract, ranked by frequency times cost.

### T11 · סט זהב ואריזה `[PLAN]`
> Implement pack/goldset.py and pack/builder.py per SPEC.md §7.1 and §7.2 step 5. Only grade-A verified cases enter the golden set. n = max(30, 3% of cluster), stratified by cost and length. builder.py emits the handover-pack directory structure. Content references are tenant-local pointers, never inlined content.

### קבלת P1
> From one real trace file, produce a valid handover pack with 8–15 clusters and at least 30 golden cases in the largest cluster. Validate the pack against a schema.

---

## P2 — ההגירה (שבועות 5–8)

### T12 · שידור חוזר עם תקציב `[PLAN]`
> Implement replay/runner.py and replay/budget.py. Runs candidate models over golden cases and over a sampled 1% of live traffic, in-tenant only. Must use the Batch API where the provider supports it, prompt caching for fixed prefixes, and deduplicate by input_fingerprint. Hard daily budget cap that stops rather than warns. Stratified sampling weighted by cluster cost share.

### T13 · תרגום פרומפטים `[PLAN]`
> Implement migrate/translator.py: rewrite the extracted system prompts for a target model's conventions, preserving the output contract and tool policy from the pack. Output a diff plus a rationale per change for human review. Never auto-apply.

### T14 · דוח פער `[PLAN]`
> Implement migrate/gap_report.py producing exactly the table in SPEC.md §7.4: per cluster, cost share, from/to pass rates, deltas for pass, cost and latency, and a PASS/BLOCK verdict. BLOCK when the pass-rate drop is significant per the §6.3 rules. Estimate engineer-days per blocked cluster from its size and edge-case count.

### T15 · לולאת אופטימיזציה חסומה `[PLAN]`
> Implement migrate/optimizer.py: iterate prompt variants against failing clusters only. Hard limits: max 8 iterations per cluster, explicit budget, early stop when improvement is under 1 point across two consecutive iterations. Log every iteration with its cost. This module must be impossible to run without a budget.

### קבלת P2
> End-to-end migration on one pilot workload with a real gap report. Target: at least 70% of clusters pass without intervention.

---

## P3 — המדד והראיה (שבועות 9–12)

### T16 · סטטיסטיקה `[PLAN]`
> Implement canary/stats.py: Wilson intervals, two-proportion power and sample-size calculator per SPEC.md §6.1, CUSUM, and Benjamini-Hochberg FDR correction. Property-based tests against known distributions. This module is the credibility of the product — no shortcuts, no hardcoded thresholds.

### T17 · קנארי וסחף `[PLAN]`
> Implement canary/scheduler.py (hourly n=30, daily n=600, weekly n=5000 per SPEC.md §6.2) and canary/drift.py enforcing all four alert conditions from §6.3. An alert must render exactly the format in §6.4. Add a test proving that 480 simultaneous null comparisons produce fewer than 1 alert per day on average.

### T18 · מדד `[BUILD]`
> Implement metrics/index.py with the three-axis score and user weights per SPEC.md §4.3. Min-max normalization within cluster only, never across clusters. Render a static HTML index page locally.

### T19 · ראיה וקבלה `[BUILD]`
> Implement report/ additions: the monthly receipt (spend vs delivered tasks, waste breakdown, routing recommendation) and an evidence pack export — model inventory derived from traffic, change-detection log, and migration gap reports, as a signed local bundle.

### קבלת P3
> 30 consecutive days of time series with no gaps, and at least one real drift event detected and manually confirmed.

---

## עצירות החלטה
- **אחרי P1:** האם אחוז ה-`unknown` אצל לקוחות אמיתיים מתחת ל-30%. אם לא — עוצרים ומתקנים את שכבת האימות לפני P2.
- **אחרי P3 + 60 יום:** פחות מאירוע סחף אמיתי אחד לחודש → סוגרים את מוצר ההתרעות, נשארים עם ההגירה והקבלה.
