#!/usr/bin/env node
// No raw enum, fake age or clipped slot name on the deck (sim pass C).
//
// WHY THIS EXISTS. Release simulator pass, 2026-11-22, at 402 pt width:
//   C1. Acquire, no declared outlook: "Your roster reads as Not_sure." The
//       inferred-outlook banner (and the classic Outlook row) capitalized the
//       raw `team_outlook` enum instead of reading OutlookBiasReceipt's
//       display table, which Home and the calculator already use.
//   C2. Deck cards printed draft picks as "PICK · 0 yo": a pick rides the
//       Player shape with age 0 and years_experience 0, and PlayerCard
//       printed any non-null age.
//   C3. The card's lineup impact rows clipped SUPER_FLEX to "SU…" and FLEX to
//       "FL…": CardImpactBlock printed the raw Sleeper slot name (underscores
//       as spaces) in a 34 pt column. The calculator already shortened three
//       slot names inline; both now read utils/slotLabel.
//   C4. Matches > Awaiting showed an "FLX" chip and team "FA" on every asset.
//       GET /api/trades/awaiting never shipped team/position (matches/all
//       does), so the client adapter fell back. The server now ships the four
//       arrays and the api normalizer carries them; the MatchesScreen adapter
//       (`awaitingToTradeCardShape`) now READS them (§4c/4d, enforced).
//   C5. Draft picks on Matches > Mutual and Awaiting tiles showed an "FLX"
//       chip and team "FA": the payload position/team arrays come from the
//       players table, so a pick gets "". The deck labels a pick PICK/PICK;
//       utils/matchAssetLabel gives both Matches adapters the same label,
//       recognising a pick by id as the server does (generic_pick_* or the
//       row's `{league_id}_` prefix).
//
// What is pinned:
//   1. TradesScreen never capitalizes an outlook enum; both outlook strings
//      go through outlookDisplayName.
//   2. PlayerCard prints no age (and no years) for a PICK.
//   3. utils/slotLabel RUN under plain node: every standard Sleeper starter
//      slot shortens to <= 4 characters, the long names map to the app's
//      short names (SF, FLX, W/R, W/T), numbering survives; both lineup
//      surfaces call it and neither keeps its own table or the underscore
//      replace.
//   4. The awaiting payload's team/position arrays exist on the server route
//      and in the client normalizer, and the Awaiting adapter reads them.
//   5. utils/matchAssetLabel RUN under plain node: picks read PICK/PICK,
//      players keep the server's position/team, an older server's missing
//      arrays keep the FLX/"" fallback; both Matches adapters call it.
//
// HONEST LABEL (G-035): §1, §2, §4, §5b-e prove presence of exact wirings in
// source; §3 and §5a execute the real modules.
//
// Run: node tests/check-deck-labels.js   (or npm run test:deck-labels)

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
const notes = [];
const ok = (n) => passes.push(n);
const bad = (n, d) => failures.push(`${n}\n      ${d}`);
const check = (n, cond, d = '') => (cond ? ok(n) : bad(n, d || 'condition false'));
const read = (rel, base = ROOT) => {
  const p = path.join(base, rel);
  if (!fs.existsSync(p)) { bad(`exists: ${rel}`, 'missing'); return ''; }
  return fs.readFileSync(p, 'utf8');
};
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');

