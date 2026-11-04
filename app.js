(function () {
  "use strict";

  var DATA_PATH_KEY = "DATA_PATH";
  var TAB_KEY = "desk.tab";
  var POLL_MS = 15000;
  var TABS = ["home", "agents", "activity", "account"];

  var model = {
    tab: "home",
    banner: "",
    book: null,
    chart: null,
    activity: null,
    refreshedAt: 0,
    busy: false
  };

  var deferredInstall = null;
  var pollTimer = 0;

  function $(id) { return document.getElementById(id); }

  function isSafePath(value) {
    if (typeof value !== "string") return false;
    if (value.length < 1 || value.length > 160) return false;
    var parts = value.split("/");
    for (var i = 0; i < parts.length; i++) {
      if (parts[i] === "" || parts[i] === "." || parts[i] === "..") return false;
    }
    return /^[A-Za-z0-9._~-]+(?:\/[A-Za-z0-9._~-]+)*$/.test(value);
  }

  function readPath() {
    var raw = "";
    try { raw = localStorage.getItem(DATA_PATH_KEY) || ""; } catch (e) { return ""; }
    if (!isSafePath(raw)) {
      try { localStorage.removeItem(DATA_PATH_KEY); } catch (e2) {}
      return "";
    }
    return raw;
  }

  function captureFragment() {
    var hash = location.hash || "";
    if (hash.slice(0, 3) !== "#d=") return;
    var decoded = "";
    try { decoded = decodeURIComponent(hash.slice(3)); } catch (e) { decoded = ""; }
    decoded = decoded.replace(/^\/+|\/+$/g, "");
    if (isSafePath(decoded)) {
      try { localStorage.setItem(DATA_PATH_KEY, decoded); } catch (e2) {}
    }
    try {
      history.replaceState(null, "", location.pathname + location.search);
    } catch (e3) {}
  }

  function dataUrl(file) {
    var path = readPath();
    if (!path) return "";
    return "d/" + path.split("/").map(encodeURIComponent).join("/") + "/" + file;
  }

  function num(value) {
    if (value == null || value === "") return null;
    var n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function pick(obj, keys) {
    if (!obj || typeof obj !== "object") return undefined;
    for (var i = 0; i < keys.length; i++) {
      if (obj[keys[i]] != null && obj[keys[i]] !== "") return obj[keys[i]];
    }
    return undefined;
  }

  function money(value) {
    var n = num(value);
    if (n == null) return "—";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 2
    }).format(n);
  }

  function signedMoney(value) {
    var n = num(value);
    if (n == null) return "";
    var body = money(Math.abs(n));
    if (n > 0) return "+" + body;
    if (n < 0) return "−" + body;
    return body;
  }

  function signedPct(value) {
    var n = num(value);
    if (n == null) return "";
    var body = Math.abs(n).toFixed(2) + "%";
    if (n > 0) return "+" + body;
    if (n < 0) return "−" + body;
    return body;
  }

  function tone(value) {
    var n = num(value);
    if (n == null || n === 0) return "";
    return n > 0 ? "up" : "down";
  }

  function formatTime(value) {
    if (value == null || value === "") return "";
    var ms = num(value);
    var date = ms == null ? new Date(value) : new Date(ms < 1e12 ? ms * 1000 : ms);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit"
    }).format(date);
  }

  function textAmount(value) {
    if (value == null || value === "") return "";
    if (typeof value === "number") return signedMoney(value);
    if (typeof value === "string" && /^-?\d+(\.\d+)?$/.test(value.trim())) return signedMoney(value);
    return String(value);
  }

  function emptyNode(title, detail) {
    var wrap = document.createElement("div");
    wrap.className = "empty";
    var strong = document.createElement("strong");
    strong.textContent = title;
    var span = document.createElement("span");
    span.textContent = detail;
    wrap.appendChild(strong);
    wrap.appendChild(span);
    return wrap;
  }

  function itemNode(spec) {
    var row = document.createElement("div");
    row.className = "item";
    var a = document.createElement("div");
    a.className = "primary";
    a.textContent = spec.primary || "—";
    var b = document.createElement("div");
    b.className = "value" + (spec.valueTone ? " " + spec.valueTone : "");
    b.textContent = spec.value || "";
    var c = document.createElement("div");
    c.className = "secondary";
    c.textContent = spec.secondary || "";
    var d = document.createElement("div");
    d.className = "aside" + (spec.asideTone ? " " + spec.asideTone : "");
    d.textContent = spec.aside || "";
    row.appendChild(a);
    row.appendChild(b);
    row.appendChild(c);
    row.appendChild(d);
    return row;
  }

  function fill(el, nodes) {
    el.replaceChildren.apply(el, nodes);
  }

  function renderPositions() {
    var host = $("positions");
    var rows = model.book && Array.isArray(model.book.positions) ? model.book.positions : [];
    if (!rows.length) {
      var linked = !!readPath();
      fill(host, [emptyNode(
        "No positions",
        linked ? "The book is empty." : "Link this browser to show the book."
      )]);
      return;
    }
    fill(host, rows.map(function (row) {
      var symbol = pick(row, ["symbol", "ticker", "name"]) || "—";
      var qty = num(pick(row, ["qty", "quantity", "shares"]));
      var price = pick(row, ["price", "last", "mark"]);
      var qtyLabel = qty == null ? "" : (qty === 1 ? "1 share" : String(qty) + " shares");
      var priceLabel = num(price) == null ? "" : money(price);
      var secondary = [qtyLabel, priceLabel].filter(Boolean).join(" · ");
      var pnl = pick(row, ["pnl", "dayPnl", "uPnl"]);
      var market = money(pick(row, ["value", "marketValue"]));
      var pnlText = signedMoney(pnl);
      if (market === "—") {
        return itemNode({ primary: String(symbol), secondary: secondary, value: pnlText, valueTone: tone(pnl) });
      }
      return itemNode({
        primary: String(symbol),
        secondary: secondary,
        value: market,
        aside: pnlText,
        asideTone: tone(pnl)
      });
    }));
  }

  function renderAgents() {
    var host = $("agents");
    var rows = model.book && Array.isArray(model.book.agents) ? model.book.agents : [];
    if (!rows.length) {
      fill(host, [emptyNode("No agents", "Agents show up here when the desk publishes them.")]);
      return;
    }
    fill(host, rows.map(function (row) {
      var name = pick(row, ["name", "id"]) || "Agent";
      var status = pick(row, ["status", "state"]);
      var detail = pick(row, ["detail", "note", "strategy"]);
      if (status) status = String(status).charAt(0).toUpperCase() + String(status).slice(1);
      var secondary = [status || "", detail ? String(detail) : ""].filter(Boolean).join(" · ");
      var pnl = pick(row, ["pnl", "dayPnl"]);
      return itemNode({
        primary: String(name),
        secondary: secondary,
        value: signedMoney(pnl),
        valueTone: tone(pnl)
      });
    }));
  }

  function renderActivity() {
    var host = $("activity");
    var rows = [];
    if (model.activity && Array.isArray(model.activity.items)) rows = model.activity.items;
    else if (Array.isArray(model.activity)) rows = model.activity;
    if (!rows.length) {
      fill(host, [emptyNode("No activity", "Fills and notes show up here.")]);
      return;
    }
    fill(host, rows.map(function (row) {
      if (typeof row === "string") return itemNode({ primary: row });
      var title = pick(row, ["title", "text", "message"]) || "Update";
      var detail = pick(row, ["detail", "body", "note"]) || "";
      var when = formatTime(pick(row, ["time", "t", "at"]));
      var amountRaw = pick(row, ["amount", "pnl", "value"]);
      return itemNode({
        primary: String(title),
        secondary: String(detail),
        value: textAmount(amountRaw),
        aside: when,
        valueTone: tone(amountRaw)
      });
    }));
  }

  function renderHero() {
    var book = model.book || {};
    $("hero-value").textContent = money(pick(book, ["equity", "nav", "value", "portfolio"]));
    var pnl = pick(book, ["dayPnl", "pnl", "day_pnl"]);
    var pct = pick(book, ["dayPnlPct", "pnlPct", "day_pnl_pct"]);
    var change = $("hero-change");
    var parts = [];
    if (num(pnl) != null) parts.push(signedMoney(pnl));
    if (num(pct) != null) parts.push("(" + signedPct(pct) + ")");
    if (!readPath()) {
      change.textContent = "Not linked";
      change.className = "change";
      return;
    }
    if (!parts.length) {
      change.textContent = model.book ? "Today —" : "—";
      change.className = "change";
      return;
    }
    parts.push("today");
    change.textContent = parts.join(" ");
    change.className = "change" + (tone(pnl) ? " " + tone(pnl) : "");
  }

  function renderChart() {
    var canvas = $("chart");
    var wrap = canvas.parentNode;
    var drew = false;
    if (window.DeskChart && model.chart) drew = window.DeskChart.render(canvas, model.chart);
    if (!drew) {
      canvas.width = 0;
      canvas.height = 0;
      wrap.classList.remove("has-line");
    } else {
      wrap.classList.add("has-line");
    }
  }

  function renderAccount() {
    var linked = !!readPath();
    $("account-link").textContent = linked ? "On this device" : "Not linked";
    var cash = model.book ? pick(model.book, ["cash", "buyingPower"]) : null;
    $("account-cash").textContent = money(cash);
    $("account-refresh").textContent = model.refreshedAt ? formatTime(model.refreshedAt) : "—";
    var standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
    $("account-display").textContent = standalone ? "Installed" : "Browser";
    $("account-forget").hidden = !linked;
    $("account-install").hidden = standalone || !deferredInstall;
  }

  function renderBanner() {
    var banner = $("banner");
    if (!model.banner) {
      banner.hidden = true;
      banner.textContent = "";
      return;
    }
    banner.hidden = false;
    banner.textContent = model.banner;
  }

  function render() {
    renderBanner();
    renderHero();
    renderChart();
    renderPositions();
    renderAgents();
    renderActivity();
    renderAccount();
  }

  function showTab(name) {
    if (TABS.indexOf(name) === -1) name = "home";
    model.tab = name;
    try { sessionStorage.setItem(TAB_KEY, name); } catch (e) {}
    TABS.forEach(function (tab) {
      var on = tab === name;
      $("view-" + tab).hidden = !on;
      var button = $("tab-" + tab);
      button.setAttribute("aria-selected", on ? "true" : "false");
      button.tabIndex = on ? 0 : -1;
    });
    if (name === "home") renderChart();
  }

  function fetchJson(url) {
    var signal = (typeof AbortSignal !== "undefined" && AbortSignal.timeout)
      ? AbortSignal.timeout(12000)
      : undefined;
    return fetch(url, {
      cache: "no-store",
      credentials: "omit",
      redirect: "manual",
      signal: signal
    }).then(function (res) {
      var cached = res.headers.get("X-Desk-From-Cache") === "1";
      if (res.type === "opaqueredirect" || !res.ok) {
        return { ok: false, status: res.status || 0, data: null, cached: false };
      }
      return res.json().then(function (data) {
        return { ok: true, status: res.status, data: data, cached: cached };
      }).catch(function () {
        return { ok: false, status: res.status, data: null, cached: false };
      });
    }).catch(function () {
      return { ok: false, status: 0, data: null, cached: false };
    });
  }

  function applyFile(result, key) {
    if (result.ok) model[key] = result.data;
    else if (result.status === 404) model[key] = null;
  }

  function bannerFor(results, kept) {
    var failed = results.filter(function (item) { return !item.ok; });
    if (!failed.length) {
      return results.some(function (item) { return item.cached; }) ? "Offline · last update kept" : "";
    }
    var allFailed = failed.length === results.length;
    var offline = failed.every(function (item) {
      return item.status === 0 || item.status === 504;
    });
    var missing = allFailed && failed.every(function (item) { return item.status === 404; });
    var label = offline ? "Offline" : missing && !kept ? "Nothing published yet" : "Couldn't refresh";
    if (offline && kept) return label + " · last update kept";
    if (!missing && kept) return label + " · last update kept";
    return label;
  }

  function poll() {
    var files = [
      dataUrl("state.json"),
      dataUrl("chart.json"),
      dataUrl("activity.json")
    ];
    if (!files[0]) {
      model.banner = "";
      model.book = null;
      model.chart = null;
      model.activity = null;
      model.refreshedAt = 0;
      render();
      return Promise.resolve();
    }
    if (model.busy) return Promise.resolve();
    model.busy = true;
    return Promise.all(files.map(fetchJson)).then(function (results) {
      applyFile(results[0], "book");
      applyFile(results[1], "chart");
      applyFile(results[2], "activity");
      if (results.some(function (item) { return item.ok && !item.cached; })) {
        model.refreshedAt = Date.now();
      }
      var kept = !!(model.book || model.chart || model.activity);
      model.banner = bannerFor(results, kept);
      render();
    }).finally(function () {
      model.busy = false;
    });
  }

  function clearDataCaches() {
    if (!("caches" in window)) return Promise.resolve();
    return caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) {
        return caches.open(key).then(function (cache) {
          return cache.keys().then(function (requests) {
            return Promise.all(requests.map(function (request) {
              var path = "";
              try { path = new URL(request.url).pathname; } catch (e) { return Promise.resolve(); }
              if (path.indexOf("/d/") === -1) return Promise.resolve();
              return cache.delete(request);
            }));
          });
        });
      }));
    }).catch(function () {});
  }

  function forgetLink() {
    try { localStorage.removeItem(DATA_PATH_KEY); } catch (e) {}
    model.book = null;
    model.chart = null;
    model.activity = null;
    model.banner = "";
    model.refreshedAt = 0;
    render();
    clearDataCaches();
  }

  function onTabClick(event) {
    var button = event.currentTarget;
    showTab(button.id.replace("tab-", ""));
  }

  function onTabKey(event) {
    var current = TABS.indexOf(model.tab);
    if (current === -1) return;
    var next = current;
    if (event.key === "ArrowRight") next = (current + 1) % TABS.length;
    else if (event.key === "ArrowLeft") next = (current - 1 + TABS.length) % TABS.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = TABS.length - 1;
    else return;
    event.preventDefault();
    showTab(TABS[next]);
    $("tab-" + TABS[next]).focus();
  }

  function boot() {
    captureFragment();
    var saved = "home";
    try { saved = sessionStorage.getItem(TAB_KEY) || "home"; } catch (e) {}
    showTab(saved);
    TABS.forEach(function (tab) {
      var button = $("tab-" + tab);
      button.addEventListener("click", onTabClick);
      button.addEventListener("keydown", onTabKey);
    });
    $("account-forget").addEventListener("click", forgetLink);
    $("account-install").addEventListener("click", function () {
      if (!deferredInstall) return;
      deferredInstall.prompt();
      deferredInstall.userChoice.finally(function () {
        deferredInstall = null;
        renderAccount();
      });
    });
    window.addEventListener("beforeinstallprompt", function (event) {
      event.preventDefault();
      deferredInstall = event;
      renderAccount();
    });
    window.addEventListener("resize", function () {
      if (model.tab === "home") renderChart();
    });
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) poll();
    });
    window.addEventListener("hashchange", function () {
      captureFragment();
      poll();
    });
    render();
    poll();
    pollTimer = window.setInterval(poll, POLL_MS);
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("sw.js", { scope: "./" }).catch(function () {});
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
