#!/usr/bin/env node
// Structural regression test for Premium Rankings Import v1
// (docs/plans/connected-rankings/build-v1-premium-import/scope.md, addendum
// §2 lanes 1 + 2a, [D-058]).
//
// WHY THIS EXISTS. Four properties of this feature are load-bearing and none
// of them is visible in a screenshot:
//
//   1. FLAG GATING, FAIL-CLOSED. The Dynasty Nerds and DLF rows reach a paid
//      third-party site. The scope block forbids `espn.link`-style fail-open:
//      both flags default `false` in the compiled client AND the rows must be
//      filtered out of the sheet when their flag is off. A row that rendered
//      on a first boot before the flag fetch would put an FTF user in front
//      of DLF/DN before the counsel read (§3.4) has landed.
//   2. CONTENDER CANNOT APPLY BY DEFAULT. Dynasty Nerds' win-now (Contender)
//      export has a byte-identical header to its dynasty export — only the
//      filename says `contender_` (risk R16). It must be blocked until the
//      user explicitly overrides, or a win-now board silently becomes the
//      user's dynasty ranks.
//   3. VALUE COLUMNS NEVER REACH THE API. Premium `Value`/`Trend`/`PPG` are
//      the licensed content (risk R14). The import is ORDER ONLY: the row
//      type carries exactly name/team/pos, the extractor never indexes a
//      forbidden column, and the import-match body carries nothing else.
//   4. THE ROWS CONTRACT DEGRADES GRACEFULLY. The optional `rows` field is
//      added by a parallel backend agent; a client that hard-failed on a 400
//      would break import entirely against an older server. The 400 path
//      must resubmit through the plain text path.
//
// Same idiom as check-send-button-platform.js: parse the real TSX/TS with
// the project's own TypeScript and walk the AST — a grep would pass on a
// branch that drifted inside an unrelated conditional.
//
// Run: node tests/check-premium-import.js   (npm run test:premium-import)

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
function ok(name) {
  console.log(`PASS  ${name}`);
}
function fail(name, why) {
  failures += 1;
  console.error(`FAIL  ${name}\n      ${why}`);
}
function assert(name, cond, why) {
  if (cond) ok(name);
  else fail(name, why);
}

function parse(...rel) {
  const file = path.join(__dirname, '..', 'src', ...rel);
  const text = fs.readFileSync(file, 'utf8');
  const kind = file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  return {
    text,
    sf: ts.createSourceFile(rel.join('/'), text, ts.ScriptTarget.Latest, true, kind),
  };
}

function walk(node, cb) {
  cb(node);
  ts.forEachChild(node, (child) => walk(child, cb));
}

/** All `const <name> = …` initializers in a file, by declared name. */
function decls(sf) {
  const out = new Map();
  walk(sf, (n) => {
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer) {
      if (!out.has(n.name.text)) out.set(n.name.text, n.initializer);
    }
  });
  return out;
}

/** Members of an interface / type-literal declaration, by name. */
function interfaceMembers(sf, name) {
  let members = null;
  walk(sf, (n) => {
    if (ts.isInterfaceDeclaration(n) && n.name.text === name) {
      members = n.members
        .filter((m) => ts.isPropertySignature(m) && m.name)
        .map((m) => m.name.getText());
    }
  });
  return members;
}

/** Every function/arrow declaration body in a file, by the name it is bound
 *  to — function declarations, plain arrow consts, and the very common
 *  `const f = useCallback(() => {…}, [deps])` shape. */
function functionBodies(sf) {
  const out = new Map();
  const unwrap = (init) => {
    if (!init) return null;
    if (ts.isArrowFunction(init) || ts.isFunctionExpression(init)) return init.body;
    if (ts.isCallExpression(init) && init.arguments.length) {
      const first = init.arguments[0];
      if (ts.isArrowFunction(first) || ts.isFunctionExpression(first)) return first.body;
    }
    return null;
  };
  walk(sf, (n) => {
    if (ts.isFunctionDeclaration(n) && n.name && n.body) {
      out.set(n.name.text, n.body);
    }
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name)) {
      const body = unwrap(n.initializer);
      if (body) out.set(n.name.text, body);
    }
  });
  return out;
}

const FLAG_KEYS = ['ranks.source.dynasty_nerds', 'ranks.source.dlf'];
const FORBIDDEN = ['value', 'trend', 'ppg'];

