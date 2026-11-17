#!/usr/bin/env node
// Founders' review, "Review pages" — the operator's review documents opened in
// a web view, comments saved to the server
// (docs/plans/founder-review/pages-design.md, pages-scope.md §3).
//
// WHY THIS EXISTS. The page is founder-only, so its failure modes are silent
// and some are security failures: a session token, cookie or API URL handed
// to the web view (the page is arbitrary HTML); a page that can navigate the
// web view somewhere else, or hand a URL scheme to the OS; a bridge message
// used before it is validated; a "Review pages" choice that shows on a server
// without the route; the two existing founder paths (Player labels, Trade
// rules) changed by the third; a save that fails silently or a close that
// drops the last keystrokes.
//
// HONEST LABEL (G-035): §1, §2, §5, §6 and §8 prove the PRESENCE of exact
// wirings in source; §3, §4 and §7 transpile and EXECUTE
// src/utils/founderPages.ts under node (§4 runs the injected bridge script
// against a stub DOM). Runtime proof is the manual TestFlight checklist in
// pages-scope.md §3.
//
// Run: npm run test:founder-pages   (or node tests/check-founder-pages.js)
'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const ROOT = path.join(MOBILE, '..');
let ts;
try {
  ts = require('typescript');
} catch (e) {
  console.error('FAIL  typescript is not installed (run npm install in mobile/)');
  process.exit(1);
}

let failures = 0;
let passes = 0;
const assert = (cond, name, why) => {
  if (cond) {
    passes += 1;
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`);
  }
};
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
const readRoot = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');
const code = (src) => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`])\/\/.*$/gm, '$1');

const HOST = code(read('src/components/founder/FounderReview.tsx'));
const LIST = code(read('src/components/founder/FounderPagesReview.tsx'));
const VIEW = code(read('src/components/founder/FounderPageViewer.tsx'));
const API = code(read('src/api/founder.ts'));
const UTIL_SRC = read('src/utils/founderPages.ts');
const SERVER = readRoot('backend/founder_pages.py');
const PKG = JSON.parse(read('package.json'));

// Execute the util (type-only imports by contract).
assert(!/^\s*import\s+(?!type\b)/m.test(UTIL_SRC), '0a. utils/founderPages.ts has no runtime imports');
const js = ts.transpileModule(UTIL_SRC, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 } }).outputText;
const mod = { exports: {} };
new Function('module', 'exports', 'require', js)(mod, mod.exports, () => { throw new Error('no imports'); });
const U = mod.exports;

// ── 1. Nothing secret reaches the web view ──────────────────────────────────
const webview = (VIEW.match(/<WebView\s[\s\S]*?\/>/) || [''])[0];
assert(webview !== '' && (VIEW.match(/<WebView\s/g) || []).length === 1, '1a. the viewer mounts exactly one WebView');
assert(/source=\{source\}/.test(webview)
  && /const source = useMemo\(\(\) => \(doc \? \{ html: doc\.html, baseUrl: 'about:blank' \} : null\), \[doc\]\);/.test(VIEW),
  '1b. the web view is given the fetched HTML as a string on about:blank (no uri, no headers)');
assert(!/uri\s*:|headers\s*[:=]|X-Session|Session-Token|sessionToken|getToken|Authorization|[Cc]ookie\s*[:=]|API_BASE|apiBase|baseURL|EXPO_PUBLIC/.test(VIEW),
  '1c. the viewer names no token, header, cookie or API URL anywhere');
assert(/incognito/.test(webview) && /sharedCookiesEnabled=\{false\}/.test(webview)
  && /thirdPartyCookiesEnabled=\{false\}/.test(webview) && /allowFileAccess=\{false\}/.test(webview),
  '1d. no shared cookies, no stored state, no file access');
assert(/import \{ ApiError \} from '\.\.\/\.\.\/api\/client';/.test(VIEW)
  && /import \{ getFounderPage, saveFounderPageNotes \} from '\.\.\/\.\.\/api\/founder';/.test(VIEW),
  '1e. the page is fetched and saved only through api/founder (the normal client)');
