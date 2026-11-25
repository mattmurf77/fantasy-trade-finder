#!/usr/bin/env node
// Launch cuts that no feature flag covers (owner's keep/cut calls of
// 2026-11-25, data/review/launch-feature-audit-2026-11-21/keep-cut-list.md,
// local to the operator's machine).
//
// WHY THIS EXISTS. The owner cut Pick Anchors, the Rank-stack Trends page and
// the Draft Room for launch, and turned off Team Review, without deleting
// their code (Rookie ranks and the draft family come back in the offseason;
// the same spirit applies to the rest). A cut that only hides the obvious
// entry leaves side doors: the launch audit's validation found a saved
// 'anchor' ranking preference routing straight into Pick Anchors at launch,
// the Settings slider still offering it, deep links to both pages, and an old
// Draft Room link showing "Couldn't load the draft room." with a "Try again"
// that could never succeed. Failure mode this catches: any of those doors
// reopening, or a kept neighbour (ESPN pick assignment, Usage Trends) being
// tied to a cut flag.
//
// Pinned:
//   A1  rankChooserModel: no chooser row (primary or "More ways to rank")
//       routes to Anchors or Trends or saves the 'anchor' preference    [AST-free text]
//   A2  SteerSlider (Settings › Ranking): no 'anchor' stop               [text]
//   A3  useSession: a stored 'anchor' preference hydrates as none — the
//       hydrate allowlist is EXECUTED and 'anchor' is not in it           [executed]
//   A4  TabNav launch routing: PREF_ROUTE has no anchor entry            [text]
//   A5  no navigate()/screen: into 'Anchors' or 'Trends' anywhere in src,
//       and the two routes stay registered (code kept)                   [text]
//   A6  deep links: V2_SCREENS has no Anchors / Trends path, and
//       rewriteUniversalPath (EXECUTED) sends app/rank/anchors and
//       app/rank/trends to app/rank/home, keeping the query, leaving every
//       other path alone                                                  [executed]
//   D1  DraftRoomScreen reads `draft.room`; the board query is off without
//       it; the closed branch is the FIRST early return, catches a 404
//       feature_disabled too, has a Back (goBack, else Main) and no
//       "Try again"                                                        [text]
//   D2  with `draft.room` and `league.rookie_board_entry` off there is no
//       Draft chip on Acquire and no Rookie draft / Rookie board tile on
//       League home: both are gated on exactly those flags               [text]
//   D3  ESPN pick assignment depends on no draft flag: League home's
//       section is `picks.assign && isEspn`, PickAssignmentScreen reads
//       only `picks.assign`                                               [text]
//   T1  Team Review: the one navigate('TeamReview') sits inside the
//       `teamReviewOn && leagueId` entry-card block; no deep-link path; no
//       other source file names the page in user-facing copy             [text]
//
// HONEST LABEL (G-035): A3 and A6 execute the real code; everything else
// proves the presence or absence of exact wirings in source, not runtime.
//
// Run: node tests/check-launch-cuts.js   (or: npm run test:launch-cuts)

'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');

let failures = 0;
let passes = 0;
const assert = (cond, name, detail) => {
  if (cond) {
    passes += 1;
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
};

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

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(p);
  }
  return out;
}

