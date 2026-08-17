#!/usr/bin/env node
// Mock-draft modes — structural + behavioural suite (#295/#296/#305).
//
// Covers the manual-mode client surface end to end:
//   1. API typing — MockDraftMode, the two settings_echo additions, the
//      conditional `mode` body spread (1.12.x wire compatibility).
//   2. Setup sheet — the two-segment mode control, CPU default, re-seed.
//   3. MockDraftScreen — echo-first resolveUserOwnerId (CALLED, not
//      pattern-matched), the picking-for clock variant, the confirm-bar
//      meta, and the ticker who-column (CALLED: in manual mode every pick
//      is `by: "user"`, so the shipped `by`-keyed fallback rendered "—"
//      for every non-own pick).
//   4. Analytics — the five emitters, their screen args, their prop keys
//      asserted EQUAL to backend/analytics_taxonomy.py's frozensets
//      (registration, not just invocation: DEFAULT-DENY silently drops an
//      unregistered name behind a 200), the NON_INTENT rows, the
//      captured-slot rule and the settings_echo-not-request rule.
//
// House rules: TSX facts come from the TypeScript AST (comments cannot
// satisfy a literal); Python facts come from analytics files with `#`
// comments STRIPPED first (the taxonomy's own comments name these events).
//
// Run: node tests/check-mock-draft-modes.js
//   (or: npm run test:mock-draft-modes)

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

let failures = 0;
const ok = (name) => console.log(`PASS  ${name}`);
const fail = (name, detail) => {
  failures += 1;
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
};
const assert = (cond, name, detail) => (cond ? ok(name) : fail(name, detail));

function parse(rel) {
  const file = path.join(__dirname, '..', rel);
  return ts.createSourceFile(
    file,
    fs.readFileSync(file, 'utf8'),
    ts.ScriptTarget.ES2020,
    true,
    ts.ScriptKind.TSX,
  );
}

function walk(node, visit) {
  visit(node);
  node.forEachChild((c) => walk(c, visit));
}

function findAll(root, pred) {
  const out = [];
  walk(root, (n) => {
    if (pred(n)) out.push(n);
  });
  return out;
}

function tagOf(node) {
  if (ts.isJsxSelfClosingElement(node)) return node.tagName.getText();
  if (ts.isJsxElement(node)) return node.openingElement.tagName.getText();
  return null;
}

/** Python source with every `#` comment stripped (string-naive but the
 *  analytics files keep `#` out of string literals; a check satisfied by a
 *  comment naming the construct is the trap this exists to dodge). */
