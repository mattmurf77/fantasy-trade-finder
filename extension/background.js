// Fantasy Trade Finder — background.js (MV3 service worker)
// Two jobs:
//   1) Keep the rankings cache fresh (alarm every 15 min).
//   2) Act as a message hub — content scripts ask for the latest cached
//      rankings without hitting storage-get 1,000 times.

const API_BASE = 'https://fantasy-trade-finder.onrender.com';
// For local dev:
// const API_BASE = 'http://127.0.0.1:5000';

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

async function fetchRankings(token) {
  const res = await fetch(`${API_BASE}/api/extension/rankings`, {
    headers: { 'X-Session-Token': token },
  });
  if (res.status === 401) {
    return { expired: true };
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return { data: await res.json() };
}

async function refreshRankings() {
  const sess = await getSession();
  if (!sess || !sess.token) return;
  try {
    const result = await fetchRankings(sess.token);
    if (result.expired) {
      await clearSession();
      broadcast({ type: 'ftf:session_expired' });
      return;
    }
    sess.cached_rankings = result.data;
    sess.cached_at = Date.now();
    await setSession(sess);
    broadcast({ type: 'ftf:rankings_updated' });
  } catch (e) {
    // Silent — transient network errors are common on service workers
  }
}

function broadcast(message) {
  // Send to every sleeper.com tab; content scripts listen for the type.
  chrome.tabs.query({ url: ['https://sleeper.com/*', 'https://sleeper.app/*'] }, (tabs) => {
    for (const tab of tabs) {
      if (tab.id != null) chrome.tabs.sendMessage(tab.id, message, () => void chrome.runtime.lastError);
    }
  });
}

// ─────────────────────────────────────────────────────────────────
//  Alarms
// ─────────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(REFRESH_ALARM, { periodInMinutes: REFRESH_PERIOD_MIN });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === REFRESH_ALARM) refreshRankings();
});

// ─────────────────────────────────────────────────────────────────
//  Message hub
// ─────────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.type) return false;

  if (msg.type === 'ftf:get_session') {
    getSession().then((sess) => sendResponse(sess));
    return true;  // async response
  }

  if (msg.type === 'ftf:force_refresh') {
    refreshRankings().then(() => sendResponse({ ok: true }));
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
