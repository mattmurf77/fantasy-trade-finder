// Fantasy Trade Finder — background.js (MV3 service worker)
//
// Two jobs:
//   1) Handle `ftf:fetch_rankings` requests from content scripts. Called
//      whenever a content script sees a new league_id on sleeper.com; we
//      fetch /api/extension/rankings?league_id=X with the stored token
//      and cache the result into sess.rankings_cache[league_id].
//   2) Periodic refresh (15 min alarm) of the ACTIVE sleeper.com tab's
//      current league, so content scripts show fresh rankings without
//      requiring a manual refresh.

const API_BASE = 'https://fantasy-trade-finder.onrender.com';
// For local dev: const API_BASE = 'http://127.0.0.1:5000';

const STORAGE_KEY = 'ftf_session';
const REFRESH_ALARM = 'ftf:refresh';
const REFRESH_PERIOD_MIN = 15;

// ─────────────────────────────────────────────────────────────────

async function getSession() {
  return new Promise((resolve) => {
    chrome.storage.local.get([STORAGE_KEY], (res) => resolve(res[STORAGE_KEY] || null));
  });
}

async function setSession(sess) {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [STORAGE_KEY]: sess }, resolve);
  });
}

async function clearSession() {
  return new Promise((resolve) => {
    chrome.storage.local.remove(STORAGE_KEY, resolve);
  });
}

async function fetchRankings(token, leagueId) {
  const qs = leagueId ? `?league_id=${encodeURIComponent(leagueId)}` : '';
  const res = await fetch(`${API_BASE}/api/extension/rankings${qs}`, {
    headers: { 'X-Session-Token': token },
  });
  if (res.status === 401) return { expired: true };
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return { data: await res.json() };
}

// Fetch + cache rankings for a given league_id. Returns a message-response
// shape so the content script's sendMessage resolves cleanly.
async function fetchAndCache(leagueId) {
  const sess = await getSession();
  if (!sess || !sess.token) return { ok: false, error: 'no_session' };
  try {
    const result = await fetchRankings(sess.token, leagueId);
    if (result.expired) {
      await clearSession();
      broadcast({ type: 'ftf:session_expired' });
      return { ok: false, expired: true };
    }
    const data = result.data;
    sess.rankings_cache = sess.rankings_cache || {};
    if (leagueId) {
      sess.rankings_cache[leagueId] = { ...data, fetched_at: Date.now() };
      await setSession(sess);
    }
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: String(e && e.message) };
  }
}

function broadcast(message) {
  chrome.tabs.query({ url: ['https://sleeper.com/*', 'https://sleeper.app/*'] }, (tabs) => {
    for (const tab of tabs) {
      if (tab.id != null) chrome.tabs.sendMessage(tab.id, message, () => void chrome.runtime.lastError);
    }
  });
}

// Find the currently-active sleeper.com tab's league and refresh it.
async function refreshActiveTab() {
  return new Promise((resolve) => {
    chrome.tabs.query({
      active: true,
      url: ['https://sleeper.com/*', 'https://sleeper.app/*'],
    }, async (tabs) => {
      const tab = tabs && tabs[0];
      if (!tab || !tab.url) return resolve();
      const m = tab.url.match(/\/leagues\/(\d+)/);
      if (!m) return resolve();
      const leagueId = m[1];
      await fetchAndCache(leagueId);
      broadcast({ type: 'ftf:rankings_updated', leagueId });
      resolve();
    });
  });
}

// ─────────────────────────────────────────────────────────────────
//  Alarms
// ─────────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(REFRESH_ALARM, { periodInMinutes: REFRESH_PERIOD_MIN });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === REFRESH_ALARM) refreshActiveTab();
});

// ─────────────────────────────────────────────────────────────────
//  Analytics emitter (analytics platform P4) — first-party events to
//  /api/events with the shared cross-client envelope. Fire-and-forget,
//  gated on analytics.client_events (fetched once, default-dark). Only the
//  taxonomy-legal client events (app_opened, signin_succeeded); richer
//  extension events need a tracking-plan addendum first.
// ─────────────────────────────────────────────────────────────────

const DEVICE_ID_KEY = 'ftf_device_id';
let _flagCache = { at: 0, on: false };   // client_events, cached 5 min, default-dark

function _uuid() {
  try { if (crypto && crypto.randomUUID) return crypto.randomUUID(); } catch (_) {}
  return 'loc-' + Date.now().toString(36) + '-' + Math.floor(Math.random() * 1e9).toString(36);
}

async function _deviceId() {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.get([DEVICE_ID_KEY], (res) => {
        let d = res[DEVICE_ID_KEY];
        if (d) return resolve(d);
        d = 'dev_' + _uuid();
        chrome.storage.local.set({ [DEVICE_ID_KEY]: d }, () => resolve(d));
      });
    } catch (_) { resolve('dev_ephemeral'); }
  });
}

async function _clientEventsOn() {
  if (Date.now() - _flagCache.at < 300000) return _flagCache.on;
  try {
    const res = await fetch(`${API_BASE}/api/feature-flags`);
    const body = await res.json();
    _flagCache = { at: Date.now(), on: !!(body.flags && body.flags['analytics.client_events']) };
  } catch (_) { _flagCache = { at: Date.now(), on: false }; }   // default-dark
  return _flagCache.on;
}

let _extSeq = 0;
const _extSession = 'ext-' + _uuid();

async function emitAnalyticsEvent(eventType, props) {
  try {
    if (!(await _clientEventsOn())) return;
    const sess = await getSession();
    const deviceId = await _deviceId();
    _extSeq += 1;
    const headers = { 'Content-Type': 'application/json', 'X-Device-Id': deviceId, 'X-Source': 'extension' };
    if (sess && sess.token) headers['X-Session-Token'] = sess.token;
    await fetch(`${API_BASE}/api/events`, {
      method: 'POST', headers,
      body: JSON.stringify({ events: [{
        event_id: _uuid(), event_type: eventType, client_ts: new Date().toISOString(),
        session_id: _extSession, seq: _extSeq, props: props || null }] }),
    });
  } catch (_) { /* analytics must never break the extension */ }
}

// ─────────────────────────────────────────────────────────────────
//  Message hub
// ─────────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.type) return false;

  if (msg.type === 'ftf:get_session') {
    getSession().then((sess) => sendResponse(sess));
    return true;
  }

  if (msg.type === 'ftf:fetch_rankings') {
    // Content script asking for rankings for a specific league_id
    fetchAndCache(msg.league_id).then(sendResponse);
    return true;  // async
  }

  if (msg.type === 'ftf:force_refresh') {
    refreshActiveTab().then(() => sendResponse({ ok: true }));
    return true;
  }

  // Popup opened — extension DAU signal (taxonomy-legal app_opened).
  if (msg.type === 'ftf:popup_opened') {
    emitAnalyticsEvent('app_opened', { launch_type: 'extension' });
    return false;
  }

  // Popup emits these; rebroadcast to tabs
  if (msg.type === 'ftf:signed_in'
      || msg.type === 'ftf:signed_out'
      || msg.type === 'ftf:rankings_updated') {
    if (msg.type === 'ftf:signed_in') emitAnalyticsEvent('signin_succeeded', { method: 'sleeper' });
    broadcast(msg);
    return false;
  }

  return false;
});
