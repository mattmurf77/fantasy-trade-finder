// Fantasy Trade Finder — popup.js
// Three-stage flow: sign-in → pick league → connected.
// All backend calls go through the configured API origin; session token is
// persisted in chrome.storage.local so the content script and background
// service worker can share it.

const API_BASE = 'https://fantasy-trade-finder.onrender.com';
// For local development, uncomment the next line and comment the one above:
// const API_BASE = 'http://127.0.0.1:5000';

const STORAGE_KEY = 'ftf_session';

const els = {
  stages: {
    signin:    document.getElementById('stage-signin'),
    pick:      document.getElementById('stage-pick'),
    connected: document.getElementById('stage-connected'),
    busy:      document.getElementById('stage-busy'),
  },
  username:   document.getElementById('username-input'),
  errSignin:  document.getElementById('err-signin'),
  errPick:    document.getElementById('err-pick'),
  leagues:    document.getElementById('leagues'),
  busyMsg:    document.getElementById('busy-msg'),
  connUser:   document.getElementById('conn-username'),
  connLeague: document.getElementById('conn-league'),
  connFmt:    document.getElementById('conn-format'),
  connCount:  document.getElementById('conn-count'),
};

// Ephemeral state — held only for the current popup lifecycle.
let _pendingUsername = null;
let _pendingUserData = null;

function show(stageName, busyMsg) {
  for (const [k, el] of Object.entries(els.stages)) {
    el.classList.toggle('hidden', k !== stageName);
  }
  if (stageName === 'busy' && busyMsg) els.busyMsg.textContent = busyMsg;
}

function setError(which, msg) {
  if (which === 'signin') els.errSignin.textContent = msg || '';
  if (which === 'pick')   els.errPick.textContent   = msg || '';
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

async function apiLookup(username) {
  const res = await fetch(`${API_BASE}/api/extension/auth`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.message || body.error || `HTTP ${res.status}`);
  return body;  // { stage: 'pick_league', user_id, username, display_name, avatar, leagues: [...] }
}

async function apiConnect(username, leagueId) {
  const res = await fetch(`${API_BASE}/api/extension/auth`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, league_id: leagueId }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.message || body.error || `HTTP ${res.status}`);
  return body;  // { session_token, expires_at, username, display_name, league_id, scoring_format }
}

async function apiRankings(token) {
  const res = await fetch(`${API_BASE}/api/extension/rankings`, {
    headers: { 'X-Session-Token': token },
  });
  if (res.status === 401) throw new Error('session_expired');
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.message || body.error || `HTTP ${res.status}`);
  return body;
}

// ─────────────────────────────────────────────────────────────────
//  UI handlers
// ─────────────────────────────────────────────────────────────────

document.getElementById('btn-lookup').addEventListener('click', async () => {
  setError('signin', '');
  const username = (els.username.value || '').trim().toLowerCase();
  if (!username) { setError('signin', 'Enter your Sleeper username.'); return; }
  show('busy', 'Looking up your leagues…');
  try {
    const body = await apiLookup(username);
    _pendingUsername = username;
    _pendingUserData = body;
    renderLeaguePicker(body.leagues || []);
    show('pick');
  } catch (e) {
    setError('signin', e.message || 'Lookup failed.');
    show('signin');
  }
});

els.username.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') document.getElementById('btn-lookup').click();
});

document.getElementById('btn-back').addEventListener('click', () => {
  setError('pick', '');
  _pendingUsername = null;
  _pendingUserData = null;
  els.username.focus();
  show('signin');
});

document.getElementById('btn-signout').addEventListener('click', async () => {
  await clearSession();
  // Tell content scripts to clear their cached badges
  try { chrome.runtime.sendMessage({ type: 'ftf:signed_out' }); } catch (_) {}
  els.username.value = '';
  _pendingUsername = null;
  _pendingUserData = null;
  show('signin');
});

