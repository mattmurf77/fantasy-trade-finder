#!/usr/bin/env node
// Guided Onboarding v2 — the script's structural contract (PRD §5.0 / FR-E7).
//
// D-056 retired Maestro, so the copy budget and the eligibility contract have
// no runtime vehicle: this suite is the enforcement. It follows the S-43
// template (check-s51-regen-diff.js) — parse the real source with the
// project's own TypeScript, then EXECUTE the shipped builders rather than
// regex their text, so a slot that silently renders "1 new trades" is caught
// by reading the string a user would actually see.
//
// WHAT IS PINNED, and the sabotage each assertion detects:
//
//   1  The builder set. `s7.1` is CUT (its target cannot mount under shipped
//      flags; it fires today pointing at nothing — the live FR-E6 exhibit),
//      `s3.1` is merged into `s3.2`, and the four phantom steps (S2.identity,
//      S2.re-entry, S4.2, S4.idle — S4.idle being the banned idle-timeout
//      trigger family) never come back. Sabotage: re-add any of them → red.
//   2  Copy budget per class, measured on the RENDERED line with slots
//      resolved: auto 12 / action 16 / tap 20 / cta 16, CTA labels ≤4 words,
//      at most one primary action per beat. Sabotage: restore any v1 line
//      (s2.1 at 21w, s5.0 at 27w …) → red.
//   3  The `autoMs` reading floor for auto steps: words/4.17×1000 + 800.
//      Sabotage: restore s6.1's 2200 ms or s6.2's 2600 ms → red.
//   4  Every v2 beat (`n`-prefixed, per useGuide.isV2NewStepId) declares the
//      §5.0 contract: retirement (a `retireAfter`, or `'never'` with a
//      written reason on the same line), a display cap, an adoptionEvent,
//      and a degrade contract. Sabotage: drop any field → red.
//   5  The degrade contract is honest: a targeted step carries a
//      `degradeLine` or `degrade:'suppress'`; an untargeted step's line
//      contains no deixis, because there is no pointer to lose.
//   6  Retirement reads CLIENT receipts only — every `retireAfter` /
//      `invalidateOn` id is a member of the exported GUIDE_RECEIPTS
//      vocabulary. This is the screen-agent contract: a receipt name that
//      drifts from the one a screen records is a retirement that never
//      fires, which FR-E3 rates worse than none.
//   7  `s5.1` is plural-safe at N=1 (the S-43 handoff defect).
//
// SLOT ASSUMPTIONS (documented because the caps are measured, not estimated):
// every slot in this script resolves to exactly ONE word — a position code
// ('WR'), a count ('12'), never a phrase — so the probe values below are the
// longest plausible renderings and the word count is slot-value-independent.
// A future builder that interpolates a phrase must extend PROBES so the
// longest form is the one measured.
//
// Run: node tests/check-guide-script.js

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

const SCRIPT_REL = 'src/components/analystScript.ts';
const SCRIPT_ABS = path.join(__dirname, '..', SCRIPT_REL);
const source = fs.readFileSync(SCRIPT_ABS, 'utf8');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

// ── Load the real module ───────────────────────────────────────────────────
// The only import is `import type { GuideStep }`, which transpiles away, so
// the module is self-contained and safe to execute.
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;
const shim = { exports: {} };
new Function('module', 'exports', 'require', js)(shim, shim.exports, () => {
  throw new Error('analystScript must stay import-free (data only)');
});
const { S, GUIDE_RECEIPTS, nextUnrankedPosition } = shim.exports;

assert(!!S && typeof S === 'object', '0a — the script table loads and executes');
assert(
  !!GUIDE_RECEIPTS && Object.keys(GUIDE_RECEIPTS).length === 8,
  '0b — the client-receipt vocabulary is exported (8 names)',
  'screens import these ids; an unexported vocabulary is a naming drift waiting to happen',
);
assert(
  typeof nextUnrankedPosition === 'function' &&
    nextUnrankedPosition(['QB', 'RB', 'WR', 'TE']) === null,
  '0c — nextUnrankedPosition still self-terminates when every position is ranked',
  's5.5 has no all_positions_ranked receipt; this null IS its retirement',
);

const RECEIPTS = new Set(Object.values(GUIDE_RECEIPTS || {}));

