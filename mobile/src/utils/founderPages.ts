// Founders' review, "Review pages" — the decisions, kept free of React and of
// runtime imports so tests/check-founder-pages.js can execute them under node
// (docs/plans/founder-review/pages-design.md).
//
// The page contract: a self-contained HTML document whose comment boxes are
// `textarea[data-k]` (data-k = the box key, free text) with an optional
// `data-label`. The app gives the page its own saved text and nothing else:
// no session token, cookie or API URL ever reaches the web view. The page
// talks back only through window.ReactNativeWebView.postMessage, and every
// message is validated here before the app uses it.

import type { FounderPageNoteSet, FounderPageSummary } from '../api/founder';

// The server's limits (backend/founder_pages.py; pinned by the check).
export const MAX_KEY_CHARS = 128;
export const MAX_LABEL_CHARS = 300;
export const MAX_BODY_CHARS = 10_000;
export const MAX_KEYS_PER_SAVE = 200;
/** The page's per-box debounce before it posts a change. */
export const PAGE_DEBOUNCE_MS = 600;

export type BridgeMessage =
  | { type: 'note'; k: string; label: string; v: string }
  | { type: 'flushed' };

const isStr = (x: unknown, max: number): x is string => typeof x === 'string' && x.length <= max;

/** A message from the page, or null for anything that is not exactly a known shape. */
export function parseBridgeMessage(data: unknown): BridgeMessage | null {
  if (typeof data !== 'string' || data.length > 4 * (MAX_BODY_CHARS + MAX_LABEL_CHARS + MAX_KEY_CHARS)) return null;
  let msg: unknown;
  try {
    msg = JSON.parse(data);
  } catch {
    return null;
  }
  if (msg === null || typeof msg !== 'object' || Array.isArray(msg)) return null;
  const m = msg as Record<string, unknown>;
  if (m.type === 'flushed') return { type: 'flushed' };
  if (m.type !== 'note') return null;
  if (!isStr(m.k, MAX_KEY_CHARS) || m.k.length === 0) return null;
  if (!isStr(m.label, MAX_LABEL_CHARS) || !isStr(m.v, MAX_BODY_CHARS)) return null;
  return { type: 'note', k: m.k, label: m.label, v: m.v };
}

export type NavDecision = 'load' | 'external' | 'block';

/** What the web view does with a navigation: the document itself and its own `#` links
 *  load; an http(s) link the founder follows opens in the system browser; everything else
 *  (other schemes, frames, form posts) is dropped. */
export function navigationDecision(req: { url: string; isTopFrame?: boolean; navigationType?: string }): NavDecision {
  const url = String(req.url || '');
  if (url === 'about:blank' || url.startsWith('about:blank#')) return 'load';
  if (req.isTopFrame === false) return 'block';
  if (/^(formsubmit|formresubmit|reload|backforward)$/.test(req.navigationType ?? '')) return 'block';
  return /^https?:\/\//i.test(url) ? 'external' : 'block';
}

/** The "Review pages" choice shows only when the server listed at least one page. */
export function pagesAvailable(pages: FounderPageSummary[] | null | undefined): boolean {
  return Array.isArray(pages) && pages.length > 0;
}

