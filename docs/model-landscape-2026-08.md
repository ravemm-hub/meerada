# LLM Model Landscape — August 2026

*Research snapshot, 2026-08-27. Prices USD per 1M tokens (input/output), first-party API, standard tier. Machine-readable seed: `data/model_registry_seed.json`.*

## 1. Model inventory

| Provider | Model (ID) | Role | Input / Output $/1M | Cache & batch notes |
|---|---|---|---|---|
| OpenAI | `gpt-5.6-sol` | Flagship | $5.00 / $30.00 | Cached in $0.50; Aug 22 price cut; Batch −50% |
| OpenAI | `gpt-5.6-terra` | Workhorse | $2.00 / $12.00 | Batch −50% |
| OpenAI | `gpt-5.6-luna` | Budget | $0.20 / $1.20 | Batch −50% |
| Anthropic | `claude-fable-5` | Frontier | $10.00 / $50.00 | Cache hits 10% of input; Batch −50% (all models) |
| Anthropic | `claude-opus-5` | Flagship | $5.00 / $25.00 | 1M context |
| Anthropic | `claude-sonnet-5` | Workhorse | $2.00 / $10.00 | Intro price made permanent |
| Anthropic | `claude-haiku-4-5` | Budget | $1.00 / $5.00 | 200K context |
| Google | `gemini-3.1-pro` | Flagship (live) | $2.00 / $12.00 | 3.5 Pro announced May, still unreleased |
| Google | `gemini-3.6-flash` | Workhorse | $1.50 / $7.50 | Promo $0.75/$3.75 through 2026-12-31; 2.5 family retires 2026-10-16; Batch −50% |
| Meta | Llama 4 Maverick / Scout | Flagship OSS | ~$0.08–$0.90 via hosts | First-party Llama API wound down 2026-07-06; price depends on host |
| DeepSeek | `deepseek-v4-flash` | Workhorse | $0.14 / $0.28 | Cache hit $0.0028; 1M ctx; off-peak −50% |
| DeepSeek | `deepseek-v4-pro` | Flagship | $0.435 / $0.87 | Cache hit $0.0036 |
| Mistral | Mistral Medium 3.5 | Flagship (open, 128B) | $1.50 / $7.50 | Modified-MIT weights |
| Mistral | Mistral Large 3 / Small 4 | Value tier | ~$0.50/$1.50 · $0.15/$0.60 | Large 3 output price conflicted across sources — verify |
| Alibaba | `qwen3.8-max` | Flagship | $2.00 / $6.00 | Cached $0.25; Beijing region 60–70% cheaper |
| Alibaba | `qwen3.7-max` | Workhorse | $1.25 / $3.75 | |
| xAI | `grok-4.6` | Flagship | $2.00 / $6.00 | Cached $0.50; ≥200K-token prompts billed 2× |
| xAI | `grok-4.3` / `grok-build-0.1` | Workhorse / coding | $1.25/$2.50 · $1.00/$2.00 | |
| Amazon | Nova Premier | Flagship | $2.50 / $12.50 | Bedrock batch −50% |
| Amazon | Nova Pro / Lite / Micro | Workhorse tiers | $0.80/$3.20 · $0.06/$0.24 · $0.035/$0.14 | |
| Moonshot | Kimi K3 | Flagship (open, 2.8T MoE) | $3.00 / $15.00 | Cached $0.30; K2.6 $0.95/$4.00 |
| Zhipu | GLM 5.3 | Flagship | No per-token price yet | Sold via $18/mo Coding Plan |

## 2. How models are ranked today

