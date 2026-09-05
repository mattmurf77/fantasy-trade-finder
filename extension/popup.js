// Fantasy Trade Finder — popup.js
// Explicit Sleeper login proof verifies ownership before private rankings. The
// content script auto-detects which league the user is viewing on
// sleeper.com and fetches rankings for that league on demand.

const API_BASE = 'https://fantasy-trade-finder.onrender.com';
// For local development, uncomment the next line and comment the one above:
// const API_BASE = 'http://127.0.0.1:5000';

const STORAGE_KEY = 'ftf_session';

// Analytics P4 — extension DAU signal (background emits app_opened, gated on
// analytics.client_events server-side). Fire-and-forget.
try { chrome.runtime.sendMessage({ type: 'ftf:popup_opened' }); } catch (_) {}

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

async function clearSessionIfCurrent(token) {
  if ((await getSession())?.token !== token) return;
  await clearSession();
  try { chrome.runtime.sendMessage({ type: 'ftf:signed_out' }); } catch (_) {}
}

async function cacheSessionIfCurrent(sess) {
  if ((await getSession())?.token === sess.token) await setSession(sess);
}

function fmtLabel(fmt) {
  return fmt === 'sf_tep' ? 'SF TEP' : fmt === '1qb_ppr' ? '1QB PPR' : fmt || '—';
}

// ─────────────────────────────────────────────────────────────────
//  API calls
// ─────────────────────────────────────────────────────────────────

const VERIFICATION_MESSAGES = {
  sleeper_tab_required: 'Open sleeper.com in a tab and sign in, then try again.',
  sleeper_login_required: 'Sign in to Sleeper and refresh that tab, then try again.',
  token_user_mismatch: 'The open Sleeper account does not match this username. Switch accounts in Sleeper and try again.',
  token_rejected: 'Sign in to Sleeper again, then retry verification.',
  token_expired: 'Sign in to Sleeper again, then retry verification.',
  verification_unavailable: 'Sleeper verification is temporarily unavailable. Please try again.',
  feature_disabled: 'Verification is unavailable on the server. Please try later.',
  verification_busy: 'Another verification is in progress. Please try again.',
};

async function apiSignIn(username) {
  const result = await chrome.runtime.sendMessage({ type: 'ftf:verify_sleeper', username });
  if (!result?.ok || result.session?.verified !== true) {
    throw new Error(VERIFICATION_MESSAGES[result?.error] || 'Could not verify your account. Sign in to Sleeper and try again.');
  }
  return result.session;
}

async function apiRankings(token, leagueId) {
  const qs = leagueId ? `?league_id=${encodeURIComponent(leagueId)}` : '';
  const res = await fetch(`${API_BASE}/api/extension/rankings${qs}`, {
    headers: { 'X-Session-Token': token },
  });
  if (res.status === 401) throw new Error('session_expired');
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
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
    const sess = await apiSignIn(username);
    try { chrome.runtime.sendMessage({ type: 'ftf:signed_in' }); } catch (_) {}
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
    await cacheSessionIfCurrent(sess);
    try { chrome.runtime.sendMessage({ type: 'ftf:rankings_updated', leagueId }); } catch (_) {}
    await renderConnectedFromActiveTab(sess);
    show('connected');
  } catch (e) {
    if (['session_expired', 'verification_required'].includes(String(e.message))) {
      await clearSessionIfCurrent(sess.token);
      setError('Verify your Sleeper account again to continue.');
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
    await cacheSessionIfCurrent(sess);
    try { chrome.runtime.sendMessage({ type: 'ftf:rankings_updated', leagueId }); } catch (_) {}
    const leagueName = data.league_name || findLeagueName(sess, leagueId) || leagueId;
    els.connCurLeague.textContent = leagueName;
    els.connFmt.textContent = fmtLabel(data.format);
    els.connCount.textContent = data.players ? `${Object.keys(data.players).length}` : '0';
  } catch (error) {
    if (['session_expired', 'verification_required'].includes(error.message)) throw error;
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
  if (sess?.token && sess.verified === true) {
    show('busy', 'Loading your rankings…');
    try {
      // Validate even without an active league; never show an old cached board
      // while the server requires a fresh proof.
      await apiRankings(sess.token, null);
      await renderConnectedFromActiveTab(sess);
      show('connected');
      return;
    } catch (error) {
      if (!['session_expired', 'verification_required'].includes(error.message)) {
        setError('Could not check your session. Please try again.');
        show('signin');
        return;
      }
    }
  }
  if (sess?.token) await clearSessionIfCurrent(sess.token);
  show('signin');
  els.username.focus();
})();