assert(/injectedJavaScript=\{bridge\}/.test(webview) && /const bridge = useMemo\(\(\) => \(doc \? bridgeScript\(doc\.notes\) : ''\), \[doc\]\);/.test(VIEW),
  '1f. the injected script is bridgeScript(the page\'s own notes) and nothing else');
const sample = U.bridgeScript({ q1: 'hello', 'k</script>': 'x\u2028y' });
assert(!/https?:|token|cookie|\/api\//i.test(sample + U.STORAGE_SHIM + U.FLUSH_SCRIPT),
  '1g. executed: the bridge, the storage stand-in and the flush script carry no URL, token or cookie');
assert(!/<\/script/i.test(sample) && !/\u2028/.test(sample), '1h. executed: notes are embedded safely (no </script, no raw U+2028)');

// ── 2. No navigation away from the document ─────────────────────────────────
assert(/originWhitelist=\{\['\*'\]\}/.test(webview) && /onShouldStartLoadWithRequest=\{onShouldStart\}/.test(webview),
  '2a. every request reaches onShouldStartLoadWithRequest (no origin list hands a URL to the OS)');
assert(/setSupportMultipleWindows=\{false\}/.test(webview) && /javaScriptCanOpenWindowsAutomatically=\{false\}/.test(webview),
  '2b. no new windows');
assert(/const decision = navigationDecision\(req\);\s*if \(decision === 'external'\) void openWebLink\(req\.url\);\s*return decision === 'load';/.test(VIEW),
  '2c. onShouldStart loads only the document; an external link opens in the system browser; the rest is dropped');
const nav = (url, extra = {}) => U.navigationDecision({ url, isTopFrame: true, navigationType: 'click', ...extra });
assert(nav('about:blank') === 'load' && nav('about:blank#section-2') === 'load', '2d. executed: the document and its # links load');
assert(nav('https://example.com/x') === 'external' && nav('HTTP://example.com') === 'external'
  && nav('https://example.com', { navigationType: 'other' }) === 'external',
  '2e. executed: an http(s) link goes to the system browser (Android reports every navigation as "other")');
for (const url of ['mailto:a@b.c', 'tel:123', 'javascript:alert(1)', 'data:text/html,x', 'file:///etc/hosts',
  'about:srcdoc', 'blob:x', 'fleeced://x', 'itms-apps://x', '']) {
  assert(nav(url) === 'block', `2f. executed: ${url || '(empty)'} is dropped`);
}
assert(nav('https://example.com', { isTopFrame: false }) === 'block'
  && nav('https://example.com', { navigationType: 'formsubmit' }) === 'block'
  && nav('https://example.com', { navigationType: 'reload' }) === 'block',
  '2g. executed: frames and form posts never open anything');

