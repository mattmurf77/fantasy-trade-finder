/** Offline browser-auth contracts: proof ownership, routing, and disclosure. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { API_BASE, verifySleeperSession, verificationSenderAllowed } from '../../extension/verify.mjs';

let checks = 0;
const check = (value, message) => { assert.ok(value, message); checks++; };
const base = { id: 'ext', url: `${API_BASE}/`, frameId: 0, tab: { id: 1, url: `${API_BASE}/` } };
check(verificationSenderAllowed(base, 'ext'), 'first-party top frame allowed');
check(verificationSenderAllowed({ id: 'ext', url: 'chrome-extension://ext/popup.html' }, 'ext'), 'popup allowed');
for (const sender of [
  { ...base, id: 'other' },
  { ...base, url: 'http://localhost:5000/', tab: { id: 2, url: 'http://localhost:5000/' } }, { ...base, frameId: 1 },
  { ...base, url: `${API_BASE}.evil.example/` },
  { ...base, tab: { id: 1, url: 'https://evil.example/' } },
  { ...base, url: 'https://sleeper.com/', tab: { id: 2, url: 'https://sleeper.com/' } },
]) check(!verificationSenderAllowed(sender, 'ext'), 'untrusted sender denied');

const jwt = 'synthetic.proof.signature';
const fakeChrome = {
  tabs: {
    query: async () => [{ id: 5, url: 'https://sleeper.com/leagues/123', active: true }],
    sendMessage: async (id, message, options) => {
      assert.equal(id, 5); assert.equal(options.frameId, 0);
      assert.equal(message.type, 'ftf:capture_sleeper_proof');
      return { token: jwt };
    },
  },
};
const auth = { session_token: 'verified-ftf-bearer', user_id: '123', username: 'owner' };
function network(linkBody, status = 200) {
  const calls = [];
  const fetch = async (url, options) => {
    calls.push({ url, options });
    assert.equal(new URL(url).origin, API_BASE);
    assert.ok(!url.includes(jwt));
    if (url.endsWith('/api/extension/auth')) return { ok: true, json: async () => auth };
    assert.equal(options.headers['X-Session-Token'], auth.session_token);
    assert.deepEqual(JSON.parse(options.body), { token: jwt });
    return { ok: status === 200, json: async () => linkBody };
  };
  return { calls, fetch };
}
const happy = network({ verified: true, sleeper_user_id: '123' });
const result = await verifySleeperSession(' Owner ', fakeChrome, happy.fetch);
check(result.verified && result.token === auth.session_token, 'only verified FTF session returned');
check(!JSON.stringify(result).includes(jwt), 'proof omitted from return/cache payload');
check(happy.calls.length === 2, 'claim followed by live verification');
for (const [body, status, code] of [
  [{ error: 'token_user_mismatch' }, 403, 'token_user_mismatch'],
  [{ error: 'verification_unavailable' }, 503, 'verification_unavailable'],
  [{ verified: false, sleeper_user_id: '123' }, 200, 'verification_incomplete'],
  [{ verified: true, sleeper_user_id: 'another' }, 200, 'verification_incomplete'],
]) {
  await assert.rejects(verifySleeperSession('owner', fakeChrome, network(body, status).fetch), { message: code });
  checks++;
}
let networkCalls = 0;
await assert.rejects(verifySleeperSession('owner', { tabs: { query: async () => [{ id: 1, url: 'https://sleeper.com.evil.example/' }] } },
  async () => { networkCalls++; }), { message: 'sleeper_tab_required' });
check(networkCalls === 0, 'invalid tab cannot trigger proof network');

// Exercise the actual isolated-world bridge without relying on source matching.
const documentListeners = {}, windowListeners = {}, posts = [];
let sends = 0;
const window = { addEventListener: (k, f) => { windowListeners[k] = f; }, postMessage: (m, target) => { posts.push({ m, target }); } };
window.top = window;
const location = { origin: API_BASE };
const document = { addEventListener: (k, f) => { documentListeners[k] = f; }, hasFocus: () => true };
const chrome = { runtime: { sendMessage: (_m, callback) => { sends++; callback({ ok: true, session: result }); } } };
vm.runInNewContext(fs.readFileSync(new URL('../../extension/web-auth.js', import.meta.url), 'utf8'), { window, document, chrome, location, Date });
const request = { source: window, origin: API_BASE, data: { type: 'ftf:web_verify', requestId: 'request-1', username: 'owner' } };
windowListeners.message(request);
check(sends === 0, 'unsolicited page message cannot capture proof');
documentListeners.click({ isTrusted: false, target: { closest: () => true } });
windowListeners.message(request);
check(sends === 0, 'synthetic click cannot authorize capture');
documentListeners.click({ isTrusted: true, target: { closest: () => true } });
windowListeners.message({ ...request, origin: 'https://evil.example' });
check(sends === 0, 'cross-origin request rejected');
windowListeners.message(request);
check(sends === 1, 'trusted first-party sign-in click permits one request');
windowListeners.message(request);
check(sends === 1, 'gesture cannot be replayed');
check(posts.every(p => p.target === API_BASE && p.m.requestId === 'request-1'), 'response is origin-bound and correlated');
check(!JSON.stringify(posts).includes(jwt), 'Sleeper credential never reaches page');
console.log(`${checks} browser/extension auth checks passed`);
