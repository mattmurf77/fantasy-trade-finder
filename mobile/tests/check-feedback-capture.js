#!/usr/bin/env node
// Feedback capture — the long-note loss guard (2026-08-22 incident).
//
// WHY THIS EXISTS. A real operator report was typed into the feedback sheet,
// exceeded the server's text cap, and vanished. Four independent failures had
// to line up, and NONE of them fails a typecheck, a backend test, or a
// runtime smoke pass — the app looked like it worked:
//
//   1. The compose sheet had no character counter and no cap awareness, so
//      the user had no way to know the note was already too long.
//   2. Save was enabled at any length, so an over-cap note could be
//      submitted.
//   3. `onSave` cleared the draft UNCONDITIONALLY, immediately after a
//      fire-and-forget `add()`. The note left the screen whether or not it
//      ever reached the server.
//   4. `useFeedback.add()` synced in a `void (async () => ...)` IIFE and
//      returned the PRE-sync item, so no caller could have checked the
//      outcome even if it wanted to. The local copy survived with
//      `synced:false`, but a 400 is permanent — `retrySync()` re-POSTs it
//      forever and it is never delivered.
//
// The highest-value assertion here is #2: the client's shared max constant
// and the server's `len(text_body) >` limit must be the SAME NUMBER. Those
// two live in different languages, different directories, and different
// deploy cadences (the client ships through TestFlight, the server through
// Render). Nothing else in the repo notices when they drift, and drift in
// the wrong direction reproduces the original defect exactly: a client that
// happily accepts what the server will reject.
//
// HONEST LABEL (G-035): this proves the presence of exact wirings — an
// exported constant, a counter bound to it, a `disabled` expression that
// mentions it, a guarded `setText('')`, an awaited sync — NOT that the
// rendered counter reads correctly or that a 9,000-character note is
// actually refused on a device. Runtime proof is the manual TestFlight
// checklist in docs/plans/feedback-capture-cap/scope.md.
//
// Dependency-free: fs + source-shape parsing, no typescript, no jest.
// Run: node tests/check-feedback-capture.js  (or npm run test:feedback-capture)
// CI picks it up automatically via the tests/check-*.js glob.

'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.resolve(__dirname, '..');
const REPO = path.resolve(MOBILE, '..');

const SHEET = path.join(MOBILE, 'src/components/FeedbackSheet.tsx');
const API = path.join(MOBILE, 'src/api/feedback.ts');
const STORE = path.join(MOBILE, 'src/state/useFeedback.ts');
const SERVER = path.join(REPO, 'backend/server.py');

const pass = [];
const fail = [];
const ok = (n) => pass.push(n);
const bad = (n, why) => fail.push(`${n}\n      ${why}`);

function read(p) {
  if (!fs.existsSync(p)) {
    bad('file exists', `missing ${path.relative(REPO, p)}`);
    return '';
  }
  return fs.readFileSync(p, 'utf8');
}

// Comment-stripped view. Every assertion below runs against this, so a
// number or a call site mentioned in prose can never satisfy a check.
const strip = (s) =>
  s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const sheetRaw = read(SHEET);
const sheet = strip(sheetRaw);
const api = strip(read(API));
const store = strip(read(STORE));
const server = read(SERVER); // python: `#` comments, no /* */; docstrings kept

// Balanced-brace slice starting at the `{` at or after `from`.
function block(src, from) {
  const open = src.indexOf('{', from);
  if (open < 0) return null;
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === '{') depth += 1;
    else if (src[i] === '}') {
      depth -= 1;
      if (depth === 0) return src.slice(open, i + 1);
    }
  }
  return null;
}

// The value of a JSX prop, brace-balanced so a nested object/array literal
// doesn't truncate it. Returns null when the prop is absent.
function propExpr(tag, name) {
  const m = tag.match(new RegExp(`\\b${name}\\s*=\\s*\\{`));
  if (!m) return null;
  const b = block(tag, m.index);
  return b === null ? null : b.slice(1, -1);
}

