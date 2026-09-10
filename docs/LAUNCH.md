# Launch kit — switch everything on for $0, then tell the world for $0

Everything below is free. Nothing here needs a card. Do the **Activate** list once,
then run the **Campaign** list day by day.

---

## Part 1 — Activate (one-time, ~45 minutes, $0)

### 1. Free grading keys → the exchange measures far more models
Each key is a free tier. Save each one as a plain text file in `Meerada\keys\`
(one line, the key only) and Claude sets the GitHub secret from the file.

| File | Where to create it | What it unlocks on the exchange |
|---|---|---|
| `groq.txt` | https://console.groq.com/keys | Llama / Qwen / gpt-oss at high speed (free tier) |
| `google.txt` | https://aistudio.google.com/apikey | Gemini 2.5 Pro / Flash (free tier) |
| `github-models.txt` | https://github.com/settings/tokens → *Fine-grained* → permission **Models: read** | GPT-4.1 / GPT-4o / Phi / Llama via GitHub Models (free tier) |
| `cerebras.txt` | https://cloud.cerebras.ai → API keys | Llama / Qwen at very high speed (free tier) |
| `mistral.txt` | https://console.mistral.ai/api-keys (free "Experiment" plan) | Mistral Small / Medium / Codestral (free tier) |

Already set: `openrouter.txt` (OpenRouter `:free` models).
Optional, costs money: `openai.txt` + a "yes to $1/day" → GPT-5.x graded on a hard daily cap.

### 2. Analytics — GoatCounter (free, no cookies, no consent banner)
1. https://www.goatcounter.com/signup → site code **`meerada`** (the pages already
   load `https://meerada.goatcounter.com/count`). If that code is taken, tell
   Claude the code you got and it is swapped in one line.
2. Dashboard: https://meerada.goatcounter.com

### 3. Search
1. https://search.google.com/search-console → *Add property* → **URL prefix**
   `https://meerada.app/` → verify with the **HTML tag** method → paste the
   `content="..."` value to Claude (it goes into the page head) → *Verify*.
2. Sitemaps → submit `https://meerada.app/sitemap.xml`.
3. https://www.bing.com/webmasters → *Import from Google Search Console* (one click).

### 4. Hosted tester on Render (already live at https://app.meerada.app)
- Dashboard → the service → **Environment**: make sure `MEERADA_BETA_OPEN` is
  **absent or `1`** (beta open = everything free).
- Free instance sleeps after 15 min; the repo's `keepalive` workflow pings it
  every 10 minutes, so it stays warm. Nothing to pay.

### 5. GitHub repo (the open-source front door)
- Topics, description and homepage are set (Claude did it).
- Settings → *General* → **Discussions: on** (free support forum, zero email).
- Star your own repo, then pin it on your profile.

### 6. Social accounts (create yourself — Claude never creates accounts)
| Account | Handle to try | Bio (paste) |
|---|---|---|
| X / Twitter | `@meerada_app` | Every AI model. Measured. Priced. Ranked. Free live exchange + LLManager: import your Claude/ChatGPT history and switch models mid-conversation. meerada.app |
| LinkedIn page | Meerada | same |
| Product Hunt | your personal account | — |
| Reddit | your personal account (needs some karma; comment helpfully for a week first) | — |
| Hacker News | your personal account | — |
| YouTube | Meerada | upload `Meerada\meerada-demo.webm` as **unlisted**, title "Meerada — import a Claude Code session and continue it on any model (90s)" |

Profile picture: `site/logo.svg` (export PNG 400×400). Banner: `site/assets/og.png`.

---

## Part 2 — The campaign (free channels, in order)

Rule: **lead with the measurement, not the product.** "Here is an honest, live,
verifiable ranking of every model" earns links; "download my app" does not.
Link the exchange first, the app second.

### Day 0 (today) — foundations
- [ ] YouTube video uploaded (unlisted) → paste the link to Claude → it goes on
      the LLManager page and in every post below.
- [ ] Pin the OG image to your X profile as the header.
- [ ] Post the **X thread** (below). Pin it.
- [ ] Post on **LinkedIn** (below) from your personal profile (pages get no reach).

### Day 1 — Reddit (largest free channel for this audience)
Post the **exchange** (not the app) to one subreddit per day, never cross-post
the same day (Reddit shadow-bans that):
1. r/LocalLLaMA — title: `I built a free live exchange that grades every model hourly on verifiable tasks (code w/ hidden tests, SQL on a real DB, agentic, safety) and prices them by cost per verified task`
2. r/ClaudeAI — the **Handshake** angle: `Import your Claude Code / Claude.ai history and continue it on any model (switch mid-conversation, history included) — free desktop app`
3. r/ChatGPT — same with ChatGPT export.
4. r/artificial, r/SideProject, r/opensource — the story: "I measured 100+ models hourly for $0 with free tiers; here is what the data says".
Post 14:00–16:00 Israel time (morning US). Answer every comment for 4 hours.

