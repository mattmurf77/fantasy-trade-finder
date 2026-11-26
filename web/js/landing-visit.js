// landing-visit.js — one anonymous visit count per landing page load (D-285).
//
// The landing has been marketing-only since the 2026-11-25 launch cut (D-284),
// which also stopped it loading events.js, and with it the visit event. This
// sends that same event again, `app_opened` {launch_type: "web"}, and nothing
// else. It is deliberately NOT events.js: no queue, no replay of stored
// events, no session token, no invite capture.
//
// Anonymous by construction: every id below is fresh random per page load and
// is never stored. The page reads and writes no localStorage, sessionStorage
// or cookie, so a visit cannot be tied to an earlier visit, or to the
// `ftf.deviceId` an old signed-in web session left behind (that id sits next
// to account ids in user_events.device_id). The server requires SOME device
// id (otherwise `no_identity`), so it gets a throwaway one.
//
// Gated on `analytics.client_events`, the client emission gate. Fails
// silently: a blocked or failed request never touches the page.
(function () {
  "use strict";
  try {
    var c = window.crypto;
    if (!window.fetch || !c || !c.randomUUID) return;
    fetch("/api/feature-flags", { cache: "no-store", credentials: "omit" })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (body) {
        if (!body || !body.flags || body.flags["analytics.client_events"] !== true) return;
        return fetch("/api/events", {
          method: "POST", credentials: "omit", keepalive: true,
          headers: { "Content-Type": "application/json",
                     "X-Device-Id": "visit_" + c.randomUUID(), "X-Source": "web" },
          body: JSON.stringify({ platform: "web", source: "web", events: [{
            event_id: c.randomUUID(), event_type: "app_opened",
            client_ts: new Date().toISOString(), session_id: c.randomUUID(), seq: 1,
            props: { launch_type: "web" } }] })
        });
      })
      .catch(function () { /* a visit count must never affect the page */ });
  } catch (e) { /* same */ }
})();
