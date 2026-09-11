# Meerada Guard — the watchdog and the cage for AI models at work

**One line:** Guard sits on every model call in your workspace and answers, live,
two questions a program can answer: *is this task still moving, or is the model
burning money in place?* and *is the model trying to take anything out of the
workspace it shouldn't?* — then tells you immediately, on the desktop, in
Slack, or in the LLManager cockpit.

It ships inside the same download as LLManager (`meerada app`), and as a
standalone command (`meerada guard`). Free, open-source, no account.

---

## 1. Where it sits on the traffic

| Mode | What it watches | How | User does |
|---|---|---|---|
| **Inside LLManager** | every call the cockpit makes, every session | `GuardedCaller` wraps the provider call: cage on what leaves, meter on what comes back, budget gate before the next call | nothing — on by default |
| **Beside Claude Code** (and any tool that writes JSONL logs) | live sessions under `~/.claude/projects` | tails the session logs, rebuilds the turn stream (tokens, thinking, tool calls, tool results), alerts from the tray | nothing — starts with the desktop app; or `meerada guard` in a terminal |
| **Company-wide** | every user on the machine | one machine policy file; `locked` fields users can't override; every alert also POSTs to the company webhook | IT drops one file |

No proxy, no key, no change to how people work. Guard reads what the tools
already write on the machine and what LLManager already sees.

## 2. The verdict: stuck vs. working hard

Every session gets a `StallDetector`. It scores two things separately —
**stuck** and **burn** — and the tie-breaker is *verifiable progress*:

| Signal | Stuck | Burn |
|---|---|---|
| no output for `silence_s` (default 120s) | ✓ | |
| the same tool call with the same arguments `max_repeat` times (3) since the last progress | ✓ | |
| the answer repeats the previous ones (trigram overlap ≥ 0.6) | ✓ | |
| thinking tokens ≫ output tokens (ratio > 8) | | ✓ |
| session or daily budget reached | | ✓✓ |
| spent > 2× what the exchange says this kind of task costs (p90 CPAT) | | ✓ |
| elapsed > 2× the exchange's TTAT for this kind of task | | ✓ |

**Progress** = a step a program can see: a file written or edited, a test run
that passed, a build that succeeded, a human sending a new message.

- Signals **without** progress → `stalled` (⏸) or `burning` (🔥).
- The same signals **with** recent progress → `watch` with *working hard —
  watch the budget* (⚠). Costly is not the same as stuck.
- A budget cap is always `burning`, progress or not: it is your money.

Alerts fire on **state changes only** — never the same verdict twice.

## 3. What happens when it fires

1. **Alert** — desktop notification (Windows balloon / macOS / Linux, zero
   dependencies), console line, cockpit toast, optional company webhook.
2. **Action** (policy `action`):
   - `alert` (default): tell the human, keep going.
   - `stop`: LLManager refuses the *next* call with a clear message
     ("session budget reached, $5.00 — raise the cap in guard.toml").
3. **In the cockpit**: ⏸/🔥 toast with the reasons, and the Handshake button is
   right there — move the whole conversation to another model with one click.
   That is the move no vendor can offer: the guard that catches the stall is
   the tool that switches you out of it.

## 4. The cage

Runs on **outbound** text — prompts, attachments, tool-call arguments, shell
commands — *before* it leaves the machine or executes. Findings never contain
the secret itself (redacted to a 4-char prefix).

| Finds | Default |
|---|---|
| API keys / tokens / private keys (OpenAI, Anthropic, AWS, GitHub, Slack, Google, generic `api_key=`) | **block** |
| paths outside the workspace roots (`allowed_roots`; default = current directory) | warn |
| outbound network commands (`curl`, `wget`, `scp`, `rsync`, `ssh`, `Invoke-WebRequest`, `aws s3 cp`, `git push`, …) | warn |
| outbound hosts not in `allowed_hosts` (a bare link in prose is fine; a link inside a `curl` is not) | warn |
| reading secrets from the environment / dotfiles (`printenv`, `$env:`, `~/.ssh`, `~/.aws`, `.env`, `id_rsa`, …) | warn |

`cage_action = "block"` turns every warn into a block. In LLManager a block
means the call never leaves the machine. Beside Claude Code the guard cannot
stop the tool (it only reads the log) — it alerts immediately, which is the
half-security the user asked for: you *know*, within two seconds, that the
model reached for `~/.aws/credentials` or ran `curl` to an unknown host.

## 5. Policy — one file, three layers

```toml
# ~/.meerada/guard.toml            (user)
# %ProgramData%\Meerada\guard.toml (company, Windows)  /etc/meerada/guard.toml (company, Unix)
enabled = true

silence_s = 120
max_repeat = 3
session_budget_usd = 5.0
daily_budget_usd = 25.0
action = "alert"          # alert | stop

cage = true
allowed_roots = ["C:/work"]
allowed_hosts = ["github.com", "api.openai.com"]
block_secrets = true
cage_action = "warn"      # warn | block

webhook_url = "https://hooks.slack.com/services/…"   # company
locked = ["session_budget_usd", "daily_budget_usd", "cage", "webhook_url"]
```

Precedence: defaults < user file < **company file** (its `locked` fields cannot
be overridden by the user) < `MEERADA_GUARD_POLICY=<path>` (explicit, for
pilots). `meerada guard policy` prints the effective result and its source.

## 6. Company-wide install (10 minutes, $0)

1. Install the desktop app (or `pip install "handover[desktop] @ git+https://github.com/ravemm-hub/meerada"`) on each machine — or just `meerada guard` as a login task.
2. `meerada guard init --company` on one machine, edit the file, copy it to
   every machine (GPO / Intune / Ansible / a shared drive script).
3. Set `webhook_url` to a Slack / Teams incoming webhook: every stall, burn and
   cage finding from every desk lands in one channel, with the session label.
4. Lock what must not change: `locked = [...]`.

Nothing leaves the company: Guard has no server, no account, no telemetry. The
webhook is yours.

## 7. Commands

```
meerada guard                 # watch live Claude Code sessions (Ctrl+C to stop)
meerada guard --no-desktop    # console only (servers, CI)
meerada guard policy          # effective policy + where it came from
meerada guard check file.txt  # run the cage on a file (exit 2 = block) — pre-commit / CI
meerada guard init            # write a starter ~/.meerada/guard.toml
meerada guard init --company  # write the machine-wide policy
```

HTTP (LLManager): `GET /guard` → per-session verdicts, today's spend, last alerts.

## 8. What's next

- **Stall & Burn index on the exchange** — per model: how often it stalls on the
  battery, how often it runs away past 3× the median output, time-to-stall.
  Public, measured, nobody publishes it.
- **Proxy mode** — an OpenAI/Anthropic-compatible `base_url` on localhost so
  *any* tool's traffic is metered and caged, with real blocking.
- **Auto-handshake** — on `stalled`, LLManager offers (or, by policy, performs)
  the move to the next-best model from the exchange with the history intact.
