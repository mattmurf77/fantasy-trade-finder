#!/usr/bin/env node
// check-share-trade-token — build O8 (unguessable share links for trades).
//
// WHY THIS EXISTS
// /s/trade/<x> and /og/trade/<x>.png used to take the sequential
// trade_matches.id with no auth, so anyone could walk the ids and read every
// mutual match's give/get and fairness verdict. The server now resolves those
// routes ONLY through a 128-bit token minted by POST /api/share/trade, and
// answers every numeric id with a generic "expired" page. A client that goes
// back to building /s/trade/<match_id> would not reopen the hole (the server
// refuses the id), but every link it shared would be dead on arrival — and
// the old code did exactly that in two clients. The server half is pinned by
// backend/tests/test_trade_share_tokens.py; this pins the client half.
//
// Asserts:
//   1. No file under mobile/src, web/js or extension/ builds /s/trade/ (or
//      /og/trade/) followed by an interpolated (`${…}`) or concatenated
//      (' + …) value. A share link's path segment must come from the server.
//   2. TradesScreen's shareLikedTrade gets the matched-trade link from
//      resolveTradeShareUrl (utils/shareLinks.ts → api/share.ts →
//      POST /api/share/trade) and keeps the package rung as its fallback.
//   3. rewriteUniversalPath maps /s/trade/<anything> to app/matches with NO id
//      segment (the token is not a match id), keeping the query suffix.
//      EXECUTED: the function is lifted out of deepLinks.ts and run.
//
// HONEST LABEL: 1 and 2 prove the absence/presence of exact wirings by
// pattern, not runtime behaviour; 3 is behavioural. Runtime proof is the
// operator TestFlight checklist in docs/plans/share-link-tokens/scope.md.
//
// Run: node tests/check-share-trade-token.js   (npm run test:share-trade-token)

'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const REPO = path.join(MOBILE, '..');
const read = (rel) => fs.readFileSync(path.join(REPO, rel), 'utf8');
const stripComments = (src) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:"'`])\/\/[^\n]*/g, '$1');

let failures = 0;
let checks = 0;
const ok = (name) => console.log(`PASS  ${name}`);
const fail = (name, detail) => {
  failures += 1;
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
};
const assert = (cond, name, detail) => {
  checks += 1;
  return cond ? ok(name) : fail(name, detail);
};