// The CHILDREN of the first <Text> …</Text> whose rendered content satisfies
// `test`. Attributes are excluded on purpose: a counter that exists only as
// an accessibilityLabel is not a counter the sighted user can see.
function textChildren(src) {
  const out = [];
  const OPEN = /<Text\b/g;
  let m;
  while ((m = OPEN.exec(src)) !== null) {
    // Walk the opening tag to its `>` at brace depth 0.
    let depth = 0;
    let i = m.index;
    for (; i < src.length; i += 1) {
      if (src[i] === '{') depth += 1;
      else if (src[i] === '}') depth -= 1;
      else if (src[i] === '>' && depth === 0) break;
    }
    if (src[i - 1] === '/') continue; // self-closing, no children
    const close = src.indexOf('</Text>', i);
    if (close > 0) out.push(src.slice(i + 1, close));
  }
  return out;
}

// Identifiers whose (single-statement) initializer mentions something
// matching `re` — one indirection level, applied twice so short chains
// resolve. This is what lets a sheet say `overLimit` / `MAX_LABEL` instead of
// spelling FEEDBACK_TEXT_MAX at every use site, without letting it launder a
// hardcoded number through a local.
function derivedNames(src, re) {
  const names = new Set();
  for (let pass = 0; pass < 2; pass += 1) {
    const seen = names.size;
    const alt = names.size ? `|${[...names].join('|')}` : '';
    const probe = new RegExp(`(?:${re.source}${alt})`);
    for (const m of src.matchAll(
      /(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*([^;\n]+)/g,
    )) {
      if (probe.test(m[2])) names.add(m[1]);
    }
    if (names.size === seen) break;
  }
  return names;
}

const tokenRe = (base, names) =>
  new RegExp(`\\b(?:${[base, ...names].join('|')})\\b`);

// ── 1. The shared max constant exists and is exported ────────────────────
let clientMax = null;
{
  const m = api.match(
    /export\s+const\s+FEEDBACK_TEXT_MAX\s*(?::\s*number)?\s*=\s*(\d+)/,
  );
  if (!m) {
    bad(
      '1. FEEDBACK_TEXT_MAX is exported from src/api/feedback.ts',
      'no `export const FEEDBACK_TEXT_MAX = <number>` found. The cap has to ' +
        'live in ONE place the sheet, the store, and this guard can all read. ' +
        'A number typed into the sheet is how the counter and the server ' +
        'silently disagree — which is the 2026-08-22 defect.',
    );
  } else {
    clientMax = Number(m[1]);
    ok(`1. FEEDBACK_TEXT_MAX exported from src/api/feedback.ts (= ${clientMax})`);
  }
}

// ── 2. Client constant == server-side limit (the cross-file pin) ─────────
{
  // The server may spell the cap as a literal or as its own module constant.
  // Resolve one level of naming so either shape is readable, and so a
  // rename cannot quietly turn this assertion into a no-op.
  const pyConsts = new Map();
  for (const m of server.matchAll(/^([A-Z][A-Z0-9_]*)\s*=\s*(\d+)\s*$/gm)) {
    pyConsts.set(m[1], Number(m[2]));
  }
  const resolve = (tok) =>
    tok === undefined ? null
      : /^\d+$/.test(tok) ? Number(tok)
      : pyConsts.has(tok) ? pyConsts.get(tok)
      : null;

  const cmp = server.match(/len\(\s*text_body\s*\)\s*>\s*([A-Za-z_0-9]+)/);
  const payload = server.match(
    /"text_too_long"[\s\S]{0,120}?"limit"\s*:\s*([A-Za-z_0-9]+)/,
  );
  const serverCmp = resolve(cmp && cmp[1]);
  const serverPayload = resolve(payload && payload[1]);

  if (serverCmp === null) {
    bad(
      '2a. backend/server.py still enforces a text cap',
      'no `if len(text_body) > <number>` in POST /api/feedback. Either the ' +
        'validation moved (re-point this guard at it) or it was deleted — in ' +
        'which case an unbounded note now reaches the database.',
    );
  } else if (serverPayload === null) {
    bad(
      '2b. the 400 names the limit it enforced',
      'found `len(text_body) > ' +
        serverCmp +
        '` but no matching `{"error": "text_too_long", "limit": N}` response. ' +
        'A client that is told a cap was hit but not WHICH cap cannot show a ' +
        'useful message.',
    );
  } else if (serverCmp !== serverPayload) {
    bad(
      '2c. the server agrees with itself',
      `enforces > ${serverCmp} but reports limit ${serverPayload}. The 400 ` +
        'body is the client\'s only machine-readable account of the rule; a ' +
        'wrong number there sends the user to trim to the wrong length.',
    );
  } else if (clientMax === null) {
    bad(
      '2d. client and server caps agree',
      `server enforces ${serverCmp} but there is no client constant to ` +
        'compare it against (assertion 1 failed). Until FEEDBACK_TEXT_MAX ' +
        'exists the two can only agree by luck.',
    );
  } else if (clientMax !== serverCmp) {
    bad(
      '2e. client and server caps agree',
      `FEEDBACK_TEXT_MAX = ${clientMax} but backend/server.py rejects above ` +
        `${serverCmp}. This is the exact 2026-08-22 failure mode: the sheet ` +
        'accepts a note the server refuses with a permanent 400, the local ' +
        'copy retries forever, and the report is never delivered. Change ' +
        'BOTH numbers, in the same PR, and update docs/api-reference.md.',
    );
  } else {
    ok(
      `2. client FEEDBACK_TEXT_MAX == backend/server.py cap == 400 payload ` +
        `limit (${clientMax})`,
    );
  }
}

// Locals in the sheet derived from the shared max / from the live note
// length. Computed once — assertions 3 and 4 both read them.
const MAX_NAMES = derivedNames(sheet, /\bFEEDBACK_TEXT_MAX\b/);
const LEN_NAMES = derivedNames(sheet, /\.length\b/);
const MAX_TOKEN = tokenRe('FEEDBACK_TEXT_MAX', MAX_NAMES);
const LEN_TOKEN = new RegExp(
  `\\.length\\b${LEN_NAMES.size ? `|\\b(?:${[...LEN_NAMES].join('|')})\\b` : ''}`,
);

// ── 3. The sheet renders a counter driven by the constant ────────────────
{
  const imported =
    /import\s*\{[^}]*\bFEEDBACK_TEXT_MAX\b[^}]*\}\s*from\s*['"][^'"]*api\/feedback['"]/.test(
      sheet,
    );
  // A counter is a rendered <Text> whose CHILDREN show both the live length
  // and the shared max. Checking that the two tokens exist somewhere in the
  // file is not enough — the constant could be used only by the Save gate
  // while the user still sees no count.
  const counter = textChildren(sheet).find(
    (c) => LEN_TOKEN.test(c) && MAX_TOKEN.test(c),
  );

  if (!imported) {
    bad(
      '3a. FeedbackSheet imports the shared max',
      'FeedbackSheet.tsx does not import FEEDBACK_TEXT_MAX from ../api/feedback.',
    );
  } else if (!counter) {
    bad(
      '3b. a character counter is RENDERED from the shared max',
      'no <Text> whose children show both the note length and the cap ' +
        `(length tokens: .length, ${[...LEN_NAMES].join(', ') || 'none'}; ` +
        `max tokens: FEEDBACK_TEXT_MAX, ${[...MAX_NAMES].join(', ') || 'none'}). ` +
        'The user has to be able to watch the note approach the cap — a ' +
        'silent maxLength that truncates, or a disabled Save with no ' +
        'explanation, both lose the note without telling anyone.',
    );
  } else if (
    clientMax !== null &&
    new RegExp(`(?<![\\w.])${clientMax}(?![\\w])`).test(sheet)
  ) {
    bad(
      '3c. the counter uses the constant, not a copy of the number',
      `the literal ${clientMax} appears in FeedbackSheet.tsx. Two copies of ` +
        'the cap is one copy too many — the next change to the server limit ' +
        'will update the constant and miss this literal.',
    );
  } else {
    ok('3. character counter rendered from FEEDBACK_TEXT_MAX, no literal copy');
  }
}

