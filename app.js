/* FOMO Desk PWA — Plan B: polls static JSON at ./d/{DATA_PATH}/ every 15s. Read-only. */
(function () {
  'use strict';
  const POLL_MS = 15000;
  const LS_DP = 'fomo.dp', LS_CACHE = 'fomo.cache.';
  const $ = s => document.querySelector(s);
  const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const SAFE_LINK = /^https:\/\/(fomo\.family|dexscreener\.com|rugcheck\.xyz|solscan\.io)\//;
  const safeUrl = u => (typeof u === 'string' && SAFE_LINK.test(u)) ? u : '#';
  const usd = (v, d = 2) => v == null || isNaN(v) ? '—' : (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  const pct = v => v == null || isNaN(v) ? '—' : (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
  const cls = v => v == null ? '' : v >= 0 ? 'pos' : 'neg';
  const price = v => v == null ? '—' : '$' + (v >= 1 ? v.toFixed(4) : Number(v).toPrecision(4));
  const ago = ts => { if (!ts) return '—'; const s = Math.max(0, Date.now() / 1000 - ts); return s < 60 ? Math.round(s) + 's' : s < 3600 ? Math.round(s / 60) + 'm' : s < 86400 ? Math.round(s / 3600) + 'h' : Math.round(s / 86400) + 'd'; };
  const short = m => m ? m.slice(0, 4) + '…' + m.slice(-4) : '';

  // ---------- DATA_PATH from #d= fragment, persisted, then stripped from the URL bar
  function dataPath() {
    const m = location.hash.match(/[#&]d=([A-Za-z0-9_-]{16,128})/);
    if (m) {
      localStorage.setItem(LS_DP, m[1]);
      history.replaceState(null, '', location.pathname + location.search);
    }
    return localStorage.getItem(LS_DP);
  }
  let DP = dataPath();
  const base = () => 'd/' + encodeURIComponent(DP) + '/';

  const S = { state: null, chart: null, activity: null, err: null, loading: true, tab: 'home', range: 'all', lastOk: null };
  ['state', 'chart', 'activity'].forEach(k => { try { S[k] = JSON.parse(localStorage.getItem(LS_CACHE + k)); } catch (e) { } });

  async function getJSON(name) {
    const r = await fetch(base() + name + '?t=' + Date.now(), { cache: 'no-store' });
    if (r.status === 404) throw new Error('404');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }

  async function poll() {
    if (!DP) { S.loading = false; render(); return; }
    try {
      const [st, ch, ac] = await Promise.all([getJSON('state.json'), getJSON('chart.json'), getJSON('activity.json')]);
      S.state = st; S.chart = ch; S.activity = ac; S.err = null; S.lastOk = Date.now();
      try { localStorage.setItem(LS_CACHE + 'state', JSON.stringify(st)); localStorage.setItem(LS_CACHE + 'chart', JSON.stringify(ch)); localStorage.setItem(LS_CACHE + 'activity', JSON.stringify(ac)); } catch (e) { }
    } catch (e) {
      S.err = e.message === '404' ? 'Data not found. The link may be wrong or the desk has not published yet.' : (navigator.onLine ? 'Could not reach desk data (' + e.message + ').' : 'You are offline.');
    }
    S.loading = false; render();
  }

  // ---------- header
  function header() {
    const titles = { home: 'Home', agents: 'Agents', activity: 'Activity', account: 'Account' };
    $('#h-title').textContent = titles[S.tab];
    const st = S.state;
    const b = $('#badge');
    b.textContent = st && st.paused ? 'PAPER · PAUSED' : 'PAPER';
    b.className = 'badge ' + (st && st.paused ? 'paused' : 'paper');
    let sub = 'Loading…';
    if (!DP) sub = 'Not linked';
    else if (st) {
      const age = Date.now() / 1000 - st.ts;
      sub = 'Updated ' + ago(st.ts) + ' ago' + (age > 90 ? ' · desk may be offline' : '') + ' · analyst ' + esc(st.analyst_mode);
    } else if (S.err) sub = 'Error';
    $('#h-sub').textContent = sub;
  }

  const errBox = () => S.err ? `<div class="err">${esc(S.err)}${S.state ? ' Showing last saved data.' : ''}</div>` : '';
  const skeleton = n => Array.from({ length: n }, () => '<div class="skel"></div>').join('');
  const empty = (e, t, s) => `<div class="empty"><div class="e">${e}</div><div>${esc(t)}</div>${s ? `<div class="small" style="margin-top:4px">${esc(s)}</div>` : ''}</div>`;

  function needLink() {
    return `<div class="card">${empty('🔗', 'Open the desk link once', 'Use the link from Telegram /app (…/index.html#d=…). It is saved on this phone.')}
      <h3>Or paste data key</h3><input id="dp-in" placeholder="data key" autocomplete="off" autocapitalize="off" spellcheck="false">
      <div class="btns"><a class="btn ghost" id="dp-save" href="#">Save</a></div></div>`;
  }

  // ---------- Home
  function home() {
    if (!DP) return needLink();
    const st = S.state;
    if (!st) return errBox() + (S.loading || !S.err ? skeleton(3) : empty('⚠️', 'No data yet'));
    const k = st.stack || {};
    let h = errBox();
    h += `<div class="card"><div class="muted small">Paper equity</div><div class="big">${usd(k.equity)}</div>
      <div class="${cls(k.pct)}">${pct(k.pct)} <span class="muted">from ${usd(k.start, 0)} start</span></div>
      <div class="seg" id="range">${['1h', '24h', 'all'].map(r => `<button data-r="${r}" class="${S.range === r ? 'on' : ''}">${r.toUpperCase()}</button>`).join('')}</div>
      <canvas id="eq-chart" class="chart"></canvas></div>`;
    h += `<div class="grid">
      <div class="stat"><div class="k">Cash</div><div class="v">${usd(k.cash)}</div></div>
      <div class="stat"><div class="k">Unrealized</div><div class="v ${cls(k.unrealized)}">${usd(k.unrealized)}</div></div>
      <div class="stat"><div class="k">Today</div><div class="v ${cls(k.realized_today)}">${usd(k.realized_today)}</div></div>
      <div class="stat"><div class="k">Win rate</div><div class="v">${k.win_rate == null ? '—' : k.win_rate.toFixed(0) + '%'}</div></div></div>`;
    h += '<h3>Open positions</h3>';
    const ps = st.positions || [];
    h += ps.length ? '<div class="list">' + ps.map(p => `<div class="item tap" data-mint="${esc(p.mint)}">
      <div class="main"><div class="t">${esc(p.symbol || short(p.mint))}</div><div class="s">${usd(p.cost)} · held ${ago(p.opened_at)}</div></div>
      <div class="r"><div>${usd(p.value)}</div><div class="small ${cls(p.pct)}">${pct(p.pct)}</div></div></div>`).join('') + '</div>'
      : '<div class="list">' + empty('🌙', 'No open positions', 'The desk is watching graduations.') + '</div>';
    const cl = st.closed || [];
    h += '<h3>Recent closes</h3>' + (cl.length ? '<div class="list">' + cl.slice(0, 10).map(p => `<div class="item tap" data-mint="${esc(p.mint)}">
      <div class="main"><div class="t">${esc(p.symbol || short(p.mint))}</div><div class="s">${esc(p.reason || '')} · ${ago(p.closed_at)} ago</div></div>
      <div class="r ${cls(p.pnl)}">${usd(p.pnl)}</div></div>`).join('') + '</div>' : '<div class="list">' + empty('📭', 'No trades yet') + '</div>');
    return h;
  }

  function drawHome() {
    const c = $('#eq-chart'); if (!c) return;
    const ch = S.chart;
    if (!ch) return DeskChart.msg(c, S.err ? 'Chart unavailable' : 'Loading…');
    let pts = ch.equity || [];
    const now = Date.now() / 1000;
    if (S.range === '1h') pts = pts.filter(p => p[0] >= now - 3600);
    if (S.range === '24h') pts = pts.filter(p => p[0] >= now - 86400);
    DeskChart.line(c, pts, { baseline: ch.start, fmt: v => '$' + v.toFixed(0), empty: 'Equity history builds up as the desk runs' });
  }

  // ---------- Agents
  function agents() {
    if (!DP) return needLink();
    const st = S.state;
    if (!st) return errBox() + skeleton(4);
    const ag = st.agents || [];
    let h = errBox();
    h += ag.length ? '<div class="list">' + ag.map(a => {
      const info = a.info || {};
      const det = Object.entries(info).filter(([k, v]) => typeof v !== 'object').map(([k, v]) => esc(k) + ' ' + esc(v)).join(' · ');
      return `<div class="item"><div class="dot ${esc(a.status)}"></div><div class="main"><div class="t">${esc(a.name)}</div><div class="s">${det || '—'}</div></div>
        <div class="r small muted">${esc(a.status)}<br>${ago(st.ts - a.age_s)} ago</div></div>`;
    }).join('') + '</div>' : '<div class="list">' + empty('🤖', 'No heartbeats yet') + '</div>';
    const c = st.counts || {};
    h += '<h3>Pipeline · 24h</h3><div class="card"><canvas id="pipe" class="chart small"></canvas></div>';
    const q = st.queues || {};
    h += '<h3>Queues</h3><div class="card">' + Object.entries(q).map(([k, v]) => `<div class="kv"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join('') + '</div>';
    return h;
  }
  function drawAgents() {
    const c = $('#pipe'); if (!c || !S.state) return;
    const n = S.state.counts || {};
    const order = [['watching', 'watch'], ['queued', 'queued'], ['audited', 'audited'], ['rejected', 'rejected'], ['signaled', 'signal'], ['bought', 'held'], ['sold', 'sold'], ['expired', 'expired']];
    DeskChart.bars(c, order.map(([k, l]) => ({ label: l, value: n[k] || 0, color: k === 'rejected' || k === 'expired' ? '#636366' : '#0a84ff' })));
  }

  // ---------- Activity
  function activity() {
    if (!DP) return needLink();
    const a = S.activity;
    if (!a) return errBox() + skeleton(5);
    const ev = a.events || [];
    return errBox() + (ev.length ? '<div class="list">' + ev.map(e => `<div class="item ${e.mint ? 'tap' : ''}" ${e.mint ? `data-mint="${esc(e.mint)}"` : ''}>
      <div class="main"><div class="t small lvl-${esc(e.level)}">${esc(e.agent)} · ${esc(e.kind)}</div><div class="s" style="white-space:normal">${esc(e.msg)}</div></div>
      <div class="r small muted">${ago(e.ts)}</div></div>`).join('') + '</div>' : '<div class="list">' + empty('🕊️', 'No activity yet') + '</div>');
  }

  // ---------- Account (read-only)
  function account() {
    const st = S.state;
    let h = '';
    if (!DP) return needLink();
    h += errBox();
    h += `<div class="card"><div class="kv"><span>FOMO handle</span><span>${st ? '@' + esc(st.fomo_handle || '—') : '—'}</span></div>
      <div class="kv"><span>Mode</span><span>PAPER</span></div>
      <div class="kv"><span>Analyst</span><span>${st ? esc(st.analyst_mode) : '—'}</span></div>
      <div class="kv"><span>Status</span><span>${st ? (st.paused ? 'Paused' : 'Running') : '—'}</span></div>
      <div class="kv"><span>Desk up since</span><span>${st ? new Date(st.started * 1000).toLocaleString() : '—'}</span></div>
      <div class="kv"><span>Last sync</span><span>${S.lastOk ? new Date(S.lastOk).toLocaleTimeString() : '—'}</span></div></div>`;
    if (st && st.settings) {
      const keys = ['paper_start_stack', 'position_usd', 'max_open_positions', 'take_profit_pct', 'stop_loss_pct', 'trail_pct', 'max_hold_min', 'daily_loss_limit_usd', 'fees_ref_discount', 'min_liquidity_usd', 'max_top10_pct'];
      h += '<h3>Settings (read-only)</h3><div class="card">' + keys.map(k => `<div class="kv"><span class="muted">${esc(k)}</span><span>${esc(st.settings[k])}</span></div>`).join('') + '</div>';
    }
    h += '<div class="card small muted">Change settings, pause or mode from Telegram: /pause, /resume, /mode, /set. Orders are never placed by the desk — use the Buy/Sell on FOMO buttons.</div>';
    h += '<div class="btns"><a class="btn ghost" id="unlink" href="#">Unlink this phone</a></div>';
    return h;
  }

  // ---------- coin sheet
  async function openCoin(mint) {
    const body = $('#sheet-body');
    $('#sheet').classList.remove('hidden');
    body.innerHTML = skeleton(2);
    let c;
    try { c = await getJSON('coin/' + encodeURIComponent(mint) + '.json'); }
    catch (e) { body.innerHTML = `<div class="err">Coin data not available (${esc(e.message)}).</div>`; return; }
    const d = c.dex || {}, a = c.audit || {}, an = c.analysis || {}, L = c.links || {};
    let h = `<div class="title" style="font-size:24px">${esc(c.symbol || short(c.mint))}</div><div class="muted small">${esc(c.name || '')} · ${esc(short(c.mint))} · ${esc(c.stage)}</div>
      <div class="btns"><a class="btn" href="${esc(safeUrl(L.buy))}" target="_blank" rel="noopener noreferrer">Buy on FOMO</a><a class="btn sell" href="${esc(safeUrl(L.sell))}" target="_blank" rel="noopener noreferrer">Sell on FOMO</a></div>
      <div class="card"><canvas id="coin-chart" class="chart"></canvas></div>
      <div class="grid"><div class="stat"><div class="k">Price</div><div class="v">${price(d.price_usd)}</div></div>
      <div class="stat"><div class="k">Liquidity</div><div class="v">${usd(d.liquidity_usd, 0)}</div></div>
      <div class="stat"><div class="k">Mcap</div><div class="v">${usd(d.market_cap, 0)}</div></div>
      <div class="stat"><div class="k">5m vol</div><div class="v">${usd(d.vol_m5, 0)}</div></div></div>`;
    if (c.reason) h += `<div class="card small">${esc(c.reason)}</div>`;
    if (a.layers) h += '<h3>Audit layers</h3><div class="card">' + a.layers.map(l => `<div class="layer"><span>${l.ok === true ? '✅' : l.ok === false ? '❌' : '❔'}</span><span style="flex:1">L${esc(l.n)} ${esc(l.name)}</span><span class="muted">${l.value == null ? '' : esc(typeof l.value === 'number' ? (Number.isInteger(l.value) ? l.value : l.value.toFixed(1)) : short(String(l.value)))}</span></div>`).join('') + '</div>';
    if (an.jev) h += '<h3>Jev</h3><div class="card">' + Object.entries(an.jev).map(([k, v]) => `<div class="kv"><span>${esc(k)}</span><span>${v == null ? '—' : esc(v.toFixed(2))}</span></div>`).join('') + '</div>';
    h += `<div class="btns"><a class="btn ghost" href="${esc(safeUrl(L.dexscreener))}" target="_blank" rel="noopener noreferrer">Chart</a><a class="btn ghost" href="${esc(safeUrl(L.rugcheck))}" target="_blank" rel="noopener noreferrer">RugCheck</a></div>`;
    body.innerHTML = h;
    const pts = c.prices || [];
    const pos = (S.state && S.state.positions || []).find(p => p.mint === mint);
    DeskChart.line($('#coin-chart'), pts, { fmt: v => Number(v).toPrecision(3), marker: pos ? pos.entry : null, empty: 'No price history yet' });
  }

  // ---------- render + events
  function render() {
    header();
    const views = { home, agents, activity, account };
    const el = $('#tab-' + S.tab);
    el.innerHTML = views[S.tab]();
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.id === 'tab-' + S.tab));
    if (S.tab === 'home') drawHome();
    if (S.tab === 'agents') drawAgents();
  }

  document.addEventListener('click', e => {
    const tb = e.target.closest('.tabbar button');
    if (tb) { S.tab = tb.dataset.tab; document.querySelectorAll('.tabbar button').forEach(b => b.classList.toggle('on', b === tb)); window.scrollTo(0, 0); render(); return; }
    const rb = e.target.closest('#range button');
    if (rb) { S.range = rb.dataset.r; render(); return; }
    const it = e.target.closest('[data-mint]');
    if (it) { openCoin(it.dataset.mint); return; }
    if (e.target.closest('#sheet-close') || e.target.id === 'sheet') { $('#sheet').classList.add('hidden'); return; }
    if (e.target.closest('#dp-save')) {
      e.preventDefault();
      const v = ($('#dp-in').value || '').trim();
      if (/^[A-Za-z0-9_-]{16,128}$/.test(v)) { localStorage.setItem(LS_DP, v); DP = v; S.loading = true; render(); poll(); }
      else alert('That key does not look right.');
      return;
    }
    if (e.target.closest('#unlink')) {
      e.preventDefault();
      if (confirm('Unlink this phone from the desk?')) { localStorage.removeItem(LS_DP); ['state', 'chart', 'activity'].forEach(k => localStorage.removeItem(LS_CACHE + k)); DP = null; S.state = S.chart = S.activity = null; render(); }
    }
  });
  window.addEventListener('hashchange', () => { const n = dataPath(); if (n && n !== DP) { DP = n; poll(); } });
  window.addEventListener('resize', () => { if (S.tab === 'home') drawHome(); if (S.tab === 'agents') drawAgents(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => { });
  render();
  poll();
  setInterval(() => { if (!document.hidden) poll(); }, POLL_MS);
  setInterval(header, 5000);
})();
