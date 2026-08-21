#!/usr/bin/env node
// Counterparty-breaker hesitation element guard
// (docs/plans/counterparty-breaker/LLD.md §1.8 + §7.5).
//
// WHY THIS EXISTS. The breaker ships behind two default-off flags
// (`trade.breaker`, `trade.breaker_narrative`) and the client has NO flag read
// of its own: the server serializes the `breaker` key ONLY for a card whose
// top objection was actually narrated, so **payload presence IS the gate**
// (LLD §1.5 — during the dark-stamp window the key is absent entirely). That
// design is only safe while four properties hold in the source, and D-056
// retired the simulator, so nothing else checks them:
//
//   • The element renders ONLY under `data.breaker?.sentence`. An
//     unconditional render, or a gate on `data.breaker` alone, would put an
//     empty hint row on every card of a flag-on deck.
//   • The optional chaining is the null-safety. A `data.breaker.sentence`
//     gate (or a `!` assertion) crashes the whole card on every legacy
//     payload — the key is absent on the overwhelming majority of cards.
//   • The card shows the server-composed SENTENCE and nothing else. `code`
//     and `severity` are dark-class analysis internals; rendering either
//     ships the taxonomy to users as inspectable data, which is exactly what
//     the narration gate exists to prevent. The fixed lead-in label
//     ("Their likely hesitation:") lives in the server template table
//     (LLD §1.6) — a client-side copy of it would fork the wording from
//     `HESITATION_TMPL_VERSION`, which the A/B readout keys on.
//   • Colors come from Chalkline tokens, with the informational dot on
//     `flare` (ADR-005: ice = actions, flare = worth noticing). A hex literal
//     here is invisible to the palette and to the contrast guard.
//
// What is pinned:
//   1. The element is gated on `data.breaker?.sentence` — no unconditional
//      render path, and every read of `data.breaker.sentence` sits inside it.
//   2. Both testIDs are present: `trade-card.breaker-hesitation` and
//      `trade-card.breaker-hesitation.body`.
//   3. The block renders the sentence only — no `code`/`severity` read, and
//      no string-literal copy of its own.
//   4. The new styles reference tokens, not hex literals, and stay within the
//      8px radius rule.
//   5. Null-safety: optional chaining, no non-null assertion on `breaker`.
//   6. The wire type declares `breaker` OPTIONAL with code/severity/sentence.
//   7. No mobile source file references the shadow stamp (it never ships).
//
// Run: node tests/check-breaker-card.js
//   (or: npm run test:breaker-card)
//
// NOTE: CI picks this file up automatically — `.github/workflows/ci.yml`'s
// mobile-typecheck job globs `tests/check-*.js`. No CI edit is needed.

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const CARD = path.join(ROOT, 'src/components/TradeCard.tsx');
const TYPES = path.join(ROOT, 'src/shared/types.ts');

const failures = [];
const checks = [];

function ok(name) { checks.push(name); }
function fail(name, detail) { failures.push(`${name}\n      ${detail}`); }

function read(p) {
  if (!fs.existsSync(p)) {
    fail('file exists', `missing: ${path.relative(ROOT, p)}`);
    return '';
  }
  return fs.readFileSync(p, 'utf8');
}

// Balanced-delimiter matcher — the house idiom for pulling one JSX/object
// block out of a big file without a parser. `openIdx` must point AT the
// opening delimiter. Returns the block including both delimiters, or ''.
function balanced(src, openIdx, open, close) {
  if (src[openIdx] !== open) return '';
  let depth = 0;
  for (let i = openIdx; i < src.length; i++) {
    if (src[i] === open) depth++;
    else if (src[i] === close) {
      depth--;
      if (depth === 0) return src.slice(openIdx, i + 1);
    }
  }
  return '';
}

// Comments are documentation, not behavior — every content assertion runs on
// a comment-stripped copy so a explanatory mention can't satisfy (or trip) it.
function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
}

const cardRaw = read(CARD);
const card = stripComments(cardRaw);
const types = stripComments(read(TYPES));

