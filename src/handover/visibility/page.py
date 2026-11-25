"""Render the public page from the report JSON: a self-contained HTML file whose
numbers are embedded, so first paint needs no request (the exchange's pattern)."""

# ruff: noqa: E501  (the HTML template is one long literal)

from __future__ import annotations

import json
from typing import Any

TEMPLATE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8">
<script src="assets/family.js" defer></script>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Search Lab — how the engines choose</title>
<link rel="canonical" href="https://meerada.app/visibility.html">
<link rel="icon" href="logo.svg" type="image/svg+xml">
<meta name="description" content="We ask ChatGPT, Perplexity, Gemini and Claude the same everyday questions — a plumber, headphones, a CRM, a hotel, a web agency — and record which options they name, where their answers come from, how many they show, and whether the same question gets the same names a week later. Every number with n and a confidence interval.">
<meta property="og:type" content="website"><meta property="og:url" content="https://meerada.app/visibility.html">
<meta property="og:title" content="AI Search Lab — how the engines choose — Meerada"><meta property="og:description" content="The same questions to four AI engines. Who they name, what they cite, how they choose, how stable they are.">
<meta property="og:image" content="https://meerada.app/assets/og.png"><meta name="twitter:card" content="summary_large_image">
<script data-goatcounter="https://meerada.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;800;900&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>
  :root{--ground:#FFFFFF;--panel:#F7F9FC;--panel2:#EEF2F7;--line:#DDE4EE;--text:#0F172A;--muted:#5B6B82;--teal:#0E8A7E;--amber:#D48A00;--good:#1E8E4C;--bad:#C8403A;}
  *{box-sizing:border-box} body{margin:0;background:var(--ground);color:var(--text);font-family:"IBM Plex Sans",system-ui,sans-serif;line-height:1.55}
  a{color:inherit} .wrap{max-width:1120px;margin:0 auto;padding:0 1.1rem}
  header{text-align:center;padding:2.6rem 0 .6rem} h1{font-family:Archivo;font-weight:900;font-size:clamp(1.9rem,5vw,2.9rem);letter-spacing:-.03em;line-height:1.05;margin:.3rem 0 .4rem} h1 em{font-style:normal;color:var(--teal)}
  .lede{color:var(--muted);max-width:760px;margin:0 auto .6rem;font-size:1.02rem}
  .stamp{font-family:"IBM Plex Mono",monospace;font-size:.74rem;color:var(--muted)}
  h2{font-family:Archivo;font-weight:800;font-size:1.25rem;margin:2.2rem 0 .5rem;letter-spacing:-.01em}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.8rem}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:1rem 1.1rem}
  .card h3{font-family:Archivo;font-size:1rem;margin:0} .card .m{font-family:"IBM Plex Mono",monospace;font-size:.7rem;color:var(--muted);margin-bottom:.6rem}
  .big{font-family:Archivo;font-weight:900;font-size:2rem;line-height:1} .k{font-size:.66rem;color:var(--muted);text-transform:uppercase;font-family:"IBM Plex Mono",monospace;letter-spacing:.05em}
  .ci{font-family:"IBM Plex Mono",monospace;font-size:.72rem;color:var(--muted)}
  .row{display:grid;grid-template-columns:1fr 1fr;gap:.45rem .6rem;margin:.6rem 0}
  .src{font-size:.8rem;color:var(--muted);margin-top:.5rem} .src b{color:var(--text)}
  .bar{display:flex;height:10px;border-radius:6px;overflow:hidden;background:var(--panel2);margin:.3rem 0 .2rem} .bar span{display:block;height:100%}
  .legend{display:flex;gap:.6rem;flex-wrap:wrap;font-size:.74rem;color:var(--muted)} .legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:.3rem;vertical-align:middle}
  table{width:100%;border-collapse:collapse;font-size:.86rem} th,td{text-align:left;padding:.5rem .55rem;border-bottom:1px solid var(--line);vertical-align:top} th{font-family:"IBM Plex Mono",monospace;font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
  td .names span{display:inline-block;background:#fff;border:1px solid var(--line);border-radius:999px;padding:.08rem .5rem;margin:.1rem .15rem .1rem 0;font-size:.78rem}
  td .err{color:var(--bad);font-size:.76rem} td .none{color:var(--muted);font-size:.78rem}
  .q{color:var(--muted);font-size:.78rem} .pill{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:.3rem .8rem;font-size:.84rem;cursor:pointer;background:#fff;margin:0 .3rem .4rem 0} .pill.on{border-color:var(--teal);background:#E6F6EC;color:var(--good);font-weight:600}
  .note{color:var(--muted);font-size:.8rem} .skip{color:var(--amber);font-size:.8rem}
  .mini{font-family:"IBM Plex Mono",monospace;font-size:.74rem;color:var(--muted)} .mini b{color:var(--text);font-size:.86rem}
  .he{direction:rtl;text-align:right}
  @media(max-width:700px){.hide-m{display:none}}
</style></head><body>
<header><div class="wrap">
  <h1>AI Search Lab<br><em>How the engines choose</em></h1>
  <div class="lede">People now ask an AI before they choose — a plumber, headphones, a CRM, a hotel, a web agency. We ask ChatGPT, Perplexity, Gemini and Claude the same questions and record, verbatim, which options they name, where the answers come from, how many they show, and whether the same question gets the same names a few days later. Nothing here can be bought.</div>
  <div class="stamp" id="stamp"></div>
</div></header>
<div class="wrap">
  <h2>The four engines</h2>
  <div class="grid" id="engines"></div>
  <div id="skipped" class="skip"></div>

  <h2>How each engine chooses, by kind of search</h2>
  <div class="note">Per intent: share of answers that name options · options per answer · share of citations that are “best of” guides · share of named options whose own site is cited · stability = overlap between the two latest answers to the same question.</div>
  <table id="intents"><thead></thead><tbody></tbody></table>

  <h2>Where the answers come from</h2>
  <div class="note">Share of citations by source family, per engine. The engine's own retrieval decides who exists.</div>
  <div id="sources"></div>

  <h2>Most named right now</h2>
  <div class="note">Across all questions and engines — the newest answer per question. A name several engines repeat is a name the models have learned.</div>
  <table id="top"><thead><tr><th>#</th><th>Option</th><th>Mentions</th><th>Engines</th><th class="hide-m">Kind</th><th class="hide-m">Where</th></tr></thead><tbody></tbody></table>

  <h2>Do the engines agree?</h2>
  <div class="note">Mean overlap (Jaccard) between the name sets two engines give the same question. 0 = never the same names, 1 = identical lists.</div>
  <table id="overlap"><thead><tr><th>Engine A</th><th>Engine B</th><th>Overlap</th><th>n questions</th></tr></thead><tbody></tbody></table>

  <div id="expwrap" style="display:none"><h2>Experiments</h2>
  <div class="note">One business, one lever, the questions it should appear in. Presence before and after the lever, per engine.</div>
  <table id="exp"><thead></thead><tbody></tbody></table></div>

  <h2>Every question, every engine</h2>
  <div id="intentPills"></div><div id="cityPills"></div>
  <table id="queries"><thead></thead><tbody></tbody></table>

  <h2>Method</h2>
  <div class="note" id="method"></div>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>
(function(){
  var D = JSON.parse(document.getElementById('data').textContent);
  var pct = function(p){ return p && p.value!=null ? Math.round(p.value*100)+'%' : '—'; };
  var pc = function(v){ return v==null ? '—' : Math.round(v*100)+'%'; };
  var ci = function(p){ return p && p.ci_low!=null ? 'n='+p.n+' · CI '+Math.round(p.ci_low*100)+'-'+Math.round(p.ci_high*100)+'%' : 'n='+(p?p.n:0); };
  var num = function(m,d){ return m && m.value!=null ? m.value.toFixed(d==null?1:d) : '—'; };
  var esc = function(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); };
  var FAM = {'Yelp':'#C8403A','Tripadvisor':'#1E8E4C','Google':'#2563EB','Reddit':'#F97316','Social':'#7C3AED','Reviews & directories':'#0E8A7E','Wikipedia':'#64748B','News & magazines':'#D48A00','Business sites':'#0F172A','Unknown':'#CBD5E1'};
  var engines = D.engines.map(function(e){ return e.engine; });
  document.getElementById('stamp').textContent = D.method.queries+' questions · '+D.method.intents.map(function(i){ return i.label+' '+i.n; }).join(' · ')+' · updated '+D.generated_at.slice(0,16).replace('T',' ')+' UTC · '+D.answers_total+' answers kept';

  var eng = document.getElementById('engines');
  D.engines.forEach(function(e){
    var c = e.choosing || {};
    var top = e.sources.slice(0,3).map(function(s){ return '<b>'+esc(s.family)+'</b> '+Math.round(s.share*100)+'%'; }).join(' · ');
    eng.insertAdjacentHTML('beforeend', '<div class="card"><h3>'+esc(e.label)+'</h3><div class="m">'+esc(e.model||'')+'</div>'+
      '<div class="k">names options</div><div class="big">'+pct(e.named_rate)+'</div><div class="ci">'+ci(e.named_rate)+'</div>'+
      '<div class="row">'+
      '<div><div class="k">searched the web</div><b>'+pct(e.searched_rate)+'</b></div><div><div class="k">options / answer</div><b>'+num(c.candidates)+'</b></div>'+
      '<div><div class="k">stability</div><b>'+num(e.stability,2)+'</b> <span class="ci">n='+(e.stability?e.stability.n:0)+'</span></div><div><div class="k">crowns a #1</div><b>'+pct(c.pick_rate)+'</b></div>'+
      '<div><div class="k">quotes ratings</div><b>'+pc(c.rated_share)+'</b></div><div><div class="k">quotes prices</div><b>'+pc(c.priced_share)+'</b></div>'+
      '<div><div class="k">own site cited</div><b>'+pc(c.own_site_share)+'</b></div><div><div class="k">“best of” cites</div><b>'+pc(c.listicle_share)+'</b></div>'+
      '<div><div class="k">distinct names</div><b>'+e.distinct_names+'</b></div><div><div class="k">errors</div><b>'+e.errors+'</b>/'+e.asked+'</div></div>'+
      (top ? '<div class="src">cites: '+top+'</div>' : '')+(e.last_error ? '<div class="err note">'+esc(e.last_error)+'</div>' : '')+'</div>');
  });
  var sk = Object.keys(D.skipped||{});
  if (sk.length) document.getElementById('skipped').textContent = 'Not asked this round: '+sk.map(function(k){ return k+' ('+D.skipped[k]+')'; }).join(', ');

  var ih = document.querySelector('#intents thead'); ih.innerHTML = '<tr><th>Kind of search</th>'+engines.map(function(e){ return '<th>'+e+'</th>'; }).join('')+'</tr>';
  var ib = document.querySelector('#intents tbody');
  (D.intents||[]).forEach(function(r){
    var cells = engines.map(function(e){
      var x = r.engines[e]; if (!x || !x.named_rate || !x.named_rate.n) return '<td><span class="none">no answers yet</span></td>';
      var c = x.choosing || {}; var src = (x.sources||[]).slice(0,2).map(function(s){ return esc(s.family)+' '+Math.round(s.share*100)+'%'; }).join(', ');
      return '<td class="mini"><b>'+pct(x.named_rate)+'</b> named · n='+x.named_rate.n+'<br>'+num(c.candidates)+' options · best-of '+pc(c.listicle_share)+' · own site '+pc(c.own_site_share)+'<br>stability '+num(x.stability,2)+' · '+src+'</td>';
    }).join('');
    ib.insertAdjacentHTML('beforeend', '<tr><td><b>'+esc(r.label)+'</b><div class="q">'+r.queries+' questions</div></td>'+cells+'</tr>');
  });

  var src = document.getElementById('sources');
  D.engines.forEach(function(e){
    if (!e.sources.length) return;
    var bar = e.sources.map(function(s){ return '<span style="width:'+(s.share*100)+'%;background:'+(FAM[s.family]||'#999')+'" title="'+esc(s.family)+' '+Math.round(s.share*100)+'%"></span>'; }).join('');
    var leg = e.sources.map(function(s){ return '<span><i style="background:'+(FAM[s.family]||'#999')+'"></i>'+esc(s.family)+' '+Math.round(s.share*100)+'%</span>'; }).join('');
    src.insertAdjacentHTML('beforeend', '<div style="margin:.7rem 0"><b>'+esc(e.label)+'</b><div class="bar">'+bar+'</div><div class="legend">'+leg+'</div></div>');
  });

  var tb = document.querySelector('#top tbody');
  D.top_names.forEach(function(r,i){
    tb.insertAdjacentHTML('beforeend', '<tr><td>'+(i+1)+'</td><td><b>'+esc(r.name)+'</b></td><td>'+r.mentions+'</td><td>'+r.engines.join(', ')+'</td><td class="hide-m">'+(r.intents||[]).join(', ')+'</td><td class="hide-m">'+r.cities.join(', ')+'</td></tr>');
  });
  if (!D.top_names.length) tb.innerHTML = '<tr><td colspan="6" class="none">No answers yet.</td></tr>';

  var ob = document.querySelector('#overlap tbody');
  D.overlap.forEach(function(o){ ob.insertAdjacentHTML('beforeend', '<tr><td>'+o.a+'</td><td>'+o.b+'</td><td><b>'+num(o.jaccard,2)+'</b></td><td>'+o.jaccard.n+'</td></tr>'); });

  if ((D.experiments||[]).length) {
    document.getElementById('expwrap').style.display = '';
    document.querySelector('#exp thead').innerHTML = '<tr><th>Business</th><th>Lever · start</th>'+engines.map(function(e){ return '<th>'+e+'</th>'; }).join('')+'</tr>';
    var xb = document.querySelector('#exp tbody');
    D.experiments.forEach(function(x){
      var cells = engines.map(function(e){ var r = x.engines[e]; if (!r) return '<td>—</td>'; return '<td class="mini">before <b>'+r.before.present+'</b>/'+r.before.n+'<br>after <b>'+r.after.present+'</b>/'+r.after.n+'</td>'; }).join('');
      xb.insertAdjacentHTML('beforeend', '<tr><td><b>'+esc(x.business)+'</b><div class="q">'+x.queries.join(', ')+'</div></td><td>'+esc(x.lever)+'<div class="q">'+x.started+'</div></td>'+cells+'</tr>');
    });
  }

  var intents = ['All'].concat(D.method.intents.map(function(i){ return i.label; }));
  var labelOf = {}; D.method.intents.forEach(function(i){ labelOf[i.intent] = i.label; });
  var cities = ['All'].concat(D.method.cities);
  var curI = 'All', curC = 'All';
  function drawQ(){
    var th = document.querySelector('#queries thead'); th.innerHTML = '<tr><th>Question</th>'+engines.map(function(e){ return '<th>'+e+'</th>'; }).join('')+'</tr>';
    var body = document.querySelector('#queries tbody'); body.innerHTML = '';
    D.queries.filter(function(q){ return (curI==='All' || labelOf[q.intent]===curI) && (curC==='All' || q.city===curC); }).forEach(function(q){
      var cells = engines.map(function(e){
        var c = q.engines[e];
        if (!c) return '<td><span class="none">not asked yet</span></td>';
        if (c.error) return '<td><span class="err">error: '+esc(c.error)+'</span></td>';
        if (!c.names.length) return '<td><span class="none">'+(c.searched?'searched, named nothing':'no search, named nothing')+'</span></td>';
        return '<td><div class="names">'+c.names.map(function(n){ return '<span>'+esc(n)+'</span>'; }).join('')+'</div><div class="q">'+(c.searched?'':'no search · ')+c.sources.join(', ')+'</div></td>';
      }).join('');
      body.insertAdjacentHTML('beforeend', '<tr><td><b>'+esc(labelOf[q.intent]||q.intent)+'</b> · '+esc(q.city)+' · '+esc(q.category)+'<div class="q'+(q.lang==='he'?' he':'')+'">'+esc(q.text)+'</div></td>'+cells+'</tr>');
    });
  }
  function pills(id, items, get, set){ var box = document.getElementById(id); items.forEach(function(c){ var p = document.createElement('span'); p.className = 'pill'+(c===get()?' on':''); p.textContent = c; p.onclick = function(){ set(c); Array.prototype.forEach.call(box.children, function(x){ x.className = 'pill'+(x.textContent===c?' on':''); }); drawQ(); }; box.appendChild(p); }); }
  pills('intentPills', intents, function(){ return curI; }, function(v){ curI = v; });
  pills('cityPills', cities, function(){ return curC; }, function(v){ curC = v; });
  drawQ();

  document.getElementById('method').innerHTML = '<p>'+D.method.queries+' questions across '+D.method.intents.length+' kinds of search ('+D.method.intents.map(function(i){ return i.label.toLowerCase()+' '+i.n; }).join(', ')+'), three markets (Israel, US, UK) and a few in Hebrew. Each engine is asked in the words a person would use, with one light nudge shared by all: <i>“'+esc(D.method.nudge)+'”</i>. Answers are stored verbatim with their citations and the number of web searches the engine ran; the options named and the features (ratings quoted, prices, own-site citations, “best of” guides) are read by a program ('+esc(D.method.extraction)+'), so the counts are reproducible and may miss a name written without a list or bold. A round of 13 questions per engine runs daily under a hard spend cap; questions are interleaved across kinds, so every round samples the whole spectrum; the newest answer per question is shown. Rates carry n and a '+D.method.interval+' interval. Promoted placements do not exist here — nothing on this page can be bought.</p>'+
    '<p>Raw data: <a href="visibility.json">visibility.json</a> · every answer: <a href="visibility_state.json">visibility_state.json</a> · method and roadmap: <a href="https://github.com/ravemm-hub/meerada/blob/master/docs/PRESENCE-ENGINE.md">PRESENCE-ENGINE.md</a>.</p>';
})();
</script>
</body></html>
"""


def render_page(report: dict[str, Any]) -> str:
    data = json.dumps(report, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data)