export function notesLabel(n: number): string {
  return n === 1 ? '1 note' : `${n} notes`;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function updatedLabel(iso: string | null | undefined): string {
  const t = iso ? Date.parse(iso) : NaN;
  if (Number.isNaN(t)) return 'Updated';
  const d = new Date(t);
  return `Updated ${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

export type PendingNotes = Record<string, { label: string; body: string }>;

/** Up to `max` pending notes, as the PUT body's `set`. */
export function takeBatch(pending: PendingNotes, max: number = MAX_KEYS_PER_SAVE): FounderPageNoteSet {
  const out: FounderPageNoteSet = {};
  for (const k of Object.keys(pending).slice(0, max)) out[k] = { ...pending[k] };
  return out;
}

/** Pending notes after `sent` was saved: a box edited again meanwhile stays pending. */
export function settle(pending: PendingNotes, sent: FounderPageNoteSet): PendingNotes {
  const out: PendingNotes = {};
  for (const [k, v] of Object.entries(pending)) {
    const s = sent[k];
    if (!s || s.body !== v.body || s.label !== v.label) out[k] = v;
  }
  return out;
}

/** 2 s, 4 s, 8 s … capped at 30 s. */
export function retryDelayMs(attempt: number): number {
  return Math.min(30_000, 2_000 * 2 ** Math.max(0, attempt));
}

/** A failure retrying will not fix (validation, gone, not allowed): stop and say so. */
export function isPermanentFailure(status: number | undefined): boolean {
  return status === 400 || status === 401 || status === 403 || status === 404 || status === 413;
}

export type SaveState = 'idle' | 'saving' | 'saved' | 'retrying' | 'failed';

export function saveStateText(state: SaveState): string {
  switch (state) {
    case 'saving': return 'Saving…';
    case 'saved': return 'Saved';
    case 'retrying': return 'Could not save, retrying';
    case 'failed': return 'Could not save';
    default: return '';
  }
}

/** Before the page's own scripts: a page that reads localStorage at load must not die on
 *  an about:blank document that has none. An in-memory stand-in, never persisted. */
export const STORAGE_SHIM = `(function () {
  try { window.localStorage.getItem('x'); return; } catch (e) {}
  var store = {};
  var shim = {
    getItem: function (k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
    setItem: function (k, v) { store[k] = String(v); },
    removeItem: function (k) { delete store[k]; },
    clear: function () { store = {}; },
    key: function (i) { return Object.keys(store)[i] || null; },
    get length() { return Object.keys(store).length; }
  };
  try { Object.defineProperty(window, 'localStorage', { configurable: true, value: shim }); } catch (e) {}
})();
true;`;

/** Ask the page to post every box still inside its debounce, then {type:'flushed'}. */
export const FLUSH_SCRIPT = 'window.__ftfFlush && window.__ftfFlush(); true;';

/** The bridge, injected after the document loads. Generic: any page that follows the
 *  contract works. Fills each box from `notes` and fires `input` (so the page's own
 *  counters update), then posts each change ({type:'note', k, label, v}) 600 ms after the
 *  last keystroke in that box, at once on blur, and on __ftfFlush. Hides #exportBtn and
 *  #clearBtn (browser download and local storage do not apply in the app). */
export function bridgeScript(notes: Record<string, string>): string {
  const clean: Record<string, string> = {};
  for (const [k, v] of Object.entries(notes || {})) {
    if (typeof v === 'string' && k.length > 0 && k.length <= MAX_KEY_CHARS) clean[k] = v;
  }
  const json = JSON.stringify(clean)
    .replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029').replace(/</g, '\\u003c');
  return `(function () {
  if (window.__ftfPages) { return; }
  window.__ftfPages = true;
  var NOTES = ${json};
  var MAX_KEY = ${MAX_KEY_CHARS}, MAX_LABEL = ${MAX_LABEL_CHARS}, MAX_BODY = ${MAX_BODY_CHARS}, WAIT = ${PAGE_DEBOUNCE_MS};
  var timers = {};
  function post(m) { if (window.ReactNativeWebView) { window.ReactNativeWebView.postMessage(JSON.stringify(m)); } }
  function isBox(el) { return !!el && el.tagName === 'TEXTAREA' && el.hasAttribute('data-k'); }
  function keyOf(el) { var k = el.getAttribute('data-k') || ''; return k.length > 0 && k.length <= MAX_KEY ? k : null; }
  function send(el) {
    var k = keyOf(el);
    if (k === null) { return; }
    if (timers[k]) { clearTimeout(timers[k].t); delete timers[k]; }
    post({ type: 'note', k: k, label: String(el.getAttribute('data-label') || '').slice(0, MAX_LABEL),
           v: String(el.value).slice(0, MAX_BODY) });
  }
  function later(el) {
    var k = keyOf(el);
    if (k === null) { return; }
    if (timers[k]) { clearTimeout(timers[k].t); }
    timers[k] = { el: el, t: setTimeout(function () { send(el); }, WAIT) };
  }
  window.__ftfFlush = function () {
    Object.keys(timers).forEach(function (k) { send(timers[k].el); });
    post({ type: 'flushed' });
  };
  ['exportBtn', 'clearBtn'].forEach(function (id) {
    var b = document.getElementById(id);
    if (b) { b.style.display = 'none'; }
  });
  var boxes = document.querySelectorAll('textarea[data-k]');
  for (var i = 0; i < boxes.length; i++) {
    var el = boxes[i], k = keyOf(el);
    if (!el.hasAttribute('maxlength')) { el.maxLength = MAX_BODY; }
    if (k !== null && Object.prototype.hasOwnProperty.call(NOTES, k)) {
      el.value = NOTES[k];
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }
  document.addEventListener('input', function (e) { if (isBox(e.target)) { later(e.target); } }, true);
  document.addEventListener('focusout', function (e) {
    var k = isBox(e.target) ? keyOf(e.target) : null;
    if (k !== null && timers[k]) { send(e.target); }
  }, true);
})();
true;`;
}