| Leaderboard | Measures | Weakness | Leader (Aug 2026) |
|---|---|---|---|
| **LMArena** (Elo) | Blind pairwise human preference | Preference ≠ correctness: rewards style, verbosity, sycophancy; self-selected voters; arena-tunable | Claude Fable 5 (~1525); Claude Opus 4.8 tops coding (~1582) |
| **Artificial Analysis** Index v4.1 | Composite benchmarks + speed + price | Public benchmarks → contamination; single-pass; editorial weights | Claude Opus 5 (63.0), Fable 5 (62.1), Grok 4.6 (60.9) |
| **SWE-bench Verified** | % real GitHub issues resolved | Near-saturated (top 3 within 1 pt); Python-only; harness variance dwarfs model gaps | Opus 5 (96–97%); field moving to SWE-bench Pro |
| **GPQA Diamond** | PhD-level science MCQ | Saturated >90%; guessing floor; contamination | Gemini 3.1 Pro ~94.1%; Kimi K3 93.5% (open) |
| **AIME / math** | Competition math | 15 questions → huge variance; effectively solved | Saturated |
| **HLE** | 2,500 hard expert questions | Static Q&A, no tools in headline | Frontier <50% — retains headroom |
| **HELM** | Holistic multi-metric | **Maintenance mode since 2026-06-01** | Historical |
| **OpenRouter rankings** | Real routed traffic (tokens/wk) | Popularity × price, not quality; cost-sensitive skew | DeepSeek V4 Flash (~692B tok/wk); Chinese models 8 of top 10 |
| **Terminal-Bench 2.0** | End-to-end agentic terminal tasks (89 verified) | Small N; harness-dependent | Emerging agent-eval standard |
| **ARC-AGI-2** | Novel visual reasoning | Narrow; compute-heavy submissions dominate | GPT-5.6 Sol 92.5%, Opus 5 90.4% |
| **GDPval** (OpenAI) | Real occupational work, expert-graded | Grader subjectivity; provider-authored | Frontier separator |

## 3. Parameter mapping to our three axes

| Axis | Partial coverage today | The gap (our lane) |
|---|---|---|
| **Quality** = verified task success | SWE-bench / Terminal-Bench (executable pass-fail — closest); GDPval; AA composite | Nobody measures **production task success** on customer-realistic tasks with acceptance criteria, per task-type |
| **Speed** = time to accepted task | AA tokens/sec + TTFT (per-token, not per-task) | Nobody measures **end-to-end latency to acceptance**: a "fast" model needing 3 retries is slower than a slow one passing first try; reasoning time invisible in tok/s |
| **Value** = cost per accepted task | AA price-per-intelligence scatter; informal "$/resolved" on SWE-bench | Nobody measures **cost-of-failure**, retries-to-success distributions, or reasoning-token inflation (hidden thinking varies 10× per task) |

**Key insight:** every public leaderboard scores single-attempt, per-token metrics. None score the transactional unit customers buy — an accepted deliverable at its fully-loaded cost. That is HV Grade's open lane.

## 4. Free/cheap access for the canary harness (~hundreds of prompts/model/day)

| Provider | Free path | Limits | Batch |
|---|---|---|---|
| Google AI Studio | Free tier, no card | Flash-Lite ~1,000 RPD; Flash ~250 RPD; Pro ~100 RPD; prompts may train models | −50% |
| OpenAI | Data-sharing opt-in → 1M–10M free tok/day | Requires sharing traffic | −50% |
| Anthropic | No free tier (trial credits only) | — | −50%; cache reads −90% |
| xAI | $25 signup + $150/mo data-share credits | Most generous | — |
| DeepSeek | 5M tokens signup; paid near-free anyway | Off-peak −50% (01:00–04:00, 06:00–10:00 UTC) | No batch; cache substitutes |
| Alibaba | 1M tok/model one-time trial (~70M total) | 90 days, Singapore endpoint | −50% |
| Mistral | Experiment tier: $0, all models | ~1 req/s, ~500K TPM, ~1B tok/mo, eval use | −50% |
| Groq | Free tier; hosts Llama 4, Qwen 3, Kimi K2 | 30 RPM, 1K–14.4K RPD/model | — |
| OpenRouter `:free` | ~18–27 rotating free models | 20 RPM; 50 RPD (1,000 after $10 lifetime credits) | — |
| Local (Ollama) | Open weights: Llama 4, Qwen3, Mistral Small 4 | Hardware-bound | — |

**Bootstrap read:** AI Studio + Groq + Mistral Experiment + OpenRouter($10) covers Gemini and all major open-weight models at $0. DeepSeek paid ≈ $0.10–0.40/day at this volume. Real spend concentrates on OpenAI/Anthropic/xAI flagships — halved by Batch APIs, and xAI's $150/mo credits can zero out Grok.

**Caveats:** Mistral Large 3 output price conflicted ($1.50 vs $6.00); Google free-tier RPD varies by source — ai.google.dev rate-limits page is authoritative; GLM 5.3 pricing unpublished.
