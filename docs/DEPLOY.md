# Deploy the hosted LLManager (real Google sign-in)

The code is complete. Making it live is **3 steps** — all in accounts only you can
access. When the four environment variables are set, the app enforces Google
sign-in and every user connects their own model keys. With them unset, the same
app runs open (that is what `meerada up` does locally).

---

## 0. See the whole hosted flow locally, right now (no Google, no deploy)

To walk the full experience — sign in → connect keys → per-user parallel sessions —
on your own machine before deploying, run with the **dev-login** bypass:

```bash
SESSION_SECRET=devsecret MEERADA_DEV_LOGIN=1 meerada up
```

Open <http://127.0.0.1:8765>: you'll get the sign-in gate, "Continue with Google"
signs you straight in (dev only), the Keys panel opens, and once you paste a real
provider key (e.g. a free Groq key) your sessions return real answers. The bypass
is **explicit opt-in, refuses to run when Google is configured, prints a warning,
and is never in the deploy config** — production always uses real Google sign-in.

---

## 1. Create a Google OAuth client (~3 min)

1. Go to <https://console.cloud.google.com/apis/credentials> → **Create
   credentials** → **OAuth client ID** → **Web application**.
2. Under **Authorized redirect URIs** add your callback URL. If you deploy to
   Render as `meerada-llmanager`, that is:
   `https://meerada-llmanager.onrender.com/auth/callback`
   (you can add your real domain's callback later, e.g.
   `https://meerada.<your-domain>/auth/callback`).
3. Copy the **Client ID** and **Client secret**.

## 2. Deploy to Render (~5 min, free tier)

1. Push is already done — the repo has `Dockerfile` + `render.yaml`.
2. At <https://dashboard.render.com> → **New** → **Blueprint** → pick the
   `ravemm-hub/meerada` repo. Render reads `render.yaml` and creates the web
   service.
3. Set the environment variables it asks for:
   - `GOOGLE_CLIENT_ID` = the client id from step 1
   - `GOOGLE_CLIENT_SECRET` = the client secret from step 1
   - `OAUTH_REDIRECT_URI` = `https://<your-render-url>/auth/callback`
   - `SESSION_SECRET` = leave it (Render generates one)
4. Deploy. Your live cockpit is `https://<your-render-url>/`.

> Any Docker host works the same way (Railway, Fly.io, a VM). `Procfile` covers
> buildpack platforms. Locally: `docker build -t llm . && docker run -p 8000:8000
> --env-file .env llm`.

## 3. Point your domain (optional, when ready)

- In Render → **Settings → Custom Domains**, add `meerada.<your-domain>` (or
  `app.meerada.ai` once you own it) and add the CNAME it shows to your DNS.
- Update `OAUTH_REDIRECT_URI` and the Google redirect URI to the custom domain.

---

## How sign-in and keys work

- `/login` → real Google consent screen → `/auth/callback` verifies a signed CSRF
  state, exchanges the code for the user's identity, and sets an **HMAC-signed,
  http-only session cookie**. No password ever touches us.
- Each signed-in user connects their own provider keys (Keys panel → `POST
  /keys`). Keys are held per-user in memory, never logged, never returned to the
  browser. **For production, move them to an encrypted store/DB** — this is the
  one thing to harden before real customers (see `keystore.py`).
- Sessions and tasks run per-user (`Board` per user); one user never sees
  another's models or conversations.
