# Meerada LLManager — desktop app

A native-window version of the Manager. It runs a local server, opens it in a
desktop window, and uses **your own provider keys**, stored **encrypted on this
machine** (`~/.meerada/keyvault.bin`). Prompts and keys never leave the device.
Every session's real cost is tracked, and you can mark answers accepted to see
**CPAT — cost per accepted task** per model.

## Run it from source (now)

```bash
pip install ".[desktop]"     # installs pywebview + cryptography
meerada app                  # opens the native window
```

No pywebview? `meerada app` still works — it opens in your default browser and
prints how to get the native window. Same app either way.

First launch: click **🔑 Keys**, connect a provider key (OpenAI, Groq, DeepSeek,
Mistral, or an **OpenRouter** key to reach Claude / Gemini / GPT through one
OpenAI-compatible endpoint). Then add sessions, give each its own model and task,
and run them in parallel. Pop any session out (**⧉**) into its own window.

## The Handshake, inside the app

Your conversations move freely between models — with the whole history:

- **📥 Import history** — the app scans `~/.claude/projects` for your **Claude Code**
  sessions (one click each), or upload a **Claude.ai** / **ChatGPT** data export
  (`conversations.json`), a Claude Code `.jsonl`, or any `User:` / `Assistant:`
  transcript. The conversation becomes a live session on the model you pick.
  Oldest turns are trimmed to a prompt budget (~120k chars); tool dumps are
  summarised; harness noise and private reasoning are dropped.
- **↔ Switch mid-conversation** — change the model in a session's dropdown and the
  history + attachments carry over. Nothing is lost.
- **⇄ Fork** (⋯ menu) — copy the conversation to a second model, side by side.
- **📎 / 📁 Attach** (⋯ menu) — files or a folder (browser picker, or a local path
  in the desktop app). Text/code only, vendor/build dirs skipped, size-capped.
  Sent as system context, so it persists across turns and travels on handoff.
- **⚡ Relay** (⋯ menu) — a cheap model drafts, the session's model polishes. Both
  costs land on the ledger.
- **⚖️ Judge answers** (toolbar) — after *Send to all* / *Compare all*, a judge
  model ranks the answers and writes one best answer, in its own Verdict pane.
- **Refresh-safe** — sessions live on the local server; reloading the window
  restores them. (They are in memory: closing the app ends them — export a
  transcript from the ⋯ menu if you want to keep one.)

Reading local files (`~/.claude` scan, folder by path) is desktop/local only;
the hosted app accepts uploads.

## New models, automatically

Connect an **OpenRouter** key and the picker grows by itself: everything that
launched in the last three weeks (🆕, e.g. Ox Alpha = `z-ai/glm-5.3-flash`),
every `:free` variant, and one flagship per big lab — pulled hourly from
OpenRouter's public catalog, on your own key. The same feed drives the Arena's
"New on the market" band and the grader's pricing.

## Model ids → which key

Routing picks the provider whose key serves the model:

| you type | uses key |
|----------|----------|
| `gpt-4o`, `gpt-4o-mini`, `o3` | OpenAI |
| `openai/gpt-oss-120b`, `qwen/qwen3.8-27b` | Groq (free tier) |
| `deepseek-chat` | DeepSeek |
| `anthropic/claude-3.5-sonnet`, `google/gemini-2.5-pro` | OpenRouter |
| `mistral-large-latest` | Mistral |

## Package a downloadable installer

Real one-click `.exe` / `.app` / `.AppImage` (per-OS, build on that OS):

```bash
pip install ".[desktop]" pyinstaller
pyinstaller --name Meerada --windowed --onedir \
    --collect-all handover --collect-all webview packaging/app_entry.py
# -> dist/Meerada/Meerada.exe  (a folder; launches instantly, AV-friendly)
```

- **`--onedir` (a folder), not `--onefile`** — onefile re-extracts to a temp dir on
  every launch, which is slow and frequently blocked/quarantined by antivirus
  (that's the "stuck at the same place" symptom). onedir is unpacked once.
- On Windows, wrap it in a proper installer (Start-menu + desktop shortcut,
  uninstaller, no admin): install [Inno Setup](https://jrsoftware.org/isdl.php),
  then `ISCC packaging\installer.iss` → `installer\MeeradaSetup.exe`.
- `--collect-all handover` bundles the package **and its data** (the cockpit UI).
- `--collect-all webview` bundles the pywebview backend.
- **Windows** uses Edge WebView2 (present on Win10/11); no extra runtime.
- **Code signing** (so the OS doesn't warn users) is the last step before public
  distribution: Apple Developer ID ($99/yr) for macOS notarization, an
  Authenticode cert (~$100–400/yr) for Windows. Skip it for internal testers.
- Cross-OS builds need each OS (use CI — GitHub Actions matrix — to produce all
  three from one push).

## Build all three OSes automatically (CI)

`.github/workflows/desktop-build.yml` builds Windows / macOS / Linux binaries for
you. Two ways to run it:

- **On demand:** GitHub → **Actions** → **desktop-build** → **Run workflow**. When
  it finishes, download the binaries from the run's **Artifacts** (Meerada-windows,
  Meerada-macos, Meerada-linux).
- **On release:** push a tag — `git tag v0.1.0 && git push origin v0.1.0` — and the
  binaries are built and **attached to a GitHub Release** automatically, so testers
  download from the Releases page.

Binaries are unsigned, so first launch shows an OS warning (Windows SmartScreen /
macOS Gatekeeper) — fine for a tester group; add code signing before public
release.
