"""The public test-case page: for each business in the registry, the question, what the
engines answered before the lever (run by run), the lever and its date, and what they
answer now. Results only — the method stays in the repo, not on the page."""

# ruff: noqa: E501  (the HTML template is one long literal)

from __future__ import annotations

import json
from typing import Any

TEMPLATE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8">
<script src="assets/family.js" defer></script>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Test cases — before and after</title>
<link rel="canonical" href="https://meerada.app/cases.html">
<link rel="icon" href="logo.svg" type="image/svg+xml">
<meta name="description" content="Real businesses, real questions to ChatGPT, Perplexity and Claude. What the engines answered before we worked on a business, and what they answer after. Every run shown; nothing can be bought.">
<meta property="og:type" content="website"><meta property="og:url" content="https://meerada.app/cases.html">
<meta property="og:title" content="Test cases — before and after — Meerada"><meta property="og:description" content="What the AI engines answered before, and after.">
<meta property="og:image" content="https://meerada.app/assets/og.png"><meta name="twitter:card" content="summary_large_image">
<script data-goatcounter="https://meerada.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;800;900&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>
  :root{--ground:#FFFFFF;--panel:#F7F9FC;--panel2:#EEF2F7;--line:#DDE4EE;--text:#0F172A;--muted:#5B6B82;--teal:#0E8A7E;--amber:#D48A00;--good:#1E8E4C;--bad:#C8403A;}
  *{box-sizing:border-box} body{margin:0;background:var(--ground);color:var(--text);font-family:"IBM Plex Sans",system-ui,sans-serif;line-height:1.55}
  a{color:inherit} .wrap{max-width:1040px;margin:0 auto;padding:0 1.1rem}
  header{text-align:center;padding:2.6rem 0 .6rem} h1{font-family:Archivo;font-weight:900;font-size:clamp(1.9rem,5vw,2.9rem);letter-spacing:-.03em;line-height:1.05;margin:.3rem 0 .4rem} h1 em{font-style:normal;color:var(--teal)}
  .lede{color:var(--muted);max-width:720px;margin:0 auto .6rem;font-size:1.02rem} .stamp{font-family:"IBM Plex Mono",monospace;font-size:.74rem;color:var(--muted)}
  .case{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:1.1rem 1.2rem;margin:1rem 0}
  .case h2{font-family:Archivo;font-weight:800;font-size:1.2rem;margin:0 0 .2rem} .meta{font-family:"IBM Plex Mono",monospace;font-size:.72rem;color:var(--muted);margin-bottom:.6rem}
  .q{font-size:.9rem;color:var(--muted);margin:.4rem 0 .6rem} .q b{color:var(--text)}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.7rem}
  .eng{background:#fff;border:1px solid var(--line);border-radius:12px;padding:.7rem .8rem} .eng h3{font-family:Archivo;font-size:.92rem;margin:0 0 .3rem}
  .k{font-size:.64rem;color:var(--muted);text-transform:uppercase;font-family:"IBM Plex Mono",monospace;letter-spacing:.05em}
  .big{font-family:Archivo;font-weight:900;font-size:1.5rem;line-height:1.1} .big.good{color:var(--good)} .big.bad{color:var(--bad)}
  .runs{display:flex;gap:3px;flex-wrap:wrap;margin:.3rem 0} .runs i{display:block;width:12px;height:12px;border-radius:3px;background:var(--panel2);border:1px solid var(--line)} .runs i.named{background:var(--good);border-color:var(--good)} .runs i.cited{background:#A7F3D0;border-color:#6EE7B7}
  .others{font-size:.76rem;color:var(--muted)} .others span{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:.02rem .45rem;margin:.1rem .1rem 0 0;background:#fff}
  .ctrl{display:inline-block;background:var(--panel2);border-radius:6px;padding:.05rem .45rem;font-size:.72rem;color:var(--muted)}
  .note{color:var(--muted);font-size:.8rem} .none{color:var(--muted);text-align:center;padding:3rem 0}
</style></head><body>
<header><div class="wrap">
  <h1>Test cases<br><em>Before and after</em></h1>
  <div class="lede">Real businesses picked from the middle of Google's results. We ask the AI engines the questions their customers ask, several times, and record every answer. Then we work on the business from the outside — truthful pages, listings, mentions — and ask again. Each square is one run: green = the business was named, light green = only its website was cited, grey = absent.</div>
  <div class="stamp" id="stamp"></div>
</div></header>
<div class="wrap" id="cases"></div>
<div class="wrap note"><p>Method in brief: the same wording every time, no brand in the question; runs are repeated because the engines are volatile; the business is marked “named” only when a program finds it among the options in the answer text. Controls are similar businesses we do not touch. Nothing on this page can be bought; businesses were not consulted and did not pay. Raw data: <a href="visibility_state.json">visibility_state.json</a>.</p></div>
<script type="application/json" id="data">__DATA__</script>
<script>
(function(){
  var D = JSON.parse(document.getElementById('data').textContent);
  var esc = function(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); };
  var qtext = {}; (D.queries||[]).forEach(function(q){ qtext[q.id] = q; });
  document.getElementById('stamp').textContent = (D.experiments||[]).length+' cases · updated '+D.generated_at.slice(0,16).replace('T',' ')+' UTC';
  var box = document.getElementById('cases');
  if (!(D.experiments||[]).length) { box.innerHTML = '<div class="none">No test cases published yet. The first cohort is being selected.</div>'; return; }
  D.experiments.forEach(function(x){
    var qs = x.queries.map(function(id){ var q = qtext[id]; return q ? '<div class="q"><b>'+esc(q.city)+' · '+esc(q.category)+':</b> '+esc(q.text)+'</div>' : ''; }).join('');
    var engines = Object.keys(x.engines).map(function(e){
      var r = x.engines[e]; var b = r.before, a = r.after;
      var pct = function(bk){ return bk.n ? Math.round(100*bk.named/bk.n)+'%' : '—'; };
      var sq = r.series.map(function(s){ return '<i class="'+(s.named?'named':(s.cited?'cited':''))+'" title="'+esc(s.t.slice(0,10))+' · '+esc(s.q)+(s.named?' · named':(s.cited?' · cited':' · absent'))+'"></i>'; }).join('');
      var last = r.series.length ? r.series[r.series.length-1] : null;
      var others = last && last.names.length ? '<div class="others">latest answer named: '+last.names.map(function(n){ return '<span>'+esc(n)+'</span>'; }).join('')+'</div>' : '';
      return '<div class="eng"><h3>'+esc(e)+'</h3><div class="k">before</div><div class="big '+(b.named?'good':'bad')+'">'+pct(b)+'</div><div class="k">'+b.named+' of '+b.n+' runs named · '+b.cited+' cited</div>'+
        '<div class="k" style="margin-top:.4rem">after</div><div class="big '+(a.named?'good':'bad')+'">'+pct(a)+'</div><div class="k">'+a.named+' of '+a.n+' runs named · '+a.cited+' cited</div><div class="runs">'+sq+'</div>'+others+'</div>';
    }).join('');
    box.insertAdjacentHTML('beforeend', '<div class="case"><h2>'+esc(x.business)+(x.control?' <span class="ctrl">control — untouched</span>':'')+'</h2><div class="meta">'+esc(x.city)+' · '+esc(x.category)+(x.domain?' · '+esc(x.domain):'')+' · '+(x.control?'no lever':'lever: '+esc(x.lever))+' · from '+x.started+'</div>'+qs+'<div class="grid">'+engines+'</div>'+(x.notes?'<div class="note" style="margin-top:.5rem">'+esc(x.notes)+'</div>':'')+'</div>');
  });
})();
</script>
</body></html>
"""


def render_cases(report: dict[str, Any]) -> str:
    slim = {
        "generated_at": report["generated_at"],
        "experiments": report.get("experiments", []),
        "queries": [
            {"id": q["id"], "city": q["city"], "category": q["category"], "text": q["text"]}
            for q in report.get("queries", [])
        ],
    }
    data = json.dumps(slim, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data)
