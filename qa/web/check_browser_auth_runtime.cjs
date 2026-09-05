/** Real Chromium + loaded MV3 extension. Every URL is fulfilled or aborted;
 * host resolution also points to loopback, so no real upstream is reachable.
 * Run with NODE_PATH pointing at a Playwright installation.
 */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const base = 'https://fantasy-trade-finder.onrender.com';
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'ftf-auth-chromium-'));
const calls = [];
let rejectSession = false;
let context;
(async () => {
  context = await chromium.launchPersistentContext(profile, {
    channel: 'chromium', headless: true,
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
    args: [`--disable-extensions-except=${path.join(root, 'extension')}`,
      `--load-extension=${path.join(root, 'extension')}`,
      '--host-resolver-rules=MAP * 127.0.0.1, EXCLUDE localhost'],
  });
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.protocol === 'chrome-extension:') return route.continue();
    if (url.origin === 'https://sleeper.com') {
      return route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Fixture Sleeper</title><script>localStorage.setItem("token","synthetic.proof.signature")</script><p>Signed in to fixture Sleeper</p>' });
    }
    if (url.origin !== base) return route.abort();
    if (url.pathname.startsWith('/api/')) {
      calls.push({ path: url.pathname, method: request.method() });
      const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
      if (url.pathname === '/api/feature-flags') return reply({ flags: { 'trade.send_in_sleeper': true, 'landing.platform_options': true, 'espn.link': true, 'mfl.link': true } });
      if (url.pathname === '/api/extension/auth') {
        const username = request.postDataJSON().username;
        return reply({ session_token: username === 'owner' ? 'ftf-owner' : 'ftf-wrong', user_id: username === 'owner' ? '123' : '456', username, display_name: username, leagues: [] });
      }
      if (url.pathname === '/api/sleeper/link') {
        assert.deepEqual(request.postDataJSON(), { token: 'synthetic.proof.signature' });
        return request.headers()['x-session-token'] === 'ftf-owner'
          ? reply({ verified: true, sleeper_user_id: '123' })
          : reply({ error: 'token_user_mismatch' }, 403);
      }
      if (url.pathname === '/api/extension/rankings') return rejectSession
        ? reply({ error: 'verification_required' }, 403)
        : reply({ players: {}, format: '1qb_ppr' });
      if (url.pathname === '/api/me/streak') return rejectSession
        ? reply({ error: 'verification_required' }, 403)
        : reply({ streak: 0 });
      if (url.pathname.startsWith('/api/sleeper/leagues/')) return reply([]);
      if (url.pathname === '/api/events') return reply({ accepted: 0 });
      return reply({ error: 'fixture_missing', path: url.pathname }, 404);
    }
    const pathname = url.pathname === '/' ? '/index.html' : url.pathname;
    const file = path.resolve(root, 'web', '.' + pathname);
    if (!file.startsWith(path.join(root, 'web') + path.sep) || !fs.existsSync(file)) return route.abort();
    const type = ({ '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' })[path.extname(file)] || 'application/octet-stream';
    return route.fulfill({ contentType: type, body: fs.readFileSync(file) });
  });
  const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
  assert.ok(worker.url().startsWith('chrome-extension://'));
  const sleeper = await context.newPage();
  await sleeper.goto('https://sleeper.com/login');
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.goto(base);
  await page.bringToFront();
  await page.locator('#username-input').fill('wrong-user');
  await page.locator('#auth-btn').click();
  await page.getByText('Your open Sleeper account does not match this username.', { exact: false }).waitFor();
  assert.equal(await page.evaluate(() => localStorage.getItem('fumble_session_token')), null);
  assert.equal(calls.filter(c => c.path === '/api/session/init').length, 0);
  await page.locator('#username-input').fill('owner');
  await page.locator('#auth-btn').click();
  await page.waitForFunction(() => localStorage.getItem('fumble_session_token') === 'ftf-owner');
  assert.ok(!await page.evaluate(() => JSON.stringify(localStorage).includes('synthetic.proof.signature')));
  const stored = await worker.evaluate(() => chrome.storage.local.get('ftf_session'));
  assert.equal(stored.ftf_session.verified, true);
  assert.ok(!JSON.stringify(stored).includes('synthetic.proof.signature'));
  rejectSession = true;
  await page.reload();
  await page.getByText('Verify your Sleeper account to continue.', { exact: false }).waitFor();
  assert.equal(await page.evaluate(() => localStorage.getItem('fumble_session_token')), null);
  assert.equal(calls.filter(c => c.path === '/api/session/init').length, 0);
  await page.locator('#platform-chip-espn').click();
  await page.getByText('For ESPN or MyFantasyLeague, verify and link your account in the Fleeced mobile app.', { exact: false }).waitFor();
  assert.equal(calls.filter(c => c.path === '/api/entry/platform').length, 0);
  // The actual extension popup must discard cached data when proof is denied.
  const extensionId = new URL(worker.url()).hostname;
  const popup = await context.newPage();
  popup.on('pageerror', error => pageErrors.push(error.message));
  await popup.goto(`chrome-extension://${extensionId}/popup.html`);
  await popup.locator('#stage-signin:not(.hidden)').waitFor();
  assert.equal((await worker.evaluate(() => chrome.storage.local.get('ftf_session'))).ftf_session, undefined);
  assert.deepEqual(pageErrors, []);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  assert.ok(await page.locator('.cb-auth-help').evaluateAll(nodes =>
    nodes.every(node => node.scrollWidth <= node.clientWidth &&
      node.getBoundingClientRect().right <= document.documentElement.clientWidth)));
  const screenshot = path.join(os.tmpdir(), 'ftf-browser-verification.png');
  await page.screenshot({ path: screenshot, fullPage: false });
  console.log('Chromium MV3 runtime: mismatch blocked, proof verified, credentials isolated, revoked session recovered, platform claims blocked, popup cache cleared.');
  console.log('Screenshot:', screenshot);
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (context) await context.close();
  fs.rmSync(profile, { recursive: true, force: true });
});
