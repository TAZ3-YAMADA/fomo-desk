/* Hand-drawn canvas charts (no libraries). */
(function () {
  function setup(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 300, h = canvas.clientHeight || 150;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx, w, h };
  }
  function fmtT(ts) { const d = new Date(ts * 1000); return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0'); }
  function msg(canvas, text) {
    const { ctx, w, h } = setup(canvas);
    ctx.fillStyle = '#8e8e93'; ctx.font = '13px -apple-system,sans-serif'; ctx.textAlign = 'center';
    ctx.fillText(text, w / 2, h / 2);
  }
  /* points: [[ts, value], ...]; opts: {baseline, fmt} */
  function line(canvas, points, opts) {
    opts = opts || {};
    if (!points || points.length < 2) return msg(canvas, opts.empty || 'Not enough data yet');
    const { ctx, w, h } = setup(canvas);
    const pad = { l: 6, r: 52, t: 10, b: 20 };
    const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
    let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    if (opts.baseline != null) { y0 = Math.min(y0, opts.baseline); y1 = Math.max(y1, opts.baseline); }
    if (y1 === y0) { y1 += Math.abs(y1) * 0.01 || 1; y0 -= Math.abs(y0) * 0.01 || 1; }
    if (x1 === x0) x1 = x0 + 1;
    const X = t => pad.l + (t - x0) / (x1 - x0) * (w - pad.l - pad.r);
    const Y = v => pad.t + (1 - (v - y0) / (y1 - y0)) * (h - pad.t - pad.b);
    const last = ys[ys.length - 1];
    const ref = opts.baseline != null ? opts.baseline : ys[0];
    const col = last >= ref ? '#30d158' : '#ff453a';
    const fmt = opts.fmt || (v => v.toPrecision(4));
    // grid
    ctx.strokeStyle = '#2c2c2e'; ctx.lineWidth = 1; ctx.fillStyle = '#8e8e93'; ctx.font = '10px -apple-system,sans-serif'; ctx.textAlign = 'left';
    for (let i = 0; i <= 3; i++) {
      const v = y0 + (y1 - y0) * i / 3, y = Y(v);
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
      ctx.fillText(fmt(v), w - pad.r + 4, y + 3);
    }
    ctx.textAlign = 'center';
    [x0, (x0 + x1) / 2, x1].forEach((t, i) => { ctx.textAlign = ['left', 'center', 'right'][i]; ctx.fillText(fmtT(t), i === 2 ? w - pad.r : X(t), h - 5); });
    if (opts.baseline != null) {
      ctx.setLineDash([4, 4]); ctx.strokeStyle = '#636366';
      ctx.beginPath(); ctx.moveTo(pad.l, Y(opts.baseline)); ctx.lineTo(w - pad.r, Y(opts.baseline)); ctx.stroke(); ctx.setLineDash([]);
    }
    // area
    const g = ctx.createLinearGradient(0, pad.t, 0, h - pad.b);
    g.addColorStop(0, col + '55'); g.addColorStop(1, col + '00');
    ctx.beginPath(); ctx.moveTo(X(xs[0]), h - pad.b);
    points.forEach(p => ctx.lineTo(X(p[0]), Y(p[1])));
    ctx.lineTo(X(xs[xs.length - 1]), h - pad.b); ctx.closePath(); ctx.fillStyle = g; ctx.fill();
    // line
    ctx.beginPath(); points.forEach((p, i) => i ? ctx.lineTo(X(p[0]), Y(p[1])) : ctx.moveTo(X(p[0]), Y(p[1])));
    ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.stroke();
    // last dot
    ctx.beginPath(); ctx.arc(X(xs[xs.length - 1]), Y(last), 3.5, 0, Math.PI * 2); ctx.fillStyle = col; ctx.fill();
    if (opts.marker != null) {
      ctx.strokeStyle = '#0a84ff'; ctx.setLineDash([2, 3]);
      ctx.beginPath(); ctx.moveTo(pad.l, Y(opts.marker)); ctx.lineTo(w - pad.r, Y(opts.marker)); ctx.stroke(); ctx.setLineDash([]);
    }
  }
  /* bars: [{label, value}] */
  function bars(canvas, items) {
    if (!items || !items.length) return msg(canvas, 'No data yet');
    const { ctx, w, h } = setup(canvas);
    const max = Math.max(1, ...items.map(i => i.value));
    const bw = (w - 10) / items.length;
    ctx.font = '10px -apple-system,sans-serif'; ctx.textAlign = 'center';
    items.forEach((it, i) => {
      const bh = (h - 30) * it.value / max, x = 5 + i * bw;
      ctx.fillStyle = it.color || '#0a84ff';
      roundRect(ctx, x + bw * 0.15, h - 18 - bh, bw * 0.7, bh, 4); ctx.fill();
      ctx.fillStyle = '#8e8e93'; ctx.fillText(it.label, x + bw / 2, h - 5);
      ctx.fillStyle = '#fff'; ctx.fillText(String(it.value), x + bw / 2, h - 22 - bh);
    });
  }
  function roundRect(ctx, x, y, w, h, r) {
    r = Math.min(r, h / 2, w / 2); ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  window.DeskChart = { line, bars, msg };
})();