// ── Locate the element block (shared by checks 1–5) ───────────────────────
const GATE = /\{\s*data\.breaker\?\.sentence\s*&&\s*\(/;
const gateMatch = card.match(GATE);
let block = '';
if (gateMatch) {
  const parenIdx = card.indexOf('(', gateMatch.index + gateMatch[0].length - 1);
  block = balanced(card, parenIdx, '(', ')');
}

// ── 1. Gated on the sentence, with no unconditional render path ───────────
{
  if (!gateMatch) {
    fail('1. element is gated on `data.breaker?.sentence`',
      'no `{data.breaker?.sentence && (` guard found in TradeCard.tsx. The server ' +
      'omits the `breaker` key entirely except on narrated cards — payload ' +
      'presence IS the gate (LLD §1.5). Gating on `data.breaker` alone renders an ' +
      'empty hint row on every card of a flag-on deck; not gating at all renders ' +
      'it on every card ever served.');
  } else if (!block) {
    fail('1. element is gated on `data.breaker?.sentence`',
      'the guard was found but its JSX block is unbalanced — cannot verify the ' +
      'render is contained by it');
  } else {
    ok('1. element is gated on `data.breaker?.sentence`');
  }

  // Every read of the sentence must live inside that one block.
  const reads = [];
  const re = /data\.breaker\.sentence/g;
  let m;
  while ((m = re.exec(card)) !== null) reads.push(m.index);
  const blockStart = block ? card.indexOf(block) : -1;
  const outside = reads.filter(
    (i) => blockStart < 0 || i < blockStart || i >= blockStart + block.length,
  );
  if (outside.length) {
    fail('1b. no ungated read of the sentence',
      `${outside.length} read(s) of \`data.breaker.sentence\` sit outside the ` +
      'gated block. Every render of the hesitation line must be inside the ' +
      'single presence gate — a second, differently-gated render is a second ' +
      'gate that can only disagree with the first.');
  } else {
    ok('1b. no ungated read of the sentence');
  }
}

// ── 2. testIDs ────────────────────────────────────────────────────────────
{
  const wanted = ['trade-card.breaker-hesitation', 'trade-card.breaker-hesitation.body'];
  const missing = wanted.filter((id) => !card.includes(`"${id}"`) && !card.includes(`'${id}'`));
  if (missing.length) {
    fail('2. both testIDs are present',
      `missing testID(s): ${missing.join(', ')}. These follow the repo dot idiom ` +
      '(`trade-card.consensus-note` precedent) and are what any future check or ' +
      'manual TestFlight pass addresses the element by. Renaming them requires ' +
      'updating LLD §1.8 and this guard in the same commit.');
  } else if (block && !/testID=["']trade-card\.breaker-hesitation["']/.test(block)) {
    fail('2b. the container testID is on the gated element',
      '`trade-card.breaker-hesitation` exists in the file but not inside the ' +
      'gated block — an id on an ungated node defeats the point.');
  } else {
    ok('2. both testIDs are present, on the gated element');
  }
}

// ── 3. Sentence only — no code/severity, no client-side copy ──────────────
{
  if (!block) {
    fail('3. renders the sentence only', 'element block not located (see check 1)');
  } else {
    const internals = /data\.breaker\??\.(code|severity|objections|top|narrated|suppressed)/
      .exec(block);
    if (internals) {
      fail('3a. no raw analysis values are rendered',
        `the element reads \`${internals[0]}\`. Only \`sentence\` may reach the UI: ` +
        'the objection codes and severities are dark-class internals, and shipping ' +
        'them as inspectable data is precisely what the narration gate exists to ' +
        'prevent (LLD §1.5). The client must never switch on `code` — ' +
        'cross-client-invariants keeps that row "n/a in v1".');
    } else {
      ok('3a. no raw code/severity values are rendered');
    }

    // Any multi-word string literal in the block is client-authored copy.
    // testIDs and style keys have no spaces, so this is a clean separator.
    const lits = (block.match(/(["'])(?:(?!\1)[^\\]|\\.)*\1/g) || [])
      .filter((s) => /\s/.test(s.slice(1, -1)));
    if (lits.length) {
      fail('3b. no client-side sentence copy',
        `found literal copy in the element: ${lits.join(', ')}. Every word the ` +
        'user sees — including the fixed "Their likely hesitation:" lead-in — is ' +
        'server-composed from the LLD §1.6 template table and versioned by ' +
        '`HESITATION_TMPL_VERSION`. A client-side copy forks the wording from the ' +
        'version the A/B readout keys on, silently.');
    } else {
      ok('3b. no client-side sentence copy');
    }

    if (!/\{\s*data\.breaker\.sentence\s*\}/.test(block)) {
      fail('3c. the text node interpolates the sentence',
        'the gated block never renders `{data.breaker.sentence}` — the element ' +
        'would show nothing, or something other than the server sentence.');
    } else {
      ok('3c. the text node interpolates the sentence');
    }
  }
}

// ── 4. Chalkline tokens, not hex literals; radius within spec ─────────────
{
  const styleNames = ['breakerRow', 'breakerDot'];
  const bodies = [];
  for (const name of styleNames) {
    const at = card.search(new RegExp(`\\b${name}\\s*:\\s*\\{`));
    if (at < 0) {
      fail('4. the new styles exist', `\`styles.${name}\` not found in TradeCard.tsx`);
      continue;
    }
    bodies.push([name, balanced(card, card.indexOf('{', at), '{', '}')]);
  }
  if (bodies.length === styleNames.length) {
    const hexed = bodies.filter(([, b]) => /#[0-9a-fA-F]{3,8}\b/.test(b));
    if (hexed.length) {
      fail('4a. no hex literals in the new styles',
        `hex color(s) in: ${hexed.map(([n]) => n).join(', ')}. Colors come from ` +
        '`theme/chalkline.ts` by reference — a literal is invisible to the palette ' +
        'and to the contrast guard. The informational dot is `flare.base` ' +
        '(ADR-005: ice = actions, flare = worth noticing).');
    } else {
      ok('4a. no hex literals in the new styles');
    }

    const dot = bodies.find(([n]) => n === 'breakerDot');
    if (dot && !/flare\.\w+/.test(dot[1])) {
      fail('4b. the informational dot uses the flare token',
        '`breakerDot` does not reference a `flare.*` token. The hesitation line is ' +
        'informational, never an action — ice is reserved for actions (ADR-005).');
    } else {
      ok('4b. the informational dot uses the flare token');
    }

    const bad = [];
    for (const [n, b] of bodies) {
      const r = /borderRadius\s*:\s*([0-9.]+)/.exec(b);
      if (r && Number(r[1]) > 8) bad.push(`${n}=${r[1]}`);
    }
    if (bad.length) {
      fail('4c. radius stays within the 8px rule',
        `${bad.join(', ')} — Chalkline allows no border-radius above 8px except ` +
        'true pills, and this row is not a pill (docs/design/design-system.md).');
    } else {
      ok('4c. radius stays within the 8px rule');
    }
  }
}

// ── 5. Null-safety pattern ────────────────────────────────────────────────
{
  const bang = /data\.breaker!/.test(card);
  const cast = /data\.breaker\s+as\s+/.test(card);
  if (bang || cast) {
    fail('5. null-safe access only',
      `found ${bang ? 'a non-null assertion (`data.breaker!`)' : ''}` +
      `${bang && cast ? ' and ' : ''}${cast ? 'a type assertion on `data.breaker`' : ''}. ` +
      'The key is ABSENT on every flag-off card, every dark-window card, and every ' +
      'card whose objection was suppressed — which is the overwhelming majority of ' +
      'cards ever rendered. Optional chaining is the only safe read; an assertion ' +
      'turns a normal payload into a crashed card.');
  } else if (!gateMatch) {
    fail('5. null-safe access only',
      'the optional-chaining gate `data.breaker?.sentence` is absent (see check 1)');
  } else {
    ok('5. null-safe access only (optional chaining, no assertions)');
  }
}

// ── 6. The wire type declares `breaker` optional ──────────────────────────
{
  const at = types.search(/\bbreaker\?\s*:/);
  if (at < 0) {
    if (/\bbreaker\s*:/.test(types)) {
      fail('6. `breaker` is declared OPTIONAL',
        'src/shared/types.ts declares `breaker` as REQUIRED. It is serialized only ' +
        'for narrated cards; a required field makes every legacy/dark-window ' +
        'payload a type lie and invites the non-null reads check 5 bans.');
    } else {
      fail('6. `breaker` is declared on the card payload type',
        'src/shared/types.ts has no `breaker?:` member on the trade-card type. New ' +
        "wire fields belong there and must match the backend's JSON " +
        '(docs/api-reference.md).');
    }
  } else {
    const body = balanced(types, types.indexOf('{', at), '{', '}');
    const missing = ['code', 'severity', 'sentence'].filter(
      (k) => !new RegExp(`\\b${k}\\s*[?]?\\s*:`).test(body),
    );
    if (missing.length) {
      fail('6b. the breaker type carries code/severity/sentence',
        `missing key(s): ${missing.join(', ')}. The serialized object is exactly ` +
        '{code, severity, sentence} (LLD §1.5) — the type mirrors the wire shape ' +
        'even though the UI reads only `sentence`.');
    } else {
      ok('6. `breaker` is optional and carries code/severity/sentence');
    }
  }
}

// ── 7. The shadow stamp never reaches the client ──────────────────────────
{
  // Split so this guard's own source is not a hit for itself.
  const SHADOW = 'breaker_' + 'shadow';
  const SKIP = new Set(['node_modules', 'ios', 'android', '.expo', 'build', '.maestro']);
  const hits = [];
  (function walk(dir) {
    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const full = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (!SKIP.has(e.name)) walk(full);
      } else if (/\.(ts|tsx|js|jsx)$/.test(e.name) && full !== __filename) {
        // A comment naming the field is documentation ("never serialized")
        // and is welcome; what must not exist is a code reference.
        if (stripComments(fs.readFileSync(full, 'utf8')).includes(SHADOW)) {
          hits.push(path.relative(ROOT, full));
        }
      }
    }
  })(path.join(ROOT, 'src'));
  (function walkTests() {
    let entries;
    try { entries = fs.readdirSync(path.join(ROOT, 'tests'), { withFileTypes: true }); }
    catch { return; }
    for (const e of entries) {
      const full = path.join(ROOT, 'tests', e.name);
      if (e.isFile() && /\.js$/.test(e.name) && full !== __filename
          && stripComments(fs.readFileSync(full, 'utf8')).includes(SHADOW)) {
        hits.push(path.relative(ROOT, full));
      }
    }
  })();
  if (hits.length) {
    fail(`7. no mobile file references \`${SHADOW}\``,
      `found in: ${hits.join(', ')}. The shadow stamp is a backend-only ` +
      'counterfactual, never serialized to any client ' +
      '(test_breaker_shadow_never_serialized). A client reference means either ' +
      'the serializer leaked it or someone is about to render it.');
  } else {
    ok(`7. no mobile file references \`${SHADOW}\``);
  }
}

// ── Report ────────────────────────────────────────────────────────────────
console.log(`\ncheck-breaker-card: ${checks.length} passed, ${failures.length} failed`);
for (const c of checks) console.log(`  ✓ ${c}`);
if (failures.length) {
  console.error('\nFAILURES:');
  for (const f of failures) console.error(`  ✗ ${f}`);
  console.error(
    '\nThese pin the counterparty-breaker client contract ' +
    '(docs/plans/counterparty-breaker/LLD.md §1.8, §7.5). The element has no ' +
    'flag read of its own — payload presence is the whole gate — so these ' +
    'source properties are what keep a dark-window or legacy payload rendering ' +
    'nothing. If a change here is genuinely intended, update the LLD and this ' +
    'guard in the SAME commit.\n');
  process.exit(1);
}
console.log('');
