# Brief for Claude in Chrome — connect meerada.app (GoDaddy DNS + Render)

You are operating the browser for the owner of the domain **meerada.app**. Do exactly
the steps below, in order. Ask before deleting anything not listed. Never enter
payment details. When done, report the final DNS table and the Render status.

## Part A — GoDaddy DNS for meerada.app

1. Open https://dcc.godaddy.com/manage/meerada.app/dns (sign-in may be required — let
   the owner sign in; do not type passwords yourself).
2. In the DNS records list:
   - If there is a **Forwarding** rule (domain forwarding / "Forward to"), remove it.
   - Delete the existing **A** record for `@` that points to a GoDaddy parking address
     (e.g. `76.223.105.230`, `13.248.243.5`, or a `WebsiteBuilder`/`Parked` value).
   - Delete any existing **CNAME** for `www` (usually `meerada.app.` or a parking value).
   - Do **not** touch NS, SOA, MX, TXT or `_domainconnect` records.
3. Add these records exactly (Type · Name · Value · TTL):

   | Type  | Name | Value                              | TTL     |
   |-------|------|------------------------------------|---------|
   | A     | @    | 185.199.108.153                    | 600 sec |
   | A     | @    | 185.199.109.153                    | 600 sec |
   | A     | @    | 185.199.110.153                    | 600 sec |
   | A     | @    | 185.199.111.153                    | 600 sec |
   | CNAME | www  | ravemm-hub.github.io               | 600 sec |
   | CNAME | app  | meerada-llmanager.onrender.com     | 600 sec |

   Notes: four separate A records, all for `@`. GoDaddy may show "600 seconds" as
   "10 minutes" — fine. Values have no trailing dot. If GoDaddy refuses `www` because a
   record exists, delete that record first (step 2), then add.
4. Click **Save**. Confirm the table now shows the 4 A records + 2 CNAMEs.

## Part B — Render custom domain for the app

1. Open https://dashboard.render.com and open the web service **meerada-llmanager**.
2. **Settings → Custom Domains → Add Custom Domain** → enter `app.meerada.app` → Save.
3. Render shows the required CNAME target (it should be `meerada-llmanager.onrender.com`).
   If it shows a *different* target, go back to GoDaddy and change the `app` CNAME value
   to exactly what Render shows.
4. Wait until Render marks the domain **Verified** and the certificate **Issued**
   (can take 5–30 minutes; reload the page). Do not add a `www` domain on Render.

## Part C — verify and report

1. Open https://meerada.app — expect the Meerada landing page (white background, "Work
   every model. Measure every model."). If GoDaddy's parking page or a certificate warning
   shows, wait 10 minutes and retry (DNS propagation); do not change anything else.
2. Open https://app.meerada.app — expect the LLManager cockpit ("LIVE · your keys" or the
   sign-in gate). If it shows a Render "not found" page, re-check Part B step 3.
3. Report back: the final GoDaddy DNS table (screenshot or text), the Render domain
   status, and whether both URLs loaded.

Do not create accounts, buy anything, or change nameservers. If any page asks to
"upgrade", "add protection" or enable a paid feature — decline.
