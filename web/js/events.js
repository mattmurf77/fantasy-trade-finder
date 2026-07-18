// events.js — first-party analytics SDK for the web app (analytics platform P4;
// mirrors mobile/src/api/events.ts and the cross-client envelope contract in
// docs/cross-client-invariants.md). Closes the source:"api" blindness — until
// now all web usage landed as anonymous server-inferred rows.
//
// Fire-and-forget by contract: analytics must NEVER block or break the app, so
// every path swallows its own errors. Exposes one global: FTFTrack(type, props,
// screen). Hard-gated on the analytics.client_events flag (window.FTF_FLAG).
(function () {
  "use strict";

  var FLAG_KEY = "analytics.client_events";
  var QUEUE_KEY = "ftf.events.queue.v1";     // {v:1, events:[…]} — shared shape
  var DEVICE_KEY = "ftf.deviceId";
  var TOKEN_KEY = "fumble_session_token";     // app.js's localStorage session key
  var QUEUE_SHAPE_V = 1;
  var MAX_QUEUE = 500, BATCH_MAX = 50, FLUSH_AT = 20;
  var FLUSH_MS = 10000, SESSION_IDLE_MS = 30 * 60000, SEND_TIMEOUT_MS = 10000;
  var FUNNEL_CRITICAL = { app_opened: 1, signin_attempted: 1, signin_succeeded: 1, experiment_exposed: 1 };
  var BACKOFF = [30000, 120000, 600000];

  var queue = [];
  var sessionId = uuid();
  var seq = 0;
  var lastActivity = Date.now();
  var inFlight = false;
  var backoffIdx = -1, nextFlushAt = 0;

  function uuid() {
    try {
      if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
      if (window.crypto && window.crypto.getRandomValues) {
        var b = new Uint8Array(16); window.crypto.getRandomValues(b);
        b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
        var h = ""; for (var i = 0; i < 16; i++) h += (b[i] + 0x100).toString(16).slice(1);
        return h.slice(0, 8) + "-" + h.slice(8, 12) + "-" + h.slice(12, 16) + "-" + h.slice(16, 20) + "-" + h.slice(20);
      }
    } catch (e) { /* fall through */ }
    // Timestamp+counter fallback (best-effort; never Math.random for an id key).
    seq = (seq + 1) % 1e6;
    return "loc-" + Date.now().toString(36) + "-" + seq.toString(36);
  }

  function flagOn() {
    try { return !!(window.FTF_FLAG && window.FTF_FLAG(FLAG_KEY)); } catch (e) { return false; }
  }

  function deviceId() {
    try {
      var d = localStorage.getItem(DEVICE_KEY);
      if (d) return d;
      d = "dev_" + uuid();
      localStorage.setItem(DEVICE_KEY, d);
      return d;
    } catch (e) { return "dev_ephemeral"; }
  }

  function loadQueue() {
    try {
      var raw = localStorage.getItem(QUEUE_KEY);
      if (!raw) return;
      var parsed = JSON.parse(raw);
      // Only the versioned shape restores; anything else (a stale array,
      // corruption) is discarded — never crash on a bad queue.
      if (parsed && parsed.v === QUEUE_SHAPE_V && Array.isArray(parsed.events)) {
        queue = parsed.events.concat(queue);
        trim();
      } else {
        localStorage.removeItem(QUEUE_KEY);
      }
    } catch (e) { try { localStorage.removeItem(QUEUE_KEY); } catch (_) {} }
  }

  function persist() {
    try { localStorage.setItem(QUEUE_KEY, JSON.stringify({ v: QUEUE_SHAPE_V, events: queue })); } catch (e) {}
  }

  function trim() {
    if (queue.length <= MAX_QUEUE) return;
    var over = queue.length - MAX_QUEUE, kept = [];
    for (var i = 0; i < queue.length; i++) {
      if (over > 0 && !FUNNEL_CRITICAL[queue[i].event_type]) { over--; continue; }
      kept.push(queue[i]);
    }
    queue = over > 0 ? kept.slice(over) : kept;
  }

  // --- public API ---
  function track(eventType, props, screen) {
    try {
      if (!flagOn()) return;
      var now = Date.now();
      if (now - lastActivity > SESSION_IDLE_MS) { sessionId = uuid(); seq = 0; }
      lastActivity = now;
      seq += 1;
      var e = { event_id: uuid(), event_type: eventType, client_ts: new Date(now).toISOString(),
                session_id: sessionId, seq: seq };
      if (screen) e.screen = screen;
      if (props) e.props = props;
      queue.push(e); trim(); persist();
      if (queue.length >= FLUSH_AT) flush();
    } catch (err) { /* analytics must never break the app */ }
  }

  function resetBackoff() { backoffIdx = -1; nextFlushAt = 0; }
  function applyBackoff(toMax) {
    backoffIdx = toMax ? BACKOFF.length - 1 : Math.min(backoffIdx + 1, BACKOFF.length - 1);
    var base = BACKOFF[backoffIdx];
    nextFlushAt = Date.now() + base + base * 0.2 * (Math.random() * 2 - 1);
  }

  function flush() {
    if (inFlight || Date.now() < nextFlushAt || !flagOn() || !queue.length) return;
    inFlight = true;
    var batch = queue.slice(0, BATCH_MAX);
    var headers = { "Content-Type": "application/json", "X-Device-Id": deviceId() };
    try { var tok = localStorage.getItem(TOKEN_KEY); if (tok) headers["X-Session-Token"] = tok; } catch (e) {}
    var ctrl = ("AbortController" in window) ? new AbortController() : null;
    var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, SEND_TIMEOUT_MS) : null;
    fetch("/api/events", { method: "POST", headers: headers,
        body: JSON.stringify({ events: batch }), signal: ctrl ? ctrl.signal : undefined,
        keepalive: true })
      .then(function (res) {
        if (timer) clearTimeout(timer);
        if (res.status >= 500) { applyBackoff(false); inFlight = false; return; }
        if (!res.ok) { consume(batch, true, []); resetBackoff(); inFlight = false; drain(); return; }
        return res.json().then(function (body) {
          if (body && body.disposition === "disabled") { applyBackoff(true); inFlight = false; return; }
          if (body && typeof body.disposition === "string" && body.disposition.indexOf("batch_rejected") === 0) {
            consume(batch, true, []); resetBackoff(); inFlight = false; drain(); return;
          }
          var acc = (body && body.accepted) || 0, ded = (body && body.deduped) || 0;
          var rej = (body && body.rejected) || [];
          var sum = acc + ded + rej.length;
          consume(batch, sum >= batch.length, rej.map(function (r) { return r.index; }));
          resetBackoff(); inFlight = false; drain();
        });
      })
      .catch(function () { if (timer) clearTimeout(timer); applyBackoff(false); inFlight = false; });
  }

  function consume(batch, purgeAll, rejectedIdx) {
    if (purgeAll) { queue.splice(0, batch.length); }
    else {
      var rej = {}; rejectedIdx.forEach(function (i) { rej[i] = 1; });
      var survivors = []; for (var i = 0; i < batch.length; i++) if (!rej[i]) survivors.push(batch[i]);
      Array.prototype.splice.apply(queue, [0, batch.length].concat(survivors));
    }
    persist();
  }
  function drain() { if (queue.length && flagOn()) flush(); }

  // Best-effort flush on page hide (sendBeacon survives unload).
  function flushOnHide() {
    try {
      if (!flagOn() || !queue.length || !navigator.sendBeacon) return;
      var batch = queue.slice(0, BATCH_MAX);
      var ok = navigator.sendBeacon("/api/events",
        new Blob([JSON.stringify({ events: batch, device_id: deviceId() })], { type: "application/json" }));
      if (ok) { queue.splice(0, batch.length); persist(); }
    } catch (e) {}
  }

  window.FTFTrack = track;
  try {
    loadQueue();
    setInterval(flush, FLUSH_MS);
    document.addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") flushOnHide(); });
    window.addEventListener("pagehide", flushOnHide);
  } catch (e) { /* SDK init best-effort */ }
})();
