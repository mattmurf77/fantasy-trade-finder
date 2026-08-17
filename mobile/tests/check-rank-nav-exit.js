#!/usr/bin/env node
// Rank-surface exit topology (operator, 2026-08-16).
//
// WHY THIS EXISTS. Every flag-on rank surface used to carry TWO controls for
// ONE destination: a Back control whose fallback was RankHome, and a "More
// ways to rank" control that opened the RankMenu sheet listing the same
// methods RankHome already shows. The operator called the redundancy: Back
// is gone from these surfaces and More-ways now navigates to the RankHome
// chooser ("Build your board") — the fuller page, and the only surface that
// carries the rankings-import entry point.
//
// The risk this pins is the repo's oldest nav trap (#162/#165, "stuck in a
// ranking loop"): a rank surface with NO path back to the chooser. Removing
// a back control is exactly the edit that can recreate it, so:
//   1. rankSubScreenOptions (flag-on surfaces) renders NO back control —
//      `headerLeft: () => null` AND `headerBackVisible: false`. The second
//      is load-bearing, not belt-and-braces: this is a NATIVE stack, so a
//      pushed screen draws the platform chevron on its own without it.
//   2. …and always renders MoreWaysButton, so the exit is never absent.
//   3. MoreWaysButton navigates to 'RankHome' and the module-level
//      `_openRankMenu` hook is GONE from the file (the sheet is no longer
//      the More-ways destination in any flag state).
//   4. RankHome KEEPS its own back control (subScreenOptions) — it is the
//      one rank screen with no More-ways control, so stripping its back
//      would strand the chooser itself.
//   5. The FLAG-OFF path is untouched: each rank screen's `: ` branch still
//      uses subScreenOptions(title, 'RankHome'), i.e. flag-off keeps Back.
//
// Run: node tests/check-rank-nav-exit.js
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
const fail = (name, why) => {
  failures += 1;
  console.error(`FAIL  ${name}\n      ${why}`);
};

const file = path.join(__dirname, '..', 'src', 'navigation', 'TabNav.tsx');
const text = fs.readFileSync(file, 'utf8');
const sf = ts.createSourceFile('TabNav.tsx', text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

function walk(node, cb) {
  cb(node);
  ts.forEachChild(node, (child) => walk(child, cb));
}

// Body text of a top-level `const <name> = ...` declaration.
function declText(name) {
  let found = null;
  walk(sf, (n) => {
    if (ts.isVariableDeclaration(n) && n.name && n.name.getText() === name) {
      found = n.getText();
    }
  });
  return found;
}

// Body text of a top-level `function <name>(...)`.
function fnText(name) {
  let found = null;
  walk(sf, (n) => {
    if (ts.isFunctionDeclaration(n) && n.name && n.name.text === name) {
      found = n.getText();
    }
  });
  return found;
}

// ── 1–2: flag-on rank surfaces have no back and always have More-ways ─────
{
  const opts = declText('rankSubScreenOptions');
  if (!opts) {
    fail('1. rankSubScreenOptions exists', 'declaration not found in TabNav.tsx');
  } else {
    if (/headerLeft:\s*\(\)\s*=>\s*null/.test(opts)) {
      ok('1a. rankSubScreenOptions renders no custom back control');
    } else {
      fail('1a. rankSubScreenOptions renders no custom back control',
           'expected `headerLeft: () => null`');
    }

    if (/headerBackVisible:\s*false/.test(opts)) {
      ok('1b. native-stack platform chevron suppressed');
    } else {
      fail('1b. native-stack platform chevron suppressed',
           'expected `headerBackVisible: false` — without it a PUSHED rank ' +
           'surface draws the OS back chevron and the redundancy returns');
    }

    if (/HeaderBack/.test(opts) || /subScreenOptions\(/.test(opts)) {
      fail('1c. no back control leaks in via subScreenOptions',
           'rankSubScreenOptions must build on chalklineHeader, not on ' +
           'subScreenOptions (which installs HeaderBack)');
    } else {
      ok('1c. no back control leaks in via subScreenOptions');
    }

    if (/headerRight:\s*\(\)\s*=>\s*<MoreWaysButton/.test(opts)) {
      ok('2. rankSubScreenOptions always renders MoreWaysButton (the only exit)');
    } else {
      fail('2. rankSubScreenOptions always renders MoreWaysButton (the only exit)',
           'expected `headerRight: () => <MoreWaysButton …/>`');
    }
  }
}

// ── 3: More-ways goes to the chooser, not the sheet ───────────────────────
{
  const btn = fnText('MoreWaysButton');
  if (!btn) {
    fail('3. MoreWaysButton exists', 'function not found in TabNav.tsx');
  } else {
    if (/navigation\.navigate\(\s*'RankHome'\s*\)/.test(btn)) {
      ok("3a. MoreWaysButton navigates to 'RankHome'");
    } else {
      fail("3a. MoreWaysButton navigates to 'RankHome'",
           'expected navigation.navigate(\'RankHome\') in the onPress');
    }
    if (/testID="rank\.more-ways"/.test(btn)) {
      ok('3b. MoreWaysButton keeps testID rank.more-ways');
    } else {
      fail('3b. MoreWaysButton keeps testID rank.more-ways', 'testID missing/renamed');
    }
  }

  if (/_openRankMenu/.test(text)) {
    fail('3c. the _openRankMenu module hook is gone',
         'More-ways must not open the RankMenu sheet; the hook existed only ' +
         'to serve it and is dead weight (and a re-wiring hazard) now');
  } else {
    ok('3c. the _openRankMenu module hook is gone');
  }
}

// ── 4: the chooser itself keeps a way out (never-strand) ──────────────────
{
  const m = text.match(/name="RankHome"[\s\S]{0,400}?\/>/);
  if (!m) {
    fail('4. RankHome screen registration found', 'could not locate name="RankHome"');
  } else if (/options=\{subScreenOptions\(/.test(m[0])) {
    ok('4. RankHome keeps its own back control (it has no More-ways control)');
  } else {
    fail('4. RankHome keeps its own back control (it has no More-ways control)',
         'RankHome must stay on subScreenOptions — it is the one rank screen ' +
         'without a More-ways control, so removing its back strands the chooser');
  }
}

// ── 5: flag-off topology untouched ────────────────────────────────────────
{
  // Two shapes: the plain ternary branch, and QuickSetTiers' spread form
  // (it layers #217's pushed-only back control on top).
  const flagOff = text.match(/(?::|\.\.\.)\s*subScreenOptions\('[^']+',\s*'RankHome'\)/g) || [];
  if (flagOff.length >= 8) {
    ok(`5. flag-off path still uses subScreenOptions with a back control (${flagOff.length} surfaces)`);
  } else {
    fail('5. flag-off path still uses subScreenOptions with a back control',
         `expected >= 8 flag-off branches, found ${flagOff.length} — the ` +
         '`ux.rank_tab_destination: false` rollback must keep working');
  }
}

console.log(
  failures === 0
    ? '\nAll rank-nav exit checks passed.'
    : `\n${failures} rank-nav exit check(s) FAILED.`,
);
process.exit(failures === 0 ? 0 : 1);