// ── 3. Every bridge message is validated before use ─────────────────────────
assert(/function onMessage\(e: WebViewMessageEvent\) \{\s*const msg = parseBridgeMessage\(e\.nativeEvent\.data\);\s*if \(msg === null\) return;/.test(VIEW),
  '3a. onMessage validates first and ignores anything invalid');
assert(/pending\.current = \{ \.\.\.pending\.current, \[msg\.k\]: \{ label: msg\.label, body: msg\.v \} \};/.test(VIEW),
  '3b. only the validated fields are queued');
const P = (o) => U.parseBridgeMessage(JSON.stringify(o));
assert(JSON.stringify(P({ type: 'note', k: 'q1', label: 'L', v: 'text' })) === JSON.stringify({ type: 'note', k: 'q1', label: 'L', v: 'text' })
  && JSON.stringify(P({ type: 'flushed', extra: 1 })) === JSON.stringify({ type: 'flushed' }),
  '3c. executed: a note and a flush are accepted (extra fields dropped)');
const bad = [
  'not json', '[]', 'null', '42', JSON.stringify({ type: 'token', k: 'q1', label: '', v: '' }),
  JSON.stringify({ type: 'note', k: '', label: '', v: 'x' }),
  JSON.stringify({ type: 'note', k: 'k'.repeat(U.MAX_KEY_CHARS + 1), label: '', v: 'x' }),
  JSON.stringify({ type: 'note', k: 'q1', label: 'l'.repeat(U.MAX_LABEL_CHARS + 1), v: 'x' }),
  JSON.stringify({ type: 'note', k: 'q1', label: '', v: 'v'.repeat(U.MAX_BODY_CHARS + 1) }),
  JSON.stringify({ type: 'note', k: 1, label: '', v: 'x' }),
  JSON.stringify({ type: 'note', k: 'q1', v: 'x' }),
  JSON.stringify({ type: 'note', k: 'q1', label: '', v: null }),
];
assert(bad.every((b) => U.parseBridgeMessage(b) === null) && U.parseBridgeMessage({ type: 'note' }) === null,
  '3d. executed: malformed, unknown, wrongly typed and over-long messages are all rejected');
assert(P({ type: 'note', k: 'k'.repeat(U.MAX_KEY_CHARS), label: 'l'.repeat(U.MAX_LABEL_CHARS), v: 'v'.repeat(U.MAX_BODY_CHARS) }) !== null,
  '3e. executed: values at the limits are accepted');

// ── 4. The bridge script, executed against a stub DOM ───────────────────────
function world(boxes, notes) {
  const posted = [];
  const timers = [];
  const listeners = {};
  const ids = {};
  const mk = (tag, attrs) => {
    const el = {
      tagName: tag, attrs: { ...attrs }, style: {}, value: '', maxLength: -1, events: [],
      getAttribute(n) { return Object.prototype.hasOwnProperty.call(this.attrs, n) ? this.attrs[n] : null; },
      hasAttribute(n) { return Object.prototype.hasOwnProperty.call(this.attrs, n); },
      dispatchEvent(ev) { this.events.push(ev.type); return true; },
    };
    if (attrs.id) ids[attrs.id] = el;
    return el;
  };
  const els = boxes.map((b) => mk('TEXTAREA', b));
  mk('BUTTON', { id: 'exportBtn' });
  mk('BUTTON', { id: 'clearBtn' });
  const window = { ReactNativeWebView: { postMessage: (s) => posted.push(JSON.parse(s)) } };
  const document = {
    querySelectorAll: (sel) => (sel === 'textarea[data-k]' ? els.filter((e) => e.hasAttribute('data-k')) : []),
    getElementById: (id) => ids[id] || null,
    addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
  };
  const setTimeout = (fn, ms) => { timers.push({ fn, ms, live: true }); return timers.length - 1; };
  const clearTimeout = (i) => { if (timers[i]) timers[i].live = false; };
  function Event(type) { this.type = type; }
  new Function('window', 'document', 'setTimeout', 'clearTimeout', 'Event', U.bridgeScript(notes))(
    window, document, setTimeout, clearTimeout, Event);
  const fire = (type, target) => (listeners[type] || []).forEach((fn) => fn({ target }));
  const tick = () => timers.filter((t) => t.live).forEach((t) => { t.live = false; t.fn(); });
  return { els, ids, posted, timers, fire, tick, window };
}
{
  const w = world([{ 'data-k': 'q1', 'data-label': 'Question 1' }, { 'data-k': 'q2' }, { 'data-k': 'q3', maxlength: '50' }],
    { q1: 'saved one', q3: 'saved three', ghost: 'no box' });
  assert(w.els[0].value === 'saved one' && w.els[1].value === '' && w.els[2].value === 'saved three',
    '4a. executed: each box with a saved note is filled; the others stay empty');
  assert(JSON.stringify(w.els[0].events) === '["input"]' && w.els[1].events.length === 0,
    '4b. executed: a filled box fires input (the page\'s own counters update)');
  assert(w.posted.length === 0, '4c. executed: filling posts nothing back');
  assert(w.ids.exportBtn.style.display === 'none' && w.ids.clearBtn.style.display === 'none',
    '4d. executed: #exportBtn and #clearBtn are hidden');
  assert(w.els[0].maxLength === U.MAX_BODY_CHARS && w.els[2].maxLength === -1,
    '4e. executed: a box without its own maxlength is capped at the server limit');
  w.els[1].value = 'typed';
  w.fire('input', w.els[1]);
  w.fire('input', w.els[1]);
  assert(w.posted.length === 0 && w.timers.filter((t) => t.live).length === 1 && w.timers.at(-1).ms === U.PAGE_DEBOUNCE_MS,
    '4f. executed: keystrokes are debounced per box (600 ms, one timer)');
  w.tick();
  assert(JSON.stringify(w.posted) === JSON.stringify([{ type: 'note', k: 'q2', label: '', v: 'typed' }]),
    '4g. executed: after the pause the box posts {type:"note", k, label, v}');
  w.els[0].value = 'edited';
  w.fire('input', w.els[0]);
  w.fire('focusout', w.els[0]);
  assert(JSON.stringify(w.posted.at(-1)) === JSON.stringify({ type: 'note', k: 'q1', label: 'Question 1', v: 'edited' })
    && w.timers.filter((t) => t.live).length === 0,
    '4h. executed: blur posts at once and cancels the pending timer');
  w.els[2].value = 'last words';
  w.fire('input', w.els[2]);
  w.window.__ftfFlush();
  assert(JSON.stringify(w.posted.slice(-2)) === JSON.stringify([
    { type: 'note', k: 'q3', label: '', v: 'last words' }, { type: 'flushed' }]),
    '4i. executed: __ftfFlush posts every pending box, then {type:"flushed"}');
  w.els[1].value = '';
  w.fire('input', w.els[1]);
  w.tick();
  assert(JSON.stringify(w.posted.at(-1)) === JSON.stringify({ type: 'note', k: 'q2', label: '', v: '' }),
    '4j. executed: clearing a box posts an empty body (the server deletes the note)');
  const other = { tagName: 'INPUT', getAttribute: () => 'x', hasAttribute: () => true };
  const before = w.posted.length;
  w.fire('input', other);
  w.tick();
  assert(w.posted.length === before, '4k. executed: input outside textarea[data-k] is ignored');
}

// ── 5. The choice appears only when the server lists pages ───────────────────
assert(/if \(e instanceof ApiError && e\.status === 404\) return null;/.test(API.split('listFounderPages')[1] || '')
  && /'\/api\/founder\/pages', \{\s*\.\.\.options, quietStatuses: \[404\],/.test(API),
  '5a. listFounderPages answers null on 404 and reports nothing');
assert(U.pagesAvailable(null) === false && U.pagesAvailable(undefined) === false && U.pagesAvailable([]) === false
  && U.pagesAvailable([{ slug: 'a', title: 'A', bytes: 1, updated_at: '2026-11-16T12:00:00Z', notes: 0 }]) === true,
  '5b. executed: the choice needs at least one page (null and [] hide it)');
assert(/const pagesAvailable = hasPages\(pagesQ\.data\);/.test(HOST) && /const pagesQ = useQuery\(founderPagesQuery\(\)\);/.test(HOST)
  && /const showPages = pagesAvailable && useCase === 'pages';/.test(HOST),
  '5c. FounderReview reads availability from the server answer only');
assert(/\{pagesAvailable \? \(\s*<Pressable\s+testID="founder-review\.use\.pages"/.test(HOST) && />Review pages</.test(HOST),
  '5d. the "Review pages" segment renders only when pages are available');
assert(/onPress=\{\(\) => confirmLeaveNotes\(\(\) => setUseCase\('pages'\)\)\}/.test(HOST),
  '5e. moving to Review pages from Trade rules asks about unsaved rule notes first');
for (const [name, src] of [['FounderReview', HOST], ['FounderPagesReview', LIST], ['FounderPageViewer', VIEW], ['api/founder', API]]) {
  assert(!/founder\.review|useFlag\(|useFeatureFlags|FOUNDER_ACCOUNTS|tester_allowlist/.test(src),
    `5f. ${name} reads no flag and no local allow-list`);
}

// ── 6. The two existing founder paths are unchanged ──────────────────────────
assert(/if \(!rulesAvailable && !pagesAvailable\) return <FounderLabelReview leagueId=\{leagueId\} \/>;/.test(HOST),
  '6a. neither route: the label review alone, exactly as before');
assert(/const rulesAvailable = rulesQ\.data != null;/.test(HOST) && /const showRules = rulesAvailable && useCase === 'rules';/.test(HOST)
  && /const showLabels = !showRules && !showPages;/.test(HOST),
  '6b. Trade rules availability and selection are unchanged; without pages, Player labels is selected exactly when Trade rules is not');
assert(/testID="founder-review\.use\.labels"[\s\S]{0,120}onPress=\{\(\) => confirmLeaveNotes\(\(\) => setUseCase\('labels'\)\)\}/.test(HOST)
  && /testID="founder-review\.use\.rules"[\s\S]{0,120}onPress=\{\(\) => setUseCase\('rules'\)\}/.test(HOST),
  '6c. Player labels still asks before leaving unsaved rule notes; Trade rules is entered directly');
assert(/\{showRules\s*\? <RuleWaterfallReview leagueId=\{leagueId\} leagueName=\{leagueName\} \/>\s*: showPages\s*\? <FounderPagesReview \/>\s*: <FounderLabelReview leagueId=\{leagueId\} \/>\}/.test(HOST),
  '6d. the body is Trade rules, Review pages or Player labels, one at a time');

// ── 7. Limits and the save queue (executed) ─────────────────────────────────
const pyConst = (name) => {
  const m = SERVER.match(new RegExp(`^${name} = ([0-9_]+)`, 'm'));
  return m ? Number(m[1].replace(/_/g, '')) : null;
};
for (const [app, server] of [['MAX_KEY_CHARS', 'MAX_KEY_CHARS'], ['MAX_LABEL_CHARS', 'MAX_LABEL_CHARS'],
  ['MAX_BODY_CHARS', 'MAX_BODY_CHARS'], ['MAX_KEYS_PER_SAVE', 'MAX_KEYS_PER_SAVE']]) {
  assert(U[app] === pyConst(server) && U[app] > 0, `7a. ${app} equals backend/founder_pages.py ${server}`,
    `app ${U[app]} server ${pyConst(server)}`);
}
const pending = Object.fromEntries(Array.from({ length: 250 }, (_, i) => [`k${i}`, { label: '', body: `b${i}` }]));
const batch = U.takeBatch(pending);
assert(Object.keys(batch).length === U.MAX_KEYS_PER_SAVE, '7b. executed: a batch never exceeds the server\'s 200 keys');
const edited = { ...pending, k0: { label: '', body: 'edited during the save' } };
const left = U.settle(edited, batch);
assert(Object.keys(left).length === 51 && left.k0.body === 'edited during the save' && !('k1' in left),
  '7c. executed: a saved box leaves the queue; one edited during the save stays');
assert(U.retryDelayMs(0) === 2000 && U.retryDelayMs(1) === 4000 && U.retryDelayMs(10) === 30000,
  '7d. executed: retries back off 2 s, 4 s … 30 s');
assert([400, 401, 403, 404, 413].every(U.isPermanentFailure) && ![undefined, 0, 408, 429, 500, 503].some(U.isPermanentFailure),
  '7e. executed: a network or server error retries; a validation or gate answer stops');
assert(U.saveStateText('retrying') === 'Could not save, retrying' && U.saveStateText('saved') === 'Saved'
  && U.saveStateText('saving') === 'Saving…' && U.saveStateText('idle') === '',
  '7f. executed: the save state words');
assert(U.notesLabel(1) === '1 note' && U.notesLabel(3) === '3 notes' && U.notesLabel(0) === '0 notes'
  && /^Updated [A-Z][a-z]{2} \d{1,2}, 2026$/.test(U.updatedLabel('2026-11-16T12:00:00+00:00')) && U.updatedLabel(null) === 'Updated',
  '7g. executed: list row words');

// ── 8. Saving, closing, loading: wiring ─────────────────────────────────────
assert(/if \(isPermanentFailure\(status\)\) \{\s*show\('failed'\);\s*return false;\s*\}\s*show\('retrying'\);\s*schedule\(retryDelayMs\(attempt\.current\)\);/.test(VIEW),
  '8a. a failed save shows "retrying" and retries with backoff (or stops on a permanent answer)');
assert(/await saveFounderPageNotes\(slug, batch\);/.test(VIEW) && /const batch = takeBatch\(pending\.current, MAX_KEYS_PER_SAVE\);/.test(VIEW)
  && /pending\.current = settle\(pending\.current, batch\);/.test(VIEW),
  '8b. saves go through saveFounderPageNotes in batches of at most 200, settling only what was sent');
assert(/webRef\.current\.injectJavaScript\(FLUSH_SCRIPT\);/.test(VIEW)
  && /const requestClose = async \(\) => \{[\s\S]*?await flushPage\(\);[\s\S]*?await save\(\);[\s\S]*?if \(left === 0\) \{\s*onClose\(\);\s*return;\s*\}[\s\S]*?Alert\.alert\(COPY\.leaveTitle/.test(VIEW),
  '8c. close flushes the page, then the queue, and warns before leaving unsaved comments');
assert(/onRequestClose=\{\(\) => \{ void requestClose\(\); \}\}/.test(VIEW)
  && /testID="founder-review\.pages\.close"[\s\S]{0,200}onPress=\{\(\) => \{ void requestClose\(\); \}\}/.test(VIEW),
  '8d. Close and the Android back button both take the flushing path');
assert(/<Modal visible animationType="slide" presentationStyle="fullScreen"/.test(VIEW)
  && /<SafeAreaView style=\{styles\.root\} edges=\{\['top', 'bottom', 'left', 'right'\]\}>/.test(VIEW),
  '8e. full screen in a Modal, inside the safe area');
assert(/gcTime: 0/.test(VIEW) && /staleTime: Infinity/.test(VIEW) && /refetchOnWindowFocus: false/.test(VIEW),
  '8f. the 2.5 MB page is not cached after close and never refetched under the open page');
for (const id of ['founder-review.pages.close', 'founder-review.pages.save-state', 'founder-review.pages.loading',
  'founder-review.pages.error', 'founder-review.pages.retry', 'founder-review.pages.webview']) {
  assert(VIEW.includes(`testID="${id}"`), `8g. testID ${id}`);
}
for (const id of ['founder-review.pages.row', 'founder-review.pages.list', 'founder-review.pages.list-loading',
  'founder-review.pages.list-error', 'founder-review.pages.list-retry']) {
  assert(LIST.includes(`testID="${id}"`), `8h. testID ${id}`);
}
assert(/timeoutMs: 45_000/.test(API) && /api\.put\(`\/api\/founder\/pages\/\$\{encodeURIComponent\(slug\)\}\/notes`, \{ set \}\)/.test(API),
  '8i. the page fetch has the slow cap; notes PUT {set}');
assert(/onClose=\{\(\) => \{\s*setOpen\(null\);\s*void qc\.invalidateQueries\(\{ queryKey: founderPagesKey \}\);/.test(LIST),
  '8j. closing a page refreshes the list\'s note counts');

// ── 9. House rules ───────────────────────────────────────────────────────────
for (const [name, src] of [['FounderPagesReview', LIST], ['FounderPageViewer', VIEW], ['utils/founderPages', code(UTIL_SRC)]]) {
  assert(!/analytics|track\(|logEvent|useAnalytics/.test(src), `9a. ${name} fires no analytics event`);
  assert(!/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(src) && !/gradient/i.test(src), `9b. ${name}: no emoji, no gradients`);
}
assert(!/<FeedbackFAB\b/.test(LIST + VIEW), '9c. no FeedbackFAB (tab-stack section and a modal)');
assert(PKG.scripts['test:founder-pages'] === 'node tests/check-founder-pages.js', '9d. npm run test:founder-pages');

console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
