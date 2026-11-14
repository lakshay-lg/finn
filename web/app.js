const view = document.getElementById("view");
const state = { tab: "brief", hours: 24, vol: 2, move: 4 };
const WINDOWS = [[24, "24 hours"], [72, "3 days"], [168, "7 days"], [720, "30 days"]];
const CATS = { "M&A": "M&A", fund_raise: "Fund raise", management_change: "Management change", results: "Results",
  litigation: "Legal", credit_rating: "Credit rating", earnings_call: "Earnings call", press_release: "Update",
  capex: "Capex", dividend: "Dividend", bonus_split: "Bonus or split", insider_trading: "Insider trade",
  pledging: "Pledge", investor_meetings: "Investor meeting", postal_ballot: "Postal ballot", agm_egm: "AGM or EGM",
  unclassified: "Paperwork" };

const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const inr = v => v == null ? "n/a" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const pct = v => v == null ? "" : `<span class="${v >= 0 ? "up" : "down"}">${v >= 0 ? "+" : ""}${v}%</span>`;
const when = ts => new Date(ts).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
const shortTitle = t => t.replace(/^Announcement under Regulation 30 \(LODR\)\s*-?\s*/i, "").replace(/^Disclosure Under Regulation 30.*$/i, "Regulation 30 disclosure");
async function get(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
  return r.json();
}
const fail = e => `<p class="error">${esc(e.message)}. Check that the FINN server is running, then reload.</p>`;

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

function row(it, tier) {
  const note = it.note || (it.related.find(r => r.note) || {}).note || "";
  return `<article class="row ${tier}">
    <div class="row-head"><span class="sym">${esc(it.symbol)}</span><span class="cat">${esc(CATS[it.category] || it.category)}</span><span class="when">${when(it.ts)}</span></div>
    <p class="title">${esc(shortTitle(it.title))}</p>
    ${note ? `<p class="note">${esc(note)} <span class="by">Summary by screener.in</span></p>` : ""}
    ${numbers(it.numbers)}
    <a class="src" href="${esc(it.url)}" target="_blank" rel="noopener">Open filing</a>
    ${it.related.length ? `<div class="more">${it.related.length} more filing${it.related.length > 1 ? "s" : ""} on this the same day</div>` : ""}
  </article>`;
}

function moveRow(m) {
  const why = [m.reasons.includes("volume") ? `volume ${m.volume_multiple}x its 20-session median` : "",
    m.reasons.includes("price") ? `price ${m.move_pct >= 0 ? "+" : ""}${m.move_pct}%` : ""].filter(Boolean).join(", ");
  return `<article class="row high"><div class="row-head"><span class="sym">${esc(m.symbol)}</span><span class="cat">Unusual move</span><span class="when">${esc(m.date)}</span></div>
    <p class="title">${esc(why[0].toUpperCase() + why.slice(1))}</p>
    <p class="note">Closed at ${inr(m.close)}, ${m.move_pct >= 0 ? "up" : "down"} ${Math.abs(m.move_pct)}%. ${m.delivery_pct ?? "n/a"}% of traded shares were delivered.</p></article>`;
}

async function brief() {
  let b;
  try { b = await get(`/api/brief?hours=${state.hours}`); } catch (e) { view.innerHTML = fail(e); return; }
  const label = WINDOWS.find(w => w[0] === state.hours)[1];
  const high = group(b.high), medium = group(b.medium);
  const movesIn = b.moves_in_window ? b.moves : [], movesOut = b.moves_in_window ? [] : b.moves;
  const n = high.length + movesIn.length;
  const lede = b.counts.total === 0 && !movesIn.length
    ? `Nothing filed in the last ${label}.`
    : `${b.counts.total} filing${b.counts.total === 1 ? "" : "s"} in the last ${label}. ${n} ${n === 1 ? "needs" : "need"} your attention.`;
  view.innerHTML = `
    <p class="lede">${lede}</p>
    <p class="stamp">As of ${when(b.generated_at)}. Prices from the ${esc(b.price_session)} session.</p>
    <div class="seg" role="group" aria-label="Time window">${WINDOWS.map(([h, t]) => `<button data-h="${h}" aria-pressed="${h === state.hours}">${t}</button>`).join("")}</div>
    ${n ? `<h2>Needs attention</h2>${movesIn.map(moveRow).join("")}${high.map(i => row(i, "high")).join("")}` : ""}
    ${movesOut.length ? `<h2>From the last trading session, before this window</h2>${movesOut.map(moveRow).join("")}` : ""}
    ${!n && b.last_high ? `<p class="muted">The last filing that mattered was ${esc(b.last_high.symbol)} on ${when(b.last_high.ts)}. Widen the window to see it.</p>` : ""}
    ${medium.length ? `<h2>Worth a look</h2>${medium.map(i => row(i, "medium")).join("")}` : ""}
    ${b.routine.length ? `<details class="routine"><summary>${b.routine.length} routine filing${b.routine.length > 1 ? "s" : ""}, set aside</summary>
      <ul>${b.routine.map(r => `<li><strong>${esc(r.symbol)}</strong> ${esc(CATS[r.category] || r.category)}: <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(shortTitle(r.title)).slice(0, 80)}</a></li>`).join("")}</ul></details>` : ""}
    <p class="coverage">Coverage: ${esc(b.coverage.statement)} Holding ${b.coverage.items} filings across ${b.coverage.companies} companies.</p>`;
  view.querySelectorAll(".seg button").forEach(btn => btn.onclick = () => { state.hours = +btn.dataset.h; brief(); });
}