// ── 4. Save is gated on the length check ─────────────────────────────────
{
  const idx = sheet.indexOf('testID="feedback.save-btn"');
  const tagStart = idx < 0 ? -1 : sheet.lastIndexOf('<Button', idx);
  const tagEnd = tagStart < 0 ? -1 : sheet.indexOf('/>', idx);
  const btn = tagStart < 0 || tagEnd < 0 ? '' : sheet.slice(tagStart, tagEnd);
  const disabled = propExpr(btn, 'disabled');
  // An emptiness gate, spelled either against the raw text or against a
  // length-derived local (`!noteLength`).
  const emptyGate =
    /!\s*text\.trim\(\)/.test(disabled || '') ||
    /(?:===|==|<)\s*(?:0|1|''|"")/.test(disabled || '') ||
    [...LEN_NAMES].some((n) => new RegExp(`!\\s*${n}\\b`).test(disabled || ''));

  if (tagStart < 0) {
    bad(
      '4a. the Save button exists',
      'no <Button testID="feedback.save-btn"> in FeedbackSheet.tsx.',
    );
  } else if (disabled === null) {
    bad(
      '4b. Save carries a disabled gate',
      'the Save <Button> has no `disabled={...}` prop at all — an empty note ' +
        'and an over-cap note can both be submitted.',
    );
  } else if (!MAX_TOKEN.test(disabled)) {
    bad(
      '4c. Save is disabled past the cap',
      `disabled={${disabled.trim()}} references neither FEEDBACK_TEXT_MAX nor ` +
        `any local derived from it (${[...MAX_NAMES].join(', ') || 'none found'}). ` +
        'A counter that turns red while Save stays live still lets the user ' +
        'submit a note the server will reject with a permanent 400.',
    );
  } else if (!emptyGate) {
    bad(
      '4d. Save is still disabled when empty',
      `disabled={${disabled.trim()}} lost its empty-note check while gaining ` +
        'the length one.',
    );
  } else {
    ok('4. Save disabled on both empty and over-cap notes');
  }
}

