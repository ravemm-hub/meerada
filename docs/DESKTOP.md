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
pyinstaller --name Meerada --windowed --onefile \
    --collect-all handover --collect-all webview packaging/app_entry.py
# -> dist/Meerada.exe  (or Meerada.app / Meerada on macOS/Linux)
```

- `--collect-all handover` bundles the package **and its data** (the cockpit UI).
- `--collect-all webview` bundles the pywebview backend.
- **Windows** uses Edge WebView2 (present on Win10/11); no extra runtime.
- **Code signing** (so the OS doesn't warn users) is the last step before public
  distribution: Apple Developer ID ($99/yr) for macOS notarization, an
  Authenticode cert (~$100–400/yr) for Windows. Skip it for internal testers.
- Cross-OS builds need each OS (use CI — GitHub Actions matrix — to produce all
  three from one push).