function bars(points, { h = 120 } = {}) {
  const vals = points.map(p => p.value ?? 0), max = Math.max(...vals, 0), min = Math.min(...vals, 0);
  const W = 320, pad = 18, span = (max - min) || 1, bw = (W - 8) / points.length, zero = pad + (max / span) * (h - 2 * pad);
  return `<svg class="chart" viewBox="0 0 ${W} ${h}" role="img">${points.map((p, i) => {
    const v = p.value ?? 0, bh = Math.abs(v) / span * (h - 2 * pad), y = v >= 0 ? zero - bh : zero;
    return `<rect x="${4 + i * bw + 2}" y="${y}" width="${bw - 4}" height="${Math.max(bh, 1)}" rx="2" fill="${v >= 0 ? "var(--ink)" : "var(--down)"}"><title>${esc(p.period)}: ${inr(p.value)}</title></rect>
      ${i % Math.ceil(points.length / 6) === 0 ? `<text x="${4 + i * bw + bw / 2}" y="${h - 3}" text-anchor="middle">${esc(p.period.slice(-4))}</text>` : ""}`;
  }).join("")}<line x1="0" x2="${W}" y1="${zero}" y2="${zero}" stroke="var(--line)"/></svg>`;
}

async function company(sym) {
  const box = document.getElementById("company");
  box.innerHTML = `<p class="muted">Reading ${esc(sym)}…</p>`;
  let r;
  try { r = await get(`/api/research/${encodeURIComponent(sym)}`); } catch (e) { box.innerHTML = fail(e); return; }
  const h = r.headline, t = r.trajectory, c = r.cash_quality, b = r.balance_sheet;
  const cashLine = c.bank ? esc(c.note) : c.cfo_to_pat_3y_pct == null ? "Not enough cash-flow history to judge."
    : `Over the last three years, operating cash flow was ${c.cfo_to_pat_3y_pct}% of reported profit${c.cfo_to_pat_3y_pct < 70 ? ". Profits are not turning into cash." : c.cfo_to_pat_3y_pct > 100 ? ". Cash runs ahead of profit." : "."}`;
  const ccc = b.cash_conversion_cycle || [];
  box.innerHTML = `
    <h1 class="co">${esc(r.name)}</h1>
    <p class="muted small">${esc(r.symbol)}, market cap Rs ${inr(r.top_ratios["Market Cap"])} crore, P/E ${r.top_ratios["Stock P/E"] ?? "n/a"}, ROCE ${r.top_ratios["ROCE"] ?? "n/a"}%</p>
    ${h ? `<h2>Latest quarter, ${esc(h.period)}</h2><div class="panel">${numbers({ status: "ok", headline: h })}</div>` : ""}
    <h2>Trajectory</h2><div class="panel"><p class="verdict">Revenue grew ${t.revenue_cagr_3y ?? "n/a"}% a year over three years; profit ${t.pat_cagr_3y ?? "n/a"}%.${t.margin_change_3y_pts != null ? ` Operating margin moved ${t.margin_change_3y_pts >= 0 ? "+" : ""}${t.margin_change_3y_pts} point${Math.abs(t.margin_change_3y_pts) === 1 ? "" : "s"}.` : ""}</p>${t.revenue.length ? bars(t.revenue) : ""}<p class="small muted">Annual revenue, Rs crore</p></div>
    <h2>Cash quality</h2><div class="panel"><p class="verdict">${cashLine}</p>${c.years.length ? bars(c.years.map(y => ({ period: y.period, value: y.cfo }))) + `<p class="small muted">Cash from operations by year, Rs crore. Three-year free cash flow: ${inr(c.fcf_3y)}.</p>` : ""}</div>
    <h2>Balance sheet, ${esc(b.period)}</h2><div class="panel"><div class="facts">
      <div class="num"><div class="k">Borrowings</div><div class="v">${inr(b.borrowings)}</div></div>
      <div class="num"><div class="k">Equity</div><div class="v">${inr(b.equity)}</div></div>
      <div class="num"><div class="k">Debt to equity</div><div class="v">${b.bank ? "n/a" : b.debt_to_equity ?? "n/a"}</div></div></div>
      ${ccc.length ? `<p class="small muted">Cash conversion cycle, days: ${ccc.map(p => `${p.period.slice(-4)} ${p.value ?? "n/a"}`).join(", ")}</p>` : b.bank ? `<p class="small muted">Leverage ratios are not shown for banks because borrowings exclude deposits.</p>` : ""}</div>
    <h2>Promised vs delivered</h2><div class="panel"><p class="muted">Not built yet. This needs a model to read the transcripts below and compare management's guidance with the numbers above.</p></div>
    <h2>Primary documents</h2><div class="panel"><ul class="docs">
      ${r.documents.transcripts.map(d => `<li><a href="${esc(d.transcript)}" target="_blank" rel="noopener">Earnings call transcript, ${esc(d.label)}</a></li>`).join("")}
      ${r.documents.annual_reports.map(d => `<li><a href="${esc(d.url)}" target="_blank" rel="noopener">Annual report ${d.year}</a></li>`).join("")}</ul></div>`;
}