### Day 2 — Show HN (Tue–Thu, 15:00–17:00 Israel time)
Title (≤80 chars): `Show HN: Meerada – every AI model graded hourly on verifiable tasks, priced by CPAT`
URL: `https://meerada.app`
First comment — paste, in your own words if you like:
> I got tired of two things: benchmarks that are vibes, and being locked into
> whichever model I started a conversation in. Meerada is (1) a live exchange
> that grades every model it can reach, every hour, on programmatically
> verifiable tasks — hidden unit tests, SQL against a real database, exact
> answers, faithful summaries, agentic tool plans, safety refusals — and prices
> each model by cost per verified task; and (2) LLManager, a free desktop app
> that imports your Claude Code / Claude.ai / ChatGPT history and lets you
> continue it on any model on your own keys, switching mid-conversation.
> Everything is free (open beta); the engine is Apache-2.0. The measurement is
> honest and therefore humble: free-tier quotas, small samples, wide CIs, all
> shown. I would love brutal feedback on the battery and on the CPAT idea.
Stay online 6 hours. Never argue; thank, fix, reply with the commit link.

### Day 3 — Product Hunt
- Submit at https://www.producthunt.com/posts/new (launches 00:01 PT = 10:01 Israel).
- Tagline (≤60): `Every AI model. Measured. Priced. Ranked. Free.`
- Gallery: og.png, 3 screenshots (exchange table, Frontier Watch, LLManager with
  a handoff trail), the GIF.
- First comment: the HN note, shorter. Ask 10 friends to leave an honest comment
  (not just an upvote — PH weights comments).

### Day 4 — Directories (10 minutes each, permanent backlinks)
- https://theresanaiforthat.com/submit · https://www.futurepedia.io/submit-tool ·
  https://www.toolify.ai/submit · https://alternativeto.net (add as alternative to
  "LMArena", "OpenRouter", "TypingMind") · https://github.com/awesome-lists (PR to
  *awesome-llm*, *awesome-ai-tools*) · https://www.saashub.com/submit ·
  https://www.indiehackers.com (post the story).

### Day 5 — Newsletters (free submission forms)
- Ben's Bites: https://www.bensbites.com/submit · TLDR AI: https://tldr.tech/ai (reply
  to any issue with the link + one line) · The Rundown: submit form on site ·
  Hacker Newsletter picks from HN automatically.

### Week 2 — content that ranks (evergreen traffic)
One article, published on dev.to **and** Hashnode **and** LinkedIn articles:
`"I graded 100+ AI models every hour for a month for $0. Here's what actually changed."`
Structure: the battery → the surprises (which cheap models beat expensive ones on
CPAT) → the Frontier Watch chart → how to reproduce (repo). Claude drafts it from
the real grade_state.json when you say go.

### Always-on (5 min/day)
- Every "which model should I use for X?" thread on Reddit/HN/X → answer with the
  measured board link and the real numbers. That is the entire growth loop.
- Every new frontier model launch (OpenAI/Anthropic/Google/xAI/DeepSeek) → within
  the hour, post its **measured** first numbers from the exchange as a reply to
  the launch tweet and a Reddit comment. Speed + honesty = reach.
- Every Monday: "Frontier Watch weekly" — one screenshot, three lines, X + LinkedIn.

---

## Posts (copy-paste)

**X thread (opener):**
> Every AI model. Measured. Priced. Ranked. Free.
> I built a live exchange that grades every model it can reach, every hour, on
> tasks a program can verify — hidden unit tests, SQL on a real DB, agentic
> plans, safety — and prices each one by cost per verified task.
> meerada.app 🧵

> 2/ Benchmarks you can't reproduce are vibes. Here the checker is code, the
> battery is public, the sample sizes and confidence intervals are on the page.

> 3/ Bonus: LLManager. Import your Claude Code / Claude.ai / ChatGPT history and
> continue it on ANY model — switch mid-conversation, fork, let a judge compare.
> On your own keys. Free. [GIF]

> 4/ Everything is free during the open beta. Engine is open-source (Apache-2.0).
> Break it, tell me. github.com/ravemm-hub/meerada

**LinkedIn (personal profile):**
> I spent the summer building something I wanted for years: an honest, live
> ranking of every AI model, measured on tasks a program can verify — not
> opinions. Every hour. Priced by what a *done* task costs (CPAT), not tokens.
> It's free, the data is open, and it comes with a desktop app that lets you
> import your Claude/ChatGPT history and switch models mid-conversation.
> meerada.app — I'd value your feedback more than your like.

**Hebrew — Facebook groups (Startup Nation, AI Israel, פיתוח תוכנה בישראל):**
> בניתי בורסה חיה למודלי AI: כל מודל נמדד כל שעה על משימות שתוכנה יכולה לאמת
> (טסטים נסתרים, SQL על DB אמיתי, סוכנים, בטיחות) ומתומחר לפי עלות למשימה
> שהושלמה — לא לפי טוקנים. בחינם, דאטה פתוח. בונוס: אפליקציה שמייבאת את
> ההיסטוריה שלכם מ-Claude/ChatGPT ומאפשרת להמשיך אותה על כל מודל, כולל החלפה
> באמצע שיחה. meerada.app — אשמח לביקורת אמיתית, לא ללייקים.

**Product Hunt tagline:** `Every AI model. Measured. Priced. Ranked. Free.`

---

## The ask to early users (it's on the pages)
> "Did the imported conversation continue correctly on the new model? Was the
> CPAT number believable? What would make you pay for this?"

## What Claude does the moment you paste things back
- key files in `Meerada\keys\` → GitHub secrets → next hourly run measures them
- GoatCounter code / Search Console tag / YouTube link → into the pages → deployed
- the first bug reports → fixes with commit links to reply with
