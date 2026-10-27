#!/usr/bin/env node
// Overhaul send — an all-refused batch must not fire the SUCCESS haptic.
//
// WHY THIS EXISTS. `POST /api/overhauls/{id}/send` answers 200 even when the
// provider refused every offer: the refusals ride in `attempts[]` as
// `send_failed` (backend/overhaul_api.py, the send loop). The summary screen
// used to fire `haptics.success()` on any resolved `sendBatch`, so a batch
// where nothing went out buzzed "done". head-eng's ruling: accept at launch,
// client fix after. The fix changes ONLY the haptic — navigation to the plan
// (whose attempt rows show `attempts[].error.message`) is untouched, and no
// copy is added.
//
// What is pinned:
//   A. (behavioral — the REAL api/overhaul.ts transpiled and run) the
//      predicate `sendBatchAllRefused(result)`:
//        A1 every attempt `send_failed`          → true  (the all-fail batch)
//        A2 one `proposed` among refusals        → false (partial success)
//        A3 every attempt `proposed`             → false (full success)
//        A4 `outcome_unknown` among refusals     → false (it may be out; the
//                                                  plan offers Mark declined)
//        A5 empty / missing / null attempts      → false (unclassifiable keeps
//                                                  the old success behavior)
//        A6 any other non-failed state           → false (only a refusal counts:
//                                                  an idempotent replay of an old
//                                                  batch can carry declined etc.)
//      Rule: attempts non-empty and EVERY one `send_failed`.
//   B. (structural — OverhaulSummaryScreen source, comments stripped) in the
//      send path between `await sendBatch(` and its `catch`:
//        B1 the result is captured and handed to sendBatchAllRefused
//        B2 all-refused → haptics.warning() (the app's refused-send haptic:
//           the same handler's catch uses it; the taxonomy has no `error`)
//        B3 otherwise → haptics.success() (partial and full success)
//        B4 NO other haptic call in that path — in particular no success
//           haptic before the branch, which would fire on the all-fail path too
//        B5 navigation is unconditional: `navigation.replace('OverhaulPlan'`
//           after the branch, not inside it
//        B6 the screen imports sendBatchAllRefused from ../api/overhaul
//
// Dependency-free except the project's own typescript. Exits 1 on any failure.
// Run: node tests/check-overhaul-allfail-haptic.js

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
const API = 'src/api/overhaul.ts';
const SUMMARY = 'src/screens/OverhaulSummaryScreen.tsx';

const pass = [];
const fail = [];
const ok = (n) => pass.push(n);
const bad = (n, d) => fail.push(`${n}\n      ${d}`);
const check = (cond, name, detail) => (cond ? ok(name) : bad(name, detail));
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

// ── A. behavioral: run the real predicate ───────────────────────────────
function load(rel, requireShim) {
  const source = fs.readFileSync(path.join(ROOT, rel), 'utf8');
  const js = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const mod = { exports: {} };
  new Function('module', 'exports', 'require', js)(mod, mod.exports, requireShim);
  return mod.exports;
}

const api = load(API, (name) => {
  // api/overhaul.ts only uses these inside fetchers; the predicate needs neither.
  if (name === './client') return { apiRequest: () => { throw new Error('not under test'); } };
  if (name === './trades') return { normalizeTradeCard: (c) => c };
  throw new Error(
    `api/overhaul.ts gained an unexpected runtime import ("${name}") — ` +
      'extend this shim deliberately, do not let it pass silently.',
  );
});

const fn = api.sendBatchAllRefused;
if (typeof fn !== 'function') {
  bad('A0. api/overhaul.ts exports sendBatchAllRefused', 'export missing or not a function');
} else {
  const att = (state) => ({ attempt_id: `at_${state}`, state });
  const res = (...states) => ({ batch_id: 'bt_1', attempts: states.map(att) });

  check(fn(res('send_failed')) === true,
    'A1a. one offer, refused → all refused',
    'a single send_failed attempt must read as an all-refused batch');
  check(fn(res('send_failed', 'send_failed', 'send_failed')) === true,
    'A1b. three offers, all refused → all refused',
    'every attempt send_failed must read as an all-refused batch');
  check(fn(res('proposed', 'send_failed')) === false,
    'A2a. one proposed among refusals (partial) → not all refused',
    'a partial success must keep the success haptic');
  check(fn(res('send_failed', 'send_failed', 'proposed')) === false,
    'A2b. last offer proposed (partial) → not all refused',
    'position of the success must not matter');
  check(fn(res('proposed')) === false && fn(res('proposed', 'proposed')) === false,
    'A3. every offer proposed (full success) → not all refused',
    'a clean batch must keep the success haptic');
  check(fn(res('outcome_unknown', 'send_failed')) === false && fn(res('outcome_unknown')) === false,
    'A4. outcome_unknown is not a refusal → not all refused',
    'an unconfirmed send may be out; it must not be reported as refused');
  check(fn({ batch_id: 'bt_1', attempts: [] }) === false
      && fn({ batch_id: 'bt_1' }) === false
      && fn(null) === false
      && fn(undefined) === false,
    'A5. empty / missing / null result → not all refused',
    'an unclassifiable result must keep the old success behavior, never turn into an error haptic');
  check(['declined', 'expired', 'withdrawn', 'accepted', 'stale', 'invalidated', 'queued']
      .every((st) => fn(res(st)) === false && fn(res('send_failed', st)) === false),
    'A6. only send_failed counts as a refusal',
    'a non-send_failed state (declined, accepted, stale, …) was read as refused — the haptic would say "failed" for a batch that was not');
}