function pythonSansComments(rel) {
  const file = path.join(__dirname, '..', '..', rel);
  return fs
    .readFileSync(file, 'utf8')
    .split('\n')
    .map((l) => l.replace(/#.*$/, ''))
    .join('\n');
}

const apiSrc = parse('src/api/mockDraft.ts');
const sheetSrc = parse('src/components/draft/MockSetupSheet.tsx');
const mockSrc = parse('src/screens/MockDraftScreen.tsx');
const roomSrc = parse('src/screens/DraftRoomScreen.tsx');

// ═══════════════════════════════════════════════════════════════════════
// 1. API typing (LLD §3.1, PRD §5.6)
// ═══════════════════════════════════════════════════════════════════════

const modeAlias = findAll(
  apiSrc,
  (n) => ts.isTypeAliasDeclaration(n) && n.name.getText() === 'MockDraftMode',
)[0];
assert(!!modeAlias, 'mockDraft.ts declares MockDraftMode');
if (modeAlias) {
  const members = findAll(modeAlias, (n) => ts.isLiteralTypeNode(n))
    .map((n) => (ts.isStringLiteral(n.literal) ? n.literal.text : null))
    .filter(Boolean);
  assert(
    members.length === 2 && members.includes('cpu') && members.includes('manual'),
    "MockDraftMode is the CLOSED two-member enum 'cpu' | 'manual'",
    `members are [${members.join(', ')}]`,
  );
}

const echoIface = findAll(
  apiSrc,
  (n) => ts.isInterfaceDeclaration(n) && n.name.getText() === 'MockSettingsEcho',
)[0];
assert(!!echoIface, 'mockDraft.ts declares MockSettingsEcho');
if (echoIface) {
  const names = echoIface.members.map((m) => m.name && m.name.getText());
  assert(names.includes('mode'), 'MockSettingsEcho carries `mode`');
  assert(names.includes('user_owner_id'), 'MockSettingsEcho carries `user_owner_id`');
}

// The body spread: `mode` rides only when set, so a 1.12.x-shaped call is
// byte-identical on the wire.
const createFn = findAll(
  apiSrc,
  (n) => ts.isFunctionDeclaration(n) && n.name && n.name.getText() === 'createMockDraft',
)[0];
assert(!!createFn, 'mockDraft.ts declares createMockDraft');
if (createFn) {
  const spreads = findAll(createFn, (n) => ts.isSpreadAssignment(n)).map((n) => n.getText());
  const modeSpread = spreads.find((t) => t.includes('params.mode'));
  assert(
    !!modeSpread && /params\.mode\s*\?/.test(modeSpread) && modeSpread.includes('mode: params.mode'),
    'createMockDraft spreads `mode` conditionally (1.12.x wire compatibility)',
    `spreads are ${JSON.stringify(spreads)}`,
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 2. Setup sheet — the mode control (M5, PRD §4.1)
// ═══════════════════════════════════════════════════════════════════════

const segs = findAll(sheetSrc, (n) => {
  if (tagOf(n) !== 'TypeSeg') return false;
  const open = ts.isJsxSelfClosingElement(n) ? n : n.openingElement;
  return open.attributes.properties.some(
    (a) =>
      ts.isJsxAttribute(a) &&
      a.name.getText() === 'testID' &&
      a.initializer &&
      ts.isStringLiteral(a.initializer) &&
      a.initializer.text.startsWith('mock-setup.mode.'),
  );
});
assert(segs.length === 2, 'MockSetupSheet renders exactly two mode segments', `found ${segs.length}`);
if (segs.length === 2) {
  const attrOf = (el, name) => {
    const open = ts.isJsxSelfClosingElement(el) ? el : el.openingElement;
    const a = open.attributes.properties.find(
      (p) => ts.isJsxAttribute(p) && p.name.getText() === name,
    );
    return a && a.initializer ? a.initializer.getText().replace(/^\{|\}$/g, '') : null;
  };
  const byId = {};
  for (const s of segs) {
    byId[attrOf(s, 'testID').replace(/"/g, '')] = s;
  }
  const cpu = byId['mock-setup.mode.cpu'];
  const man = byId['mock-setup.mode.manual'];
  assert(!!cpu && !!man, 'Segment testIDs are mock-setup.mode.cpu / mock-setup.mode.manual');
  if (cpu && man) {
    assert(
      attrOf(cpu, 'label') === '"Your team"' && attrOf(man, 'label') === '"Every team"',
      'Segment labels are the PRD strings ("Your team" / "Every team")',
      `got ${attrOf(cpu, 'label')} / ${attrOf(man, 'label')}`,
    );
    assert(
      attrOf(cpu, 'disabled') === 'busy' && attrOf(man, 'disabled') === 'busy',
      'Both segments are disabled={busy}',
    );
    assert(
      /mode\s*===\s*'cpu'/.test(attrOf(cpu, 'active')) &&
        /mode\s*===\s*'manual'/.test(attrOf(man, 'active')),
      'Active segment tracks the mode state',
    );
  }
}

// Default + re-seed: 'cpu' at declaration AND on every open (pending-Q2
// designed-for default — flipping either half is a one-line operator call,
// and this is where it would be caught drifting).
{
  const decl = findAll(
    sheetSrc,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isArrayBindingPattern(n.name) &&
      n.name.getText().includes('mode') &&
      n.initializer &&
      n.initializer.getText().includes('useState<MockDraftMode>'),
  )[0];
  assert(
    !!decl && decl.initializer.getText().includes("'cpu'"),
    "Mode state defaults to 'cpu' (Q2 designed-for default)",
    decl ? decl.initializer.getText() : 'declaration not found',
  );
  const effects = findAll(
    sheetSrc,
    (n) => ts.isCallExpression(n) && n.expression.getText() === 'useEffect',
  );
  const reseed = effects.some((e) =>
    findAll(e, (n) =>
      ts.isCallExpression(n) &&
      n.expression.getText() === 'setMode' &&
      n.arguments.length === 1 &&
      ts.isStringLiteral(n.arguments[0]) &&
      n.arguments[0].text === 'cpu',
    ).length > 0,
  );
  assert(reseed, "The visibility effect re-seeds mode to 'cpu' on each open");
}

// onStart carries the mode.
{
  const onStartCalls = findAll(
    sheetSrc,
    (n) => ts.isCallExpression(n) && n.expression.getText() === 'onStart',
  );
  assert(
    onStartCalls.length === 1 &&
      ts.isObjectLiteralExpression(onStartCalls[0].arguments[0]) &&
      onStartCalls[0].arguments[0].properties.some(
        (p) => (p.name && p.name.getText()) === 'mode' || p.getText() === 'mode',
      ),
    'onStart result carries `mode`',
  );
}

// The PRD copy, byte-exact (curly apostrophes — Maestro matches source bytes).
{
  const text = findAll(
    sheetSrc,
    (n) => ts.isJsxText(n) || ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n),
  )
    .map((n) => (n.text || '').replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .join(' | ');
  assert(text.includes('You pick for'), 'Field label "You pick for" present');
  assert(
    text.includes('You make each team’s pick, in draft order, from first to last.'),
    'Manual field hint is the PRD string, byte-exact',
  );
  assert(
    text.includes('Computer drafters handle the other teams and stop when you’re up.'),
    'CPU field hint is the PRD string, byte-exact',
  );
  assert(
    text.includes('Nothing here is written to your league. You’re making every pick in this mock.'),
    'Manual footNote is the PRD string, byte-exact',
  );
  assert(
    text.includes('Nothing here is written to your league. Computer drafters pick for the other'),
    'CPU footNote keeps the shipped string',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 3. MockDraftScreen — echo-first identity, picking-for, ticker
// ═══════════════════════════════════════════════════════════════════════

// resolveUserOwnerId — transpiled and CALLED. The shipped inference is
// UNSOUND in manual mode (is_user is true on every owned slot), so the echo
// must win whenever it is present.
const resolveFn = findAll(
  mockSrc,
  (n) => ts.isFunctionDeclaration(n) && n.name && n.name.getText() === 'resolveUserOwnerId',
)[0];
assert(!!resolveFn, 'MockDraftScreen declares resolveUserOwnerId');
if (resolveFn) {
  const js = ts.transpileModule(`${resolveFn.getText()}\nreturn resolveUserOwnerId;`, {
    compilerOptions: { target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.None },
  }).outputText;
  let resolve;
  try {
    // eslint-disable-next-line no-new-func
    resolve = new Function(js)();
  } catch (e) {
    fail('resolveUserOwnerId is evaluable in isolation', String(e));
  }
  if (typeof resolve === 'function') {
    // Manual-mode shape: another team (id 3) is on the clock with
    // is_user: true — the echo (id 8) is the only sound answer.
    const manualState = {
      settings_echo: { user_owner_id: '8', mode: 'manual' },
      on_the_clock: { is_user: true, roster_id: '3' },
      my_picks: [],
    };
    assert(
      resolve(manualState) === '8',
      'resolveUserOwnerId reads the echo FIRST (manual-mode soundness)',
      `answered ${JSON.stringify(resolve(manualState))} — the shipped inference returns the on-clock team, which in manual mode is whichever team is up`,
    );
    // Old server: no echo → the shipped inference, sound in cpu mode.
    const oldServer = {
      settings_echo: { rounds: 4 },
      on_the_clock: { is_user: true, roster_id: '3' },
      my_picks: [],
    };
    assert(
      resolve(oldServer) === '3',
      'Old-server fallback keeps the shipped inference',
      `answered ${JSON.stringify(resolve(oldServer))}`,
    );
    assert(
      resolve({ settings_echo: { user_owner_id: '' }, on_the_clock: null, my_picks: [{ picked_by_user_id: '9' }] }) === '9',
      'An empty-string echo is not an identity (falls through)',
    );
  }
}

// forOwnTeam keys on userOwnerId, never on `by`.
{
  const decl = findAll(
    mockSrc,
    (n) => ts.isVariableDeclaration(n) && n.name.getText() === 'forOwnTeam',
  )[0];
  assert(!!decl, 'MockDraftScreen derives forOwnTeam');
  if (decl) {
    const t = decl.initializer ? decl.initializer.getText() : '';
    assert(
      t.includes('String(onClock.roster_id) === userOwnerId'),
      'forOwnTeam compares the slot owner to userOwnerId',
      `initializer is \`${t}\``,
    );
    assert(!/\bby\b/.test(t), 'forOwnTeam never reads `by`');
  }
}

// The picking-for sub-line: gated `isUser && !forOwnTeam`, PRD copy.
{
  const subline = findAll(
    mockSrc,
    (n) =>
      ts.isConditionalExpression(n) &&
      n.whenTrue.getText().includes('mock-draft.clock.picking-for'),
  )[0];
  assert(!!subline, 'The clock card renders the picking-for sub-line');
  if (subline) {
    const cond = subline.condition.getText().replace(/\s+/g, ' ');
    assert(
      /isUser\s*&&\s*!forOwnTeam/.test(cond),
      'The sub-line renders only when isUser && !forOwnTeam',
      `condition is \`${cond}\``,
    );
    assert(
      subline.whenTrue.getText().includes('You chose to pick for every team in this mock.'),
      'The sub-line copy is the PRD string, byte-exact',
    );
  }
  const clockText = findAll(
    mockSrc,
    (n) => ts.isTemplateExpression(n) || ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n),
  )
    .map((n) => n.getText())
    .join(' | ');
  assert(
    clockText.includes('`You’re picking for ${who}`'),
    'The on-behalf headline names the team (curly apostrophe)',
  );
  assert(
    clockText.includes("'You’re picking for this team'"),
    'The unresolvable-name headline fallback is the PRD string',
  );
  assert(
    clockText.includes("'You’re on the clock'"),
    'The own-turn headline is unchanged',
  );
}

// Confirm-bar meta: `your pick` only for the user's own team's slot.
{
  const meta = findAll(
    mockSrc,
    (n) =>
      ts.isConditionalExpression(n) &&
      n.getText().includes('your pick') &&
      n.getText().includes('forOwnTeam'),
  )[0];
  assert(!!meta, 'The confirm-bar meta branches on forOwnTeam');
  if (meta) {
    const t = meta.getText();
    assert(
      t.includes('’s pick '),
      "The on-behalf meta names the team (`{clockName}’s pick`, curly apostrophe)",
    );
    assert(
      t.includes('` · pick ${'),
      'The unresolvable-name meta degrades to a bare `pick`',
    );
  }
}

// The ticker who-column — extracted and CALLED. Mockup finding #1: shipped
// `mine ? 'You' : by === 'cpu' ? 'CPU' : '—'` renders "—" for every
// non-own pick in manual mode (all manual picks are `by: "user"`).
{
  const whoExpr = findAll(
    mockSrc,
    (n) =>
      ts.isConditionalExpression(n) &&
      ts.isConditionalExpression(n.whenFalse) &&
      n.whenTrue.getText() === "'You'" &&
      n.whenFalse.whenTrue.getText() === "'CPU'",
  )[0];
  assert(!!whoExpr, 'PickTicker has the who-column ternary');
  if (whoExpr) {
    const js = ts.transpileModule(
      `return function who(mine, p, nameOf) { return (${whoExpr.getText()}); };`,
      { compilerOptions: { target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.None } },
    ).outputText;
    let who;
    try {
      // eslint-disable-next-line no-new-func
      who = new Function(js)();
    } catch (e) {
      fail('The who-column expression is evaluable in isolation', String(e));
    }
    if (typeof who === 'function') {
      const names = new Map([['5', 'jakes_lakers']]);
      assert(
        who(true, { by: 'user', picked_by_user_id: '8' }, names) === 'You',
        "Own-team picks still render 'You'",
      );
      assert(
        who(false, { by: 'cpu', picked_by_user_id: '2' }, names) === 'CPU',
        "CPU picks still render 'CPU'",
      );
      assert(
        who(false, { by: 'user', picked_by_user_id: '5' }, names) === 'jakes_lakers',
        'A manual-mode pick for another team names that team',
        'the shipped column rendered "—" here — the mockup finding this fix exists for',
      );
      assert(
        who(false, { by: 'user', picked_by_user_id: '7' }, names) === '—',
        "An unnameable owner still degrades to '—'",
      );
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 4. Analytics — five emitters, registration-checked
// ═══════════════════════════════════════════════════════════════════════

const trackCallsIn = (src) =>
  findAll(src, (n) => ts.isCallExpression(n) && n.expression.getText() === 'track').filter(
    (c) => c.arguments.length >= 1 && ts.isStringLiteral(c.arguments[0]),
  );

const roomCalls = trackCallsIn(roomSrc);
const mockCalls = trackCallsIn(mockSrc);

const callFor = (calls, name) =>
  calls.find((c) => ts.isStringLiteral(c.arguments[0]) && c.arguments[0].text === name);

const EXPECT = [
  ['mock_started', roomCalls, 'DraftRoom'],
  ['mock_create_refused', roomCalls, 'DraftRoom'],
  ['mock_pick_made', mockCalls, 'MockDraft'],
  ['mock_completed', mockCalls, 'MockDraft'],
  ['mock_abandoned', mockCalls, 'MockDraft'],
];

// Prop keys of each call's object literal, top level only.
function propKeysOf(call) {
  const obj = call.arguments[1];
  if (!obj || !ts.isObjectLiteralExpression(obj)) return null;
  return obj.properties
    .map((p) => {
      if (ts.isPropertyAssignment(p) || ts.isShorthandPropertyAssignment(p)) {
        return p.name.getText();
      }
      return null;
    })
    .filter(Boolean)
    .sort();
}

// The taxonomy's frozensets, comments stripped BEFORE matching.
const taxonomy = pythonSansComments('backend/analytics_taxonomy.py');
const queries = pythonSansComments('backend/analytics_queries.py');

function frozensetKeys(eventName) {
  const re = new RegExp(`"${eventName}":\\s*frozenset\\(\\{([\\s\\S]*?)\\}\\)`);
  const m = re.exec(taxonomy);
  if (!m) return null;
  return [...m[1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1]).sort();
}

// ALLOWED_CLIENT_EVENTS block (a set literal; grab its braces).
const allowedBlock = (() => {
  const start = taxonomy.indexOf('ALLOWED_CLIENT_EVENTS');
  if (start < 0) return '';
  const open = taxonomy.indexOf('{', start);
  const close = taxonomy.indexOf('}', open);
  return taxonomy.slice(open, close);
})();
const allowedNames = new Set([...allowedBlock.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]));

// NON_INTENT_EVENTS block.
const nonIntentBlock = (() => {
  const start = queries.indexOf('NON_INTENT_EVENTS');
  if (start < 0) return '';
  const open = queries.indexOf('{', start);
  const close = queries.indexOf('}', open);
  return queries.slice(open, close);
})();
const nonIntent = new Set([...nonIntentBlock.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]));

for (const [name, calls, screen] of EXPECT) {
  const call = callFor(calls, name);
  assert(!!call, `track('${name}') is fired`);
  if (!call) continue;
  const screenArg = call.arguments[2];
  assert(
    !!screenArg && ts.isStringLiteral(screenArg) && screenArg.text === screen,
    `track('${name}') carries screen '${screen}'`,
    screenArg ? screenArg.getText() : 'no screen arg',
  );
  // Registration, not just invocation — an unregistered event is silently
  // dropped behind a 200.
  assert(
    allowedNames.has(name),
    `'${name}' is registered in ALLOWED_CLIENT_EVENTS`,
    'DEFAULT-DENY drops it silently; the emitter would read like working instrumentation',
  );
  const want = frozensetKeys(name);
  const got = propKeysOf(call);
  assert(
    !!want && !!got && JSON.stringify(want) === JSON.stringify(got),
    `'${name}' props equal the CLIENT_EVENT_PROPS frozenset exactly`,
    `client sends [${(got || []).join(', ')}], taxonomy allows [${(want || []).join(', ')}]`,
  );
}

// The DAU seam: outcomes are NON_INTENT; decisions are INTENT.
assert(nonIntent.has('mock_completed'), "'mock_completed' is NON_INTENT (an outcome)");
assert(nonIntent.has('mock_create_refused'), "'mock_create_refused' is NON_INTENT (an impression)");
for (const name of ['mock_started', 'mock_pick_made', 'mock_abandoned']) {
  assert(!nonIntent.has(name), `'${name}' stays INTENT (a real user decision)`);
}

// mock_pick_made reads the slot captured in onMutate — never the response's
// on_the_clock, which is the NEXT slot.
{
  const call = callFor(mockCalls, 'mock_pick_made');
  if (call) {
    const t = call.getText();
    assert(
      !t.includes('on_the_clock'),
      "mock_pick_made never reads the response's on_the_clock",
      'the response carries the NEXT slot, not the one just picked',
    );
    assert(
      /picked\.round/.test(t) && /picked\.pick_no/.test(t),
      'mock_pick_made reads the onMutate-captured slot',
    );
    assert(
      t.includes('user_owner_id') && !/picked\.by|\bp\.by\b|ns\.by/.test(t),
      'for_own_team keys on user_owner_id, never on `by`',
    );
  }
  const onMutate = findAll(
    mockSrc,
    (n) =>
      (ts.isPropertyAssignment(n) || ts.isMethodDeclaration(n)) &&
      n.name &&
      n.name.getText() === 'onMutate',
  )[0];
  assert(
    !!onMutate && onMutate.getText().includes('onClock'),
    'pickMutation captures the pre-mutation onClock in onMutate',
  );
}

// mock_completed fires only on the active → complete transition, and its
// user_picks counts the TEAM's picks (my_picks), never a by==="user" count.
{
  const call = callFor(mockCalls, 'mock_completed');
  if (call) {
    assert(
      call.getText().includes('my_picks.length'),
      "mock_completed.user_picks counts my_picks (the user's TEAM)",
      'a by==="user" count would be every pick in manual mode (HLD §4.3)',
    );
    let guard = null;
    for (let p = call.parent; p; p = p.parent) {
      if (ts.isIfStatement(p) && p.getText().includes('mock_completed')) {
        guard = p.expression.getText();
        break;
      }
    }
    assert(
      !!guard && guard.includes("'active'") && guard.includes("'complete'"),
      'mock_completed is gated on the active → complete transition',
      `guard is \`${guard}\` — without it a resumed recap could re-emit`,
    );
  }
}

// mock_started reads the server's RESOLVED settings_echo, never the sheet's
// request values.
{
  const call = callFor(roomCalls, 'mock_started');
  if (call) {
    const t = call.getText();
    assert(
      (t.match(/settings_echo/g) || []).length >= 6,
      'mock_started props read off res.settings_echo (all six, incl. #328 ownership_source)',
      'a clamped rounds or degraded order_source/ownership_source must report as resolved',
    );
    assert(
      /ownership_source:\s*res\.settings_echo\?\.ownership_source/.test(t),
      "mock_started carries ownership_source off the RESOLVED echo (#328)",
      'the fallback-rate-per-platform query needs the resolved value, never the request',
    );
    assert(
      !/setup\.|board\??\./.test(t),
      'mock_started never reads the request values or the board',
    );
  }
}

// mock_abandoned fires from the destructive onPress BEFORE the abandon call.
{
  const call = callFor(mockCalls, 'mock_abandoned');
  if (call) {
    const abandonCall = findAll(
      mockSrc,
      (n) => ts.isCallExpression(n) && n.expression.getText() === 'abandonMockDraft',
    )[0];
    assert(
      !!abandonCall && call.getStart() < abandonCall.getStart(),
      'mock_abandoned fires before the abandonMockDraft promise',
      'the tap is the intent; the network result is not',
    );
    assert(
      call.getText().includes('picks.length'),
      'mock_abandoned.picks_made counts state.picks',
    );
  }
}

// Every emitter derives platform from the session league cache (the
// InLeagueCalculator convention) — never the device platform.
for (const [name, src] of [
  ['DraftRoomScreen', roomSrc],
  ['MockDraftScreen', mockSrc],
]) {
  const t = src.getFullText();
  assert(
    t.includes('useSession.getState().leagues.find'),
    `${name} derives platform from the session league cache`,
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All mock-draft mode checks passed.');