document.getElementById('btn-refresh').addEventListener('click', async () => {
  show('busy', 'Refreshing rankings…');
  const sess = await getSession();
  if (!sess) { show('signin'); return; }
  try {
    const data = await apiRankings(sess.token);
    sess.cached_rankings = data;
    sess.cached_at = Date.now();
    await setSession(sess);
    try { chrome.runtime.sendMessage({ type: 'ftf:rankings_updated' }); } catch (_) {}
    renderConnected(sess, data);
    show('connected');
  } catch (e) {
    if (String(e.message) === 'session_expired') {
      await clearSession();
      show('signin');
    } else {
      renderConnected(sess, sess.cached_rankings);
      show('connected');
    }
  }
});

function renderLeaguePicker(leagues) {
  els.leagues.innerHTML = '';
  if (!leagues.length) {
    els.leagues.innerHTML = '<div class="note">No 2026 NFL leagues found on your Sleeper account.</div>';
    return;
  }
  for (const lg of leagues) {
    const row = document.createElement('button');
    row.className = 'lg-row';
    row.innerHTML = `
      <div class="lg-ball">🏈</div>
      <div class="lg-body">
        <div class="lg-name"></div>
        <div class="lg-sub">${(lg.total_rosters || 0)} teams</div>
      </div>
      <div class="lg-chev">›</div>
    `;
    row.querySelector('.lg-name').textContent = lg.name || 'League';
    row.addEventListener('click', () => pickLeague(lg.league_id, lg.name));
    els.leagues.appendChild(row);
  }
}

async function pickLeague(leagueId, leagueName) {
  if (!_pendingUsername) { show('signin'); return; }
  setError('pick', '');
  show('busy', 'Connecting to Fantasy Trade Finder…');
  try {
    const auth = await apiConnect(_pendingUsername, leagueId);
    const sess = {
      token:          auth.session_token,
      username:       auth.username,
      display_name:   auth.display_name,
      user_id:        auth.user_id,
      league_id:      auth.league_id,
      league_name:    leagueName,
      scoring_format: auth.scoring_format,
      expires_at:     auth.expires_at,
    };
    // Prime the rankings cache immediately so the content script has data
    try {
      const data = await apiRankings(sess.token);
      sess.cached_rankings = data;
      sess.cached_at = Date.now();
    } catch (_) { /* non-fatal — background alarm will retry */ }
    await setSession(sess);
    try { chrome.runtime.sendMessage({ type: 'ftf:signed_in', sess }); } catch (_) {}
    renderConnected(sess, sess.cached_rankings);
    show('connected');
  } catch (e) {
    setError('pick', e.message || 'Connection failed.');
    show('pick');
  }
}

function renderConnected(sess, rankings) {
  els.connUser.textContent   = '@' + (sess.username || '—');
  els.connLeague.textContent = sess.league_name || sess.league_id || '—';
  els.connFmt.textContent    = fmtLabel(sess.scoring_format);
  const count = rankings && rankings.players ? Object.keys(rankings.players).length : 0;
  els.connCount.textContent = count ? `${count} players` : '—';
}

// ─────────────────────────────────────────────────────────────────
//  Init
// ─────────────────────────────────────────────────────────────────

(async function init() {
  const sess = await getSession();
  if (sess && sess.token) {
    // Quietly refresh on popup open so "player count" is fresh
    show('busy', 'Refreshing rankings…');
    try {
      const data = await apiRankings(sess.token);
      sess.cached_rankings = data;
      sess.cached_at = Date.now();
      await setSession(sess);
      try { chrome.runtime.sendMessage({ type: 'ftf:rankings_updated' }); } catch (_) {}
      renderConnected(sess, data);
      show('connected');
    } catch (e) {
      if (String(e.message) === 'session_expired') {
        await clearSession();
        show('signin');
      } else {
        // Show cached state even if refresh fails
        renderConnected(sess, sess.cached_rankings);
        show('connected');
      }
    }
  } else {
    show('signin');
    els.username.focus();
  }
})();