// ══ 1. Flag gating, fail-closed ══════════════════════════════════════════
{
  const { sf } = parse('state', 'useFeatureFlags.ts');
  const d = decls(sf);
  const defaults = d.get('LAUNCHED_FLAG_DEFAULTS');
  if (!defaults || !ts.isObjectLiteralExpression(defaults)) {
    fail('1a compiled flag defaults', 'LAUNCHED_FLAG_DEFAULTS object literal not found');
  } else {
    for (const key of FLAG_KEYS) {
      const prop = defaults.properties.find(
        (p) =>
          ts.isPropertyAssignment(p) &&
          p.name &&
          p.name.getText().replace(/['"]/g, '') === key,
      );
      if (!prop) {
        fail(
          `1a ${key} stated in compiled defaults`,
          'key absent — the compiled default must SAY false, not rely on a missing key reading falsy',
        );
      } else if (prop.initializer.kind !== ts.SyntaxKind.FalseKeyword) {
        fail(
          `1a ${key} defaults false`,
          `compiled default is \`${prop.initializer.getText()}\` — premium sources must never fail open (scope.md §2)`,
        );
      } else {
        ok(`1a ${key} defaults false in the compiled client`);
      }
    }
  }
}

{
  const { text, sf } = parse('components', 'ImportRankingsSheet.tsx');

  // Both flags are actually read.
  const readKeys = new Set();
  walk(sf, (n) => {
    if (
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === 'useFlag' &&
      n.arguments.length === 1 &&
      ts.isStringLiteral(n.arguments[0])
    ) {
      readKeys.add(n.arguments[0].text);
    }
  });
  for (const key of FLAG_KEYS) {
    assert(
      `1b sheet reads ${key}`,
      readKeys.has(key),
      `no useFlag('${key}') call in ImportRankingsSheet`,
    );
  }

  // Every premium row declares the flag it is gated by, and no other row
  // shape sneaks a premium source in without one.
  const d = decls(sf);
  const rows = d.get('PREMIUM_ROWS');
  if (!rows || !ts.isArrayLiteralExpression(rows)) {
    fail('1c PREMIUM_ROWS table', 'PREMIUM_ROWS array literal not found');
  } else {
    const declared = rows.elements
      .filter(ts.isObjectLiteralExpression)
      .map((el) => {
        const get = (k) => {
          const p = el.properties.find(
            (q) => ts.isPropertyAssignment(q) && q.name.getText() === k,
          );
          return p && ts.isStringLiteral(p.initializer) ? p.initializer.text : null;
        };
        return { source: get('source'), flag: get('flag') };
      });
    assert(
      '1c every premium row names a ranks.source.* flag',
      declared.length === 2 && declared.every((r) => FLAG_KEYS.includes(r.flag)),
      `rows declared: ${JSON.stringify(declared)}`,
    );
  }

  // The rows are FILTERED by their flag before render — not merely rendered
  // with a dimmed style, and not `flag || true`.
  let filtered = false;
  walk(sf, (n) => {
    if (
      ts.isCallExpression(n) &&
      ts.isPropertyAccessExpression(n.expression) &&
      n.expression.name.text === 'filter' &&
      ts.isIdentifier(n.expression.expression) &&
      n.expression.expression.text === 'PREMIUM_ROWS' &&
      n.arguments.length === 1 &&
      /flagOn\[/.test(n.arguments[0].getText())
    ) {
      filtered = true;
    }
  });
  assert(
    '1d premium rows are filtered out when their flag is off',
    filtered,
    'no PREMIUM_ROWS.filter(... flagOn[...] ...) — a flag-off row must not render at all',
  );

  // The CSV-upload row is deliberately NOT gated by these flags (scope §2:
  // plain file intake for the existing import).
  assert(
    '1e CSV-upload row is not gated by a ranks.source.* flag',
    /testID="import-rankings\.upload"/.test(text) &&
      !FLAG_KEYS.some((k) =>
        new RegExp(`${k.replace(/\./g, '\\.')}[^\\n]*upload`, 'i').test(text),
      ),
    'the upload row must stay visible with both premium flags off',
  );
}

// ══ 2. Contender files cannot apply by default ═══════════════════════════
{
  const { sf } = parse('components', 'ImportRankingsSheet.tsx');
  const d = decls(sf);

  const blocked = d.get('blockedByContender');
  assert(
    '2a blockedByContender derives from isContender() AND the override',
    !!blocked &&
      /isContender\(/.test(blocked.getText()) &&
      /!\s*contenderOverride/.test(blocked.getText()),
    blocked
      ? `initializer is \`${blocked.getText()}\``
      : 'blockedByContender not declared',
  );

  const can = d.get('canContinue');
  assert(
    '2b the confirm control is disabled while blocked',
    !!can && /!\s*blockedByContender/.test(can.getText()),
    can ? `canContinue = \`${can.getText()}\`` : 'canContinue not declared',
  );

  // The override starts OFF. `useState(true)` here would make every
  // contender file apply silently.
  let overrideInit = null;
  walk(sf, (n) => {
    if (
      ts.isVariableDeclaration(n) &&
      n.name.getText().includes('contenderOverride') &&
      n.initializer &&
      ts.isCallExpression(n.initializer) &&
      n.initializer.expression.getText() === 'useState'
    ) {
      overrideInit = n.initializer.arguments[0]
        ? n.initializer.arguments[0].kind
        : ts.SyntaxKind.UndefinedKeyword;
    }
  });
  assert(
    '2c the contender override starts off',
    overrideInit === ts.SyntaxKind.FalseKeyword,
    'useState for contenderOverride must be initialized to false',
  );

  // The handler itself refuses — a disabled button is not the only guard.
  const bodies = functionBodies(sf);
  const confirm = bodies.get('confirm');
  assert(
    '2d confirm() itself early-returns while blocked',
    !!confirm && /if\s*\([^)]*blockedByContender[^)]*\)\s*return/.test(confirm.getText()),
    confirm
      ? 'confirm() has no `if (… blockedByContender …) return` guard'
      : 'confirm callback not found',
  );

  // …and the user is told what it is, by name.
  const { text } = parse('components', 'ImportRankingsSheet.tsx');
  assert(
    '2e the contender warning names the win-now set out loud',
    /win-now \(Contender\) set/.test(text) &&
      /testID="import-rankings\.contender-warning"/.test(text),
    'the flag must be operator-visible copy, not a silent remap (addendum §3.2)',
  );
}

// ══ 3. Value columns never reach the API ════════════════════════════════
{
  const { sf } = parse('utils', 'rankPresets.ts');

  const members = interfaceMembers(sf, 'PresetRow');
  assert(
    '3a PresetRow carries exactly name/team/pos',
    !!members && JSON.stringify([...members].sort()) === JSON.stringify(['name', 'pos', 'team']),
    `PresetRow members: ${JSON.stringify(members)}`,
  );

  // The extractor may only look up the three hint columns. Any string handed
  // to columnIndex() is a column it reads — none may be a premium column.
  const bodies = functionBodies(sf);
  let extract = null;
  walk(sf, (n) => {
    if (ts.isFunctionDeclaration(n) && n.name && n.name.text === 'extractRows') {
      extract = n.body;
    }
  });
  extract = extract || bodies.get('extractRows');
  if (!extract) {
    fail('3b extractRows reads no premium column', 'extractRows not found');
  } else {
    const read = [];
    walk(extract, (n) => {
      if (
        ts.isCallExpression(n) &&
        ts.isIdentifier(n.expression) &&
        n.expression.text === 'columnIndex'
      ) {
        walk(n, (m) => {
          if (ts.isStringLiteral(m)) read.push(m.text.toLowerCase());
        });
      }
    });
    const leaked = read.filter((c) => FORBIDDEN.includes(c));
    assert(
      '3b extractRows never looks up Value/Trend/PPG',
      read.length > 0 && leaked.length === 0,
      `extractRows reads columns ${JSON.stringify(read)} — forbidden: ${JSON.stringify(leaked)}`,
    );

    // …and the object it emits has exactly the three fields.
    let emitted = null;
    walk(extract, (n) => {
      if (
        ts.isCallExpression(n) &&
        ts.isPropertyAccessExpression(n.expression) &&
        n.expression.name.text === 'push' &&
        n.arguments.length === 1 &&
        ts.isObjectLiteralExpression(n.arguments[0])
      ) {
        emitted = n.arguments[0].properties.map((p) => p.name.getText());
      }
    });
    assert(
      '3c extractRows emits exactly name/team/pos',
      !!emitted && JSON.stringify([...emitted].sort()) === JSON.stringify(['name', 'pos', 'team']),
      `emitted fields: ${JSON.stringify(emitted)}`,
    );
  }
}

{
  const { sf } = parse('api', 'rankings.ts');

  const members = interfaceMembers(sf, 'ImportRowHint');
  assert(
    '3d the wire row type carries exactly name/team/pos',
    !!members && JSON.stringify([...members].sort()) === JSON.stringify(['name', 'pos', 'team']),
    `ImportRowHint members: ${JSON.stringify(members)}`,
  );

  // Every body posted to import-match may only carry `names` and `rows`.
  const posted = [];
  walk(sf, (n) => {
    if (
      ts.isCallExpression(n) &&
      ts.isPropertyAccessExpression(n.expression) &&
      n.expression.name.text === 'post' &&
      n.arguments.length >= 2 &&
      ts.isStringLiteral(n.arguments[0]) &&
      n.arguments[0].text === '/api/rankings/import-match'
    ) {
      const body = n.arguments[1];
      posted.push(
        ts.isObjectLiteralExpression(body)
          ? body.properties.map((p) => (p.name ? p.name.getText() : p.getText()))
          : [body.getText()],
      );
    }
  });
  const allKeys = posted.flat();
  assert(
    '3e import-match bodies carry only names/rows',
    posted.length >= 2 && allKeys.every((k) => k === 'names' || k === 'rows'),
    `posted bodies: ${JSON.stringify(posted)}`,
  );
}

// ══ 4. Graceful fallback to the plain text path ═════════════════════════
{
  const { sf } = parse('api', 'rankings.ts');

  // The predicate matches a 400 and only a 400.
  let pred = null;
  walk(sf, (n) => {
    if (ts.isFunctionDeclaration(n) && n.name && n.name.text === 'isRowsUnsupported') {
      pred = n.body;
    }
  });
  assert(
    '4a the fallback triggers on a 400, not on any error',
    !!pred && /status\s*===\s*400/.test(pred.getText()) && /ApiError/.test(pred.getText()),
    pred ? `isRowsUnsupported = \`${pred.getText()}\`` : 'isRowsUnsupported not found',
  );

  // importMatchRankings: rows-bearing attempt inside a try; the catch
  // rethrows anything that is not the 400; a text-only post follows.
  let fn = null;
  walk(sf, (n) => {
    if (ts.isFunctionDeclaration(n) && n.name && n.name.text === 'importMatchRankings') {
      fn = n;
    }
  });
  if (!fn) {
    fail('4b importMatchRankings fallback', 'function not found');
  } else {
    const body = fn.body.getText();
    let tryStmt = null;
    walk(fn, (n) => {
      if (ts.isTryStatement(n)) tryStmt = n;
    });
    assert(
      '4b the rows attempt is wrapped in try/catch',
      !!tryStmt && /rows/.test(tryStmt.tryBlock.getText()),
      'no try block posting `rows`',
    );
    assert(
      '4c anything that is not a 400 is rethrown',
      !!tryStmt &&
        tryStmt.catchClause &&
        /if\s*\(\s*!\s*isRowsUnsupported\([^)]*\)\s*\)\s*throw/.test(
          tryStmt.catchClause.getText(),
        ),
      'the catch must rethrow unless isRowsUnsupported(e) — a silent retry would hide auth/5xx failures',
    );
    assert(
      '4d a text-only post follows the try as the fallback',
      /return\s+api\.post<[^>]*>\(\s*'\/api\/rankings\/import-match',\s*\{\s*names\s*\}/.test(
        body.replace(/\s+/g, ' ').replace(/ \}/g, ' }'),
      ) || /\{ names \},/.test(body.replace(/\s+/g, ' ')),
      'no `{ names }`-only post after the rows attempt',
    );
  }
}

{
  // The preset path actually uses that contract: RankImportSheet hands the
  // parsed rows to importMatchRankings as the optional second argument, and
  // the preset intake lands on the SAME review/apply step as paste.
  const { text, sf } = parse('components', 'RankImportSheet.tsx');
  let passesHints = false;
  walk(sf, (n) => {
    if (
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === 'importMatchRankings' &&
      n.arguments.length === 2
    ) {
      passesHints = true;
    }
  });
  assert(
    '4e RankImportSheet passes the row hints through the one match call',
    passesHints,
    'importMatchRankings must be called with (lines, hints) so presets and paste share one path',
  );
  assert(
    '4f preset intake reuses the existing review/apply step',
    /presetRows/.test(text) && /setStep\('review'\)/.test(text),
    'the preset path must not fork a second apply implementation',
  );
}

// ══ 5. Lane-2a boundaries ([D-058] hard rules) ══════════════════════════
{
  const { text } = parse('screens', 'PremiumRankingsBrowserScreen.tsx');
  assert(
    '5a the browser screen never calls injectJavaScript imperatively',
    !/\.injectJavaScript\(/.test(text),
    'FTF must not operate the site — the shim is passive, injected once at load',
  );
  assert(
    '5b no timers drive the browser screen',
    !/setInterval\(/.test(text) && !/setTimeout\(/.test(text),
    'user-present and on-demand only: no background fetching, no polling',
  );
  assert(
    '5c both source URLs are constants, and there are exactly two',
    /const SOURCE_URL: Record<PremiumSource, string> = \{/.test(text) &&
      (text.match(/https:\/\//g) || []).length === 2,
    'no auto-navigation beyond the initial URL',
  );
  assert(
    '5d the screen mounts its own FeedbackFAB (root-stack push)',
    /<FeedbackFAB activeScreen="PremiumRankingsBrowser" aboveTabBar=\{false\} \/>/.test(text),
    'root CLAUDE.md: every root-stack push renders its own FeedbackFAB',
  );
}

if (failures) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll premium-import structural checks passed.');