// ── B. structural: the call site in the summary screen ──────────────────
const summaryPath = path.join(ROOT, SUMMARY);
const summary = fs.existsSync(summaryPath) ? strip(fs.readFileSync(summaryPath, 'utf8')) : '';
if (!summary) {
  bad('B0. summary screen source exists', `missing ${SUMMARY}`);
} else {
  check(/import\s*\{[^}]*\bsendBatchAllRefused\b[^}]*\}\s*from\s*'\.\.\/api\/overhaul'/.test(summary),
    'B6. summary imports sendBatchAllRefused from ../api/overhaul',
    'the screen must use the one predicate, not re-derive "all failed" inline');

  // The send path: from the awaited sendBatch to the catch that follows it.
  const start = summary.search(/await\s+sendBatch\(/);
  const end = start === -1 ? -1 : summary.indexOf('} catch (e) {', start);
  if (start === -1 || end === -1) {
    bad('B0. send path located', 'could not find `await sendBatch(` … `} catch (e) {` in OverhaulSummaryScreen');
  } else {
    const head = summary.slice(Math.max(0, start - 60), start);
    const bound = head.match(/(?:const|let)\s+(\w+)\s*=\s*$/);
    const path_ = summary.slice(start, end);

    check(!!bound,
      'B1a. the sendBatch result is captured',
      'the awaited sendBatch(...) result is discarded — the screen cannot tell an all-refused batch from a sent one');

    const branch = path_.match(
      /if\s*\(\s*sendBatchAllRefused\(\s*(\w+)\s*\)\s*\)\s*\{?\s*(haptics\.\w+\(\))\s*;?\s*\}?\s*else\s*\{?\s*(haptics\.\w+\(\))\s*;?\s*\}?/,
    );
    if (!branch) {
      bad('B1b. result goes through if (sendBatchAllRefused(x)) … else …',
        'no `if (sendBatchAllRefused(result)) haptics.… else haptics.…` in the send path. If the shape was ' +
        'refactored on purpose, update this pin in the same commit — the three rules (B2/B3/B4) still hold.');
    } else {
      check(bound && branch[1] === bound[1],
        'B1b. the predicate is fed the captured sendBatch result',
        `predicate argument "${branch[1]}" is not the awaited result "${bound && bound[1]}"`);
      check(branch[2] === 'haptics.warning()',
        'B2. all refused → haptics.warning()',
        `the all-refused arm calls ${branch[2]} — it must be the refused-send haptic, never success`);
      check(branch[3] === 'haptics.success()',
        'B3. otherwise (partial / full success) → haptics.success()',
        `the else arm calls ${branch[3]} — a batch with an offer out keeps the success haptic`);

      // B5: navigation after the branch, unconditional.
      const after = path_.slice(path_.indexOf(branch[0]) + branch[0].length);
      check(/navigation\.replace\('OverhaulPlan',\s*\{\s*overhaulId\s*\}\)/.test(after),
        'B5a. navigation.replace(OverhaulPlan) follows the branch',
        'navigation must stay after the haptic branch so an all-refused batch still opens the plan (the refusal reasons live there)');
      const opens = (after.match(/\{/g) || []).length;
      const closes = (after.match(/\}/g) || []).length;
      check(opens === closes && !/^\s*(if|else)\b[^\n]*navigation\.replace/m.test(path_),
        'B5b. navigation is not conditional on the result',
        'navigation.replace sits inside an if/else arm (unbalanced braces after the branch, or a one-line ' +
        'conditional) — an all-refused batch must navigate exactly as before');
    }

    // B4: exactly two haptic calls in the whole send path — the two arms.
    const calls = path_.match(/haptics\.\w+\(/g) || [];
    check(calls.length === 2
        && calls.filter((c) => c === 'haptics.success(').length === 1
        && calls.filter((c) => c === 'haptics.warning(').length === 1,
      'B4. exactly one success and one warning haptic in the send path',
      `found ${JSON.stringify(calls)} — a success haptic outside the else arm fires on the all-refused path too`);
  }
}

console.log(`\ncheck-overhaul-allfail-haptic: ${pass.length} passed, ${fail.length} failed`);
for (const p of pass) console.log(`  ✓ ${p}`);
if (fail.length) {
  console.error('\nFAILURES:');
  for (const f of fail) console.error(`  ✗ ${f}`);
  console.error(
    '\nAn all-refused overhaul batch (200 with every attempt send_failed) must fire the refused-send ' +
    'haptic, not success; partial and full success keep success; navigation is unchanged.\n',
  );
  process.exit(1);
}
console.log('');