// ── 5. onSave clears the draft ONLY on a successful sync ─────────────────
{
  const fnIdx = sheet.search(/async\s+function\s+onSave\s*\(/);
  const body = fnIdx < 0 ? null : block(sheet, fnIdx);

  if (!body) {
    bad(
      '5a. onSave exists',
      'no `async function onSave()` in FeedbackSheet.tsx (renamed? inlined?). ' +
        'Re-point this guard before assuming the guarantee still holds.',
    );
  } else {
    // 5b — the outcome of add() is actually consulted.
    const consulted =
      /(?:const|let)\s+\w+\s*=\s*await\s+add\s*\(/.test(body) ||
      /\(\s*await\s+add\s*\(/.test(body);

    // 5c — every draft clear sits inside a conditional. Depth 1 is the
    // function's own top level, i.e. it runs no matter what add() did.
    const clears = [];
    const CLEAR = /setText\s*\(\s*(?:''|""|`\s*`)\s*\)/g;
    let m;
    while ((m = CLEAR.exec(body)) !== null) {
      const before = body.slice(0, m.index);
      const depth =
        (before.match(/\{/g) || []).length - (before.match(/\}/g) || []).length;
      const inlineIf = /\bif\s*\([^;{}]*\)\s*$/.test(before.replace(/\s+$/, ' '));
      clears.push({ depth, guarded: depth >= 2 || inlineIf });
    }

    if (!consulted) {
      bad(
        '5b. onSave reads the result of add()',
        'the `await add({...})` result is discarded. The 2026-08-22 note was ' +
          'lost precisely here: the sheet closed and the draft was wiped ' +
          'without anyone asking whether the POST landed.',
      );
    } else if (clears.length === 0) {
      bad(
        '5c. onSave clears the draft on success',
        'no setText(\'\') anywhere in onSave — a successful save now leaves ' +
          'the old note in the box and the next report gets appended to it.',
      );
    } else if (clears.some((c) => !c.guarded)) {
      bad(
        '5d. the draft clear is reachable ONLY on a successful sync',
        `${clears.filter((c) => !c.guarded).length} of ${clears.length} ` +
          'setText(\'\') call(s) sit at the top level of onSave, so they run ' +
          'whatever add() reported. That is the defect: an over-cap note ' +
          'gets a permanent 400, and the only copy the user could still ' +
          'copy-paste out is erased from the screen.',
      );
    } else {
      ok('5. onSave consults add() and clears the draft only inside a success branch');
    }
  }
}

// ── 6. useFeedback.add surfaces the sync outcome to its caller ───────────
{
  const addIdx = store.search(/\badd\s*:\s*async\s*\(/);
  const body = addIdx < 0 ? null : block(store, store.indexOf('=>', addIdx));

  if (!body) {
    bad(
      '6a. useFeedback.add exists',
      'no `add: async (entry) => {` in src/state/useFeedback.ts.',
    );
  } else {
    const fireAndForget = /void\s*\(?\s*async/.test(body);
    // The await has to sit at add()'s OWN top level (depth 1). An `await`
    // nested inside a detached IIFE is the defect, not the fix: it settles
    // long after add() has already resolved.
    const syncCall = body.match(/await\s+_syncOne\s*\(/);
    let awaitedInline = false;
    if (syncCall) {
      const before = body.slice(0, syncCall.index);
      awaitedInline =
        (before.match(/\{/g) || []).length -
          (before.match(/\}/g) || []).length ===
        1;
    }
    const returnsPreSyncItem = /return\s+item\s*;/.test(body);

    if (fireAndForget || !awaitedInline) {
      bad(
        '6b. add() awaits the sync instead of firing it into the void',
        `detached \`void (async …)\` IIFE present: ${fireAndForget}; ` +
          `_syncOne awaited in add()'s own body: ${awaitedInline}` +
          (syncCall && !awaitedInline
            ? ' (it is awaited, but nested inside a detached callback, which ' +
              'settles after add() has already resolved)'
            : '') +
          '. While the POST runs detached there is no outcome in scope to ' +
          'return, so onSave cannot possibly hold the draft on failure — ' +
          'assertion 5 becomes unimplementable.',
      );
    } else if (returnsPreSyncItem) {
      bad(
        '6c. add() returns the POST-sync result, not the pre-sync item',
        '`return item;` hands back the object built BEFORE the request, whose ' +
          '`synced` is hardcoded false and whose `server_id` is absent. A ' +
          'caller reading it cannot tell a delivered note from a rejected ' +
          'one — which is how a 400 read as success.',
      );
    } else {
      ok('6. add() awaits the sync and returns the post-sync outcome');
    }
  }
}

// ── Report ───────────────────────────────────────────────────────────────
console.log(
  `\ncheck-feedback-capture: ${pass.length} passed, ${fail.length} failed`,
);
for (const p of pass) console.log(`  ✓ ${p}`);
if (fail.length) {
  console.error('\nFAILURES:');
  for (const f of fail) console.error(`  ✗ ${f}`);
  console.error(
    '\nThese pin the note-loss guarantees from the 2026-08-22 incident ' +
      '(docs/plans/feedback-capture-cap/scope.md). Raising or lowering the cap ' +
      'is a deliberate, two-file change: backend/server.py AND ' +
      'FEEDBACK_TEXT_MAX, plus docs/api-reference.md, in one commit.\n',
  );
  process.exit(1);
}
console.log('');
