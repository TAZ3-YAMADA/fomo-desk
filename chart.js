(function (global) {
  "use strict";

  function num(value) {
    if (value == null || value === "") return null;
    var n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function asPoint(raw, index) {
    if (typeof raw === "number") {
      return Number.isFinite(raw) ? { v: raw, i: index } : null;
    }
    if (!raw || typeof raw !== "object") return null;
    var v = num(raw.v != null ? raw.v : raw.value != null ? raw.value : raw.c != null ? raw.c : raw.close);
    if (v == null) return null;
    var t = num(raw.t != null ? raw.t : raw.time);
    return { v: v, t: t, i: index };
  }

  function seriesOf(data) {
    var rows = null;
    if (Array.isArray(data)) rows = data;
    else if (data && typeof data === "object") {
      if (Array.isArray(data.points)) rows = data.points;
      else if (Array.isArray(data.values)) rows = data.values;
      else if (Array.isArray(data.series)) rows = data.series;
      else if (Array.isArray(data.candles)) rows = data.candles;
    }
    if (!rows) return [];
    var out = [];
    for (var i = 0; i < rows.length; i++) {
      var point = asPoint(rows[i], i);
      if (point) out.push(point);
    }
    return out;
  }

  function render(canvas, data) {
    if (!canvas || !canvas.getContext) return false;
    var points = seriesOf(data);
    var width = canvas.clientWidth;
    var height = canvas.clientHeight;
    if (width < 2 || height < 2 || points.length < 2) {
      canvas.width = 0;
      canvas.height = 0;
      return false;
    }

    var dpr = Math.min(global.devicePixelRatio || 1, 3);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    var ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    var min = points[0].v;
    var max = points[0].v;
    var i;
    for (i = 1; i < points.length; i++) {
      if (points[i].v < min) min = points[i].v;
      if (points[i].v > max) max = points[i].v;
    }
    var span = max - min;
    if (span === 0) {
      min -= 1;
      max += 1;
      span = 2;
    }

    var padX = 10;
    var padY = 18;
    var usable = Math.max(1, height - padY * 2);
    var inner = Math.max(1, width - padX * 2);
    var useT = points.every(function (point) { return point.t != null; });
    var t0 = useT ? points[0].t : 0;
    var t1 = useT ? points[points.length - 1].t : 1;
    function xAt(index) {
      var ratio;
      if (useT && t1 !== t0) ratio = (points[index].t - t0) / (t1 - t0);
      else ratio = points.length === 1 ? 0.5 : index / (points.length - 1);
      return padX + ratio * inner;
    }
    function yAt(value) {
      return padY + (1 - (value - min) / span) * usable;
    }

    ctx.beginPath();
    ctx.moveTo(xAt(0), yAt(points[0].v));
    for (i = 1; i < points.length; i++) ctx.lineTo(xAt(i), yAt(points[i].v));
    ctx.lineWidth = 1.75;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.strokeStyle = "#ffffff";
    ctx.stroke();

    var lastX = xAt(points.length - 1);
    var lastY = yAt(points[points.length - 1].v);
    ctx.beginPath();
    ctx.arc(lastX, lastY, 3, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    return true;
  }

  global.DeskChart = { render: render };
})(window);
