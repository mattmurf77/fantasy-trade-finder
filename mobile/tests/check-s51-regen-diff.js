#!/usr/bin/env node
// S-43 — the post-Quick-Set reveal (`s5.1` celebrate / `s5.0` honest null).
//
// Pins the three defects proved in docs/plans/open-access-phase-a-gates.md
// § Gate (b) and ratified for fix by living-memory/DECISIONS.md D-047:
//
//   1  STALE-DECK READ. The diff effect used to count against `deck`, which
//      on the commit where job.status flips to 'complete' is still the
//      PRE-regeneration deck (`deck` is written only from inside the append
//      effect). `fresh` was structurally 0 and the ref was nulled before the
//      new cards landed, so `s5.1` had never rendered for any user.
//   2  UUID DIFF. `trade_id` is a fresh uuid per generation, so an id-based
//      diff calls 33 identical packages 33 "new" trades.
//   3  DOUBLED DECK. The regen path never cleared the deck; the append
//      effect de-dupes on trade_id, so regenerated cards piled on top of the
//      ones they replace and the index rewind landed the user on a doubled
//      deck.
//
// WHAT IS PINNED, and the sabotage each assertion detects:
//
//   1  `tradePackageKey` exists at module scope, never mentions `trade_id`,
//      sorts BOTH sides and includes the opponent — asserted structurally
//      AND behaviourally (the real function is transpiled and executed).
//      Sabotage: drop a .sort() → a re-ordered but identical package scores
//      as new; drop the opponent → the same package with two counterparties
//      collapses to one. Red either way.
//   2  The diff effect counts over `job.cards`, never over `deck`, and does
//      it through `tradePackageKey`/`prevPackages` with no `trade_id` in
//      sight. Sabotage: restore `deck.filter(c => !prevIds.has(c.trade_id))`
//      → red on both halves (defects 1 + 2).
//   3  The diff effect is late-bound: it returns unless the pending ref
//      carries a jobId AND `job.job_id` matches it. Sabotage: drop the
//      match and the deck clear resolves the reveal against the previous,
//      already-'complete' job. Red.
//   4  The Quick Set focus handoff clears the deck BEFORE firing the forced
//      generate, and stamps that job's id onto the pending ref. Sabotage:
//      remove setDeck([]) → the deck doubles again. Red.
//   5  Honest zero survives: exactly one `fresh` binding in the effect feeds
//      all three consumers (the s5.1/s5.0 ternary, the diff banner, and
//      `deck_regenerated.new_trades`), and the celebrate branch is still
//      guarded by `fresh > 0`. Sabotage: floor the count or celebrate
//      unconditionally → an all-skip Quick Set walk would celebrate. Red.
//
// Structural + behavioural, no renderer: parses the real TSX with the
// project's own TypeScript and walks the AST (same harness family as
// check-trades-banner-region.js), then transpiles the one pure helper and
// runs it (same idiom as check-session-rerank.js).
//
// Run: node tests/check-s51-regen-diff.js

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

function parse(rel) {
  const abs = path.join(__dirname, '..', rel);
  return ts.createSourceFile(
    abs,
    fs.readFileSync(abs, 'utf8'),
    ts.ScriptTarget.ES2019,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );
}

let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

function walk(node, visit) {
  visit(node);
  node.forEachChild((c) => walk(c, visit));
}

function findAll(sf, pred) {
  const out = [];
  walk(sf, (n) => {
    if (pred(n)) out.push(n);
  });
  return out;
}

// Comments in this file talk ABOUT `deck` and `trade_id` on purpose, so the
// negative assertions below have to read code only. Quote/template aware;
// no regex literals live in the spans this test inspects.
function stripComments(text) {
  let out = '';
  let i = 0;
  let quote = null; // "'" | '"' | '`' when inside a string
  while (i < text.length) {
    const c = text[i];
    const d = text[i + 1];
    if (quote) {
      out += c;
      if (c === '\\') { out += d ?? ''; i += 2; continue; }
      if (c === quote) quote = null;
      i += 1;
      continue;
    }
    if (c === "'" || c === '"' || c === '`') { quote = c; out += c; i += 1; continue; }
    if (c === '/' && d === '/') {
      while (i < text.length && text[i] !== '\n') i += 1;
      out += ' ';
      continue;
    }
    if (c === '/' && d === '*') {
      i += 2;
      while (i < text.length && !(text[i] === '*' && text[i + 1] === '/')) i += 1;
      i += 2;
      out += ' ';
      continue;
    }
    out += c;
    i += 1;
  }
  return out;
}

const host = parse('src/screens/TradesScreen.tsx');

function callsNamed(sf, name) {
  return findAll(
    sf,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === name,
  );
}

// ═══ 1 — tradePackageKey: content identity, not trade_id ═══════════════════

