# Outreach kit — Fold Yoga London (lever: `outreach`, experiment `ldn-yoga-fold`)

Why this lever: in the 25.11.2026 baseline (21 answers to "a yoga studio in London for a beginner,
evening classes" across ChatGPT, gpt-5-mini and Claude) the engines cited the same few pages again
and again. Fold Yoga London appears on none of them. The strongest predictor of being named is the
number of third-party pages that name the business, so the job is to get Fold into the pages the
engines already read — truthfully, with facts, no payment, no reviews.

## Who the engines read (baseline, 21 answers)
| Cited page | Cited in | Mentions Fold? | Contact |
|---|---|---|---|
| bestinbritain.org/guides/best-yoga-studios-london | 21 of 21 | no | no email or contact link in the page HTML (JS-rendered); find the route by hand on the site footer or its social accounts |
| timeout.com/london/sports-fitness/yoga-in-london | 19 | no | timeout.com/about/contact-us (form) |
| yogarise.london/beginners-yoga-classes-london (competitor page) | 17 | — | not a target |
| thelondonmother.net/yoga-classes-london | 13 | no | thelondonmother.net/contact/ (form) and /work-with-us/ |
| countryandtownhouse.com/style/health-and-beauty/yoga-london | 7 | no | editorial contact form |
| thenudge.com/the-best-yoga-classes-in-london | 6 | no | Editor@TheNudge.com |
| bestplacesinlondon.co.uk/11-best-yoga-studios-in-london | 3 | no | Hello@bestplacesinlondon.co.uk |
| womenshealthmag.com/uk/…/best-yoga-studios-in-london | 2 | no | author's work email shown on the page |
| lamplitlondon.com/guides/best-yoga-studios-london | 1 | no | hello@lamplitlondon.com |

Priority: bestinbritain.org (every single answer), then thenudge, bestplacesinlondon, lamplitlondon
(they publish contact emails), then the big publishers via their forms.

## Facts about Fold Yoga London (from foldyoga.co.uk, checked 25.11.2026)
- Founded 2016; second studio opened July 2023. Two studios: Stoke Newington, 97 Green Lanes, N16 9BX;
  Leyton, First Floor, Mainyard Studios, 691 High Road, E10 6RA. Phone 07972 367 663.
- Styles stated: dynamic, vinyasa, restorative, yin, power. Online classes ("FOLD at Home") alongside studio classes.
- Prices stated: 3-week intro offer £45 (unlimited in-studio + on-demand); mini membership 5 classes/month £75;
  all-in unlimited £115/month; 10-class pass £180 (valid 1 year); single class £21.
- Positioning in their own words: "sweaty, judgement-free yoga for everyone", "no matter your experience".
- Not stated on the site (do not claim): class times, teacher count, ratings.

## Rules for every message
1. Truthful facts only, each from the list above. No ratings, no "best", no testimonials.
2. Say who we are: Meerada, a visibility service that studies how AI engines pick businesses; Fold did not
   pay us and was not consulted. (Israel CPL s.7(c), UK CAP 2.1: an editorial suggestion must not be a disguised ad.)
3. Offer value to the editor: a gap in their list (two studios in north-east London, an intro offer, online option),
   not a request for a favour. Never offer payment or links in exchange.
4. One email per publisher, one polite follow-up after 10 days, then stop.
5. Log each send in `data/experiments.json` → `ldn-yoga-fold.notes` with the date, so the test-case page can
   show when the lever was pulled. **Emails are sent by the founder, not by the system.**

## Draft 1 — bestinbritain.org (via their contact route)
Subject: A gap in "Best yoga studios in London" — Fold Yoga (Stoke Newington & Leyton)

Hello,

I run Meerada, a small service that measures how AI assistants pick local businesses. When people ask
ChatGPT or Claude for a beginner-friendly yoga studio in London, your guide is the page they cite most
often — in our test it appeared in 21 of 21 answers. That makes it worth keeping complete, so here is one
studio your list does not cover:

Fold Yoga London — two studios in north-east London (Stoke Newington, 97 Green Lanes N16 9BX; Leyton,
691 High Road E10 6RA), founded 2016, styles from vinyasa and power to yin and restorative, plus online
classes. Beginner-relevant facts from their site: a 3-week intro offer at £45, single class £21, unlimited
membership £115/month. Website: foldyoga.co.uk.

Full disclosure: Fold Yoga did not ask for this and has not paid anyone; I am writing because the gap is
measurable. If it helps, I can send the source links for each fact. Thank you for the guide.

[Founder name], Meerada — meerada.app

## Draft 2 — thenudge.com (Editor@TheNudge.com) / bestplacesinlondon / lamplitlondon
Subject: One more for your London yoga list — Fold Yoga, N16 & E10

Hi [name / team],

Your piece on the best yoga classes in London is one of the few pages AI assistants quote when someone
asks where to start yoga in London. Readers of that kind of question are often north-east London
beginners, and the list currently has no studio in Stoke Newington or Leyton.

Fold Yoga London (foldyoga.co.uk) has studios at 97 Green Lanes N16 9BX and 691 High Road E10 6RA, has
run since 2016, teaches vinyasa, dynamic, power, yin and restorative, offers online classes, and publishes a
3-week intro offer at £45 and a £21 single class. Every fact here is from their own site; I can send the links.

For transparency: I run Meerada, which studies how AI engines choose businesses; Fold Yoga did not pay
for this and was not consulted. No reply needed if it is not a fit — thank you for the work you put into
the guide.

[Founder name], Meerada — meerada.app

## Draft 3 — publisher forms (Time Out, Country & Town House, Women's Health, The London Mother)
Short form text (≤600 chars):
"Suggestion for your London yoga studios guide: Fold Yoga London — studios in Stoke Newington (97 Green
Lanes N16 9BX) and Leyton (691 High Road E10 6RA), founded 2016, vinyasa/power/yin/restorative plus
online classes, 3-week intro offer £45, single class £21 (facts from foldyoga.co.uk, 25 Nov 2026). I run
Meerada, a service that measures how AI assistants pick local businesses; the studio did not pay or ask for
this. Happy to send source links."

## After sending
- Record date + outlet in experiments.json notes. Re-measure at weeks 2, 4, 8 (`--runs 7`); watch two things
  separately: Fold *named* in answers, and the outlet's page cited with Fold now on it.
- If an editor adds Fold, note the publication date — the gap between "page updated" and "engine names Fold"
  is the time-to-effect number nobody has measured.
