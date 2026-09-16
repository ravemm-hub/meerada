/* Meerada family chrome — one company bar on top and one footer at the bottom of
   every page, so the whole site reads as one company with many products.
   Include with <script src="assets/family.js" defer></script>. */
(function () {
  var P = [
    { href: "index.html", id: "index", ic: "📊", name: "Exchange", tag: "every model, measured hourly" },
    { href: "manager.html", id: "manager", ic: "🎛️", name: "Manager", tag: "one app for every model" },
    { href: "guard.html", id: "guard", ic: "🛡", name: "Guard", tag: "watchdog + cage for AI at work" },
    { href: "crosscheck.html", id: "crosscheck", ic: "🔎", name: "Cross-check", tag: "models examining models" },
    { href: "judge.html", id: "judge", ic: "⚖️", name: "Judge", tag: "the reliability layer" },
    { href: "handshake.html", id: "handshake", ic: "🤝", name: "Handshake", tag: "measured migration" },
    { href: "tribes.html", id: "tribes", ic: "🏙️", name: "Tribes", tag: "AI-powered city app" },
    { href: "company.html", id: "company", ic: "🏢", name: "Company", tag: "who we are" }
  ];
  var here = (location.pathname.split("/").pop() || "index.html").replace(".html", "");
  if (here === "llmanager") here = "manager";
  var css = [
    "#mfam{position:relative;z-index:30;background:#0F172A;color:#E2E8F0;font-family:'IBM Plex Sans',system-ui,sans-serif;font-size:.78rem}",
    "#mfam .w{max-width:1180px;margin:0 auto;padding:.38rem 1.1rem;display:flex;align-items:center;gap:1rem;flex-wrap:wrap}",
    "#mfam .co{display:flex;align-items:center;gap:.55rem;color:#fff;text-decoration:none;white-space:nowrap}",
    "#mfam .co img{height:18px;width:auto;display:block;filter:brightness(0) invert(1)}",
    "#mfam .co small{color:#94A3B8;font-size:.7rem}",
    "#mfam .links{display:flex;gap:.15rem;flex-wrap:wrap;margin-left:auto}",
    "#mfam .links a{color:#CBD5E1;text-decoration:none;padding:.22rem .55rem;border-radius:6px;white-space:nowrap}",
    "#mfam .links a:hover{background:#1E293B;color:#fff}",
    "#mfam .links a.on{background:#0E8A7E;color:#fff}",
    "#mfam .free{color:#4ADE80!important}",
    "#mfoot{background:#0F172A;color:#CBD5E1;font-family:'IBM Plex Sans',system-ui,sans-serif;margin-top:3rem}",
    "#mfoot .w{max-width:1180px;margin:0 auto;padding:2.2rem 1.1rem 2.6rem;display:grid;grid-template-columns:1.4fr repeat(4,1fr);gap:1.4rem}",
    "@media(max-width:820px){#mfoot .w{grid-template-columns:1fr 1fr}}",
    "#mfoot h4{margin:0 0 .5rem;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:#94A3B8;font-family:'IBM Plex Mono',monospace}",
    "#mfoot a{display:block;color:#E2E8F0;text-decoration:none;font-size:.86rem;padding:.14rem 0}",
    "#mfoot a:hover{color:#5EEAD4}",
    "#mfoot .about{color:#94A3B8;font-size:.86rem;line-height:1.55}",
    "#mfoot .about b{color:#fff}",
    "#mfoot .about img{height:22px;filter:brightness(0) invert(1);display:block;margin-bottom:.6rem}",
    "#mfoot .legal{grid-column:1/-1;border-top:1px solid #1E293B;padding-top:1rem;color:#64748B;font-size:.74rem;display:flex;gap:1rem;flex-wrap:wrap}"
  ].join("");
  var st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  var links = P.map(function (p) {
    return '<a href="' + p.href + '"' + (p.id === here ? ' class="on"' : "") + ' title="' + p.tag + '">' + p.ic + " " + p.name + "</a>";
  }).join("") + '<a href="pricing.html" class="free' + (here === "pricing" ? " on" : "") + '">Free</a>';
  var bar = '<div id="mfam"><div class="w"><a class="co" href="company.html"><img src="assets/meerada-wordmark.png" alt="Meerada"><small>the AI operations company</small></a><nav class="links">' + links + "</nav></div></div>";
  document.body.insertAdjacentHTML("afterbegin", bar);

  var col = function (title, items) {
    return "<div><h4>" + title + "</h4>" + items.map(function (i) { return '<a href="' + i[1] + '">' + i[0] + "</a>"; }).join("") + "</div>";
  };
  var foot = '<footer id="mfoot"><div class="w">'
    + '<div class="about"><img src="assets/meerada-wordmark.png" alt="Meerada"><b>Meerada</b> is the AI operations company: we <b>measure</b> models, <b>operate</b> them for you, <b>protect</b> your work, <b>verify</b> every answer, and <b>build</b> AI-powered apps. One rule under everything: measure what is real.</div>'
    + col("Measure", [["Exchange — live model ranking", "index.html"], ["Which model for me?", "pick.html"], ["Grade board", "grade.html"], ["Frontier Watch", "index.html#frontier"], ["Labs & valuations", "index.html#labs"], ["RSS: grade moves & new models", "feed.xml"], ["Badges for your model", "index.html#measured-wrap"]])
    + col("Operate", [["Manager (LLManager)", "manager.html"], ["Handshake — switch models with history", "handshake.html"], ["Try it in the browser", "https://app.meerada.app"], ["Download the app", "manager.html#get"]])
    + col("Protect & verify", [["Guard — watchdog + cage", "guard.html"], ["Cross-check — models examining models", "crosscheck.html"], ["Judge — the reliability layer", "judge.html"], ["Outcome Exchange", "index.html#exchange"]])
    + col("Company", [["About Meerada", "company.html"], ["Tribes — the city app", "tribes.html"], ["Everything is free", "pricing.html"], ["Open source on GitHub", "https://github.com/ravemm-hub/meerada"], ["Contact", "mailto:rave.mm@gmail.com"]])
    + '<div class="legal"><span>© 2026 Meerada · Israel</span><span>Open beta — every product is free</span><span>Engine: Apache-2.0</span><span>Measurements are reproducible; grades come only from tasks a program verified.</span></div>'
    + "</div></footer>";
  document.body.insertAdjacentHTML("beforeend", foot);
})();