// ── 1. Outlook strings read the display table ─────────────────────────────
{
  const s = strip(read('src/screens/TradesScreen.tsx'));
  check('1a. no capitalized raw outlook enum (cap(team_outlook) / cap(inferredOutlook))',
    !/cap\(\s*(prefsQuery\.data\??\.team_outlook|inferredOutlook)\s*\)/.test(s));
  check('1b. the inferred banner reads outlookDisplayName',
    /Your roster reads as \{outlookDisplayName\(inferredOutlook\)/.test(s));
  check('1c. the classic Outlook row reads outlookDisplayName',
    /\{outlookDisplayName\(prefsQuery\.data\?\.team_outlook\) \?\? 'Not set'\}/.test(s));
  const receipt = read('src/components/OutlookBiasReceipt.tsx');
  check("1d. the display table still names not_sure 'Not sure'", /not_sure: 'Not sure',/.test(receipt));
}

// ── 2. Picks carry no age ─────────────────────────────────────────────────
{
  const s = strip(read('src/components/PlayerCard.tsx'));
  check('2a. PlayerCard knows a pick', /const isPick = String\(player\.position\) === 'PICK';/.test(s));
  check('2b. no "N yo" for a pick',
    /const ageStr = player\.age != null && !isPick \? `\$\{player\.age\} yo` : null;/.test(s));
  check('2c. no "N yrs" for a pick', /player\.years_experience != null && !isPick/.test(s));
}

// ── 3. Lineup slot short names, executed ──────────────────────────────────
{
  const src = read('src/utils/slotLabel.ts');
  let m = null;
  if (src) {
    try {
      const js = ts.transpileModule(src, {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
      }).outputText;
      const mod = { exports: {} };
      new Function('module', 'exports', 'require', js)(mod, mod.exports, (n) => {
        throw new Error(`slotLabel.ts gained a runtime import ("${n}")`);
      });
      m = mod.exports;
    } catch (e) {
      bad('3. slotLabel.ts loads under plain node', String(e));
    }
  }
  if (m) {
    const f = m.slotShortLabel;
    const table = {
      SUPER_FLEX: 'SF', SUPER_FLEX2: 'SF2', FLEX: 'FLX', FLEX2: 'FLX2',
      WRRB_FLEX: 'W/R', REC_FLEX: 'W/T', QB: 'QB', RB2: 'RB2', WR3: 'WR3', TE: 'TE',
    };
    const wrong = Object.entries(table).filter(([k, v]) => f(k) !== v).map(([k, v]) => `${k} → ${f(k)} (want ${v})`);
    check('3a. Sleeper slot names map to the app\'s short names', wrong.length === 0, wrong.join('; '));
    const starters = ['QB', 'RB', 'RB2', 'WR', 'WR2', 'WR3', 'TE', 'FLEX', 'FLEX2', 'FLEX3',
      'SUPER_FLEX', 'SUPER_FLEX2', 'WRRB_FLEX', 'REC_FLEX', 'K', 'DEF'];
    const long = starters.filter((sl) => f(sl).length > 4).map((sl) => `${sl} → ${f(sl)}`);
    check('3b. every standard starter slot fits the 34 pt column (<= 4 chars)', long.length === 0, long.join('; '));
  }
  const block = strip(read('src/components/CardImpactBlock.tsx'));
  check('3c. the deck card impact block prints slotShortLabel',
    /import \{ slotShortLabel \} from '\.\.\/utils\/slotLabel';/.test(block) && /\{slotShortLabel\(s\.slot\)\}/.test(block));
  check('3d. … and no longer prints the raw name with underscores as spaces',
    !/slot\.replace\(\/_\/g, ' '\)/.test(block));
  const calc = strip(read('src/components/InLeagueCalculator.tsx'));
  check('3e. the calculator lineup table reads the same table (no local copy)',
    /import \{ slotShortLabel \} from '\.\.\/utils\/slotLabel';/.test(calc) && !/const SLOT_SHORT/.test(calc));
}

// ── 4. Awaiting tiles get team + position ─────────────────────────────────
{
  const server = read('backend/server.py', REPO);
  const route = server.slice(server.indexOf('@app.route("/api/trades/awaiting")'),
    server.indexOf('@app.route("/api/trades/awaiting/dismiss"'));
  check('4a. GET /api/trades/awaiting ships the four team/position arrays',
    ['my_give_teams', 'my_receive_teams', 'my_give_positions', 'my_receive_positions']
      .every((k) => new RegExp(`"${k}":\\s*\\[player_(team|pos)_by_id\\.get\\(pid, ""\\)`).test(route)));
  const api = read('src/api/trades.ts');
  const norm = api.slice(api.indexOf('function normalizeAwaitingTrade('), api.indexOf('export async function getAwaitingTrades('));
  check('4b. normalizeAwaitingTrade carries them',
    /my_side_player_positions:\s*Array\.isArray\(raw\?\.my_give_positions\)/.test(norm)
      && /their_side_player_positions:\s*Array\.isArray\(raw\?\.my_receive_positions\)/.test(norm)
      && /my_side_player_teams:\s*Array\.isArray\(raw\?\.my_give_teams\)/.test(norm)
      && /their_side_player_teams:\s*Array\.isArray\(raw\?\.my_receive_teams\)/.test(norm));
  // 4c — enforced since the MatchesScreen follow-up: the adapter READS the
  // awaiting arrays (through matchAssetLabel, §5) instead of hard-coding the
  // FLX / '' fallback.
  const matches = strip(read('src/screens/MatchesScreen.tsx'));
  const adapter = matches.slice(matches.indexOf('function awaitingToTradeCardShape('),
    matches.indexOf('const styles = StyleSheet.create('));
  check('4c. MatchesScreen.awaitingToTradeCardShape reads the awaiting positions/teams',
    /a\.my_side_player_positions\?\.\[i\]/.test(adapter) && /a\.my_side_player_teams\?\.\[i\]/.test(adapter)
      && /a\.their_side_player_positions\?\.\[i\]/.test(adapter) && /a\.their_side_player_teams\?\.\[i\]/.test(adapter));
  check('4d. … and no longer hard-codes the FLX chip / empty team',
    !/position:\s*POS_UNKNOWN,/.test(adapter) && !/team:\s*'',/.test(adapter));
}

// ── 5. Picks on Matches tiles read PICK / PICK, like the deck ─────────────
{
  const src = read('src/utils/matchAssetLabel.ts');
  let m = null;
  if (src) {
    try {
      const js = ts.transpileModule(src, {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
      }).outputText;
      const mod = { exports: {} };
      new Function('module', 'exports', 'require', js)(mod, mod.exports, (n) => {
        throw new Error(`matchAssetLabel.ts gained a runtime import ("${n}")`);
      });
      m = mod.exports;
    } catch (e) {
      bad('5. matchAssetLabel.ts loads under plain node', String(e));
    }
  }
  if (m) {
    const f = m.matchAssetLabel;
    const L = 'lg123';
    const cases = [
      // [id, league, pos, team, want]
      ['lg123_2026_1_3', L, '', '', 'PICK/PICK'],          // owned pick, server sends ""
      ['generic_pick_1_early', L, '', '', 'PICK/PICK'],    // generic rung
      ['generic_pick_2_mid', undefined, '', '', 'PICK/PICK'],
      ['4034', L, 'RB', 'SF', 'RB/SF'],                    // real player, new server
      ['4034', L, undefined, undefined, 'FLX/'],           // older server: legacy fallback
      ['SF', L, 'DEF', 'SF', 'DEF/SF'],                    // team DEF id is not a pick
      ['other_2026_1_3', L, '', '', 'FLX/'],               // another league's prefix is not ours
    ];
    const wrong = cases.filter(([id, lg, pos, team, want]) => {
      const r = f(id, lg, pos, team);
      return `${r.position}/${r.team}` !== want;
    }).map(([id, lg, pos, team, want]) => {
      const r = f(id, lg, pos, team);
      return `${id} → ${r.position}/${r.team} (want ${want})`;
    });
    check('5a. matchAssetLabel: picks read PICK/PICK, players keep server pos/team, legacy fallback FLX/""',
      wrong.length === 0, wrong.join('; '));
  }
  const matches = strip(read('src/screens/MatchesScreen.tsx'));
  check('5b. MatchesScreen imports matchAssetLabel',
    /import \{ matchAssetLabel \} from '\.\.\/utils\/matchAssetLabel';/.test(matches));
  const mutual = matches.slice(matches.indexOf('function matchToTradeCardShape('),
    matches.indexOf('function awaitingToTradeCardShape('));
  const awaiting = matches.slice(matches.indexOf('function awaitingToTradeCardShape('),
    matches.indexOf('const styles = StyleSheet.create('));
  const calls = (s) => (s.match(/matchAssetLabel\(/g) || []).length;
  check('5c. the Mutual adapter labels both sides through matchAssetLabel', calls(mutual) === 2,
    `found ${calls(mutual)} calls`);
  check('5d. the Awaiting adapter labels both sides through matchAssetLabel', calls(awaiting) === 2,
    `found ${calls(awaiting)} calls`);
  check("5e. PlayerCard's pick test still keys on position 'PICK' (what the label feeds)",
    /const isPick = String\(player\.position\) === 'PICK';/.test(strip(read('src/components/PlayerCard.tsx'))));
}

for (const p of passes) console.log(`  ✓ ${p}`);
for (const n of notes) console.log(`  · ${n}`);
if (failures.length) {
  console.error('\nFAILURES:');
  for (const f of failures) console.error(`  ✗ ${f}`);
  console.error(`\ncheck-deck-labels: ${failures.length} FAILED`);
  process.exit(1);
}
console.log(`\ncheck-deck-labels: all ${passes.length} checks passed`);
