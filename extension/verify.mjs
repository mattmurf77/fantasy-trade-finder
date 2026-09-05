// User-initiated ownership proof. Sleeper credentials stay inside the extension
// until they are sent to the fixed first-party verification endpoint.
export const API_BASE = 'https://fantasy-trade-finder.onrender.com';
export const WEB_ORIGINS = new Set([
  API_BASE,
]);
const SLEEPER_ORIGINS = new Set(['https://sleeper.com', 'https://sleeper.app']);

export function isSleeperUrl(url) {
  try { return SLEEPER_ORIGINS.has(new URL(url).origin); } catch { return false; }
}

export function verificationSenderAllowed(sender, extensionId) {
  if (sender.id !== extensionId) return false;
  if (sender.url === `chrome-extension://${extensionId}/popup.html` && !sender.tab) return true;
  try {
    return sender.frameId === 0 && !!sender.tab &&
      WEB_ORIGINS.has(new URL(sender.url).origin) &&
      new URL(sender.tab.url).origin === new URL(sender.url).origin;
  } catch { return false; }
}

export async function verifySleeperSession(username, chromeApi, fetchApi = fetch) {
  username = String(username || '').trim().toLowerCase();
  if (!username || username.length > 100) throw new Error('missing_username');
  const tabs = await chromeApi.tabs.query({ url: ['https://sleeper.com/*', 'https://sleeper.app/*'] });
  const candidates = tabs.filter(tab => Number.isInteger(tab.id) && isSleeperUrl(tab.url));
  if (!candidates.length) throw new Error('sleeper_tab_required');

  // Never scan storage or collect other keys. The selected page returns only
  // Sleeper's known login token; the server checks its account and live proof.
  let proof = null;
  for (const tab of candidates.sort((a, b) => Number(b.active) - Number(a.active))) {
    try {
      const reply = await chromeApi.tabs.sendMessage(tab.id, { type: 'ftf:capture_sleeper_proof' }, { frameId: 0 });
      if (typeof reply?.token === 'string' && reply.token.length <= 16384 && reply.token.split('.').length === 3) {
        proof = reply.token;
        break;
      }
    } catch { /* A tab opened before installation needs a refresh. */ }
  }
  if (!proof) throw new Error('sleeper_login_required');

  try {
    const authRes = await fetchApi(`${API_BASE}/api/extension/auth`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username }),
    });
    const auth = await authRes.json().catch(() => ({}));
    if (!authRes.ok || !auth.session_token || !auth.user_id) throw new Error('account_lookup_failed');
    const linkRes = await fetchApi(`${API_BASE}/api/sleeper/link`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': auth.session_token },
      body: JSON.stringify({ token: proof }),
    });
    const link = await linkRes.json().catch(() => ({}));
    if (!linkRes.ok) {
      const safeCodes = ['token_user_mismatch', 'token_rejected', 'token_expired', 'verification_unavailable', 'feature_disabled'];
      throw new Error(safeCodes.includes(link.error) ? link.error : 'verification_failed');
    }
    if (link.verified !== true || String(link.sleeper_user_id) !== String(auth.user_id)) {
      throw new Error('verification_incomplete');
    }
    return {
      token: auth.session_token, user_id: String(auth.user_id),
      username: auth.username || username, display_name: auth.display_name || username,
      avatar: auth.avatar || null, expires_at: auth.expires_at,
      leagues: Array.isArray(auth.leagues) ? auth.leagues : [],
      verified: true, rankings_cache: {},
    };
  } finally {
    proof = null;
  }
}
