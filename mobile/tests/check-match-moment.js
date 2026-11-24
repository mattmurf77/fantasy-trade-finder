#!/usr/bin/env node
// The deck tells the user when their like completed a match (sim pass A).
//
// WHY THIS EXISTS. Release simulator pass, 2026-11-22: account M liked a deck
// card badged "THEY'RE INTERESTED" (owner F had already liked the mirror).
// POST /api/trades/swipe created the mutual match and answered
// `{ matched: true, match_id, partner_name }`; Matches listed "New match with
// @F, just now" for both owners. The deck showed "Liked" and the line
// "1 liked trade awaiting their swipe", which was false twice over:
//   - the client read the reply's `matched` only to remember a share-link id
//     (TradesScreen swipeMutation.onSuccess), so no match moment existed;
//   - GET /api/trades/liked (the line's count) returned every in-session
//     card with decision 'like', matched or not.
//
// What is pinned:
//   1. utils/matchMoment.ts, RUN under plain node: a match reply yields a
//      moment; a non-match reply, a missing id or a non-object yields null;
//      the card's handle wins; a digit-only partner_name (the server's raw-id
//      fallback for a redacted partner) is never printed.
//   2. TradesScreen's swipe onSuccess turns a like's reply into the moment:
//      matchMomentFrom(res, ...) -> setToast with matchMomentLine and an
//      action that navigates to 'Matches' with { match_id, src, ts } (the
//      MatchesScreen arrival a match push uses: scroll + mark).
//   4. Every path that writes or retracts a like (deck swipe, calculator ✓
//      queue, presentation-v2 swipe, Awaiting dismiss) calls
//      state/matchesLists.refreshMatchesLists, which is RUN here against a
//      stub client; a posted standing offer refreshes Matches' list.
//   3. The server leaves a matched like out of /api/trades/liked
//      (matched_package_keys in the route). Behaviour is proven by
//      backend/tests/test_liked_awaiting_after_match.py; this is the
//      cross-client pin that the client's count source is the filtered one.
//
// HONEST LABEL (G-035): §2, §3 and §4b-h prove presence of exact wirings, not
// runtime behaviour; §1 and §4a execute the real modules.
//
// Run: node tests/check-match-moment.js   (or npm run test:match-moment)

'use strict';

const fs = require('fs');
const path = require('path');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

const ROOT = path.resolve(__dirname, '..');
const REPO = path.resolve(ROOT, '..');
const failures = [];
const passes = [];
const ok = (n) => passes.push(n);
const bad = (n, d) => failures.push(`${n}\n      ${d}`);
const check = (n, cond, d = '') => (cond ? ok(n) : bad(n, d || 'condition false'));

function read(rel, base = ROOT) {
  const p = path.join(base, rel);
  if (!fs.existsSync(p)) {
    bad(`file exists: ${rel}`, `missing: ${rel}`);
    return '';
  }
  return fs.readFileSync(p, 'utf8');
}

// ── 1. utils/matchMoment.ts, executed ─────────────────────────────────────
{
  const src = read('src/utils/matchMoment.ts');
  let m = null;
  if (src) {
    try {
      const js = ts.transpileModule(src, {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
      }).outputText;
      const mod = { exports: {} };
      new Function('module', 'exports', 'require', js)(mod, mod.exports, (n) => {
        throw new Error(`matchMoment.ts gained a runtime import ("${n}")`);
      });
      m = mod.exports;
    } catch (e) {
      bad('1. matchMoment.ts loads under plain node', String(e));
    }
  }
  if (m) {
    const reply = { matched: true, match_id: 3, partner_name: 'qa_founder' };
    const a = m.matchMomentFrom(reply, 'qa_founder');
    check('1a. a match reply yields the match id and partner',
      a && a.matchId === '3' && a.partner === 'qa_founder', JSON.stringify(a));
    check('1b. the toast line names the partner like the Matches row does',
      m.matchMomentLine(a) === 'New match with @qa_founder', m.matchMomentLine(a || { partner: null }));
    check('1c. a plain like (matched: false) yields no moment',
      m.matchMomentFrom({ matched: false, trade_id: 'x' }, 'qa_founder') === null);
    check('1d. a reply with no match id yields no moment',
      m.matchMomentFrom({ matched: true }, 'qa_founder') === null);
    check('1e. a missing / non-object reply yields no moment',
      m.matchMomentFrom(undefined) === null && m.matchMomentFrom(null) === null && m.matchMomentFrom('matched') === null);
    const b = m.matchMomentFrom({ matched: true, match_id: '9', partner_name: 'qa_member' });
    check('1f. with no card handle the reply\'s partner_name is used',
      b && b.partner === 'qa_member', JSON.stringify(b));
    const c = m.matchMomentFrom({ matched: true, match_id: 9, partner_name: '910000000000000002' });
    check('1g. a digit-only partner_name (raw id fallback) is never printed',
      c && c.partner === null && m.matchMomentLine(c) === 'New trade match', JSON.stringify(c));
    check('1h. the toast holds long enough to reach its action',
      typeof m.MATCH_MOMENT_HOLD_MS === 'number' && m.MATCH_MOMENT_HOLD_MS >= 5000);
  }
}

