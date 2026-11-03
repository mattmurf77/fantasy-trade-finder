#!/usr/bin/env node
// No raw member id as a team label (head-eng, 2026-11-03: a raw user id must
// not be shown to leaguemates).
//
// WHY THIS EXISTS. Three screens fell back to the member id when the server
// sent no name:
//   - PickAssignmentScreen's setup list: `m.display_name || m.username || m.user_id`
//   - DraftRoomScreen's board: `owner_username ?? owner_user_id ?? 'Unassigned'`,
//     where `??` also let a blank or whitespace name through
//   - MockDraftScreen's `ownerNameOf`: every non-MFL id returned raw
// So an ESPN member with no name showed `espn:{SWID}`, `espn:<lid>.t7`,
// `acct_…` or a blank row. The server heals its own stored names (#497);
// these were the CLIENT's fallbacks, and nothing a server fix does reaches them.
//
// Pins:
//   §1 `utils/teamLabel.ts`, the one helper: zero runtime imports, then
//      transpiled and EXECUTED. A real name is trimmed and wins; a blank,
//      whitespace, a minted id, the member's own id or `Team <id>` is not a
//      name; then `Team <fid>` (MFL), `Team <slot>`, `Unnamed team`. An id
//      is never returned and a label is never blank. `assignmentSlots` keeps
//      a grid member's `original_roster_id`, gives the rest the next free
//      integer in the server's order, and its slots are distinct.
//   §2 PickAssignment: `<SetupView members>` is `setupMembers`, and the
//      `setupMembers` memo body is lifted out of the screen and EXECUTED:
//      nameless members never show an id and never share a label, seeded or
//      not. No `|| m.user_id` / `?? m.user_id` anywhere.
//   §3 DraftRoom: the owner cell's expression and the `ownSlotByUser` memo
//      are lifted and EXECUTED: an owner's slot is read off the row they
//      originally hold, an owner with no name reads `Team <slot>` or
//      `Unnamed team`, no owner at all reads `Unassigned`. No
//      `?? slot.owner_user_id` / `|| slot.owner_user_id`.
//   §4 MockDraft: `ownerNameOf` and `ownSlotOf` are lifted and EXECUTED.
//      ESPN / acct_ ids and blank names never render; MFL keeps `Team <fid>`.
//      The ONE raw-id return left is D-16's Sleeper path, guarded by an
//      all-digit test, and it is pinned here so widening it goes red. Both
//      call sites pass the owner's own slot.
//   §5 Single source: `Unnamed team` and the MFL id regex live only in the
//      helper.
//
// HONEST LABEL (G-035): §2-§4 execute the expressions the screens ship, cut
// out of the source, with React stubbed out by construction (no hooks run).
// They prove what each call site computes, not what a device renders. The
// TestFlight checklist in docs/plans/draft-extensions/
// scope-mobile-no-raw-id-labels.md is the runtime half.
//
// Run: node tests/check-no-raw-id-labels.js   (or: npm run test:no-raw-id-labels)
'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
let ts;
try {
  ts = require('typescript');
} catch (e) {
  console.error('FAIL  typescript is not installed (run npm install in mobile/)');
  process.exit(1);
}

