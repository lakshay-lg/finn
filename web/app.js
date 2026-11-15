const view = document.getElementById("view");
const state = { tab: "brief", hours: 24, vol: 2, move: 4, company: null, ticket: 0, entered: false };
/* Thresholds are a per-device preference; storage can be unavailable (private mode), so never rely on it. */
try { const t = JSON.parse(localStorage.getItem("finn.thresholds") || "null"); if (t) { state.vol = +t.vol || 2; state.move = +t.move || 4; } } catch {}
const saveThresholds = () => { try { localStorage.setItem("finn.thresholds", JSON.stringify({ vol: state.vol, move: state.move })); } catch {} };

/* Everything the three screens need is loaded once and kept in memory, so switching tabs, time
   windows and thresholds never waits on the network. The 30-day brief is filtered in the browser. */
const store = { brief: null, alerts: null, symbols: null, companies: new Map(), prices: new Map(), at: 0 };
const STALE_MS = 10 * 60 * 1000;
let loading = null;
function load(force = false) {
  if (!force && store.brief && Date.now() - store.at < STALE_MS) return Promise.resolve();
  loading ??= Promise.all([get("/api/brief?hours=720"), get("/api/alerts")])
    .then(([b, a]) => { store.brief = b; store.alerts = a.results; store.at = Date.now(); stampHeader(); })
    .finally(() => { loading = null; });
  return loading;
}
/* Same rule as the server (alerts.py), applied to its unrounded figures with this device's thresholds. */
function judged() {
  return (store.alerts || []).map(r => {
    const reasons = [];
    if (r.volume_multiple_raw != null && r.volume_multiple_raw > state.vol) reasons.push("volume");
    if (Math.abs(r.move_pct_raw) > state.move) reasons.push("price");
    return { ...r, reasons, triggered: reasons.length > 0 };
  }).sort((x, y) => (y.triggered - x.triggered) || (Math.abs(y.move_pct_raw) - Math.abs(x.move_pct_raw)));
}

const WINDOWS = [[24, "24 hours"], [72, "3 days"], [168, "7 days"], [720, "30 days"]];
const CATS = { "M&A": "M&A", fund_raise: "Fund raise", management_change: "Management change", results: "Results",
  litigation: "Legal", credit_rating: "Credit rating", earnings_call: "Earnings call", press_release: "Update",
  capex: "Capex", dividend: "Dividend", bonus_split: "Bonus or split", insider_trading: "Insider trade",
  pledging: "Pledge", investor_meetings: "Investor meeting", postal_ballot: "Postal ballot", agm_egm: "AGM or EGM",
  unclassified: "Paperwork" };

const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
/* Links come from scraped pages: only plain web links are allowed through. */
const link = u => /^https?:\/\//i.test(String(u ?? "")) ? esc(u) : "#";
const inr = v => v == null ? "n/a" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const signed = (v, d = 2) => v == null ? "n/a" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(d)}%`;
const pct = v => v == null ? "" : `<span class="${v >= 0 ? "up" : "down"}">${v >= 0 ? "+" : ""}${v}%</span>`;
const IST = { timeZone: "Asia/Kolkata" };
const day = ts => new Date(ts).toLocaleDateString("en-IN", { ...IST, day: "numeric", month: "short" });
const clock = ts => new Date(ts).toLocaleTimeString("en-IN", { ...IST, hour: "2-digit", minute: "2-digit", hour12: false });
const when = ts => `${day(ts)}, ${clock(ts)}`;
const sessionDay = d => day(`${d}T15:30:00+05:30`);
const shortTitle = t => t.replace(/^Announcement under Regulation 30 \(LODR\)\s*-?\s*/i, "").replace(/^Disclosure Under Regulation 30.*$/i, "Regulation 30 disclosure");
async function get(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
  return r.json();
}
/* A failed fetch (no signal) is a TypeError; anything else is the server's own message. */
const fail = e => e instanceof TypeError
  ? `<p class="error">No connection. FINN needs the internet to read the latest filings; reload when you are back online.</p>`
  : `<p class="error">${esc(e.message)}. Reload to try again.</p>`;
/* One entrance, on the first screen drawn after the page opens; never again on tab or window changes. */
function entered() { if (state.entered) return ["", ""]; state.entered = true; return [" enter", " enter-2"]; }
function stampHeader() {
  const b = store.brief; if (!b) return;
  document.getElementById("asof").textContent = `As of ${when(b.generated_at)}`;
}

/* Filings about the same event (same company, category and day) show as one row. */
function group(items) {
  const out = new Map();
  for (const it of items) {
    const k = `${it.symbol}|${it.category}|${it.ts.slice(0, 10)}`;
    if (out.has(k)) out.get(k).related.push(it); else out.set(k, { ...it, related: [] });
  }
  return [...out.values()];
}

function numbers(n) {
  if (!n) return "";
  if (n.status !== "ok")
    return `<p class="pending">Numbers for ${esc(n.expected_period)} are not in the data source yet${n.have_period ? ` (latest there is ${esc(n.have_period)})` : ""}. Open the filing for the figures.</p>`;
  const h = n.headline;
  return `<div class="nums">${h.lines.map(l => `<div class="num"><div class="k">${esc(l.label)}</div>
    <div class="v">${inr(l.value)}</div><div class="d">${pct(l.qoq_pct)} QoQ, ${pct(l.yoy_pct)} YoY</div></div>`).join("")}</div>
    <p class="small muted">${esc(h.period)}, Rs crore${h.consolidated ? ", consolidated" : ""}. From screener.in's standardised table, not parsed from the filing.</p>`;
}