// ── A. Pick Anchors and Trends ─────────────────────────────────────────────
{
  const model = strip(read('src/navigation/rankChooserModel.ts'));
  assert(/export const MORE_METHODS/.test(model) && /export const PRIMARY_METHODS/.test(model)
      && !/route: 'Anchors'/.test(model) && !/route: 'Trends'/.test(model)
      && !/pref: 'anchor'/.test(model) && /route: 'ManualRanks'/.test(model),
    'A1. the rank chooser (both surfaces) offers neither Pick Anchors nor Trends; Overall ranks stays');

  const slider = strip(read('src/components/SteerSlider.tsx'));
  assert(/const STOPS/.test(slider) && !/pref: 'anchor'/.test(slider)
      && ['quickset', 'trio', 'tiers', 'manual'].every((p) => slider.includes(`pref: '${p}'`)),
    'A2. the Settings ranking slider has no Pick Anchors stop (four stops remain)');

  const session = read('src/state/useSession.ts');
  const m = /const RANK_METHOD_PREFS: readonly RankMethodPref\[\] = (\[[^\]]*\]);/.exec(session);
  let prefs = null;
  try {
    // eslint-disable-next-line no-new-func
    prefs = m ? new Function(`return ${m[1]};`)() : null;
  } catch { prefs = null; }
  const hydrateUsesIt = /const rankingMethodPref = RANK_METHOD_PREFS\.includes\(prefRaw as RankMethodPref\)\s*\?\s*\(prefRaw as RankMethodPref\)\s*:\s*null;/.test(session);
  assert(Array.isArray(prefs) && !prefs.includes('anchor') && prefs.includes('quickset') && hydrateUsesIt,
    'A3. a stored \'anchor\' preference hydrates as no preference (executed allowlist; hydrate reads it)',
    JSON.stringify(prefs));

  const tab = read('src/navigation/TabNav.tsx');
  const pr = /const PREF_ROUTE: Record<string, RankRoute> = (\{[^}]*\});/.exec(tab);
  assert(pr && !/anchor/.test(strip(pr[1])) && /quickset:\s*'QuickSetTiers'/.test(pr[1]),
    'A4. Rank-tab launch routing has no anchor entry (a saved anchor falls to the default)');

  const hits = [];
  for (const f of walk(path.join(MOBILE, 'src'))) {
    const rel = path.relative(MOBILE, f);
    const s = strip(fs.readFileSync(f, 'utf8'));
    const re = /navigate\(\s*'(Anchors|Trends)'|screen:\s*'(Anchors|Trends)'|route:\s*'(Anchors|Trends)'|name:\s*'(Anchors|Trends)'/g;
    let x;
    while ((x = re.exec(s))) hits.push(`${rel}: ${x[0]}`);
  }
  assert(hits.length === 0, 'A5a. nothing in src navigates to Anchors or Trends', hits.join(' | '));
  const tabS = strip(tab);
  assert(/name="Anchors"\s+component=\{PickAnchorScreen\}/.test(tabS) && /name="Trends"\s+component=\{TrendsScreen\}/.test(tabS),
    'A5b. the Anchors and Trends routes stay registered (code kept for a later return)');

  const dl = read('src/utils/deepLinks.ts');
  const dlS = strip(dl);
  assert(!/\bAnchors:\s*'/.test(dlS) && !/\bTrends:\s*'/.test(dlS) && /RankHome:\s*'home'/.test(dlS),
    'A6a. the deep-link table has no Anchors / Trends path');
  const sig = 'export function rewriteUniversalPath(pathWithQuery: string): string';
  const at = dl.indexOf(sig);
  const body = at === -1 ? null : braceBody(dl, at + sig.length);
  let rewrite = null;
  try {
    // eslint-disable-next-line no-new-func
    rewrite = body ? new Function('pathWithQuery', body.slice(1, -1)) : null;
  } catch { rewrite = null; }
  if (!rewrite) {
    assert(false, 'A6b. rewriteUniversalPath runs as plain JS');
  } else {
    const cases = [
      ['app/rank/anchors', 'app/rank/home'],
      ['/app/rank/trends', 'app/rank/home'],
      ['app/rank/trends/', 'app/rank/home'],
      ['app/rank/anchors?ref=bob', 'app/rank/home?ref=bob'],
      ['app/rank/tiers', 'app/rank/tiers'],
      ['app/rank/ranks', 'app/rank/ranks'],
      ['app/league/usage-trends', 'app/league/usage-trends'],
      ['/s/trade/tok', 'app/matches'],
    ];
    const bad = cases.map(([i, w]) => [i, w, rewrite(i)]).filter(([, w, g]) => g !== w)
      .map(([i, w, g]) => `${i} → ${g} (want ${w})`);
    assert(bad.length === 0,
      'A6b. old Anchors / Trends links land on the rank chooser; other paths unchanged (executed)', bad.join(' | '));
  }
}