// ── The expected builder set ───────────────────────────────────────────────
// name → { id, args: [argument tuples to render] }. Every tuple is rendered
// and every rendering is held to the full contract.
const PROBES = {
  s0_1: { id: 's0.1', args: [[]] },
  s0_2: { id: 's0.2', args: [[]] },
  s0_err_notfound: { id: 's0.err-notfound', args: [[]] },
  s0_err_down: { id: 's0.err-down', args: [[]] },
  s1_1: { id: 's1.1', args: [[]] },
  s2_wait: { id: 's2.wait', args: [[12], [null]] }, // numbered + no-number variant
  s2_1: { id: 's2.1', args: [[]] },
  s2_2: { id: 's2.2', args: [[]] },
  s2_3: { id: 's2.3', args: [[]] }, // deprecated; dies with its call site
  s3_2: { id: 's3.2', args: [['WR', true], ['WR', false]] },
  s4_1: { id: 's4.1', args: [[]] },
  s5_1: { id: 's5.1', args: [[1, 'WR'], [12, 'WR']] },
  s5_0: { id: 's5.0', args: [['WR']] },
  s5_5: { id: 's5.5', args: [['QB', 'WR']] },
  s6_1: { id: 's6.1', args: [[]] }, // deprecated; dies with its call site
  s6_2: { id: 's6.2', args: [[]] },
  s8_1: { id: 's8.1', args: [[]] },
  n1: { id: 'n1', args: [[]] },
  n2a: { id: 'n2a', args: [[]] },
  n2b: { id: 'n2b', args: [[]] },
  n4: { id: 'n4', args: [[]] },
  n6_1: { id: 'n6.1', args: [[true], [false]] }, // router + router-less
  n8: { id: 'n8', args: [[]] },
  n9: { id: 'n9', args: [[]] },
  n5: { id: 'n5', args: [[]] },
  // #384 W4 — the merged calculator tour. Every beat is argument-free
  // (no slots), so one probe each is the whole surface.
  n10: { id: 'n10', args: [[]] },
  n11: { id: 'n11', args: [[]] },
  n12: { id: 'n12', args: [[]] },
  n13: { id: 'n13', args: [[]] },
  n15: { id: 'n15', args: [[]] },
  n16: { id: 'n16', args: [[]] },
  n18: { id: 'n18', args: [[]] },
  n19: { id: 'n19', args: [[]] },
  n20: { id: 'n20', args: [[]] },
  n21: { id: 'n21', args: [[]] },
  n22: { id: 'n22', args: [[]] },
  n23: { id: 'n23', args: [[]] },
  // The off-Sleeper sibling of n23 — same slot in the runner, chosen by
  // `resolveSendPlatform`. It is a full beat and is held to the full contract.
  n23b: { id: 'n23b', args: [[]] },
  n24: { id: 'n24', args: [[]] },
};

// ═══ 1 — the builder set: cuts stay cut ════════════════════════════════════

const actual = Object.keys(S).sort();
const expected = Object.keys(PROBES).sort();
assert(
  actual.join(',') === expected.join(','),
  '1a — the script exports exactly the expected builders',
  `unexpected: [${actual.filter((k) => !expected.includes(k))}] · missing: [${expected.filter((k) => !actual.includes(k))}]`,
);

