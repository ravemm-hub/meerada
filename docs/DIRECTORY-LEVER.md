# Directory lever — what a non-owner can and cannot do (checked 25.11.2026)

The research (SEARCH-ENGINE-RESEARCH.md §2) ranks open directory listings as presence hygiene the
engines read: Yelp reaches all three engines and feeds ChatGPT under licence since July 2026;
easy.co.il is what gpt-5-mini cites for Tel Aviv trades. Below: the exact procedure per directory,
who can do it, and what it means for the two `directory` test businesses. Nothing here was executed
by the system; no account or listing was created.

## Yelp (US) — New York General Dentistry, 133 E 58th St Ste 409, New York, NY 10022
- **Non-owner additions are an official route.** Yelp: "Confirm that a listing does not already exist,
  and then select 'Add A Business'." Page: https://www.yelp.com/writeareview/newbiz — it redirects to
  login, so a **free consumer Yelp account is required** (not a business account).
- Steps: (1) search Yelp for "New York General Dentistry" near 10022 to make sure it is not listed;
  (2) log in; (3) Add a Business with: name "New York General Dentistry" (no "Dr", no PC/LLC),
  Address1 "133 E 58th St", Address2 "Ste 409", New York, NY 10022, phone and website
  (https://newyorkgeneraldentistry.com) exactly as on their site, category "General Dentistry",
  hours as on their site; (4) no description text, no promotional words.
- Moderation: "typically two business days or less"; do not resubmit while pending. The page stays
  "unclaimed" until the practice claims it (that part is the owner's).
- Rules that bind us: name succinct, no keyword stuffing, website must belong to the business,
  hours verifiable; consumer guidelines forbid promotional posts. Writing a *review* is forbidden for
  us (conflict of interest) — adding the page is not.
- Whether a new unclaimed page flows into the Yelp→OpenAI feed, and how fast, is not documented.
- **Who does it:** the founder (needs a Yelp account; the system does not create accounts).
  After adding: set `started` for `nyc-dentist-ny-general` to the day Yelp approves it.

## easy.co.il — א.ל פתרונות אינסטלציה מתקדמים, Tel Aviv
- Help article "הוספת עסק חדש לאיזי" (updated 13.7.2026): add name, category, phone, address, then
  **mandatory owner verification: an SMS/voice code is sent to the business phone** (050-250-9104).
  A stranger cannot complete it. Moderation up to 5 business days; free tier; "עסק מקודם" is a paid tier.
- d.co.il (Dapei Zahav): free form, then **a rep calls the contact back** — written for the owner.
- b144.co.il: "רישום עצמי חינם", approval within 2 business days; form is JS-rendered, verification
  unknown — a human must open it.
- **Consequence for the experiment:** the directory lever for A.L cannot be pulled from outside
  without the owner's phone. To keep one lever per business and the baseline valid, A.L's lever is
  switched to `guide` (added to the Tel Aviv plumbers guide on 25.11.2026 with facts from its own site).
  The easy.co.il listing becomes a phase-2 (owner) action, which fits the product: the first thing we
  would tell a Tel Aviv plumber who subscribes is "verify your easy.co.il listing, gpt-5 reads it".

## Tripadvisor (restaurants) — for later cohorts
Two routes: the owner requests a listing, or "a Tripadvisor user can write a review and initiate a
listing". The non-owner route is the review route, which we never use (conflict of interest), and the
CreateListing form asks to tick "I am the business representative". So Tripadvisor is owner-only for us.

## Sources
business.yelp.com/resources/articles/how-to-add-a-business-to-yelp (15.7.2023) · yelp.com/writeareview/newbiz
(redirect observed 25.11.2026) · docs.developer.yelp.com/docs/yelp-data-quality-guidelines · yelp.com/guidelines ·
axios.com 23.7.2026 (Yelp–OpenAI) · support.easy.co.il/hc/he/articles/360015704412 (13.7.2026) · easy.co.il/biz/kidum-lp ·
d.co.il/LandingPage/AddBusiness · b144.co.il/selfRegister · tripadvisor.com/TripAdvisorInsights/claimyourbusiness ·
brightlocal.com (Yelp 6.1.2022; Tripadvisor 23.5.2023).