// ── D. Draft Room off ──────────────────────────────────────────────────────
{
  const dr = strip(read('src/screens/DraftRoomScreen.tsx'));
  assert(/const roomOn = useFlag\('draft\.room'\);/.test(dr) && /enabled: !!leagueId && roomOn,/.test(dr),
    'D1a. the room reads draft.room and makes no board request without it');
  const closedAt = dr.indexOf('if (roomClosed) {');
  const firstReturnBranch = Math.min(
    ...['if (!leagueId) {', 'if (query.isLoading) {', 'if (query.isError || !board) {']
      .map((k) => (dr.indexOf(k) === -1 ? Infinity : dr.indexOf(k))),
  );
  assert(closedAt !== -1 && closedAt < firstReturnBranch,
    'D1b. the closed state is decided before the no-league, loading and error branches');
  assert(/const roomClosed =\s*!roomOn \|\|\s*\(query\.error instanceof ApiError &&\s*query\.error\.status === 404 &&\s*\(query\.error\.body as \{ error\?: string \} \| null\)\?\.error === 'feature_disabled'\);/.test(dr),
    'D1c. a server 404 feature_disabled also shows the closed state (stale client flag)');
  const closed = closedAt === -1 ? '' : braceBody(dr, closedAt) || '';
  assert(/testID="draft-room\.closed-text"/.test(closed) && /testID="draft-room\.closed-back"/.test(closed)
      && /navigation\?\.canGoBack\?\.\(\) \? navigation\.goBack\(\) : navigation\?\.navigate\?\.\('Main'\)/.test(closed)
      && !/Try again|onRefresh|Couldn't load/.test(closed),
    'D1d. the closed state has a working Back and no "Try again" / load-error copy');

  const trades = strip(read('src/screens/TradesScreen.tsx'));
  assert(/const draftRoomOn = useFlag\('draft\.room'\);/.test(trades)
      && /onDraft=\{\s*draftRoomOn\s*\?\s*\(\) => navigation\?\.navigate\?\.\('DraftRoom'\)\s*:\s*undefined\s*\}/.test(trades)
      && (trades.match(/navigate\?\.\('DraftRoom'\)|navigate\('DraftRoom'/g) || []).length === 1,
    'D2a. Acquire\'s only Draft Room entry is the mode-bar chip, created only with draft.room on');
  const league = strip(read('src/screens/LeagueScreen.tsx'));
  assert(/const showRookieBoard = useFlag\('league\.rookie_board_entry'\);/.test(league)
      && /const showDraftRoom = useFlag\('draft\.room'\);/.test(league)
      && /\{showDraftRoom \? \(\s*<ExploreTile\s+testID="league\.draft-room-row"[\s\S]*?\) : showRookieBoard \? \(\s*<ExploreTile\s+testID="league\.rookie-board-row"[\s\S]*?\) : null\}/.test(league),
    'D2b. League home\'s Rookie draft / Rookie board tile exists only with draft.room / league.rookie_board_entry');

  assert(/const showPickAssignFlag = useFlag\('picks\.assign'\);/.test(league)
      && /const showPickAssign = showPickAssignFlag && isEspn;/.test(league)
      && /\{showPickAssign \? \(/.test(league),
    'D3a. League home\'s ESPN "Draft picks" section depends on picks.assign and ESPN only');
  const pa = strip(read('src/screens/PickAssignmentScreen.tsx'));
  const paFlags = [...pa.matchAll(/useFlag\('([^']+)'\)/g)].map((x) => x[1]);
  assert(paFlags.length === 1 && paFlags[0] === 'picks.assign',
    'D3b. PickAssignmentScreen reads no draft flag (only picks.assign)', JSON.stringify(paFlags));
}

// ── T. Team Review off ─────────────────────────────────────────────────────
{
  const all = walk(path.join(MOBILE, 'src'));
  const navs = [];
  for (const f of all) {
    const s = strip(fs.readFileSync(f, 'utf8'));
    const n = (s.match(/navigate\(\s*'TeamReview'/g) || []).length;
    if (n) navs.push([path.relative(MOBILE, f), n]);
  }
  assert(navs.length === 1 && navs[0][0] === path.join('src', 'screens', 'TradesScreen.tsx') && navs[0][1] === 1,
    'T1a. exactly one navigate(\'TeamReview\') in src, in TradesScreen', JSON.stringify(navs));
  const trades = strip(read('src/screens/TradesScreen.tsx'));
  const gate = trades.indexOf('{teamReviewOn && leagueId ? (');
  const block = gate === -1 ? '' : trades.slice(gate, trades.indexOf(') : null}', gate));
  assert(/const teamReviewOn = useFlag\('trades\.team_review'\);/.test(trades)
      && /<TeamReviewEntryCard/.test(block) && /navigation\.navigate\('TeamReview' as never\)/.test(block),
    'T1b. that navigate lives inside the trades.team_review-gated entry card block');
  assert(!/TeamReview/.test(strip(read('src/utils/deepLinks.ts'))), 'T1c. no deep-link path to Team Review');
  const allowed = new Set([
    'src/screens/TeamReviewScreen.tsx', 'src/components/TeamReviewEntryCard.tsx', 'src/navigation/TabNav.tsx',
  ].map((p) => path.join(...p.split('/'))));
  const copyHits = [];
  for (const f of all) {
    const rel = path.relative(MOBILE, f);
    if (allowed.has(rel)) continue;
    const s = strip(fs.readFileSync(f, 'utf8'));
    for (const x of s.matchAll(/(['"`>])[^'"`<>\n]*\bteam review\b[^'"`<>\n]*/gi)) copyHits.push(`${rel}: ${x[0].trim()}`);
  }
  assert(copyHits.length === 0, 'T1d. no other screen or component names Team Review in copy', copyHits.join(' | '));
}

console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