const keyFns = findAll(
  host,
  (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === 'tradePackageKey',
);
assert(
  keyFns.length === 1,
  '1a — TradesScreen declares exactly one module-level tradePackageKey',
  `found ${keyFns.length}`,
);

if (keyFns.length === 1) {
  const src = stripComments(keyFns[0].getText(host));
  assert(
    !/trade_id/.test(src),
    '1b — tradePackageKey never reads trade_id',
    'the uuid is back in the identity — an unchanged board scores 100% new',
  );
  assert(
    /opponent_user_id/.test(src),
    '1c — tradePackageKey includes the opponent',
    'without it, the same package with two counterparties is one identity',
  );
  const sorts = (src.match(/\.sort\(\)/g) || []).length;
  assert(
    sorts === 2,
    '1d — tradePackageKey sorts both sides (give + receive)',
    `found ${sorts} .sort() calls — within-side order is an engine artifact`,
  );

  // Behavioural half: run the real function.
  const js = ts.transpileModule(`${src}\nmodule.exports = tradePackageKey;`, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const shim = { exports: {} };
  new Function('module', 'exports', js)(shim, shim.exports);
  const key = shim.exports;

  const card = (opp, give, recv) => ({
    opponent_user_id: opp,
    give_player_ids: give,
    receive_player_ids: recv,
  });
  assert(
    key(card('u1', ['a', 'b'], ['x', 'y'])) === key(card('u1', ['b', 'a'], ['y', 'x'])),
    '1e — re-ordering players WITHIN a side does not make a package new',
  );
  assert(
    key(card('u1', ['a'], ['x'])) !== key(card('u2', ['a'], ['x'])),
    '1f — a different counterparty is a different package',
  );
  assert(
    key(card('u1', ['a'], ['x'])) !== key(card('u1', ['x'], ['a'])),
    '1g — give and receive are not interchangeable',
  );
  assert(
    key(card('u1', ['a'], ['x'])) !== key(card('u1', ['a'], ['x', 'z'])),
    '1h — an extra asset on one side is a different package',
  );
}

// ═══ 2-5 — the diff effect + the Quick Set handoff ═════════════════════════

// The diff effect is the useEffect whose body emits `deck_regenerated`.
const diffEffects = callsNamed(host, 'useEffect').filter((n) =>
  /['"]deck_regenerated['"]/.test(n.getText(host)),
);
assert(
  diffEffects.length === 1,
  '2a — exactly one useEffect owns the post-Quick-Set reveal',
  `found ${diffEffects.length}`,
);

if (diffEffects.length === 1) {
  const eff = diffEffects[0];
  const body = stripComments(eff.arguments[0].getText(host));
  const deps = eff.arguments[1] ? stripComments(eff.arguments[1].getText(host)) : '';

  assert(
    /job\.cards\.filter\(/.test(body),
    '2b — the count is taken over job.cards',
    'defect 1 is back: `deck` lags a commit behind the status flip, so fresh is always 0',
  );
  assert(
    !/\bdeck\b/.test(body) && !/\bdeck\b/.test(deps),
    '2c — the reveal no longer reads `deck` (body or deps)',
    'reading the render closure of `deck` here is exactly defect 1',
  );
  assert(
    !/trade_id/.test(body),
    '2d — the reveal no longer diffs on trade_id',
    'defect 2 is back: uuids make every regenerated card look new',
  );
  assert(
    /prevPackages/.test(body) && /tradePackageKey/.test(body),
    '2e — the reveal diffs pre-Quick-Set package identities',
  );

  // 3 — late binding to the forced job.
  assert(
    /pending\.jobId/.test(body) && /job\?\.job_id !== pending\.jobId/.test(body),
    '3 — the reveal resolves only for the job the handoff forced',
    'without the id match the deck clear resolves it against the previous job',
  );

  // 5 — honest zero.
  const freshDecls = (body.match(/const fresh =/g) || []).length;
  assert(
    freshDecls === 1,
    '5a — one `fresh` binding feeds all three consumers',
    `found ${freshDecls} — the beat, the banner and the analytics prop must agree`,
  );
  assert(
    /fresh > 0 \? GUIDE\.s5_1\(/.test(body) && /GUIDE\.s5_0\(/.test(body),
    '5b — celebrate stays gated on fresh > 0, with s5.0 as the honest null',
    'an all-skip Quick Set walk must still land on s5.0',
  );
  assert(
    /new_trades: fresh/.test(body),
    '5c — deck_regenerated.new_trades reports the same corrected count',
  );
  assert(
    !/Math\.max\(/.test(body),
    '5d — the count is not floored',
    'flooring fresh would manufacture a celebration out of an honest zero',
  );
}

// ═══ 4 — the handoff clears the deck and stamps the job id ═════════════════

const handoffs = callsNamed(host, 'useFocusEffect').filter((n) =>
  /consumePendingQuicksetRegen\(/.test(n.getText(host)),
);
assert(
  handoffs.length === 1,
  '4a — exactly one focus effect consumes the Quick Set handoff',
  `found ${handoffs.length}`,
);

if (handoffs.length === 1) {
  const src = stripComments(handoffs[0].getText(host));
  const clearAt = src.indexOf('setDeck([])');
  const mutateAt = src.indexOf('generateMutation.mutate(');
  assert(
    clearAt !== -1,
    '4b — the handoff clears the deck',
    'defect 3: the regenerated cards append to the ones they replace and the deck doubles',
  );
  assert(
    clearAt !== -1 && mutateAt !== -1 && clearAt < mutateAt,
    '4c — the clear happens before the forced generate is fired',
  );
  assert(
    /force: true/.test(src),
    '4d — the regen still forces past the server job cache',
  );
  assert(
    /pendingRegenRef\.current\.jobId = snapshot\.job_id/.test(src),
    '4e — the forced job stamps its id onto the pending reveal',
    'without the stamp the reveal can never resolve',
  );
  assert(
    /prevPackages: new Set\(deck\.map\(tradePackageKey\)\)/.test(src),
    '4f — the pre-Quick-Set snapshot stores package identities',
    'snapshotting trade_ids is defect 2',
  );
}

console.log(
  failures === 0
    ? '\nAll s5.1 regen-diff assertions passed.'
    : `\n${failures} assertion(s) failed.`,
);
process.exit(failures === 0 ? 0 : 1);