let failures = 0;
const assert = (cond, name, why) => {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`);
  }
};
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
const parse = (rel) =>
  ts.createSourceFile(rel, read(rel), ts.ScriptTarget.ES2019, true, ts.ScriptKind.TSX);
const findAll = (root, pred) => {
  const out = [];
  const walk = (n) => {
    if (pred(n)) out.push(n);
    n.forEachChild(walk);
  };
  walk(root);
  return out;
};
/** Source with every comment removed, so a fallback cannot hide in prose. */
const codeOf = (sf) => ts.createPrinter({ removeComments: true }).printFile(sf);
/** Transpile `body` (statements ending in a `return`) and run it with `scope`. */
const run = (body, scope) => {
  const js = ts.transpileModule(body, {
    compilerOptions: { target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.None },
  }).outputText;
  const names = Object.keys(scope);
  // eslint-disable-next-line no-new-func
  return new Function(...names, js)(...names.map((k) => scope[k]));
};
/** The first argument of the `useMemo(...)` that initialises `name`. */
const memoBody = (sf, name) => {
  const decl = findAll(
    sf,
    (n) => ts.isVariableDeclaration(n) && n.name.getText() === name,
  )[0];
  const init = decl && decl.initializer;
  if (!init || !ts.isCallExpression(init) || init.expression.getText() !== 'useMemo') return null;
  return init.arguments[0] ? init.arguments[0].getText() : null;
};
const ID_SHAPE = /espn:|acct_|mfl:/;

// ═══════════════════════════════════════════════════════════════════════
// §1. The helper
// ═══════════════════════════════════════════════════════════════════════

const HELPER_REL = 'src/utils/teamLabel.ts';
const helperSrc = read(HELPER_REL);
assert(!/^\s*import\s+(?!type\b)/m.test(helperSrc), '1a. teamLabel.ts has zero runtime imports');
const h = (() => {
  const js = ts.transpileModule(helperSrc, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const m = { exports: {} };
  new Function('module', 'exports', 'require', js)(m, m.exports, () => {
    throw new Error('teamLabel.ts must not require anything at runtime');
  });
  return m.exports;
})();
const { teamLabel, realName, assignmentSlots } = h;

const SWID = 'espn:{1A2B3C4D-5E6F-7A8B-9C0D-1E2F3A4B5C6D}';
const IDS = [SWID, 'espn:62846.t7', 'acct_12345', 'mfl:62846.f0003'];

assert(teamLabel(['  Mike  '], SWID, 3) === 'Mike', '1b. a real name passes through, trimmed');
assert(
  teamLabel([' ', null, undefined, 'bravo'], 'acct_1', 2) === 'bravo',
  '1c. the first candidate that is a real name wins',
);
assert(
  teamLabel(['Team Rocket'], SWID, 3) === 'Team Rocket' &&
    teamLabel(['Unnamed team'], SWID, 3) === 'Unnamed team',
  '1d. a real name that starts with "Team", and the server\'s own label, pass as names',
);
assert(
  teamLabel(['   '], SWID, 3) === 'Team 3' &&
    teamLabel([''], 'acct_1', '7') === 'Team 7' &&
    teamLabel([null], 'espn:62846.t7', 12) === 'Team 12',
  '1e. a blank or whitespace name falls back to Team <slot>',
);
assert(
  teamLabel([null], SWID) === 'Unnamed team' &&
    teamLabel([undefined], 'acct_1', null) === 'Unnamed team' &&
    teamLabel(['\t'], '', '  ') === 'Unnamed team' &&
    teamLabel([], null, undefined) === 'Unnamed team',
  '1f. a blank name with no slot is Unnamed team',
);
assert(
  teamLabel([null], 'mfl:62846.f0003', 9) === 'Team 0003' &&
    teamLabel(['  '], 'mfl:62846.f0012') === 'Team 0012' &&
    teamLabel(['mattmurf77'], 'mfl:62846.f0001', 1) === 'mattmurf77',
  '1g. an MFL id still gives Team <fid>, zero-padding kept; a real name still wins',
);
{
  const bad = [];
  for (const id of IDS) {
    const names = [null, undefined, '', '   ', id, ` ${id} `, `Team ${id}`, `Team  ${id}`];
    for (const name of names) {
      for (const slot of [null, undefined, '', 4, '4']) {
        const got = teamLabel([name], id, slot);
        const shapeOk = got === 'Unnamed team' || /^Team \S+$/.test(got);
        if (got.includes(id) || ID_SHAPE.test(got) || !got.trim() || !shapeOk) {
          bad.push(`teamLabel([${JSON.stringify(name)}], ${JSON.stringify(id)}, ${JSON.stringify(slot)}) = ${JSON.stringify(got)}`);
        }
      }
    }
  }
  assert(bad.length === 0, '1h. an ESPN, acct_ or MFL id is never returned, never blank', bad.slice(0, 6).join(' ; '));
}
assert(
  realName(['867530912'], '867530912') === null &&
    realName(['Team 867530912'], '867530912') === null &&
    realName(['  Ann '], '867530912') === 'Ann',
  '1i. realName: the member\'s own id and `Team <their id>` are not names, on any platform',
);
{
  const s1 = assignmentSlots(['u3', 'u1', 'u2'], []);
  assert(
    s1.get('u3') === '1' && s1.get('u1') === '2' && s1.get('u2') === '3',
    '1j. assignmentSlots, no grid: the slot is the position in the server\'s order',
  );
  const grid = [
    { original_user_id: 'A', original_roster_id: '1' },
    { original_user_id: 'X', original_roster_id: '3' },
    { original_user_id: 'X', original_roster_id: '3' },
  ];
  const s2 = assignmentSlots(['X', 'B', '', 'A', 'B', 'C'], grid);
  const vals = [...s2.values()];
  assert(
    s2.get('X') === '3' && s2.get('A') === '1' && s2.get('B') === '2' && s2.get('C') === '4' &&
      !s2.has('') && new Set(vals).size === vals.length,
    '1k. assignmentSlots, seeded: grid members keep their slot, newcomers take the next free one, all distinct',
    JSON.stringify([...s2.entries()]),
  );
}

// ═══════════════════════════════════════════════════════════════════════
// §2. PickAssignmentScreen — the setup step's member list
// ═══════════════════════════════════════════════════════════════════════

const paSf = parse('src/screens/PickAssignmentScreen.tsx');
const paCode = codeOf(paSf);
{
  const setupViews = findAll(
    paSf,
    (n) => ts.isJsxSelfClosingElement(n) && n.tagName.getText() === 'SetupView',
  );
  const membersAttr = setupViews
    .map((el) => el.attributes.properties.find((a) => a.name && a.name.getText() === 'members'))
    .filter(Boolean);
  assert(
    membersAttr.length === 1 && /^\{\s*setupMembers\s*\?\?\s*teams\s*\}$/.test(membersAttr[0].initializer.getText()),
    '2a. <SetupView members> is `setupMembers ?? teams`',
    membersAttr.map((a) => a.getText()).join(' | '),
  );
  assert(
    !/(\|\||\?\?)\s*m\.user_id\b/.test(paCode),
    '2b. no member label falls back to `m.user_id`',
  );
  const body = memoBody(paSf, 'setupMembers');
  assert(
    !!body && /teamLabel\(/.test(body) && /assignmentSlots\(/.test(body) && /settings\.order/.test(body),
    '2c. setupMembers labels through teamLabel, with slots from assignmentSlots over settings.order',
  );
  if (body) {
    const label = (members, data, teamNameOf) =>
      run(`return (${body})();`, {
        membersQuery: { data: members ? { members } : undefined },
        data,
        teamNameOf,
        assignmentSlots,
        teamLabel,
      });
    const members = [
      { user_id: 'espn:{B}', display_name: '', username: '' },
      { user_id: 'acct_2', display_name: '  ', username: null },
      { user_id: 'espn:{C}', display_name: 'Carla', username: 'carla' },
      { user_id: 'espn:{D}', display_name: 'espn:{D}', username: '' },
      { user_id: 'espn:62846.t7', display_name: '', username: '  ' },
    ];
    const check = (rows, name) => {
      const names = rows.map((r) => r.name);
      const bad = rows.filter(
        (r) => r.name.includes(r.user_id) || ID_SHAPE.test(r.name) || !r.name.trim(),
      );
      assert(
        bad.length === 0 && new Set(names).size === names.length,
        name,
        JSON.stringify(names),
      );
      return rows;
    };
    // Unseeded: no grid, the server's default order.
    const fresh = check(
      label(members, { settings: { order: members.map((m) => m.user_id) }, seasons: [] }, () => null),
      '2d. unseeded: no member shows an id, a blank, or another member\'s label',
    );
    assert(
      fresh.find((r) => r.user_id === 'espn:{C}').name === 'Carla' &&
        fresh.find((r) => r.user_id === 'espn:{B}').name === 'Team 1',
      '2e. unseeded: a real name stays; a nameless member is Team <their position in the server order>',
    );
    // Seeded: the grid's server-healed name, else the grid slot, else the next free slot.
    const grid = [
      { original_user_id: 'espn:{B}', original_roster_id: '2' },
      { original_user_id: 'acct_2', original_roster_id: '1' },
      { original_user_id: 'espn:{C}', original_roster_id: '3' },
      { original_user_id: 'espn:62846.t7', original_roster_id: '4' },
    ];
    const gridName = { 'espn:{B}': 'Team 2', acct_2: 'Team acct_2', 'espn:{C}': 'Carla', 'espn:62846.t7': '' };
    const seeded = check(
      label(
        members,
        {
          settings: { order: ['espn:{D}', 'espn:{B}', 'acct_2', 'espn:{C}', 'espn:62846.t7'] },
          seasons: [{ slots: grid }],
        },
        (id) => gridName[id] ?? null,
      ),
      '2f. seeded: no member shows an id, a blank, or another member\'s label',
    );
    const by = Object.fromEntries(seeded.map((r) => [r.user_id, r.name]));
    assert(
      by['espn:{B}'] === 'Team 2' && by.acct_2 === 'Team 1' && by['espn:{D}'] === 'Team 5' &&
        by['espn:62846.t7'] === 'Team 4',
      '2g. seeded: the healed grid name, a pre-#497 `Team <id>` replaced by the grid slot, a newcomer on the next free slot',
      JSON.stringify(by),
    );
    assert(
      label(null, { settings: { order: [] }, seasons: [] }, () => null) === null,
      '2h. members not loaded yet: null, so the list falls back to the grid teams',
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════
// §3. DraftRoomScreen — the board's owner cell
// ═══════════════════════════════════════════════════════════════════════

const drSf = parse('src/screens/DraftRoomScreen.tsx');
const drCode = codeOf(drSf);
{
  assert(
    !/(\?\?|\|\|)\s*slot\.owner_user_id\b/.test(drCode),
    '3a. no owner cell falls back to `slot.owner_user_id`',
  );
  const ownerTexts = findAll(drSf, (n) => {
    if (!ts.isJsxElement(n)) return false;
    return n.openingElement.attributes.properties.some(
      (a) => a.name && a.name.getText() === 'style' && a.initializer &&
        a.initializer.getText() === '{draftRow.ownerText}',
    );
  });
  const cell = ownerTexts[0] && ownerTexts[0].children.find((c) => ts.isJsxExpression(c) && c.expression);
  const cellExpr = cell ? cell.expression.getText() : '';
  assert(
    ownerTexts.length === 1 && /teamLabel\(/.test(cellExpr) && /ownSlotByUser\.get\(/.test(cellExpr),
    '3b. the one owner cell labels through teamLabel with the owner\'s own slot',
    cellExpr,
  );
  const slotBody = memoBody(drSf, 'ownSlotByUser');
  assert(
    !!slotBody && /\.original_user_id\b/.test(slotBody),
    '3c. ownSlotByUser keys on original_user_id (`slot` is the original owner\'s)',
  );
  if (cellExpr && slotBody) {
    const order = [
      { round: 1, slot: 3, original_user_id: SWID, owner_user_id: SWID, owner_username: null, is_traded: false },
      { round: 1, slot: 5, original_user_id: 'acct_7', owner_user_id: SWID, owner_username: '  ', is_traded: true },
      { round: 2, slot: 5, original_user_id: 'acct_7', owner_user_id: 'acct_7', owner_username: '', is_traded: false },
      { round: 2, slot: 1, original_user_id: 'u1', owner_user_id: 'u1', owner_username: ' Mike ', is_traded: false },
      { round: 3, slot: null, original_user_id: null, owner_user_id: null, owner_username: null, is_traded: false },
      { round: 3, slot: 2, original_user_id: 'u2', owner_user_id: 'acct_9', owner_username: null, is_traded: true },
      { round: 3, slot: 4, original_user_id: null, owner_user_id: null, owner_username: 'Team 0004', is_traded: false },
      { round: 3, slot: 6, original_user_id: null, owner_user_id: null, owner_username: '   ', is_traded: false },
    ];
    const ownSlotByUser = run(`return (${slotBody})();`, { board: { order } });
    const got = order.map((slot) => run(`return (${cellExpr});`, { slot, ownSlotByUser, teamLabel }));
    const want = ['Team 3', 'Team 3', 'Team 5', 'Mike', 'Unassigned', 'Unnamed team', 'Team 0004', 'Unassigned'];
    assert(
      JSON.stringify(got) === JSON.stringify(want),
      '3d. owner cell: own slot (not the traded row\'s), trimmed name, Unnamed team, Unassigned only with no owner',
      `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`,
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════
// §4. MockDraftScreen — ownerNameOf
// ═══════════════════════════════════════════════════════════════════════

const mdSf = parse('src/screens/MockDraftScreen.tsx');
{
  const fnNamed = (name) =>
    findAll(mdSf, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.getText() === name)[0];
  const ownerFn = fnNamed('ownerNameOf');
  const slotFn = fnNamed('ownSlotOf');
  assert(!!ownerFn && !!slotFn, '4a. MockDraftScreen declares ownerNameOf and ownSlotOf');
  if (ownerFn) {
    const text = ownerFn.getText();
    assert(/teamLabel\(/.test(text), '4b. ownerNameOf labels through teamLabel');
    // The one raw-id return is D-16's Sleeper path, and only an all-digit id reaches it.
    const idReturns = findAll(
      ownerFn,
      (n) => ts.isReturnStatement(n) && n.expression && n.expression.getText() === 'id',
    );
    const guard = idReturns[0] && idReturns[0].parent;
    assert(
      idReturns.length === 1 && guard && ts.isIfStatement(guard) &&
        guard.expression.getText().startsWith('/^\\d+$/.test(id)'),
      '4c. the only raw-id return is guarded by an all-digit (Sleeper) id test',
      idReturns.map((r) => (r.parent ? r.parent.getText() : r.getText())).join(' | '),
    );
    let ownerNameOf;
    try {
      ownerNameOf = run(`${text}\nreturn ownerNameOf;`, { realName, teamLabel });
    } catch (e) {
      assert(false, '4d. ownerNameOf is evaluable with the helper', String(e));
    }
    if (typeof ownerNameOf === 'function') {
      const cases = [
        // [username, ownerId, slot, expected, why]
        ['  Mike ', SWID, 2, 'Mike', 'a real name passes, trimmed'],
        [null, SWID, 2, 'Team 2', 'a nameless ESPN owner is Team <slot>'],
        ['   ', 'espn:62846.t7', null, 'Unnamed team', 'whitespace and no slot'],
        [SWID, SWID, 4, 'Team 4', 'a username that IS the ESPN id is not a name'],
        ['', 'acct_12345', 6, 'Team 6', 'a nameless acct_ owner is Team <slot>'],
        [undefined, 'acct_12345', undefined, 'Unnamed team', 'acct_ with nothing to go on'],
        [null, '', null, 'Unnamed team', 'no id and no name: never a blank'],
        [null, 'mfl:62846.f0003', 1, 'Team 0003', 'MFL keeps Team <fid>'],
        ['Ann', '867530912', 1, 'Ann', 'a named Sleeper owner'],
        // D-16 — kept as shipped and FLAGGED: this is a Sleeper USER id.
        [null, '867530912', 1, '867530912', 'D-16 Sleeper path (raw id kept, flagged to draft-eng)'],
      ];
      const bad = [];
      for (const [name, id, slot, want, why] of cases) {
        let got;
        try {
          got = ownerNameOf(name, id, slot);
        } catch (e) {
          got = `threw ${e}`;
        }
        if (got !== want) bad.push(`ownerNameOf(${JSON.stringify(name)}, ${JSON.stringify(id)}, ${JSON.stringify(slot)}) = ${JSON.stringify(got)}, want ${JSON.stringify(want)} (${why})`);
      }
      assert(bad.length === 0, '4e. ownerNameOf: ESPN / acct_ / blank never render; MFL and D-16 unchanged', bad.join(' ; '));
    }
  }
  if (slotFn) {
    const ownSlotOf = run(`${slotFn.getText()}\nreturn ownSlotOf;`, {});
    const order = [
      { slot: 1, owner_user_id: 'B', is_traded: true },
      { slot: 2, owner_user_id: 'B', is_traded: false },
      { slot: 3, owner_user_id: 'C', is_traded: true },
    ];
    assert(
      ownSlotOf(order, 'B') === 2 && ownSlotOf(order, 'C') === null && ownSlotOf(order, 'Z') === null,
      '4f. ownSlotOf reads a row the owner was not traded; an owner with only traded rows has no slot',
    );
  }
  const calls = findAll(
    mdSf,
    (n) => ts.isCallExpression(n) && n.expression.getText() === 'ownerNameOf',
  );
  assert(
    calls.length === 2 && calls.every((c) => c.arguments.length === 3 && /^ownSlotOf\(/.test(c.arguments[2].getText())),
    '4g. both owner-name sites pass the owner\'s own slot',
    calls.map((c) => c.getText()).join(' | '),
  );
}

// ═══════════════════════════════════════════════════════════════════════
// §5. Single source
// ═══════════════════════════════════════════════════════════════════════

{
  const files = [];
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (/\.(ts|tsx)$/.test(e.name)) files.push(p);
    }
  };
  walk(path.join(MOBILE, 'src'));
  const rel = (p) => path.relative(MOBILE, p);
  const unnamed = files.filter((p) => fs.readFileSync(p, 'utf8').includes("'Unnamed team'"));
  assert(
    unnamed.length === 1 && rel(unnamed[0]) === HELPER_REL,
    "5a. the 'Unnamed team' literal lives only in utils/teamLabel.ts",
    unnamed.map(rel).join(', '),
  );
  const mflRe = files.filter((p) => fs.readFileSync(p, 'utf8').includes('/^mfl:.*\\.f(\\w+)$/'));
  assert(
    mflRe.length === 1 && rel(mflRe[0]) === HELPER_REL,
    '5b. the MFL member-id regex lives only in utils/teamLabel.ts',
    mflRe.map(rel).join(', '),
  );
  assert(files.length > 100, '5c. the sweep read mobile/src (positive control)', `${files.length} files`);
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All no-raw-id-label checks passed.');