// ── 2. TradesScreen wires the reply into the moment ───────────────────────
{
  const s = read('src/screens/TradesScreen.tsx');
  const start = s.indexOf('const swipeMutation = useMutation({');
  const onSuccess = start >= 0 ? s.slice(s.indexOf('onSuccess:', start), s.indexOf('onError:', start)) : '';
  check('2a. swipe onSuccess reads the match off the reply (matchMomentFrom)',
    /const moment = matchMomentFrom\(res, vars\.card\.opponent_username\);/.test(onSuccess),
    'expected `const moment = matchMomentFrom(res, vars.card.opponent_username);` in swipeMutation.onSuccess');
  check('2b. only a like can produce the moment (inside the `like` branch)',
    onSuccess.indexOf("if (vars.decision === 'like') {") >= 0
      && onSuccess.indexOf('matchMomentFrom(') > onSuccess.indexOf("if (vars.decision === 'like') {"));
  check('2c. the moment is a toast with the match line and a Matches action',
    /setToast\(\{\s*msg: matchMomentLine\(moment\),[\s\S]*?action: \{\s*label: MATCH_MOMENT_ACTION,\s*onPress: \(\) => navigation\.navigate\('Matches', \{\s*match_id: moment\.matchId,\s*src: 'deck',\s*ts: Date\.now\(\),/.test(onSuccess),
    'expected setToast({ msg: matchMomentLine(moment), ..., action: { label: MATCH_MOMENT_ACTION, onPress: () => navigation.navigate(\'Matches\', { match_id, src, ts }) } })');
  // Since §4 the refresh is the shared helper, run for EVERY like (a match
  // is one case of it) — see 4a-4d.
  check('2d. Matches and Awaiting are refreshed for the arrival (refreshMatchesLists on a like)',
    /if \(vars\.decision === 'like'\) void refreshMatchesLists\(\);/.test(onSuccess));
  // The arrival contract on the receiving side (MatchesScreen is not edited
  // here; this only confirms the params it reads still exist).
  const matches = read('src/screens/MatchesScreen.tsx');
  check('2e. MatchesScreen still arrives on route.params.match_id + ts',
    /route\.params\?\.match_id != null \? String\(route\.params\.match_id\)/.test(matches)
      && /route\.params\?\.ts != null \? String\(route\.params\.ts\)/.test(matches));
}

// ── 3. The awaiting count's source leaves matched likes out ───────────────
{
  const server = read('backend/server.py', REPO);
  const route = server.slice(server.indexOf('@app.route("/api/trades/liked")'),
    server.indexOf('@app.route("/api/trades/matches")'));
  check('3a. GET /api/trades/liked filters by matched_package_keys',
    /matched = matched_package_keys\(g_user_id, \{c\.league_id for c in cards\}\)/.test(route)
      && /not in matched\]/.test(route));
  const db = read('backend/database.py', REPO);
  check('3b. database.matched_package_keys exists', /\ndef matched_package_keys\(user_id: str, league_ids\) -> set:/.test(db));
}

// ── 4. Every like / unlike path refreshes the Matches lists ───────────────
// Sim pass 2026-11-22 (after §2): a deck like that did NOT complete a match
// left Matches > Awaiting at its old count, across tab switches, until a
// manual pull-to-refresh. Only the matched branch invalidated
// ['awaiting-trades']; the queries stay mounted and nothing refetches them on
// return (refetchOnWindowFocus: false). state/matchesLists.refreshMatchesLists
// is the one helper; every path that writes or retracts a like calls it.
{
  const src = read('src/state/matchesLists.ts');
  let m = null;
  const calls = [];
  if (src) {
    try {
      const js = ts.transpileModule(src, {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
      }).outputText;
      const mod = { exports: {} };
      const fakeClient = { invalidateQueries: (o) => { calls.push(JSON.stringify(o.queryKey)); return Promise.resolve(); } };
      new Function('module', 'exports', 'require', js)(mod, mod.exports, (n) => {
        if (n === './queryClient') return { queryClient: fakeClient };
        throw new Error(`matchesLists.ts gained a runtime import ("${n}")`);
      });
      m = mod.exports;
    } catch (e) {
      bad('4. matchesLists.ts loads under plain node', String(e));
    }
  }
  if (m) {
    const r = m.refreshMatchesLists();
    const want = ['["awaiting-trades"]', '["liked-trades"]', '["matches","all"]'];
    check('4a. refreshMatchesLists invalidates Awaiting, every league\'s liked count, and Mutual',
      r && typeof r.then === 'function' && want.every((k) => calls.includes(k)) && calls.length === want.length,
      `invalidated ${calls.join(', ')}`);
  }
  const imp = (s) => /import \{ refreshMatchesLists \} from '\.\.\/state\/matchesLists';/.test(s);

  const t = read('src/screens/TradesScreen.tsx');
  const start = t.indexOf('const swipeMutation = useMutation({');
  const onSuccess = start >= 0 ? t.slice(t.indexOf('onSuccess:', start), t.indexOf('onError:', start)) : '';
  const guard = onSuccess.indexOf('if (!ctx || !actionCanUpdateScreen(ctx.action)) return;');
  const refresh = onSuccess.indexOf("if (vars.decision === 'like') void refreshMatchesLists();");
  check('4b. deck swipe: EVERY acknowledged like refreshes the lists, not only a matched one',
    imp(t) && refresh >= 0,
    "expected `if (vars.decision === 'like') void refreshMatchesLists();` in swipeMutation.onSuccess");
  check('4c. … before the screen-update guard, so a like that lands after the user left still refreshes',
    refresh >= 0 && guard >= 0 && refresh < guard);
  check('4d. … and the matched branch no longer carries its own partial invalidation',
    !/invalidateQueries\(\{ queryKey: \['awaiting-trades'\] \}\)/.test(onSuccess));

  const q = read('src/utils/queueCalcTrade.ts');
  check('4e. calculator ✓ queue (both hosts): a queued like refreshes the lists',
    imp(q) && /if \(queued\) \{(\s*\/\/[^\n]*)*\s*void refreshMatchesLists\(\);/.test(q));

  const ps = read('src/hooks/usePresentationSignals.ts');
  check('4f. presentation-v2 / Today\'s Trade likes refresh the lists once the swipe lands',
    imp(ps) && /\.then\(\(\) => \{\s*if \(decision === 'like'\) void refreshMatchesLists\(\);\s*\}\)/.test(ps));

  const ms = read('src/screens/MatchesScreen.tsx');
  const dm = ms.slice(ms.indexOf('const dismissAwaitingMutation = useMutation({'));
  const dmOk = dm.slice(dm.indexOf('onSuccess:'), dm.indexOf('\n  });'));
  check('4g. Awaiting dismiss (retracts the like) also refreshes the liked count via the helper',
    imp(ms) && /void refreshMatchesLists\(\);/.test(dmOk));

  check('4h. a posted standing offer refreshes Matches\' standing-offer list too (prefix key)',
    /onPosted=\{\(offer\) => \{\s*setStandingOfferPrompt\(null\);(\s*\/\/[^\n]*)*\s*queryClient\.invalidateQueries\(\{ queryKey: \['standing-offers'\] \}\);/.test(t));
}

for (const p of passes) console.log(`  ✓ ${p}`);
if (failures.length) {
  console.error('\nFAILURES:');
  for (const f of failures) console.error(`  ✗ ${f}`);
  console.error(`\ncheck-match-moment: ${failures.length} FAILED`);
  process.exit(1);
}
console.log(`\ncheck-match-moment: all ${passes.length} checks passed`);