const symButton = s => `<button class="sym" data-open="${esc(s)}" aria-label="Research ${esc(s)}">${esc(s)}</button>`;

function item(it, tier) {
  const note = it.note || (it.related.find(r => r.note) || {}).note || "";
  return `<article class="item ${tier}">
    <div class="rail"><span class="d">${day(it.ts)}</span>${clock(it.ts)}</div>
    <div class="body">
      <div class="meta">${symButton(it.symbol)}<span class="cat">${esc(CATS[it.category] || it.category)}</span></div>
      <p class="title">${esc(shortTitle(it.title))}</p>
      ${note ? `<p class="note">${esc(note)} <span class="by">Summary by screener.in</span></p>` : ""}
      ${numbers(it.numbers)}
      <a class="src" href="${link(it.url)}" target="_blank" rel="noopener">Open filing</a>
      ${it.related.length ? `<span class="more">and ${it.related.length} more on the same day</span>` : ""}
    </div>
  </article>`;
}

function moveItem(m) {
  const why = [m.reasons.includes("volume") ? `volume ${m.volume_multiple}x its 20-session median` : "",
    m.reasons.includes("price") ? `price ${signed(m.move_pct)}` : ""].filter(Boolean).join(", ");
  return `<article class="item high">
    <div class="rail"><span class="d">${sessionDay(m.date)}</span>close</div>
    <div class="body">
      <div class="meta">${symButton(m.symbol)}<span class="cat">Unusual move</span></div>
      <p class="title">${esc(why[0].toUpperCase() + why.slice(1))}</p>
      <p class="note">Closed at Rs ${inr(m.close)}, ${m.move_pct >= 0 ? "up" : "down"} ${Math.abs(m.move_pct)}%. ${m.delivery_pct ?? "n/a"}% of traded shares were delivered.</p>
    </div></article>`;
}

/* ---------------- Brief ---------------- */
function windowed(b, hours) {
  const since = Date.parse(b.generated_at) - hours * 3600e3;
  const keep = it => Date.parse(it.ts) >= since;
  const sinceDay = new Date(since).toLocaleDateString("en-CA", IST);
  const high = b.high.filter(keep), medium = b.medium.filter(keep), routine = b.routine.filter(keep);
  return { high, medium, routine, total: high.length + medium.length + routine.length,
           movesInWindow: b.price_session >= sinceDay };
}

function pulse(rows) {
  const sorted = [...rows].sort((a, b) => a.symbol.localeCompare(b.symbol));
  return `<div class="pulse" role="list" aria-label="Your holdings, last session">${sorted.map(r => {
    const t = Math.abs(r.move_pct) < 0.5 ? "" : r.move_pct > 0 ? " t-up" : " t-down";
    return `<button class="tile${t}${r.triggered ? " alert" : ""}" role="listitem" data-open="${esc(r.symbol)}" aria-label="${esc(r.symbol)} ${signed(r.move_pct)}${r.triggered ? ", unusual" : ""}">
      <span class="s">${esc(r.symbol)}</span><span class="m">${signed(r.move_pct, 1)}</span></button>`;
  }).join("")}</div>`;
}