/** The `{…}` body that starts at the first `{` at or after `from`. */
function braceBody(src, from) {
  const open = src.indexOf('{', from);
  if (open === -1) return null;
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

// ── 1. No client builds /s/trade/<value> ─────────────────────────────────
{
  const ROOTS = ['mobile/src', 'web/js', 'extension'];
  const EXT = /\.(ts|tsx|js|jsx|mjs|cjs|html)$/;
  const BUILT = /\/(?:s|og)\/trade\/?(?:\$\{|['"`]\s*\+)/;
  const files = [];
  const walk = (rel) => {
    const abs = path.join(REPO, rel);
    if (!fs.existsSync(abs)) return;
    for (const ent of fs.readdirSync(abs, { withFileTypes: true })) {
      if (ent.name === 'node_modules' || ent.name.startsWith('.')) continue;
      const child = path.join(rel, ent.name);
      if (ent.isDirectory()) walk(child);
      else if (EXT.test(ent.name)) files.push(child);
    }
  };
  ROOTS.forEach(walk);
  const offenders = [];
  for (const f of files) {
    stripComments(read(f)).split('\n').forEach((line, i) => {
      if (BUILT.test(line)) offenders.push(`${f}:${i + 1}: ${line.trim()}`);
    });
  }
  assert(files.length > 50, `1a. scanned ${files.length} client files under ${ROOTS.join(', ')}`,
    'the walk found almost nothing — did a root move?');
  assert(offenders.length === 0,
    '1b. no client builds /s/trade/ or /og/trade/ from an interpolated or concatenated value',
    offenders.join(' | '));
}

// ── 2. shareLikedTrade goes through resolveTradeShareUrl ─────────────────
{
  const SCREEN = stripComments(read('mobile/src/screens/TradesScreen.tsx'));
  const at = SCREEN.indexOf('async function shareLikedTrade(');
  const body = at === -1 ? null : braceBody(SCREEN, at);
  assert(body !== null, '2a. TradesScreen defines async function shareLikedTrade');
  const flat = (body || '').replace(/\s+/g, ' ');
  assert(/await resolveTradeShareUrl\(matchId\)/.test(flat),
    '2b. shareLikedTrade awaits resolveTradeShareUrl(matchId)');
  assert(/url = `\$\{tradeUrl\}/.test(flat) && /const tradeUrl = [^;]*resolveTradeShareUrl\(/.test(flat),
    '2c. the matched-trade url is the server-minted link (tradeUrl), not a client-built path');
  assert(/else if \(tradeUrl\)/.test(flat) && /await resolveShareUrl\(/.test(flat),
    '2d. a failed trade mint (null) falls through to the package rung (resolveShareUrl)');
  assert(/import \{[^}]*\bresolveTradeShareUrl\b[^}]*\} from '\.\.\/utils\/shareLinks';/.test(SCREEN),
    '2e. TradesScreen imports resolveTradeShareUrl from utils/shareLinks');

  const LINKS = stripComments(read('mobile/src/utils/shareLinks.ts')).replace(/\s+/g, ' ');
  const fnAt = LINKS.indexOf('export async function resolveTradeShareUrl(');
  const fn = fnAt === -1 ? '' : braceBody(LINKS, LINKS.indexOf(')', fnAt)) || '';
  assert(/await createTradeShare\(matchId/.test(fn) && /return `\$\{getBaseUrl\(\)\}\$\{res\.url\}`/.test(fn),
    '2f. resolveTradeShareUrl returns getBaseUrl() + the url the server returned');
  const API = stripComments(read('mobile/src/api/share.ts'));
  assert(/apiRequest<[\s\S]*?>\('\/api\/share\/trade'/.test(API) && /match_id: matchId/.test(API),
    '2g. api/share.ts posts {match_id} to /api/share/trade');
}

// ── 3. rewriteUniversalPath: /s/trade/* → app/matches, no id ─────────────
{
  const DL = read('mobile/src/utils/deepLinks.ts');
  const sig = 'export function rewriteUniversalPath(pathWithQuery: string): string';
  const at = DL.indexOf(sig);
  const body = at === -1 ? null : braceBody(DL, at + sig.length);
  assert(body !== null, '3a. rewriteUniversalPath found with its known signature');
  let rewrite = null;
  try {
    // eslint-disable-next-line no-new-func
    rewrite = new Function('pathWithQuery', body.slice(1, -1));
  } catch (e) {
    fail('3b. rewriteUniversalPath body runs as plain JS', String(e));
  }
  if (rewrite) {
    const cases = [
      ['/s/trade/AbC_-1234567890123456Xy', 'app/matches'],
      ['/s/trade/AbC_-1234567890123456Xy?ref=bob', 'app/matches?ref=bob'],
      ['s/trade/12345', 'app/matches'],
      ['/s/trade/12345/', 'app/matches'],
      ['/s/trade/tok#frag', 'app/matches#frag'],
      ['/s/p/abc123?ref=bob', 'app/trades?ref=bob'],
      ['/leagues', '/leagues'],
    ];
    const bad = cases
      .map(([input, want]) => [input, want, rewrite(input)])
      .filter(([, want, got]) => got !== want)
      .map(([input, want, got]) => `${input} → ${got} (want ${want})`);
    assert(bad.length === 0,
      '3b. /s/trade/<x> → app/matches (no id, query kept); /s/p and others unchanged',
      bad.join(' | '));
  }
}

console.log(failures ? `\n${failures} FAILURE(S) of ${checks}` : `\nALL CHECKS PASSED (${checks})`);
process.exit(failures ? 1 : 0);
