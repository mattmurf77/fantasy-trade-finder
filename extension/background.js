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

  // Popup emits these; rebroadcast to tabs
  if (msg.type === 'ftf:signed_in'
      || msg.type === 'ftf:signed_out'
      || msg.type === 'ftf:rankings_updated') {
    broadcast(msg);
    return false;
  }

  return false;
});