function renderBrief() {
  const b = store.brief, w = windowed(b, state.hours), [e1, e2] = entered();
  const label = WINDOWS.find(x => x[0] === state.hours)[1];
  const high = group(w.high), medium = group(w.medium), all = judged(), moves = all.filter(m => m.triggered);
  const movesIn = w.movesInWindow ? moves : [], movesOut = w.movesInWindow ? [] : moves;
  const n = high.length + movesIn.length;
  const lede = w.total === 0 && !movesIn.length
    ? `Nothing filed in the last ${label}.`
    : `${w.total} filing${w.total === 1 ? "" : "s"} in the last ${label}. <em>${n} ${n === 1 ? "needs" : "need"} your attention.</em>`;
  view.innerHTML = `
    <p class="lede${e1}">${lede}</p>
    <div class="${e2.trim()}">
      ${pulse(all)}
      <p class="pulse-key">Your ${all.length} holdings on ${sessionDay(b.price_session)}. <i></i>Outlined: volume above ${state.vol}x or a move beyond ${state.move}%. Tap one to research it.</p>
      <div class="seg" role="group" aria-label="Time window">${WINDOWS.map(([h, t]) => `<button data-h="${h}" aria-pressed="${h === state.hours}">${t}</button>`).join("")}</div>
      ${n ? `<h2>Needs your attention <span class="count">${n}</span></h2><div class="group">${movesIn.map(moveItem).join("")}${high.map(i => item(i, "high")).join("")}</div>` : ""}
      ${movesOut.length ? `<h2>From the last session, before this window</h2><div class="group">${movesOut.map(moveItem).join("")}</div>` : ""}
      ${!n && b.last_high ? `<p class="quiet">The last filing that mattered was ${esc(b.last_high.symbol)} on ${when(b.last_high.ts)}. Widen the window to see it.</p>` : ""}
      ${medium.length ? `<h2>Worth a look <span class="count">${medium.length}</span></h2><div class="group">${medium.map(i => item(i, "medium")).join("")}</div>` : ""}
      ${w.routine.length ? `<details class="routine"><summary>${w.routine.length} routine filing${w.routine.length > 1 ? "s" : ""}, set aside</summary>
        <ul>${w.routine.map(r => `<li><strong>${esc(r.symbol)}</strong> ${esc(CATS[r.category] || r.category)}: <a href="${link(r.url)}" target="_blank" rel="noopener">${esc(shortTitle(r.title)).slice(0, 80)}</a></li>`).join("")}</ul></details>` : ""}
      <p class="coverage">Coverage: ${esc(b.coverage.statement)} Holding ${b.coverage.items} filings across ${b.coverage.companies} companies.</p>
    </div>`;
  view.querySelectorAll(".seg button").forEach(btn => btn.onclick = () => { state.hours = +btn.dataset.h; renderBrief(); });
}

const skeleton = () => `<div class="ph l"></div><div class="ph g"></div><div class="ph r"></div><div class="ph r"></div>`;

async function brief() {
  if (!store.brief) {
    view.innerHTML = `<p class="lede">Reading the latest filings…</p>${skeleton()}`;
    try { await load(); } catch (e) { view.innerHTML = fail(e); return; }
  }
  if (state.tab !== "brief") return;
  renderBrief();
  if (Date.now() - store.at >= STALE_MS)
    load(true).then(() => { if (state.tab === "brief") renderBrief(); }).catch(() => {});
}

/* ---------------- Research ---------------- */
function bars(points, { h = 120 } = {}) {
  const vals = points.map(p => p.value ?? 0), max = Math.max(...vals, 0), min = Math.min(...vals, 0);
  const W = 320, pad = 18, span = (max - min) || 1, bw = (W - 8) / points.length, zero = pad + (max / span) * (h - 2 * pad);
  return `<svg class="chart" viewBox="0 0 ${W} ${h}" role="img" aria-label="Bar chart">${points.map((p, i) => {
    const v = p.value ?? 0, bh = Math.abs(v) / span * (h - 2 * pad), y = v >= 0 ? zero - bh : zero;
    return `<rect x="${4 + i * bw + 2}" y="${y}" width="${bw - 4}" height="${Math.max(bh, 1)}" rx="2" fill="${v >= 0 ? "var(--ink)" : "var(--down)"}"><title>${esc(p.period)}: ${inr(p.value)}</title></rect>
      ${i % Math.ceil(points.length / 6) === 0 ? `<text x="${4 + i * bw + bw / 2}" y="${h - 3}" text-anchor="middle">${esc(p.period.slice(-4))}</text>` : ""}`;
  }).join("")}<line x1="0" x2="${W}" y1="${zero}" y2="${zero}" stroke="var(--line)"/></svg>`;
}

