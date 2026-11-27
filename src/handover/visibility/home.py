"""The home page — Google against the AI engines across every measured question, a
checker for one business, and the offer.

Built from the published question JSON (``site/s/*.json``): every question with a Google
side becomes a card (Google's top three, the engines' top three, how many of Google's list
no engine names); the headline numbers are sums over the same files. The checker calls the
live API (``/api/search`` and ``/api/audit``) and the sign-up posts to the same Supabase
table as the search page. Copy in English with a Hebrew switch (international first).

    meerada visibility home --pages site/s --out site/index.html
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

PRICE_USD = 29


def load_questions(pages_dir: Path) -> list[dict[str, Any]]:
    out = []
    for path in sorted(pages_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


def stats(questions: list[dict[str, Any]]) -> dict[str, int]:
    engines: set[str] = set()
    runs = 0
    g_total = g_invisible = 0
    for q in questions:
        runs += int(q.get("runs", 0))
        engines |= set((q.get("engines") or {}).keys())
        c = q.get("comparison")
        if c:
            g_total += int(c["google_count"])
            g_invisible += len(c["google_only"])
    return {
        "questions": len(questions),
        "answers": runs,
        "engines": len(engines),
        "google_listed": g_total,
        "invisible": g_invisible,
        "invisible_pct": round(100 * g_invisible / g_total) if g_total else 0,
    }


def _card(q: dict[str, Any]) -> str:
    c = q["comparison"]
    google = sorted(c["both"] + c["google_only"], key=lambda r: r["google_rank"])[:3]
    ai = (q.get("results") or [])[:3]
    g_rows = "".join(
        f'<li>{escape(r["name"])} <span class="{"on" if r.get("ai_rank") else "off"}">{"AI #" + str(r["ai_rank"]) if r.get("ai_rank") else "not in AI"}</span></li>'
        for r in google
    )
    a_rows = (
        "".join(
            f'<li>{escape(r["name"])} <span class="n">{r["named_runs"]}/{r["runs"]}</span></li>'
            for r in ai
        )
        or '<li class="s">no option named</li>'
    )
    inv, n = len(c["google_only"]), c["google_count"]
    rtl = ' dir="rtl"' if q.get("lang") == "he" else ""
    return (
        f'<a class="card" href="s/{escape(q["id"])}.html"{rtl}><div class="q">{escape(q["text"][:90])}</div>'
        f'<div class="two"><div><div class="k">Google shows</div><ol>{g_rows}</ol></div><div><div class="k">The AI names</div><ol>{a_rows}</ol></div></div>'
        f'<div class="badge {"bad" if inv else "good"}">{inv} of Google\'s {n} never named by any engine · {c["runs"]} answers</div></a>'
    )


TEMPLATE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meerada — is your business in the AI answer?</title>
<link rel="canonical" href="https://meerada.app/">
<link rel="icon" href="logo.svg" type="image/svg+xml">
<meta name="description" content="What ChatGPT and the other AI engines recommend, next to what Google shows, for the same questions — measured in public. Check your business, then let Meerada work the gap: $__PRICE__ a month after a free month.">
<meta property="og:type" content="website"><meta property="og:url" content="https://meerada.app/"><meta property="og:title" content="Meerada — is your business in the AI answer?"><meta property="og:description" content="Google vs the AI engines, question by question, in public. Check your business free."><meta property="og:image" content="https://meerada.app/assets/og.png">
<script data-goatcounter="https://meerada.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
<script src="assets/family.js" defer></script>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;800;900&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;600&display=swap">
<link rel="stylesheet" href="assets/search.css">
<style>
.wrap{max-width:1060px}
.hero{text-align:center;padding:2.4rem 0 1rem}.hero h1{font-size:clamp(2rem,5.2vw,3.3rem);margin:.4rem 0 .6rem}.hero h1 em{font-style:normal;color:var(--teal)}
.hero .lede{max-width:760px;margin:0 auto .9rem;font-size:1.08rem}
.lang{font-family:"IBM Plex Mono",monospace;font-size:.72rem;color:var(--muted)}.lang a{cursor:pointer;margin:0 .3rem}.lang a.on{color:var(--text);font-weight:600}
[data-l]{display:none}html[data-lang=en] [data-l=en],html[data-lang=he] [data-l=he]{display:block}html[data-lang=he] .he{direction:rtl;text-align:right}
.stats{display:flex;gap:.6rem;flex-wrap:wrap;justify-content:center;margin:1rem 0 1.6rem}.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:.6rem 1rem;min-width:140px}.stat b{display:block;font-family:Archivo;font-size:1.5rem;font-weight:900}.stat span{font-size:.74rem;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:.8rem;margin:1rem 0}
.card{display:block;background:#fff;border:1px solid var(--line);border-radius:14px;padding:.9rem 1rem;text-decoration:none;color:inherit}.card:hover{border-color:var(--teal)}
.card .q{font-weight:600;font-size:.92rem;margin-bottom:.5rem;line-height:1.35}.card .two{display:grid;grid-template-columns:1fr 1fr;gap:.6rem}.card .k{font-family:"IBM Plex Mono",monospace;font-size:.64rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.card ol{margin:.2rem 0 0;padding-left:1.1rem;font-size:.8rem}.card li{margin:.12rem 0}.card li span{font-family:"IBM Plex Mono",monospace;font-size:.64rem;margin-left:.25rem}.card .off{color:var(--bad)}.card .on{color:var(--good)}.card .n{color:var(--muted)}
.badge{margin-top:.6rem;font-family:"IBM Plex Mono",monospace;font-size:.7rem;border-radius:999px;padding:.15rem .6rem;display:inline-block}.badge.bad{color:var(--bad);background:#FBEAEA}.badge.good{color:var(--good);background:#E6F6EC}
.check{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:1.2rem 1.3rem;margin:2rem 0}.check form{display:grid;grid-template-columns:1fr 1fr 1fr;gap:.5rem;margin-top:.6rem}.check input{font:inherit;padding:.7rem .8rem;border:1px solid var(--line);border-radius:10px;background:#fff}
.check button{grid-column:1/-1;font-family:Archivo;font-weight:700;padding:.8rem;border-radius:10px;border:1px solid transparent;background:#F2B84B;color:#171205;cursor:pointer;font-size:1rem}
.res{margin-top:1rem;display:none}.res .big{font-family:Archivo;font-weight:900;font-size:1.6rem}.res .big.bad{color:var(--bad)}.res .big.good{color:var(--good)}
.plan{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin:1.2rem 0}.plan>div{background:#fff;border:1px solid var(--line);border-radius:14px;padding:1rem 1.1rem}.plan .price{font-family:Archivo;font-weight:900;font-size:2rem}.plan ul{padding-left:1.1rem;font-size:.9rem}.plan li{margin:.3rem 0}
.steps4{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.8rem;margin:1rem 0}.steps4>div{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:.8rem 1rem;font-size:.9rem}.steps4 b{display:block;font-family:Archivo;margin-bottom:.2rem}
.signup{display:grid;grid-template-columns:1fr 1fr;gap:.5rem;margin-top:.8rem}.signup input{font:inherit;padding:.6rem .7rem;border:1px solid var(--line);border-radius:10px;background:#fff}.signup button{grid-column:1/-1;font-family:Archivo;font-weight:700;padding:.7rem;border-radius:10px;border:1px solid transparent;background:#0F172A;color:#fff;cursor:pointer}
@media(max-width:700px){.check form,.plan,.signup{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
<div class="hero">
  <div class="lang"><a data-set="en" class="on">English</a>·<a data-set="he">עברית</a></div>
  <div data-l="en"><h1>Your customers now ask AI.<br><em>Is your business in the answer?</em></h1>
  <p class="lede">Meerada is the only engine that measures what ChatGPT and the other AI assistants actually recommend <b>next to what Google shows</b>, for the same questions, in public — and then works the gap for your business: it finds the exact pages the AI reads for your question, fixes what can be fixed from the outside, hands you a file for your side, and measures you again every week.</p></div>
  <div data-l="he" class="he"><h1>הלקוחות שלך כבר שואלים AI.<br><em>העסק שלך בתשובה?</em></h1>
  <p class="lede">Meerada הוא המנוע היחיד שמודד מה ChatGPT ושאר עוזרי ה-AI באמת ממליצים <b>לצד מה שגוגל מראה</b>, לאותן שאלות, בפומבי — ואז עובד על הפער בשביל העסק שלך: מוצא את העמודים המדויקים שה-AI קורא לשאלה שלך, מתקן מבחוץ מה שאפשר, נותן לך קובץ לצד שלך, ומודד אותך שוב כל שבוע.</p></div>
  <div class="stats">__STATS__</div>
</div>

<h2 data-l="en">Google on the left, the AI on the right — the same question</h2><h2 data-l="he" class="he">גוגל משמאל, ה-AI מימין — אותה שאלה</h2>
<p class="s" data-l="en">Every card is one question we ask the engines repeatedly, next to Google's list for it. Click a card for every run and every business.</p><p class="s he" data-l="he">כל כרטיס הוא שאלה אחת שאנחנו שואלים את המנועים שוב ושוב, לצד רשימת גוגל לאותה שאלה. לחיצה פותחת את כל הריצות וכל העסקים.</p>
<div class="grid">__CARDS__</div>
<p class="s"><a href="s/">All measured questions →</a> · <a href="gap/">Every business Google lists that the AI does not name →</a> · <a href="search.html">Ask any question →</a></p>

<div class="check" id="check">
  <h2 data-l="en" style="margin-top:0">Check your business — free, one minute</h2><h2 data-l="he" class="he" style="margin-top:0">בדקו את העסק שלכם — חינם, דקה אחת</h2>
  <p class="s" data-l="en">What do your customers ask an AI when they look for you? We show who the engines name for it, whether you are among them, and what an engine can and cannot read on your site.</p>
  <p class="s he" data-l="he">מה הלקוחות שלכם שואלים AI כשהם מחפשים אתכם? נראה במי המנועים נוקבים, אם אתם ביניהם, ומה מנוע מצליח או לא מצליח לקרוא באתר שלכם.</p>
  <form id="cf"><input name="q" placeholder="a plumber in Tel Aviv · a dentist in New York" required><input name="business" placeholder="Business name" required><input name="website" placeholder="Website"><button type="submit" id="go">Check</button></form>
  <div class="status" id="status"></div>
  <div class="res" id="res"></div>
</div>

<h2 data-l="en">How the lift works</h2><h2 data-l="he" class="he">איך ההעלאה עובדת</h2>
<div class="steps4">
  <div><b>1 · Measure</b>We ask the engines your customers' question, several times, every week, and record every answer.</div>
  <div><b>2 · Find the pages</b>For each question the engines read a small set of pages. We know which, and check whether you are on each.</div>
  <div><b>3 · Work the gap</b>Our robots publish your factual entity page, request the listings that can be created from public facts, and send you a fix-kit file for your site and Google listing — paste it into Claude or ChatGPT and it does the work.</div>
  <div><b>4 · Prove it</b>Weekly numbers, run by run, per engine. A daily note only when there is something for you to do.</div>
</div>

<h2 data-l="en">The offer</h2><h2 data-l="he" class="he">ההצעה</h2>
<div class="plan">
  <div><div class="price">Free</div><div class="s">the first month, no card</div><ul><li>your question measured on every engine</li><li>your entity page on meerada.app</li><li>the fix kit for your site</li><li>weekly numbers</li></ul></div>
  <div><div class="price">$__PRICE__<span class="s"> / month</span></div><div class="s">after the free month · cancel any time</div><ul><li>continuous measurement and re-work, as long as you subscribe</li><li>up to 4 questions, any city, any language</li><li>a daily to-do note when your side needs a change</li><li>public before/after case, with your permission</li><li>option: pay only for months in which you were named</li></ul></div>
</div>
<div class="claim" id="claim"><h2 id="claimTitle" style="margin-top:0">Start the free month</h2>
<form class="signup" id="sf"><input name="business" placeholder="Business name" required><input name="website" placeholder="Website"><input name="q" placeholder="What customers ask (e.g. a plumber in Tel Aviv)" required><input name="phone" placeholder="WhatsApp / phone" required><input name="contact" placeholder="Email"><button type="submit">Start free — no card</button></form><div id="smsg"></div></div>

<div class="note"><b>What we do not do.</b> No reviews, no ratings, no paid placement in anyone's answer. A business under the quality bar (4.3★ or 20 reviews on Google) is not promoted, whatever it pays. The businesses on this page did not pay and were not asked; Google positions come from dated reads of Google Maps, AI counts from the engines' APIs with web search. <a href="visibility.html">How the engines choose</a> · <a href="cases.html">Before/after cases</a> · <a href="company.html">Company</a>.</div>
</div>
<script>
(function(){
  var API = 'https://app.meerada.app/api', SB_URL = 'https://vytkiwibuohtcmjmslkh.supabase.co', SB_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ5dGtpd2lidW9odGNtam1zbGtoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUzODIwNDUsImV4cCI6MjA5MDk1ODA0NX0.jgggUmp5stzW-9QKLjtrVJdQE4MBbKaFLuySZjgi-ds';
  var $ = function(id){ return document.getElementById(id); };
  var esc = function(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); };
  function setLang(l){ document.documentElement.setAttribute('data-lang', l); document.querySelectorAll('.lang a').forEach(function(a){ a.classList.toggle('on', a.getAttribute('data-set') === l); }); try { localStorage.setItem('mlang', l); } catch(e){} }
  document.querySelectorAll('.lang a').forEach(function(a){ a.addEventListener('click', function(){ setLang(a.getAttribute('data-set')); }); });
  var saved = null; try { saved = localStorage.getItem('mlang'); } catch(e){}
  setLang(saved || (/^he/.test(navigator.language || '') ? 'he' : 'en'));
  function same(a, b){ a = (a||'').toLowerCase(); b = (b||'').toLowerCase(); return a && b && (a.indexOf(b) >= 0 || b.indexOf(a) >= 0); }
  $('cf').addEventListener('submit', function(e){
    e.preventDefault();
    var fd = new FormData(e.target), q = fd.get('q'), biz = fd.get('business'), site = fd.get('website');
    $('status').innerHTML = '<span class="spin"></span>asking the engines…'; $('res').style.display = 'none';
    var calls = [fetch(API + '/search?q=' + encodeURIComponent(q)).then(function(r){ return r.json(); }).catch(function(){ return null; })];
    if (site) calls.push(fetch(API + '/audit?url=' + encodeURIComponent(site) + '&name=' + encodeURIComponent(biz)).then(function(r){ return r.json(); }).catch(function(){ return null; }));
    Promise.all(calls).then(function(out){
      var d = out[0], a = out[1]; $('status').textContent = '';
      var html = '';
      if (d && d.results) {
        var hit = null; d.results.forEach(function(r, i){ if (!hit && same(r.name, biz)) hit = { i: i + 1, r: r }; });
        html += hit ? '<div class="big good">Named in ' + hit.r.named_runs + ' of ' + hit.r.runs + ' AI answers</div><div class="s">#' + hit.i + ' among the options the engines name for “' + esc(d.query) + '”.</div>'
                    : '<div class="big bad">Not named in ' + (d.runs || 0) + ' AI answers</div><div class="s">For “' + esc(d.query) + '” the engines name: ' + esc(d.results.slice(0, 5).map(function(r){ return r.name; }).join(', ') || 'no specific option') + '.</div>';
        if (d.matched) html += '<div class="s"><a href="s/' + esc(d.matched) + '.html">Every run, every business, and Google\\'s list for this question →</a></div>';
      } else { html += '<div class="s">The engines could not be asked right now; leave your details below and we run it for you.</div>'; }
      if (a && a.score != null) html += '<div style="margin-top:.6rem"><b>What an engine reads on your site: ' + a.score + '/100</b>' + (a.fixes && a.fixes.length ? '<ol class="fixes">' + a.fixes.slice(0, 4).map(function(f){ return '<li>' + esc(f) + '</li>'; }).join('') + '</ol>' : '') + '</div>';
      html += '<p><a class="cta" href="#claim">Start the free month for ' + esc(biz) + ' →</a></p>';
      $('res').innerHTML = html; $('res').style.display = 'block';
      var sf = document.getElementById('sf'); sf.business.value = biz; sf.website.value = site || ''; sf.q.value = q;
    });
  });
  $('sf').addEventListener('submit', function(e){
    e.preventDefault(); var fd = new FormData(e.target);
    var row = { kind: 'signup', query: fd.get('q'), business: fd.get('business'), website: fd.get('website'), phone: fd.get('phone'), contact: fd.get('contact'), lang: document.documentElement.getAttribute('data-lang'), page: location.href.slice(0, 300), user_agent: navigator.userAgent.slice(0, 200) };
    $('smsg').innerHTML = '<span class="spin"></span>saving…';
    fetch(SB_URL + '/rest/v1/search_claims', { method: 'POST', headers: { 'apikey': SB_KEY, 'Authorization': 'Bearer ' + SB_KEY, 'Content-Type': 'application/json', 'Prefer': 'return=minimal' }, body: JSON.stringify(row) })
      .then(function(r){ if (!r.ok) throw new Error('save failed ' + r.status); $('smsg').innerHTML = '<span class="ok"><b>Saved.</b> Your free month starts now: within a day you get the first measurement, your entity page draft and the fix kit. Nothing to pay, no card.</span>'; })
      .catch(function(err){ $('smsg').innerHTML = '<span class="err">Could not save (' + esc(err.message) + '). Write to hello@meerada.app and we start by hand.</span>'; });
  });
})();
</script>
</body></html>
"""


def render_home(questions: list[dict[str, Any]]) -> str:
    cards = [q for q in questions if q.get("comparison")]
    cards.sort(key=lambda q: (-q["comparison"]["invisible_share"], -int(q.get("runs", 0))))
    s = stats(questions)
    stat_html = "".join(
        f"<div class='stat'><b>{v}</b><span>{label}</span></div>"
        for v, label in (
            (
                f"{s['invisible_pct']}%",
                f"of {s['google_listed']} Google-listed businesses never named by any AI engine",
            ),
            (s["questions"], "questions measured"),
            (s["answers"], "AI answers recorded"),
            (s["engines"], "engines asked"),
        )
    )
    return (
        TEMPLATE.replace("__PRICE__", str(PRICE_USD))
        .replace("__STATS__", stat_html)
        .replace(
            "__CARDS__",
            "".join(_card(q) for q in cards)
            or '<p class="s">The first comparisons are being recorded.</p>',
        )
        .replace("__UPDATED__", datetime.now(tz=UTC).date().isoformat())
    )


def build_home(pages_dir: Path, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_home(load_questions(pages_dir)), encoding="utf-8")
    return out
