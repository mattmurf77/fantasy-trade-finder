// Fantasy Trade Finder — popup.js
// Single-step auth: username → token. League picker is gone — the
// content script auto-detects which league the user is viewing on
// sleeper.com and fetches rankings for that league on demand.

const API_BASE = 'https://fantasy-trade-finder.onrender.com';
// For local development, uncomment the next line and comment the one above:
// const API_BASE = 'http://127.0.0.1:5000';

const STORAGE_KEY = 'ftf_session';

const els = {
  stages: {
    signin:    document.getElementById('stage-signin'),
    connected: document.getElementById('stage-connected'),
    busy:      document.getElementById('stage-busy'),
  },
  username:      document.getElementById('username-input'),
  errSignin:     document.getElementById('err-signin'),
  busyMsg:       document.getElementById('busy-msg'),
  connUser:      document.getElementById('conn-username'),
  connLeagues:   document.getElementById('conn-leagues'),
  connCurLeague: document.getElementById('conn-current-league'),
  connFmt:       document.getElementById('conn-format'),
  connCount:     document.getElementById('conn-count'),
};

function show(stageName, busyMsg) {
  for (const [k, el] of Object.entries(els.stages)) {
    el.classList.toggle('hidden', k !== stageName);
  }
  if (stageName === 'busy' && busyMsg) els.busyMsg.textContent = busyMsg;
}

function setError(msg) {
  els.errSignin.textContent = msg || '';
}

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

function fmtLabel(fmt) {
  return fmt === 'sf_tep' ? 'SF TEP' : fmt === '1qb_ppr' ? '1QB PPR' : fmt || '—';
}

// ─────────────────────────────────────────────────────────────────
//  API calls
// ─────────────────────────────────────────────────────────────────

async function apiSignIn(username) {
  const res = await fetch(`${API_BASE}/api/extension/auth`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.message || body.error || `HTTP ${res.status}`);
  return body;  // { session_token, expires_at, user_id, username, display_name, avatar, leagues }
}

async function apiRankings(token, leagueId) {
  const qs = leagueId ? `?league_id=${encodeURIComponent(leagueId)}` : '';
  const res = await fetch(`${API_BASE}/api/extension/rankings${qs}`, {
    headers: { 'X-Session-Token': token },
  });
  if (res.status === 401) throw new Error('session_expired');
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.message || body.error || `HTTP ${res.status}`);
  return body;
}

// ─────────────────────────────────────────────────────────────────
//  Tab inspection — find the active sleeper.com tab + extract league_id
// ─────────────────────────────────────────────────────────────────

async function getActiveSleeperLeague() {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tab = tabs && tabs[0];
      if (!tab || !tab.url) return resolve(null);
      const m = tab.url.match(/(?:sleeper\.com|sleeper\.app)\/leagues\/(\d+)/);
      resolve(m ? m[1] : null);
    });
  });
}

// ─────────────────────────────────────────────────────────────────
//  UI handlers
// ─────────────────────────────────────────────────────────────────

document.getElementById('btn-signin').addEventListener('click', async () => {
  setError('');
  const username = (els.username.value || '').trim().toLowerCase();
  if (!username) { setError('Enter your Sleeper username.'); return; }
  show('busy', 'Signing in…');
  try {
    const auth = await apiSignIn(username);
    const sess = {
      token:         auth.session_token,
      username:      auth.username,
      display_name:  auth.display_name,
      user_id:       auth.user_id,
      avatar:        auth.avatar,
      expires_at:    auth.expires_at,
      leagues:       auth.leagues || [],
      // Cache rankings per league so we don't refetch on every popup open
      rankings_cache: {},
    };
    await setSession(sess);
    try { chrome.runtime.sendMessage({ type: 'ftf:signed_in', sess }); } catch (_) {}
    await renderConnectedFromActiveTab(sess);
    show('connected');
  } catch (e) {
    setError(e.message || 'Sign-in failed.');
    show('signin');
  }
});

els.username.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') document.getElementById('btn-signin').click();
});

document.getElementById('btn-signout').addEventListener('click', async () => {
  await clearSession();
  try { chrome.runtime.sendMessage({ type: 'ftf:signed_out' }); } catch (_) {}
  els.username.value = '';
  show('signin');
});

document.getElementById('btn-refresh').addEventListener('click', async () => {
  show('busy', 'Refreshing rankings…');
  const sess = await getSession();
  if (!sess) { show('signin'); return; }
  const leagueId = await getActiveSleeperLeague();
  try {
    const data = await apiRankings(sess.token, leagueId);
    sess.rankings_cache = sess.rankings_cache || {};
    if (leagueId) {
      sess.rankings_cache[leagueId] = { ...data, fetched_at: Date.now() };
    }
    await setSession(sess);
    try { chrome.runtime.sendMessage({ type: 'ftf:rankings_updated', leagueId }); } catch (_) {}
    await renderConnectedFromActiveTab(sess);
    show('connected');
  } catch (e) {
    if (String(e.message) === 'session_expired') {
      await clearSession();
      show('signin');
    } else {
      await renderConnectedFromActiveTab(sess);
      show('connected');
    }
  }
});

async function renderConnectedFromActiveTab(sess) {
  els.connUser.textContent    = '@' + (sess.username || '—');
  els.connLeagues.textContent = (sess.leagues && sess.leagues.length) ? `${sess.leagues.length}` : '—';

  const leagueId = await getActiveSleeperLeague();
  if (!leagueId) {
    els.connCurLeague.textContent = 'Open a league on sleeper.com';
    els.connFmt.textContent = '—';
    els.connCount.textContent = '—';
    return;
  }

  // Try to find a cached entry for this league
  const cached = (sess.rankings_cache && sess.rankings_cache[leagueId]) || null;
  if (cached) {
    const leagueName = cached.league_name || findLeagueName(sess, leagueId) || leagueId;
    els.connCurLeague.textContent = leagueName;
    els.connFmt.textContent = fmtLabel(cached.format);
    els.connCount.textContent = cached.players ? `${Object.keys(cached.players).length}` : '0';
    return;
  }

  // Not cached yet — fetch fresh so the popup shows accurate numbers
  try {
    const data = await apiRankings(sess.token, leagueId);
    sess.rankings_cache = sess.rankings_cache || {};
    sess.rankings_cache[leagueId] = { ...data, fetched_at: Date.now() };
    await setSession(sess);
    try { chrome.runtime.sendMessage({ type: 'ftf:rankings_updated', leagueId }); } catch (_) {}
    const leagueName = data.league_name || findLeagueName(sess, leagueId) || leagueId;
    els.connCurLeague.textContent = leagueName;
    els.connFmt.textContent = fmtLabel(data.format);
    els.connCount.textContent = data.players ? `${Object.keys(data.players).length}` : '0';
  } catch (_) {
    els.connCurLeague.textContent = findLeagueName(sess, leagueId) || leagueId;
    els.connFmt.textContent = '—';
    els.connCount.textContent = '—';
  }
}

function findLeagueName(sess, leagueId) {
  if (!sess.leagues) return null;
  const lg = sess.leagues.find((l) => String(l.league_id) === String(leagueId));
  return lg ? lg.name : null;
}

// ─────────────────────────────────────────────────────────────────
//  Init
// ─────────────────────────────────────────────────────────────────

(async function init() {
  const sess = await getSession();
  if (sess && sess.token) {
    show('busy', 'Loading your rankings…');
    await renderConnectedFromActiveTab(sess);
    show('connected');
  } else {
    show('signin');
    els.username.focus();
  }
})();