function spark(series) {
  if (!series || series.length < 2) return "";
  const c = series.map(p => p.close), lo = Math.min(...c), hi = Math.max(...c), W = 320, H = 56, span = (hi - lo) || 1;
  const pts = c.map((v, i) => `${(i / (c.length - 1) * W).toFixed(1)},${(H - 4 - (v - lo) / span * (H - 8)).toFixed(1)}`).join(" ");
  const up = c.at(-1) >= c[0];
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Closing price over ${c.length} sessions">
    <polyline points="${pts}" fill="none" stroke="var(--${up ? "up" : "down"})" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>`;
}

const METRIC = { revenue: "Revenue", revenue_growth: "Revenue growth", operating_margin: "Operating margin", ebitda_margin: "EBITDA margin" };
const isCr = u => /crore/i.test(u || "");
const amt = (v, u) => isCr(u) ? `Rs ${inr(v)} cr` : `${v}${u}`;
const range = g => g.low == null ? "no number" : g.low === g.high ? amt(g.low, g.unit)
  : isCr(g.unit) ? `Rs ${inr(g.low)} to ${inr(g.high)} cr` : `${g.low} to ${g.high}${g.unit}`;

function ledgerView(l) {
  if (!l || l.status !== "ready") return `<div class="panel"><p class="muted">${esc(l?.message || "Not available.")}</p></div>`;
  if (!l.rows.length) return `<div class="panel"><p class="muted">Management gave no numeric guidance on revenue or margins in the ${l.calls_read.length} calls read.</p></div>`;
  const head = l.scored ? `Management kept ${l.kept} of ${l.scored} promises that can be scored.` : `No promise can be scored yet.`;
  return `<div class="panel ledger"><p class="verdict">${head}</p>
    <p class="small muted">Read ${l.calls_read.length} earnings calls, ${esc(l.calls_read[0])} to ${esc(l.calls_read.at(-1))}. Every quote is checked word for word against the transcript${l.dropped_unverified ? `; ${l.dropped_unverified} that did not match were discarded` : ""}.</p>
    ${l.rows.map(r => { const last = r.guided.at(-1); return `<div class="promise v-${r.verdict.replace(/ /g, "-")}">
      <div class="meta"><strong>${esc(METRIC[r.metric] || r.metric)}, ${esc(r.period)}</strong><span class="chip">${esc(r.verdict)}</span></div>
      <div class="pd"><div><div class="k">Promised</div><div class="v">${esc(range(last))}</div></div>
        <div><div class="k">Reported</div><div class="v">${r.reported ? esc(amt(r.reported.value, r.reported.unit)) : "n/a"}</div></div></div>
      ${r.revisions ? `<p class="trail"><b>Guidance changed ${r.revisions} time${r.revisions > 1 ? "s" : ""}:</b> ${r.guided.map(g => `${esc(g.call)} ${esc(range(g))}`).join(", then ")}.</p>` : ""}
      <blockquote>${esc(last.quote)}<cite>${esc(last.speaker ? last.speaker + ", " : "")}${esc(last.call)} call</cite></blockquote>
      <p class="small muted">${esc(r.why)}${r.reported ? ` Reported basis: ${esc(r.reported.basis)}.` : ""}</p></div>`; }).join("")}
    ${l.other_statements.length ? `<details class="others"><summary>${l.other_statements.length} other forward-looking statements, not scored</summary>
      <ul>${l.other_statements.map(o => `<li><strong>${esc(o.call)}</strong> ${esc(o.summary)}</li>`).join("")}</ul></details>` : ""}</div>`;
}

async function company(sym) {
  const box = document.getElementById("company");
  const ticket = ++state.ticket;
  state.company = sym;
  let r = store.companies.get(sym), p = store.prices.get(sym);
  if (!r) {
    box.innerHTML = `<div class="ph l"></div><div class="ph g"></div><div class="ph r"></div>`;
    try {
      [r, p] = await Promise.all([get(`/api/research/${encodeURIComponent(sym)}`),
                                  get(`/api/prices/${encodeURIComponent(sym)}?sessions=60`).catch(() => null)]);
    } catch (e) { if (ticket === state.ticket) box.innerHTML = fail(e); return; }
    store.companies.set(sym, r); store.prices.set(sym, p);
  }
  // a later tap, or a tab change, has replaced this request
  if (ticket !== state.ticket || state.tab !== "research") return;
  const h = r.headline, t = r.trajectory, c = r.cash_quality, b = r.balance_sheet, ser = p?.series || [];
  const cashLine = c.bank ? esc(c.note) : c.cfo_to_pat_3y_pct == null ? "Not enough cash-flow history to judge."
    : `Over three years, operating cash flow was ${c.cfo_to_pat_3y_pct}% of reported profit${c.cfo_to_pat_3y_pct < 70 ? ". Profits are not turning into cash." : c.cfo_to_pat_3y_pct > 100 ? ". Cash runs ahead of profit." : "."}`;
  const ccc = b.cash_conversion_cycle || [];
  const ledgerReady = r.ledger?.status === "ready" && r.ledger.rows?.length;
  const first = ser[0]?.close, last = ser.at(-1)?.close;
  document.title = `${r.name} | FINN`;
  box.innerHTML = `
    <h1 class="co">${esc(r.name)}</h1>
    <p class="muted small">${esc(r.symbol)}, market cap Rs ${inr(r.top_ratios["Market Cap"])} cr, P/E ${r.top_ratios["Stock P/E"] ?? "n/a"}, ROCE ${r.top_ratios["ROCE"] ?? "n/a"}%</p>
    ${last ? `<div class="price"><span class="v">Rs ${inr(last)}</span><span class="${last >= first ? "up" : "down"}">${signed((last / first - 1) * 100, 1)} over ${ser.length} sessions</span></div>${spark(ser)}` : ""}
    ${ledgerReady ? `<h2>Promised vs delivered</h2>${ledgerView(r.ledger)}` : ""}
    ${h ? `<h2>Latest quarter, ${esc(h.period)}</h2><div class="panel">${numbers({ status: "ok", headline: h })}</div>` : ""}
    <h2>Trajectory</h2><div class="panel"><p class="verdict">Revenue grew ${t.revenue_cagr_3y ?? "n/a"}% a year over three years; profit ${t.pat_cagr_3y ?? "n/a"}%.${t.margin_change_3y_pts != null ? ` Operating margin moved ${t.margin_change_3y_pts >= 0 ? "+" : ""}${t.margin_change_3y_pts} point${Math.abs(t.margin_change_3y_pts) === 1 ? "" : "s"}.` : ""}</p>${t.revenue.length ? bars(t.revenue) : ""}<p class="small muted">Annual revenue, Rs crore</p></div>
    <h2>Cash quality</h2><div class="panel"><p class="verdict">${cashLine}</p>${c.years.length ? bars(c.years.map(y => ({ period: y.period, value: y.cfo }))) + `<p class="small muted">Cash from operations by year, Rs crore. Three-year free cash flow: Rs ${inr(c.fcf_3y)} cr.</p>` : ""}</div>
    <h2>Balance sheet, ${esc(b.period)}</h2><div class="panel"><div class="facts">
      <div class="num"><div class="k">Borrowings</div><div class="v">${inr(b.borrowings)}</div></div>
      <div class="num"><div class="k">Equity</div><div class="v">${inr(b.equity)}</div></div>
      <div class="num"><div class="k">Debt / equity</div><div class="v">${b.bank ? "n/a" : b.debt_to_equity ?? "n/a"}</div></div></div>
      ${ccc.length ? `<p class="small muted">Cash conversion cycle, days: ${ccc.map(q => `${q.period.slice(-4)} ${q.value ?? "n/a"}`).join(", ")}</p>` : b.bank ? `<p class="small muted">Leverage ratios are not shown for banks because borrowings exclude deposits.</p>` : ""}</div>
    ${ledgerReady ? "" : `<h2>Promised vs delivered</h2>${ledgerView(r.ledger)}`}
    <h2>Primary documents</h2><div class="panel"><ul class="docs">
      ${r.documents.transcripts.map(d => `<li><a href="${link(d.transcript)}" target="_blank" rel="noopener">Earnings call transcript, ${esc(d.label)}</a></li>`).join("")}
      ${r.documents.annual_reports.map(d => `<li><a href="${link(d.url)}" target="_blank" rel="noopener">Annual report ${d.year}</a></li>`).join("")}</ul></div>`;
}

function search(text) {
  const all = store.symbols.symbols, q = text.trim().toUpperCase();
  if (!q) return store.symbols.portfolio.map(p => all.find(x => x[0] === p)).filter(Boolean);
  const first = all.filter(x => x[0].startsWith(q));
  return [...first, ...all.filter(x => !x[0].startsWith(q) && x[1].toUpperCase().includes(q))].slice(0, 12);
}

async function research() {
  const [e1] = entered();
  view.innerHTML = `${state.company ? "" : `<p class="lede${e1}">Research any NSE company.</p>`}
    <div class="search"><input id="q" type="search" placeholder="Symbol or name, for example INFY" autocomplete="off" aria-label="Company"></div>
    <ul class="hits" id="hits"></ul><p class="hint" id="hint"></p><div id="company"></div>`;
  const q = document.getElementById("q"), hits = document.getElementById("hits"), hint = document.getElementById("hint");
  if (!store.symbols) {
    hits.innerHTML = `<li class="muted nohit">Loading the list of NSE companies…</li>`;
    try { store.symbols = await get("/api/symbols/all"); } catch (e) { hits.innerHTML = `<li>${fail(e)}</li>`; return; }
    if (state.tab !== "research") return;
  }
  const moves = Object.fromEntries((store.alerts || []).map(r => [r.symbol, r.move_pct]));
  const show = text => {
    const list = search(text);
    hint.textContent = text.trim() ? "" : "Your holdings. Promise ledgers are ready for INFY and KAYNES; any other company shows its numbers and documents.";
    if (!list.length) { hits.innerHTML = `<li class="muted nohit">No NSE company matches "${esc(text.trim())}". Try the exchange symbol, for example TCS.</li>`; return; }
    hits.innerHTML = list.map(([s, n]) => `<li><button data-s="${esc(s)}"><strong>${esc(s)}</strong> <span class="muted">${esc(n)}</span>${moves[s] != null ? `<span class="m ${moves[s] >= 0 ? "up" : "down"}">${signed(moves[s], 1)}</span>` : ""}</button></li>`).join("");
    hits.querySelectorAll("button").forEach(b => b.onclick = () => navigate("research", b.dataset.s));
  };
  q.oninput = () => show(q.value);
  if (state.company) { q.value = state.company; company(state.company); } else show("");
}

/* ---------------- Thresholds ---------------- */
/* An SVG, not inline styles: the content security policy blocks style attributes. */
function vbar(x, hit) {
  const SCALE = 5, w = Math.min(100, (x || 0) / SCALE * 100), t = Math.min(99, state.vol / SCALE * 100);
  return `<svg class="vbar" viewBox="0 0 100 14" preserveAspectRatio="none" aria-hidden="true">
    <rect x="0" y="3" width="100" height="8" rx="4" class="bg"/><rect x="0" y="3" width="${w.toFixed(1)}" height="8" rx="4" class="${hit ? "fg hit" : "fg"}"/>
    <rect x="${t.toFixed(1)}" y="0" width="1.4" height="14" class="tick"/></svg>`;
}
async function thresholds() {
  if (!store.alerts) {
    view.innerHTML = `<p class="lede">Reading the last session…</p>${skeleton()}`;
    try { await load(); } catch (e) { view.innerHTML = fail(e); return; }
    if (state.tab !== "thresholds") return;
  }
  const [e1] = entered();
  view.innerHTML = `<p class="lede${e1}">You decide what counts as unusual.</p>
    <div class="ctl"><label for="vol">Volume above <b id="volv"></b></label><small>times the stock's median volume over the previous 20 sessions</small>
      <input id="vol" type="range" min="1.2" max="5" step="0.1" value="${state.vol}"></div>
    <div class="ctl"><label for="mv">Price move beyond <b id="mvv"></b></label><small>up or down, close against the previous close</small>
      <input id="mv" type="range" min="1" max="10" step="0.5" value="${state.move}"></div>
    <div id="res"></div>
    <p class="small muted">Saved on this device. The brief uses the same settings.</p>`;
  const vol = document.getElementById("vol"), mv = document.getElementById("mv"), res = document.getElementById("res");
  const run = () => {
    state.vol = +vol.value; state.move = +mv.value;
    document.getElementById("volv").textContent = `${state.vol}x`;
    document.getElementById("mvv").textContent = `${state.move}%`;
    const rows = judged(), n = rows.filter(r => r.triggered).length;
    const on = store.brief ? sessionDay(store.brief.price_session) : "the last session";
    res.innerHTML = `<h2>${n} of ${rows.length} would have alerted on ${esc(on)}</h2>
      <table><thead><tr><th>Stock</th><th>Move</th><th class="barh">Volume vs median</th><th>x</th></tr></thead><tbody>
      ${rows.map(r => `<tr class="${r.triggered ? "hit" : ""}"><td>${esc(r.symbol)}</td><td>${pct(r.move_pct)}</td>
        <td class="bar">${vbar(r.volume_multiple, r.triggered)}</td>
        <td>${r.volume_multiple}x</td></tr>`).join("")}</tbody></table>`;
  };
  vol.oninput = mv.oninput = run;
  vol.onchange = mv.onchange = saveThresholds;
  run();
}

/* ---------------- Navigation ----------------
   Every screen opened (a tab, or a company in Research) is a history entry, so the phone's back
   gesture returns to the previous screen instead of leaving the app. Below the first screen sits a
   guard entry: reaching it asks "Close FINN?"; a second back gesture, or "Close", leaves. The screen
   is also in the address (#research/KAYNES), so a reload reopens it. */
const TABS = { brief, research, thresholds };
const hashOf = (tab, co) => `#${tab}${tab === "research" && co ? "/" + encodeURIComponent(co) : ""}`;
function route() {
  const [t, c] = location.hash.slice(1).split("/");
  return { tab: TABS[t] ? t : "brief", company: t === "research" && c ? decodeURIComponent(c).toUpperCase() : null };
}
function show(tab, co) {
  if (tab === "research") state.company = co ?? null;
  state.tab = tab;
  state.ticket++;
  document.querySelectorAll(".tabs button").forEach(x => { if (x.dataset.tab === tab) x.setAttribute("aria-current", "page"); else x.removeAttribute("aria-current"); });
  document.title = `${tab[0].toUpperCase() + tab.slice(1)} | FINN`;
  window.scrollTo(0, 0); TABS[tab]();
}
/* A user's own move: a new entry, unless it is the screen already showing. */
function navigate(tab, co = state.company) {
  const company = tab === "research" ? co : null;
  if (tab === state.tab && (tab !== "research" || company === state.company)) { window.scrollTo({ top: 0, behavior: "smooth" }); return; }
  history.pushState({ tab, company }, "", hashOf(tab, company));
  show(tab, company);
}

const sheet = document.getElementById("exit");
function askToClose() { sheet.hidden = false; document.getElementById("exit-stay").focus(); }
function stay() {
  sheet.hidden = true;
  history.pushState({ tab: state.tab, company: state.company }, "", hashOf(state.tab, state.company));
}
document.getElementById("exit-stay").onclick = stay;
document.getElementById("exit-close").onclick = () => { sheet.hidden = true; history.back(); };
sheet.addEventListener("click", e => { if (e.target === sheet) stay(); });
sheet.addEventListener("keydown", e => { if (e.key === "Escape") stay(); });

addEventListener("popstate", e => {
  const st = e.state;
  if (!st || st.root) { askToClose(); return; }
  sheet.hidden = true;
  show(st.tab, st.company);
});

document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => navigate(b.dataset.tab));
/* Any company named anywhere opens its research: from an alert to the analysis in one tap. */
view.addEventListener("click", e => {
  const t = e.target.closest("[data-open]");
  if (t) navigate("research", t.dataset.open);
});

const first = route();
history.replaceState({ root: true }, "", location.pathname + location.search);
history.pushState(first, "", hashOf(first.tab, first.company));
show(first.tab, first.company);
/* Installable on a phone's home screen; the worker keeps the app shell for when there is no signal. */
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
/* Fetch the company list once the brief has drawn, so the Research tab opens instantly. */
load().then(() => setTimeout(() => { if (!store.symbols) get("/api/symbols/all").then(d => { store.symbols ??= d; }).catch(() => {}); }, 300)).catch(() => {});