async function research() {
  view.innerHTML = `<p class="lede">Research any NSE company.</p>
    <div class="search"><input id="q" type="search" placeholder="Symbol or name, for example INFY" autocomplete="off" aria-label="Company"></div>
    <ul class="hits" id="hits"></ul><div id="company"></div>`;
  const q = document.getElementById("q"), hits = document.getElementById("hits");
  let timer;
  const show = async text => {
    let list; try { list = await get(`/api/symbols?q=${encodeURIComponent(text)}`); } catch { list = []; }
    hits.innerHTML = list.map(s => `<li><button data-s="${esc(s.symbol)}"><strong>${esc(s.symbol)}</strong> <span class="muted">${esc(s.name)}</span></button></li>`).join("");
    hits.querySelectorAll("button").forEach(b => b.onclick = () => { hits.innerHTML = ""; q.value = b.dataset.s; company(b.dataset.s); });
  };
  q.oninput = () => { clearTimeout(timer); timer = setTimeout(() => show(q.value), 180); };
  show("");
}

async function thresholds() {
  view.innerHTML = `<p class="lede">You decide what counts as unusual.</p>
    <div class="ctl"><label for="vol">Volume above <span id="volv"></span></label><input id="vol" type="range" min="1.2" max="5" step="0.1" value="${state.vol}"></div>
    <div class="ctl"><label for="mv">Price move beyond <span id="mvv"></span></label><input id="mv" type="range" min="1" max="10" step="0.5" value="${state.move}"></div>
    <div id="res"></div>`;
  const vol = document.getElementById("vol"), mv = document.getElementById("mv"), res = document.getElementById("res");
  const run = async () => {
    state.vol = +vol.value; state.move = +mv.value;
    document.getElementById("volv").textContent = `${state.vol}x the 20-session median`;
    document.getElementById("mvv").textContent = `${state.move}% in a day`;
    let d; try { d = await get(`/api/alerts?volume_multiple=${state.vol}&price_move_pct=${state.move}`); } catch (e) { res.innerHTML = fail(e); return; }
    const n = d.results.filter(r => r.triggered).length;
    res.innerHTML = `<h2>${n} of ${d.results.length} stocks would alert on the last session</h2>
      <table><thead><tr><th>Stock</th><th>Move</th><th>Volume</th><th>Delivered</th></tr></thead><tbody>
      ${d.results.map(r => `<tr class="${r.triggered ? "hit" : ""}"><td>${esc(r.symbol)}</td><td>${pct(r.move_pct)}</td><td>${r.volume_multiple}x</td><td>${r.delivery_pct ?? "n/a"}%</td></tr>`).join("")}</tbody></table>`;
  };
  vol.oninput = mv.oninput = run; run();
}

const TABS = { brief, research, thresholds };
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
  state.tab = b.dataset.tab;
  document.querySelectorAll(".tabs button").forEach(x => x.toggleAttribute("aria-current", false));
  b.setAttribute("aria-current", "page");
  window.scrollTo(0, 0); TABS[state.tab]();
});
brief();