assert(!('s7_1' in S), '1b — s7.1 is CUT (it fires today pointing at nothing)');
assert(
  !/id:\s*['"]s7\.1['"]/.test(source),
  '1c — no step object carries the id s7.1',
  'a renamed builder is the same live deictic incoherence',
);
assert(!('s3_1' in S), '1d — s3.1 is CUT (merged into s3.2)');
for (const phantom of ['s2_identity', 's2_re_entry', 's4_2', 's4_idle']) {
  assert(!(phantom in S), `1e — phantom step ${phantom} is absent`);
}
assert(
  !/idle/i.test(source.replace(/S4\.idle/g, '')),
  '1f — no idle-timeout trigger anywhere (the banned trigger family, NG-5)',
);

// ── Render every probe ─────────────────────────────────────────────────────
const rendered = []; // { builder, step }
for (const [name, spec] of Object.entries(PROBES)) {
  if (typeof S[name] !== 'function') continue;
  for (const args of spec.args) {
    const step = S[name](...args);
    rendered.push({ builder: name, args, step });
  }
  const ids = new Set(spec.args.map((a) => S[name](...a).id));
  assert(
    ids.size === 1 && ids.has(spec.id),
    `1g — ${name} renders exactly one script id (${spec.id})`,
    `got [${[...ids]}] — variants of one beat share an id so the seen/retired ledgers agree`,
  );
}

// ── Word counting ──────────────────────────────────────────────────────────
// A token counts only if it carries a letter or a digit, so em dashes and the
// CTA arrow are punctuation, not words.
function words(text) {
  return text
    .split(/\s+/)
    .filter((t) => /[A-Za-z0-9]/.test(t)).length;
}

const CAPS = { auto: 12, action: 16, tap: 20, cta: 16 };

// ═══ 2 — copy budget per class ═════════════════════════════════════════════

for (const { builder, args, step } of rendered) {
  const cap = CAPS[step.advance];
  const tag = `${step.id}${args.length ? `(${args.join(',')})` : ''}`;
  assert(cap != null, `2a — ${tag} declares a known copy class`, `advance=${step.advance}`);
  if (cap == null) continue;
  assert(
    words(step.line) <= cap,
    `2b — ${tag} line is within the ${step.advance} cap (${cap})`,
    `${words(step.line)} words: "${step.line}"`,
  );
  if (step.degradeLine) {
    assert(
      words(step.degradeLine) <= cap,
      `2c — ${tag} degradeLine is within the ${step.advance} cap (${cap})`,
      `${words(step.degradeLine)} words`,
    );
  }
  const ctas = step.ctas || [];
  for (const c of ctas) {
    assert(
      words(c.label) <= 4,
      `2d — ${tag} CTA "${c.label}" is ≤4 words`,
      `${words(c.label)} words`,
    );
  }
  assert(
    ctas.filter((c) => c.kind === 'primary').length <= 1,
    `2e — ${tag} declares at most one primary action`,
    'two primaries is two asks in one interrupt slot',
  );
  if (step.advance === 'cta') {
    assert(ctas.length > 0, `2f — ${tag} is a cta step and has buttons`);
  }
  void builder;
}

// ═══ 3 — the auto-advance reading floor ════════════════════════════════════

for (const { step } of rendered) {
  if (step.advance !== 'auto') continue;
  const floor = Math.ceil((words(step.line) / 4.17) * 1000 + 800);
  assert(
    typeof step.autoMs === 'number' && step.autoMs >= floor,
    `3a — ${step.id} autoMs clears the reading floor`,
    `${step.autoMs} ms for ${words(step.line)} words needs ≥${floor} ms`,
  );
}

// ═══ 4/5 — the v2 eligibility + degrade contract ═══════════════════════════

// `isV2NewStepId` in useGuide.ts — the FR-E9 release cap finds new beats by
// this shape, so a v2 beat with an `s` id is invisible to it.
const isV2 = (id) => /^n\d/i.test(id);

// Justified `'never'`: the lint requires a stated reason ON THE SAME LINE.
const neverLines = source
  .split('\n')
  .filter((l) => /retireAfter:\s*'never'/.test(l));
const justifiedNevers = neverLines.filter((l) => /\/\/\s*reason:\s*\S+(\s+\S+){2,}/.test(l));
assert(
  neverLines.length === justifiedNevers.length,
  "4a — every retireAfter: 'never' carries a written reason on its line",
  `${neverLines.length - justifiedNevers.length} unjustified`,
);

// Deixis: words that point at a UI element the spotlight was supposed to
// frame. Screen-level orientation ("land here") is not deixis — there is no
// pointer to lose. Element-level pointing is.
//
// The noun list was widened 2026-08-22 (#384 W5) with the element nouns the
// calculator beats actually use — `cross`, `check`, `canvas`, `meter`,
// `columns`, `arrows`, `switch`, `panel`, `sheet` — plus the bare "this is
// your X" form. Removing n12's `target` while keeping "This is your canvas"
// was green under the narrower list, because `canvas` was not a noun it knew.
const DEIXIS =
  /\b(?:that|this|these|those)\s+(?:label|chip|button|control|card|row|pill|tab|section|icon|badge|banner|menu|toggle|slider|field|cross|check|canvas|meter|column|columns|arrow|arrows|switch|panel|sheet|link)\b|\bthis is your\b|\b(?:tap|see|hit|press)\s+(?:that|this)\b|\b(?:right|up|down)\s+there\b|\bbelow\b|\babove\b/i;

for (const { step, args } of rendered) {
  if (!isV2(step.id)) continue;
  const tag = `${step.id}${args.length ? `(${args.join(',')})` : ''}`;

  assert(
    step.retireAfter !== undefined,
    `4b — ${tag} declares retirement (retireAfter or a justified 'never')`,
  );
  if (step.retireAfter && step.retireAfter !== 'never') {
    assert(
      RECEIPTS.has(step.retireAfter.event) && step.retireAfter.count >= 1,
      `4c — ${tag} retires on a CLIENT receipt from the exported vocabulary`,
      `${step.retireAfter.event} is not a GUIDE_RECEIPTS value — a server-fired name never retires anything`,
    );
  }
  assert(
    typeof step.maxDisplayCount === 'number' || step.once === true,
    `4d — ${tag} carries a display cap (maxDisplayCount or once)`,
  );
  assert(
    typeof step.adoptionEvent === 'string' && step.adoptionEvent.length > 0,
    `4e — ${tag} names the downstream event it claims to cause`,
    'no event, no thesis',
  );

  const degradeOk = step.target
    ? !!step.degradeLine || step.degrade === 'suppress'
    : !DEIXIS.test(step.line);
  assert(
    degradeOk,
    `5a — ${tag} has a degrade contract`,
    step.target
      ? 'a targeted step needs a degradeLine or degrade:"suppress"'
      : `an untargeted line must carry no deixis: "${step.line}"`,
  );

  // 5b is the CONVERSE, and it is what makes 5a falsifiable by the sabotage
  // that matters: deleting a beat's `target` line while leaving its copy
  // alone. 5a then evaluates the untargeted branch, and a deictic line only
  // fails if the DEIXIS vocabulary happens to know the noun — a copy-shaped
  // dependency, not a structural one. A `degradeLine` is the beat's own
  // declaration that it HAS a spotlight to lose; carrying one with no target
  // is a contradiction inside a single object, and every #384 beat carries
  // one. Verified: removing `target` from n12/n16/n19/n22 was green before
  // this and is red after.
  assert(
    !step.degradeLine || !!step.target,
    `5b — ${tag} declares a degradeLine only if it has a target to lose`,
    'a degradeLine on an untargeted beat means the target was deleted and the '
      + 'copy was not — the beat now points at nothing on every run',
  );
}

// Receipt hygiene applies to every step that declares one, v1 rows included.
for (const { step } of rendered) {
  for (const e of step.invalidateOn || []) {
    assert(
      RECEIPTS.has(e),
      `6a — ${step.id} invalidateOn "${e}" is a client receipt`,
      'invalidation wired to a server-fired name never fires (FR-E3: worse than none)',
    );
  }
  if (step.retireAfter && step.retireAfter !== 'never') {
    assert(
      RECEIPTS.has(step.retireAfter.event),
      `6b — ${step.id} retireAfter "${step.retireAfter.event}" is a client receipt`,
    );
  }
}

// Every receipt in the vocabulary is documented in the header block, because
// that block is what screen agents read when wiring `recordGuideReceipt`.
const header = source.slice(0, source.indexOf('export const GUIDE_RECEIPTS'));
for (const name of RECEIPTS) {
  assert(
    header.includes(name),
    `6c — receipt "${name}" is documented in the header contract block`,
  );
}

// ═══ 7 — s5.1 is plural-safe ═══════════════════════════════════════════════

const one = S.s5_1(1, 'WR').line;
const many = S.s5_1(12, 'WR').line;
assert(!/\b1 new trades\b/.test(one), '7a — N=1 does not render "1 new trades"');
assert(/\btrade\b/.test(one) && !/\btrades\b/.test(one), '7b — N=1 renders the singular noun');
assert(/\bexists\b/.test(one), '7c — N=1 agrees the verb too ("exists", not "exist")');
assert(/\b12 new trades\b/.test(many), '7d — N>1 renders the plural noun');
assert(/\bexist\b/.test(many) && !/\bexists\b/.test(many), '7e — N>1 keeps the plural verb');

// ═══ 8 — the CTA lifetime bound on the one beat that needs it ══════════════

const n61 = S.n6_1(true);
assert(
  n61.lifetimeMs === 8000,
  '8a — n6.1 (router form) is lifetime-bounded at 8 s',
  'an unbounded cta bubble holds the interrupt slot across further swipes and starves the Apple ask',
);
assert(
  S.n6_1(false).ctas === undefined,
  '8b — the router-less n6.1 variant offers no route it cannot honour',
  'routing into an empty "Awaiting them" one tap after "logged" is the R1 moment',
);

// ═══ 9 — the n23 pair: one platform claim, two beats ═══════════════════════
//
// "Passwords never leave your phone" is true on Sleeper only: MFL POSTs the
// password to /api/mfl/auth-link and ESPN stores espn_s2/SWID server-side.
// The operator vouched for the Sleeper claim, so the sentence may exist in
// exactly one beat and the sibling must carry no password claim at all.
{
  const sleeper = S.n23().line;
  const other = S.n23b().line;
  assert(
    /password/i.test(sleeper),
    '9a — n23 (Sleeper) is the beat that carries the password claim',
  );
  assert(
    !/password/i.test(other),
    '9b — n23b (off-Sleeper) makes no password claim',
    `"${other}" — MFL and ESPN both send a credential off the device`,
  );
  assert(
    S.n23().screen === 'Trades' && S.n23b().screen === 'Trades',
    '9c — both n23 variants declare the deck screen',
  );
}

console.log(
  failures === 0
    ? '\nAll guide-script assertions passed.'
    : `\n${failures} assertion(s) failed.`,
);
process.exit(failures === 0 ? 0 : 1);
